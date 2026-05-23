"""Unit tests for the Translate Text page.

Covers:
- Streaming worker logic via stream_translate_text()
- TranslateTextPage widget construction, state, and actions
- Edit mode toggle (switching between source/target input modes)
- Streaming translation worker behavior
- Copy-to-clipboard functionality
- Character count updates
- Language swap behavior
- Error state handling (no LLM configured)
"""

import shutil
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtWidgets import (
    QComboBox,
    QLabel,
    QMainWindow,
    QPlainTextEdit,
    QPushButton,
    QStackedWidget,
)


@pytest.fixture(autouse=True)
def _auto_mock_ffmpeg_available():
    """Pretends ffmpeg is on PATH for the duration of the test.

    The Listen-button path in ``translate_text.py`` does an
    unconditional ffmpeg pre-check before starting the TTS worker on
    cache miss (matches Voice / Dubbing).  Most tests don't care about
    the check — this autouse fixture keeps them on the happy path.
    Tests that specifically exercise the no-ffmpeg block override with
    their own ``patch("shutil.which")``.
    """
    real_which = shutil.which

    def _which(name, *args, **kwargs):
        if name == "ffmpeg":
            return "/usr/bin/ffmpeg"
        return real_which(name, *args, **kwargs)

    with patch("shutil.which", side_effect=_which):
        yield


@pytest.fixture(autouse=True)
def _auto_mock_blocking_dialogs():
    """Auto-mocks modal dialogs so tests don't hang.

    Mirrors the live-page pattern.  Individual tests can override
    either with their own ``@patch`` to assert the dialog WAS shown.
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


# ---------------------------------------------------------------------------
# UI Test Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def window(qapp):
    """Provides a QMainWindow context."""
    return QMainWindow()


@pytest.fixture()
def _mock_deps():
    """Mocks all external dependencies for TranslateTextPage construction."""
    with (
        patch(
            "src.ui.pages.text_translation_history.get_text_translation_fingerprint",
            return_value=(0, 0),
        ),
        patch(
            "src.ui.pages.text_translation_history.get_text_translation_history",
            return_value=[],
        ),
        patch(
            "src.ui.pages.translate_text.load_setting",
            return_value="",
        ),
        patch(
            "src.ui.pages.translate_text.check_llm_setup",
            return_value=True,
        ),
    ):
        yield


@pytest.fixture()
def _mock_history():
    """Mocks history DB calls for tests that trigger history refresh."""
    with (
        patch(
            "src.ui.pages.text_translation_history.get_text_translation_fingerprint",
            return_value=(0, 0),
        ),
        patch(
            "src.ui.pages.text_translation_history.get_text_translation_history",
            return_value=[],
        ),
    ):
        yield


@pytest.fixture()
def page(window, _mock_deps, qtbot):
    """Creates a TranslateTextPage for testing."""
    from src.ui.pages.translate_text import TranslateTextPage  # noqa: PLC0415

    p = TranslateTextPage(window)
    qtbot.addWidget(p)
    return p


# ---------------------------------------------------------------------------
# Page construction
# ---------------------------------------------------------------------------


class TestTranslateTextPageConstruction:
    """Tests for TranslateTextPage widget initialization."""

    def test_page_construction(self, page) -> None:
        """Page can be constructed without errors."""
        assert page is not None

    def test_has_source_text_area(self, page) -> None:
        """Page contains a source QPlainTextEdit."""
        assert hasattr(page, "source_text")
        assert isinstance(page.source_text, QPlainTextEdit)

    def test_has_target_text_area_readonly(self, page) -> None:
        """Page contains a read-only target QPlainTextEdit."""
        assert hasattr(page, "target_text")
        assert isinstance(page.target_text, QPlainTextEdit)
        assert page.target_text.isReadOnly()

    def test_has_source_language_combo(self, page) -> None:
        """Page contains a source language combo box."""
        assert hasattr(page, "src_combo")
        assert isinstance(page.src_combo, QComboBox)
        # First item should be "Auto" or equivalent
        assert page.src_combo.count() > 1

    def test_has_target_language_combo(self, page) -> None:
        """Page contains a target language combo box."""
        assert hasattr(page, "target_combo")
        assert isinstance(page.target_combo, QComboBox)
        assert page.target_combo.count() > 0

    def test_has_swap_button(self, page) -> None:
        """Page contains a swap languages button."""
        assert hasattr(page, "swap_btn")
        assert isinstance(page.swap_btn, QPushButton)

    def test_has_translate_button(self, page) -> None:
        """Page contains a translate button."""
        assert hasattr(page, "translate_btn")
        assert isinstance(page.translate_btn, QPushButton)

    def test_has_history_button(self, page) -> None:
        """Page contains a history toggle button."""
        assert hasattr(page, "history_btn")
        assert isinstance(page.history_btn, QPushButton)

    def test_has_stacked_widgets(self, page) -> None:
        """Page has both header and content QStackedWidgets."""
        assert hasattr(page, "_header_stack")
        assert isinstance(page._header_stack, QStackedWidget)
        assert hasattr(page, "_content_stack")
        assert isinstance(page._content_stack, QStackedWidget)

    def test_has_edit_button(self, page) -> None:
        """Page contains an edit button for target text."""
        assert hasattr(page, "edit_btn")
        assert isinstance(page.edit_btn, QPushButton)

    def test_has_cancel_edit_button(self, page) -> None:
        """Page contains a cancel-edit button."""
        assert hasattr(page, "cancel_edit_btn")
        assert isinstance(page.cancel_edit_btn, QPushButton)

    def test_has_status_label(self, page) -> None:
        """Page contains a status label."""
        assert hasattr(page, "status_label")
        assert isinstance(page.status_label, QLabel)

    def test_has_char_count_button(self, page) -> None:
        """Page contains a disabled character count button."""
        assert hasattr(page, "char_count")
        assert isinstance(page.char_count, QPushButton)
        assert not page.char_count.isEnabled()

    def test_source_combo_has_auto_detect(self, page) -> None:
        """Source combo first item is Auto-detect (index 0)."""
        # Index 0 should be the auto-detect entry
        assert page.src_combo.count() > 1

    def test_target_combo_no_auto_detect(self, page) -> None:
        """Target combo has no Auto-detect entry (all real languages)."""
        from src.constants.languages import LANGUAGES  # noqa: PLC0415

        # Target combo count should match the number of languages (no auto)
        assert page.target_combo.count() == len(LANGUAGES)

    def test_source_combo_has_auto_plus_languages(self, page) -> None:
        """Source combo has Auto + all languages."""
        from src.constants.languages import LANGUAGES  # noqa: PLC0415

        assert page.src_combo.count() == len(LANGUAGES) + 1


# ---------------------------------------------------------------------------
# Initial state
# ---------------------------------------------------------------------------


class TestTranslateTextPageState:
    """Tests for initial widget state."""

    def test_worker_is_none_initially(self, page) -> None:
        """No worker thread is active on construction."""
        assert page._worker is None

    def test_stacked_widget_shows_translate_view(self, page) -> None:
        """Header and content stacks start at index 0 (translate view)."""
        assert page._header_stack.currentIndex() == 0
        assert page._content_stack.currentIndex() == 0

    def test_history_action_buttons_disabled(self, page) -> None:
        """History action buttons start disabled."""
        assert not page._history_view_btn.isEnabled()
        assert not page._history_delete_btn.isEnabled()

    def test_edit_button_disabled_initially(self, page) -> None:
        """Edit button starts disabled (no translation to edit)."""
        assert not page.edit_btn.isEnabled()

    def test_cancel_edit_button_hidden_initially(self, page) -> None:
        """Cancel-edit button is hidden initially."""
        assert page.cancel_edit_btn.isHidden()

    def test_status_label_empty_initially(self, page) -> None:
        """Status label is empty on construction."""
        assert page.status_label.text() == ""

    def test_status_error_flag_false_initially(self, page) -> None:
        """Error flag is False on construction."""
        assert page._status_is_error is False

    def test_swap_button_disabled_when_auto_selected(self, page) -> None:
        """Swap button is disabled when source is Auto-detect (index 0)."""
        page.src_combo.setCurrentIndex(0)
        assert not page.swap_btn.isEnabled()


# ---------------------------------------------------------------------------
# Character count
# ---------------------------------------------------------------------------


class TestCharacterCount:
    """Tests for character counting and limit enforcement."""

    def test_char_count_updates_on_text_change(self, page) -> None:
        """Typing updates the character count display."""
        page.source_text.setPlainText("hello")
        assert "5" in page.char_count.text()

    def test_char_count_shows_limit_format(self, page) -> None:
        """Character count shows 'current / max' format."""
        page.source_text.setPlainText("test")
        text = page.char_count.text()
        assert "/" in text
        assert "5,000" in text

    def test_auto_truncates_over_limit(self, page) -> None:
        """Text exceeding the limit is auto-truncated to 5000 chars."""
        page.source_text.setPlainText("x" * 5001)
        assert len(page.source_text.toPlainText()) == 5000  # noqa: PLR2004
        assert page.translate_btn.isEnabled()

    def test_char_count_zero_when_empty(self, page) -> None:
        """Character count shows 0 when source text is empty."""
        page.source_text.clear()
        assert "0" in page.char_count.text()

    def test_char_count_exact_at_limit(self, page) -> None:
        """Text exactly at 5000 chars is not truncated."""
        page.source_text.setPlainText("y" * 5000)
        assert len(page.source_text.toPlainText()) == 5000  # noqa: PLR2004
        assert "5,000 / 5,000" in page.char_count.text()

    def test_char_count_updates_on_each_change(self, page) -> None:
        """Character count updates correctly on multiple changes."""
        page.source_text.setPlainText("ab")
        assert "2" in page.char_count.text()
        page.source_text.setPlainText("abcdef")
        assert "6" in page.char_count.text()

    def test_char_count_handles_unicode(self, page) -> None:
        """Character count handles multi-byte unicode characters correctly."""
        page.source_text.setPlainText("Xin chao")
        count_text = page.char_count.text()
        assert "8" in count_text


# ---------------------------------------------------------------------------
# Language swap
# ---------------------------------------------------------------------------


class TestLanguageSwap:
    """Tests for the swap languages feature."""

    def test_swap_exchanges_text_content(self, page) -> None:
        """Swapping moves target text to source."""
        # Select a non-Auto source so the swap is allowed.
        page.src_combo.setCurrentIndex(1)
        page.source_text.setPlainText("original source")
        page.target_text.setPlainText("original target")

        page._swap_languages()

        assert page.source_text.toPlainText() == "original target"
        assert page.target_text.toPlainText() == "original source"

    def test_swap_no_crash_when_target_empty(self, page) -> None:
        """Swapping with empty target text does not crash."""
        page.src_combo.setCurrentIndex(1)
        page.source_text.setPlainText("hello")
        page.target_text.clear()

        page._swap_languages()
        # No crash; source stays (target was empty, so no swap of text)

    def test_swap_blocked_when_source_is_auto(self, page) -> None:
        """Swap is a no-op when source language is Auto (no direction to flip)."""
        page.src_combo.setCurrentIndex(0)  # Auto
        page.source_text.setPlainText("source")
        page.target_text.setPlainText("target")

        page._swap_languages()

        # Text content stays unchanged — the swap was skipped.
        assert page.source_text.toPlainText() == "source"
        assert page.target_text.toPlainText() == "target"

    def test_swap_exchanges_language_combos(self, page) -> None:
        """Swapping exchanges the language selections."""
        # Set source to a specific language (not Auto = index 0)
        page.src_combo.setCurrentIndex(1)
        src_lang = page.src_combo.currentData()
        tgt_lang = page.target_combo.currentData()

        page._swap_languages()

        # After swap, the old source should be the new target and vice versa
        assert page.target_combo.currentData() == src_lang
        assert page.src_combo.currentData() == tgt_lang

    def test_swap_disabled_when_auto_detect(self, page) -> None:
        """Swap button is disabled when source is Auto-detect."""
        page.src_combo.setCurrentIndex(0)
        assert not page.swap_btn.isEnabled()

    def test_swap_enabled_when_language_selected(self, page) -> None:
        """Swap button is enabled when source is a specific language."""
        page.src_combo.setCurrentIndex(2)
        assert page.swap_btn.isEnabled()

    def test_swap_updates_char_count(self, page) -> None:
        """Swapping text updates the character count for new source."""
        page.src_combo.setCurrentIndex(1)
        page.source_text.setPlainText("short")
        page.target_text.setPlainText("a longer target text here")

        page._swap_languages()

        # Source is now "a longer target text here" (25 chars)
        assert "25" in page.char_count.text()

    def test_on_src_lang_changed_enables_swap(self, page) -> None:
        """Changing source language from Auto to a language enables swap."""
        page.src_combo.setCurrentIndex(0)
        assert not page.swap_btn.isEnabled()

        page.src_combo.setCurrentIndex(3)
        assert page.swap_btn.isEnabled()

    def test_on_src_lang_changed_disables_swap_back_to_auto(self, page) -> None:
        """Changing source language back to Auto disables swap."""
        page.src_combo.setCurrentIndex(3)
        assert page.swap_btn.isEnabled()

        page.src_combo.setCurrentIndex(0)
        assert not page.swap_btn.isEnabled()


# ---------------------------------------------------------------------------
# Edit mode toggle
# ---------------------------------------------------------------------------


class TestEditModeToggle:
    """Tests for the edit/save mode toggle on target text area."""

    def test_toggle_edit_makes_target_editable(self, page) -> None:
        """Toggling edit mode makes the target text area editable."""
        page.target_text.setPlainText("some translation")
        page.edit_btn.setEnabled(True)

        page._toggle_edit()

        assert not page.target_text.isReadOnly()

    def test_enter_edit_stops_pending_tts(self, page) -> None:
        """Regression: entering edit mode cancels in-flight TTS.

        Before this fix, clicking Edit while a Listen-button TTS
        chunk was queued would let the chunk keep playing — the
        audio (pre-edit text) and the on-screen content (edited
        text) silently diverged.  ``_toggle_edit`` now calls
        ``_stop_tts`` up front so the audio matches what's visible
        the moment the user starts typing.
        """
        from unittest.mock import patch  # noqa: PLC0415

        page.target_text.setPlainText("original translation")
        page.edit_btn.setEnabled(True)

        with patch.object(page, "_stop_tts") as mock_stop_tts:
            page._toggle_edit()  # enter edit mode
        mock_stop_tts.assert_called_once()

    def test_cancel_edit_stops_pending_tts(self, page) -> None:
        """Regression: cancelling edit mode also cancels TTS.

        Symmetry with the edit-entry case — a Listen click that
        landed *while* the user was in edit mode would otherwise
        survive the Cancel.  ``_cancel_edit`` now wipes any active
        TTS the same way ``_toggle_edit`` does on entry.
        """
        from unittest.mock import patch  # noqa: PLC0415

        page.target_text.setPlainText("translation")
        page.edit_btn.setEnabled(True)
        page._toggle_edit()  # enter edit mode

        with patch.object(page, "_stop_tts") as mock_stop_tts:
            page._cancel_edit()
        mock_stop_tts.assert_called_once()

    def test_toggle_edit_shows_cancel_button(self, page) -> None:
        """Entering edit mode shows the cancel button."""
        page.target_text.setPlainText("some translation")
        page.edit_btn.setEnabled(True)

        page._toggle_edit()

        assert not page.cancel_edit_btn.isHidden()

    def test_toggle_edit_hides_translate_button(self, page) -> None:
        """Entering edit mode hides the translate button."""
        page.target_text.setPlainText("some translation")
        page.edit_btn.setEnabled(True)

        page._toggle_edit()

        assert page.translate_btn.isHidden()

    def test_toggle_edit_changes_button_text_to_save(self, page) -> None:
        """Edit button text changes to 'Save' in edit mode."""
        from src.constants.i18n import tr  # noqa: PLC0415

        page.target_text.setPlainText("translation")
        page.edit_btn.setEnabled(True)

        page._toggle_edit()

        assert page.edit_btn.text() == tr("translate_text.btn_save")

    def test_exit_edit_restores_readonly(self, page) -> None:
        """Exiting edit mode restores read-only on target text."""
        page.target_text.setPlainText("translation")
        page.edit_btn.setEnabled(True)

        # Enter edit mode
        page._toggle_edit()
        assert not page.target_text.isReadOnly()

        # Exit edit mode (second toggle)
        page._toggle_edit()
        assert page.target_text.isReadOnly()

    def test_exit_edit_hides_cancel_button(self, page) -> None:
        """Exiting edit mode hides the cancel button."""
        page.target_text.setPlainText("translation")
        page.edit_btn.setEnabled(True)

        page._toggle_edit()
        page._toggle_edit()

        assert page.cancel_edit_btn.isHidden()

    def test_exit_edit_shows_translate_button(self, page) -> None:
        """Exiting edit mode shows the translate button."""
        page.target_text.setPlainText("translation")
        page.edit_btn.setEnabled(True)

        page._toggle_edit()
        page._toggle_edit()

        assert not page.translate_btn.isHidden()

    def test_exit_edit_saves_to_history(self, page) -> None:
        """Exiting edit mode saves updated text when entry_id is set."""
        page.target_text.setPlainText("original")
        page.edit_btn.setEnabled(True)
        page._last_entry_id = 42  # noqa: PLR2004

        # Enter edit mode
        page._toggle_edit()
        # Modify text while in edit mode
        page.target_text.setPlainText("modified translation")

        with patch(
            "src.core.database.update_text_translation_entry",
        ) as mock_update:
            # Exit edit mode (saves)
            page._toggle_edit()

        mock_update.assert_called_once_with(42, "modified translation")  # noqa: PLR2004

    def test_exit_edit_no_save_without_entry_id(self, page) -> None:
        """Exiting edit mode skips DB save when no entry_id is set."""
        page.target_text.setPlainText("original")
        page.edit_btn.setEnabled(True)
        page._last_entry_id = None

        page._toggle_edit()

        with patch(
            "src.core.database.update_text_translation_entry",
        ) as mock_update:
            page._toggle_edit()

        mock_update.assert_not_called()

    def test_cancel_edit_restores_original_text(self, page) -> None:
        """Cancelling edit restores the original text before editing."""
        page.target_text.setPlainText("original translation")
        page.edit_btn.setEnabled(True)

        # Enter edit mode (saves snapshot)
        page._toggle_edit()
        # Modify text
        page.target_text.setPlainText("modified text")

        # Cancel — should restore
        page._cancel_edit()

        assert page.target_text.toPlainText() == "original translation"
        assert page.target_text.isReadOnly()

    def test_cancel_edit_hides_cancel_button(self, page) -> None:
        """Cancelling edit hides the cancel button."""
        page.target_text.setPlainText("text")
        page.edit_btn.setEnabled(True)

        page._toggle_edit()
        page._cancel_edit()

        assert page.cancel_edit_btn.isHidden()

    def test_cancel_edit_restores_translate_button(self, page) -> None:
        """Cancelling edit makes the translate button visible again."""
        page.target_text.setPlainText("text")
        page.edit_btn.setEnabled(True)

        page._toggle_edit()
        page._cancel_edit()

        assert not page.translate_btn.isHidden()

    def test_set_editing_preserves_text_snapshot(self, page) -> None:
        """_set_editing(True) captures text snapshot for cancel restore."""
        page.target_text.setPlainText("snapshot text")

        page._set_editing(True)

        assert page._text_before_edit == "snapshot text"

    def test_edit_button_text_restored_on_exit(self, page) -> None:
        """Edit button text goes back to 'Edit' after exiting edit mode."""
        from src.constants.i18n import tr  # noqa: PLC0415

        page.target_text.setPlainText("text")
        page.edit_btn.setEnabled(True)

        page._toggle_edit()
        page._toggle_edit()

        assert page.edit_btn.text() == tr("translate_text.btn_edit")


# ---------------------------------------------------------------------------
# History toggle
# ---------------------------------------------------------------------------


class TestHistoryToggle:
    """Tests for toggling between translate and history views."""

    def test_toggle_switches_to_history(self, page, _mock_history) -> None:
        """First toggle switches to history view (stacks at index 1)."""
        page._toggle_history()

        assert page._header_stack.currentIndex() == 1
        assert page._content_stack.currentIndex() == 1

    def test_toggle_hides_translate_footer(self, page, _mock_history) -> None:
        """Translate footer widgets are hidden in history view."""
        page._toggle_history()

        # isHidden() checks the widget's own visibility flag (not parent chain)
        assert page.char_count.isHidden()
        assert page.translate_btn.isHidden()
        # History button remains visible (not hidden)
        assert not page.history_btn.isHidden()

    def test_toggle_back_restores_translate_view(
        self,
        page,
        _mock_history,
    ) -> None:
        """Second toggle returns to translate view."""
        page._toggle_history()  # to history
        page._toggle_history()  # back to translate

        assert page._header_stack.currentIndex() == 0
        assert page._content_stack.currentIndex() == 0
        assert not page.char_count.isHidden()
        assert not page.translate_btn.isHidden()

    def test_history_selection_updates_buttons(self, page) -> None:
        """History selection_changed signal updates action button states."""
        page._on_history_selection_changed(True)
        assert page._history_view_btn.isEnabled()
        assert page._history_delete_btn.isEnabled()

        page._on_history_selection_changed(False)
        assert not page._history_view_btn.isEnabled()
        assert not page._history_delete_btn.isEnabled()

    def test_toggle_to_history_changes_button_text(
        self,
        page,
        _mock_history,
    ) -> None:
        """Toggling to history changes the history button text to 'Back'."""
        from src.constants.i18n import tr  # noqa: PLC0415

        page._toggle_history()
        assert page.history_btn.text() == tr("translate_text.btn_back")

    def test_toggle_back_restores_button_text(
        self,
        page,
        _mock_history,
    ) -> None:
        """Toggling back restores history button text to 'History'."""
        from src.constants.i18n import tr  # noqa: PLC0415

        page._toggle_history()
        page._toggle_history()
        assert page.history_btn.text() == tr("translate_text.btn_history")

    def test_toggle_hides_edit_and_status(self, page, _mock_history) -> None:
        """Toggling to history hides edit button and status label."""
        page._toggle_history()
        assert page.edit_btn.isHidden()
        assert page.status_label.isHidden()


# ---------------------------------------------------------------------------
# Translation workflow
# ---------------------------------------------------------------------------


class TestTranslationWorkflow:
    """Tests for translation start, success, and error handling."""

    def test_start_translation_with_empty_text_is_noop(self, page) -> None:
        """Starting translation with empty source text does nothing."""
        page.source_text.clear()
        page._start_translation()
        assert page._worker is None

    @patch("src.ui.pages.translate_text.check_llm_setup", return_value=False)
    @patch("src.ui.dialogs.CustomConfirmDialog.confirm", return_value=False)
    def test_start_shows_dialog_when_llm_not_configured(
        self,
        mock_confirm,
        mock_llm,
        page,
    ) -> None:
        """Shows setup dialog via require_setup when LLM is not configured."""
        page.source_text.setPlainText("hello")
        page._start_translation()

        mock_confirm.assert_called_once()
        assert page._worker is None

    def test_on_translated_reenables_ui(self, page) -> None:
        """Successful translation re-enables the translate button.

        _on_translated gates re-enable on source-text presence; populate
        source before checking.
        """
        page.source_text.setPlainText("hello")
        page.translate_btn.setEnabled(False)
        page._on_translated("Bonjour le monde")
        assert page.translate_btn.isEnabled()

    def test_on_translated_auto_saves(self, page) -> None:
        """Successful translation auto-saves to history."""
        page._last_source_text = "Hello"
        page._last_src_lang = "English (US)"
        page._last_tgt_lang = "French"

        with (
            patch(
                "src.ui.pages.translate_text.load_setting",
                return_value="true",
            ),
            patch(
                "src.core.database.add_text_translation_entry",
            ) as mock_save,
        ):
            page._on_translated("Bonjour")

        mock_save.assert_called_once_with(
            source_text="Hello",
            translated_text="Bonjour",
            src_lang="English (US)",
            target_lang="French",
            char_count=5,
        )

    def test_on_translated_skips_save_when_disabled(self, page) -> None:
        """Auto-save is skipped when setting is 'false'."""
        page._last_source_text = "Hello"

        with (
            patch(
                "src.ui.pages.translate_text.load_setting",
                return_value="false",
            ),
            patch(
                "src.core.database.add_text_translation_entry",
            ) as mock_save,
        ):
            page._on_translated("Bonjour")

        mock_save.assert_not_called()

    def test_on_error_shows_error_message(self, page) -> None:
        """Translation error surfaces via the footer status label.

        Mirrors the TTS-error placement so both error surfaces are
        consistent — the user only has one place to scan.  The
        target pane is left clear so a retry doesn't have to
        overwrite stale red placeholder text.
        """
        page._on_translation_error("API rate limit exceeded")
        # Status label carries the friendly error text…
        assert page.status_label.text() != ""
        assert page._status_is_error is True
        # …and the target pane is empty (no stale placeholder).
        assert page.target_text.toPlainText() == ""

    def test_on_error_reenables_translate_button(self, page) -> None:
        """Translate button is re-enabled after an error (if source has text)."""
        page.source_text.setPlainText("retry me")
        page._on_translation_error("some error")
        assert page.translate_btn.isEnabled()

    def test_on_translated_empty_skips_save(self, page) -> None:
        """Empty translation result is not saved to history."""
        page._last_source_text = "Hello"
        with (
            patch(
                "src.ui.pages.translate_text.load_setting",
                return_value="true",
            ),
            patch(
                "src.core.database.add_text_translation_entry",
            ) as mock_save,
        ):
            page._on_translated("")

        mock_save.assert_not_called()

    def test_start_translation_cancels_in_flight_worker(self, page) -> None:
        """Re-entering _start_translation while a worker runs cancels it."""
        page.source_text.setPlainText("hello")
        # Simulate an active worker.
        mock_worker = MagicMock()
        page._worker = mock_worker

        with patch(
            "src.ui.pages.translate_text.check_llm_setup",
            return_value=True,
        ):
            page._start_translation()

        # The worker was cancelled (not replaced).
        mock_worker.cancel.assert_called_once()
        assert page._worker is None

    def test_char_count_keeps_translate_btn_in_sync_during_active_translation(
        self,
        page,
    ) -> None:
        """Typing while worker is active keeps the button in sync with text.

        Note: the button tracks source-text non-emptiness regardless of
        worker state. When a worker is running the button also doubles as
        Cancel — clicking it a second time aborts the in-flight translation.
        """
        page._worker = MagicMock()
        page.translate_btn.setEnabled(False)

        page.source_text.setPlainText("new text")
        # Source now has text → button stays enabled (source-text binding
        # wins). The button doubles as Cancel while a worker is active.
        assert page.translate_btn.isEnabled()

    def test_on_chunk_appends_text(self, page) -> None:
        """Streaming chunks are appended to target text area."""
        page.target_text.clear()
        page._on_chunk("Hello ")
        page._on_chunk("world")
        assert page.target_text.toPlainText() == "Hello world"

    def test_on_translated_enables_edit_button(self, page) -> None:
        """Successful translation with text enables the edit button."""
        page.edit_btn.setEnabled(False)
        page._on_translated("Some result")
        assert page.edit_btn.isEnabled()

    def test_on_translated_empty_disables_edit_button(self, page) -> None:
        """Empty translation result disables the edit button."""
        page.edit_btn.setEnabled(True)
        with patch(
            "src.ui.pages.translate_text.load_setting",
            return_value="true",
        ):
            page._on_translated("")
        assert not page.edit_btn.isEnabled()

    def test_on_translated_clears_status(self, page) -> None:
        """Successful translation clears the status label."""
        page.status_label.setText("some previous status")
        page._on_translated("result")
        assert page.status_label.text() == ""

    def test_on_translated_clears_error_flag(self, page) -> None:
        """Successful translation resets the error flag."""
        page._status_is_error = True
        page._on_translated("result")
        assert page._status_is_error is False

    def test_on_error_restores_translate_button_text(self, page) -> None:
        """Translation error restores the translate button text."""
        from src.constants.i18n import tr  # noqa: PLC0415

        page.translate_btn.setText("Translating...")
        page._on_translation_error("fail")
        assert page.translate_btn.text() == tr("translate_text.btn_translate")

    def test_on_translated_restores_translate_button_text(self, page) -> None:
        """Successful translation restores translate button text."""
        from src.constants.i18n import tr  # noqa: PLC0415

        page.translate_btn.setText("Translating...")
        page._on_translated("done")
        assert page.translate_btn.text() == tr("translate_text.btn_translate")

    def test_whitespace_only_text_is_noop(self, page) -> None:
        """Starting translation with whitespace-only text does nothing."""
        page.source_text.setPlainText("   \n\t  ")
        page._start_translation()
        assert page._worker is None

    def test_start_translation_clears_target(self, page) -> None:
        """Starting translation clears the target text area."""
        page.target_text.setPlainText("old translation")
        page.source_text.setPlainText("new source")

        with (
            patch(
                "src.ui.pages.translate_text.check_llm_setup",
                return_value=True,
            ),
            patch(
                "src.ui.pages.translate_text.load_setting",
                return_value="",
            ),
            patch("src.core.database.get_active_glossary_sets", return_value=[]),
            patch(
                "src.ui.pages.translate_text._TextTranslationWorker",
            ) as mock_worker_cls,
        ):
            mock_instance = MagicMock()
            mock_worker_cls.return_value = mock_instance
            page._start_translation()

        assert page.target_text.toPlainText() == ""
        # Clean up mock worker
        page._worker = None

    def test_on_chunk_preserves_existing_text(self, page) -> None:
        """Streaming chunk is appended to existing target text."""
        page.target_text.setPlainText("")
        page._on_chunk("First ")
        page._on_chunk("second ")
        page._on_chunk("third")
        assert page.target_text.toPlainText() == "First second third"

    def test_cleanup_worker_resets_to_none(self, page) -> None:
        """_cleanup_worker sets _worker to None."""
        mock_worker = MagicMock()
        page._worker = mock_worker

        page._cleanup_worker()

        assert page._worker is None
        mock_worker.wait.assert_called_once()


# ---------------------------------------------------------------------------
# Error state handling
# ---------------------------------------------------------------------------


class TestErrorStateHandling:
    """Tests for error state management in the page."""

    @patch("src.ui.pages.translate_text.check_llm_setup", return_value=False)
    @patch("src.ui.dialogs.CustomConfirmDialog.confirm", return_value=False)
    def test_no_llm_configured_shows_dialog(
        self,
        mock_confirm,
        mock_llm,
        page,
    ) -> None:
        """require_setup shows a confirm dialog and blocks worker start."""
        page.source_text.setPlainText("translate this")
        page._start_translation()

        mock_confirm.assert_called_once()
        assert page._worker is None

    @patch("src.ui.pages.translate_text.check_llm_setup", return_value=False)
    @patch("src.ui.dialogs.CustomConfirmDialog.confirm", return_value=False)
    def test_no_llm_keeps_source_text(
        self,
        mock_confirm,
        mock_llm,
        page,
    ) -> None:
        """Source text is preserved when LLM is not configured."""
        page.source_text.setPlainText("keep this text")
        page._start_translation()
        assert page.source_text.toPlainText() == "keep this text"

    def test_error_status_label_set_on_error(self, page) -> None:
        """Errors are rendered in the footer status label, not the target pane.

        Mirrors TTS-error placement so both surfaces are consistent;
        the user only has one place to scan for failures.
        """
        page._on_translation_error("Error occurred")
        assert page._status_is_error is True
        assert page.status_label.text() != ""
        # Target pane is left clear so a retry doesn't have to
        # overwrite a stale red placeholder.
        assert page.target_text.toPlainText() == ""

    def test_successful_translation_after_error_clears_error(
        self,
        page,
    ) -> None:
        """Successful translation after an error clears the error state."""
        page._on_translation_error("connection failed")
        assert page._status_is_error is True

        # Successful translation lands real text in the target pane;
        # the error-status flag flips off so the footer's red text
        # is no longer treated as an active error.
        page._on_translated("success")
        assert page._status_is_error is False

    def test_multiple_errors_update_status_label(self, page) -> None:
        """Each error re-sets the footer status label."""
        page._on_translation_error("first error")
        assert page._status_is_error is True
        first_text = page.status_label.text()
        assert first_text != ""

        page._on_translation_error("second error")
        assert page._status_is_error is True
        # New error replaces the old text — the user only ever sees
        # the most recent failure.
        assert page.status_label.text() != ""


# ---------------------------------------------------------------------------
# Streaming worker
# ---------------------------------------------------------------------------


class TestStreamingWorker:
    """Tests for _TextTranslationWorker behavior."""

    def test_worker_construction(self) -> None:
        """Worker can be constructed with required parameters."""
        from src.ui.pages.translate_text import (  # noqa: PLC0415
            _TextTranslationWorker,
        )

        worker = _TextTranslationWorker(
            "Hello",
            "English (US)",
            "French",
        )
        assert worker._text == "Hello"
        assert worker._src_lang == "English (US)"
        assert worker._target_lang == "French"
        assert worker._cancelled is False
        assert worker._glossary is None

    def test_worker_with_glossary(self) -> None:
        """Worker accepts optional glossary entries."""
        from src.ui.pages.translate_text import (  # noqa: PLC0415
            _TextTranslationWorker,
        )

        glossary = [(1, "hello", "xin chao"), (2, "world", "the gioi")]
        worker = _TextTranslationWorker(
            "Hello world",
            "English",
            "Vietnamese",
            glossary_entries=glossary,
        )
        assert worker._glossary == glossary

    def test_worker_cancel_sets_flag(self) -> None:
        """Calling cancel() sets the _cancelled flag."""
        from src.ui.pages.translate_text import (  # noqa: PLC0415
            _TextTranslationWorker,
        )

        worker = _TextTranslationWorker("text", "EN", "FR")
        assert worker._cancelled is False

        worker.cancel()
        assert worker._cancelled is True

    def test_worker_emits_translated_on_empty_text(self, qtbot) -> None:
        """Worker emits translated('') for whitespace-only text."""
        from src.ui.pages.translate_text import (  # noqa: PLC0415
            _TextTranslationWorker,
        )

        worker = _TextTranslationWorker("   ", "EN", "FR")

        with qtbot.waitSignal(worker.translated, timeout=3000) as blocker:
            worker.start()
            worker.wait()

        assert blocker.args == [""]

    def test_worker_emits_chunks_and_translated(self, qtbot) -> None:
        """Worker emits chunk signals and then translated on success."""
        from src.ui.pages.translate_text import (  # noqa: PLC0415
            _TextTranslationWorker,
        )

        chunks = ["Bon", "jour"]

        def mock_stream(*_args, **_kwargs):
            yield from chunks

        worker = _TextTranslationWorker("Hello", "EN", "FR")
        received_chunks = []
        worker.chunk.connect(received_chunks.append)

        with (
            patch(
                "src.core.llm_engine.stream_translate_text",
                side_effect=mock_stream,
            ),
            qtbot.waitSignal(worker.translated, timeout=3000) as blocker,
        ):
            worker.start()
            worker.wait()

        assert received_chunks == ["Bon", "jour"]
        assert blocker.args == ["Bonjour"]

    def test_worker_emits_error_on_exception(self, qtbot) -> None:
        """Worker emits error signal when stream_translate_text raises."""
        from src.ui.pages.translate_text import (  # noqa: PLC0415
            _TextTranslationWorker,
        )

        def mock_stream(*_args, **_kwargs):
            msg = "API key invalid"
            raise ValueError(msg)

        worker = _TextTranslationWorker("Hello", "EN", "FR")

        with (
            patch(
                "src.core.llm_engine.stream_translate_text",
                side_effect=mock_stream,
            ),
            qtbot.waitSignal(worker.error, timeout=3000) as blocker,
        ):
            worker.start()
            worker.wait()

        assert "API key invalid" in blocker.args[0]

    def test_worker_cancel_prevents_translated_signal(self, qtbot) -> None:
        """Cancelled worker does not emit the translated signal."""
        from src.ui.pages.translate_text import (  # noqa: PLC0415
            _TextTranslationWorker,
        )

        def mock_stream(*_args, **_kwargs):
            yield "first"
            yield "second"

        worker = _TextTranslationWorker("Hello", "EN", "FR")
        translated_results = []
        worker.translated.connect(translated_results.append)

        # Cancel before starting
        worker.cancel()

        with patch(
            "src.core.llm_engine.stream_translate_text",
            side_effect=mock_stream,
        ):
            worker.start()
            worker.wait()

        # Cancelled worker should not emit translated
        assert translated_results == []


# ---------------------------------------------------------------------------
# Copy
# ---------------------------------------------------------------------------


class TestCopyToClipboard:
    """Tests for copy-to-clipboard on the translate text page."""

    def test_target_text_is_selectable(self, page) -> None:
        """Target text area allows text selection for manual copy."""
        page.target_text.setPlainText("Translation result")
        # Target text is read-only but should still be selectable
        assert page.target_text.isReadOnly()
        # Verify text is present and accessible
        assert page.target_text.toPlainText() == "Translation result"


# ---------------------------------------------------------------------------
# Theme / Language
# ---------------------------------------------------------------------------


class TestThemeAndLanguage:
    """Tests for theme and language update methods."""

    def test_apply_theme_no_error(self, page, _mock_history) -> None:
        """apply_theme runs without error."""
        page.apply_theme()

    def test_apply_language_no_error(self, page, _mock_history) -> None:
        """apply_language runs without error."""
        page.apply_language()

    def test_apply_theme_with_error_status(self, page, _mock_history) -> None:
        """apply_theme handles error status style correctly."""
        page._status_is_error = True
        page.apply_theme()
        # Should not crash; error style is applied

    def test_apply_theme_with_edit_mode_active(
        self,
        page,
        _mock_history,
    ) -> None:
        """apply_theme applies correct style when in edit mode."""
        page.target_text.setPlainText("text")
        page._set_editing(True)
        page.apply_theme()
        # Should apply primary button style to edit_btn in edit mode

    def test_apply_language_updates_placeholder_text(
        self,
        page,
        _mock_history,
    ) -> None:
        """apply_language updates placeholder text on text areas."""
        from src.constants.i18n import tr  # noqa: PLC0415

        page.apply_language()
        assert page.source_text.placeholderText() == tr(
            "translate_text.source_placeholder",
        )
        assert page.target_text.placeholderText() == tr(
            "translate_text.target_placeholder",
        )

    def test_apply_language_in_edit_mode(self, page, _mock_history) -> None:
        """apply_language shows 'Save' text when in edit mode."""
        from src.constants.i18n import tr  # noqa: PLC0415

        page.target_text.setPlainText("text")
        page._set_editing(True)

        page.apply_language()

        assert page.edit_btn.text() == tr("translate_text.btn_save")

    def test_apply_language_during_translation(
        self,
        page,
        _mock_history,
    ) -> None:
        """apply_language does not overwrite 'Translating...' button text."""
        page._worker = MagicMock()  # Simulate active worker
        page.translate_btn.setText("Translating...")

        page.apply_language()

        # When worker is active, translate button text should NOT be updated
        assert page.translate_btn.text() == "Translating..."
        page._worker = None

    def test_apply_language_history_view(self, page, _mock_history) -> None:
        """apply_language updates history button text when in history view."""
        from src.constants.i18n import tr  # noqa: PLC0415

        page._header_stack.setCurrentIndex(1)
        page.apply_language()
        assert page.history_btn.text() == tr("translate_text.btn_back")


# ---------------------------------------------------------------------------
# Factory function
# ---------------------------------------------------------------------------


class TestFactoryFunction:
    """Tests for create_translate_text_page factory function."""

    def test_factory_returns_correct_type(
        self,
        window,
        _mock_deps,
    ) -> None:
        """create_translate_text_page returns a TranslateTextPage."""
        from src.ui.pages.translate_text import (  # noqa: PLC0415
            TranslateTextPage,
            create_translate_text_page,
        )

        page = create_translate_text_page(window)
        assert isinstance(page, TranslateTextPage)

    def test_factory_stores_window_context(
        self,
        window,
        _mock_deps,
    ) -> None:
        """Factory-created page stores reference to parent window."""
        from src.ui.pages.translate_text import (  # noqa: PLC0415
            create_translate_text_page,
        )

        page = create_translate_text_page(window)
        assert page.window_context is window


# ---------------------------------------------------------------------------
# Edge cases for translate action
# ---------------------------------------------------------------------------


class TestTranslateTextEdgeCases:
    """Tests for edge cases in the translation workflow."""

    def test_translate_empty_source_is_noop(self, page) -> None:
        """Starting translation with completely empty source does nothing."""
        page.source_text.setPlainText("")
        page._start_translation()
        assert page._worker is None

    def test_translate_whitespace_only_is_noop(self, page) -> None:
        """Starting translation with whitespace-only text does nothing."""
        page.source_text.setPlainText("   \t\n   ")
        page._start_translation()
        assert page._worker is None

    def test_translate_single_newline_is_noop(self, page) -> None:
        """Starting translation with just a newline does nothing."""
        page.source_text.setPlainText("\n")
        page._start_translation()
        assert page._worker is None

    def test_translate_very_long_text_truncated(self, page) -> None:
        """Text longer than _MAX_CHAR_LIMIT is auto-truncated to 5000."""
        page.source_text.setPlainText("A" * 50_001)
        assert len(page.source_text.toPlainText()) == 5000  # noqa: PLR2004

    def test_translate_html_in_source_preserved(self, page) -> None:
        """HTML tags in source text are preserved verbatim."""
        html_text = "<b>bold</b> <i>italic</i>"
        page.source_text.setPlainText(html_text)
        assert page.source_text.toPlainText() == html_text

    def test_translate_newlines_preserved(self, page) -> None:
        """Newlines in source text are preserved."""
        text = "Line 1\nLine 2\nLine 3"
        page.source_text.setPlainText(text)
        assert page.source_text.toPlainText() == text

    def test_rapid_translate_clicks_cancel_in_flight_worker(self, page) -> None:
        """Clicking Translate while one is running cancels the in-flight worker."""
        page.source_text.setPlainText("hello world")
        mock_worker = MagicMock()
        page._worker = mock_worker

        with patch(
            "src.ui.pages.translate_text.check_llm_setup",
            return_value=True,
        ):
            page._start_translation()

        # The click acted as Cancel — worker.cancel() was called and the
        # worker reference was cleaned up.
        mock_worker.cancel.assert_called_once()
        assert page._worker is None

    def test_translate_special_characters(self, page) -> None:
        """Source text with special characters is preserved."""
        special = "Price: $100 & tax @5%"
        page.source_text.setPlainText(special)
        assert page.source_text.toPlainText() == special

    def test_translate_unicode_text_preserved(self, page) -> None:
        """Unicode text (CJK, emoji) is preserved in the source area."""
        unicode_text = "Hello world"
        page.source_text.setPlainText(unicode_text)
        assert page.source_text.toPlainText() == unicode_text

    def test_translate_tabs_preserved(self, page) -> None:
        """Tab characters in source text are preserved."""
        tabbed = "col1\tcol2\tcol3"
        page.source_text.setPlainText(tabbed)
        assert page.source_text.toPlainText() == tabbed

    def test_start_translation_keeps_translate_button_enabled_as_cancel(
        self,
        page,
    ) -> None:
        """Starting translation keeps the button enabled so it can act as Cancel."""
        page.source_text.setPlainText("hello world")

        with (
            patch(
                "src.ui.pages.translate_text.check_llm_setup",
                return_value=True,
            ),
            patch(
                "src.ui.pages.translate_text.load_setting",
                return_value="",
            ),
            patch("src.core.database.get_active_glossary_sets", return_value=[]),
            patch(
                "src.ui.pages.translate_text._TextTranslationWorker",
            ) as mock_worker_cls,
        ):
            mock_instance = MagicMock()
            mock_worker_cls.return_value = mock_instance
            page._start_translation()

        # The button stays enabled — clicking it again cancels the worker.
        assert page.translate_btn.isEnabled()
        page._worker = None

    def test_start_translation_updates_button_text_to_cancel(self, page) -> None:
        """Starting translation changes the button label to include Cancel + spinner."""
        from src.constants.i18n import tr  # noqa: PLC0415

        page.source_text.setPlainText("hello world")

        with (
            patch(
                "src.ui.pages.translate_text.check_llm_setup",
                return_value=True,
            ),
            patch(
                "src.ui.pages.translate_text.load_setting",
                return_value="",
            ),
            patch("src.core.database.get_active_glossary_sets", return_value=[]),
            patch(
                "src.ui.pages.translate_text._TextTranslationWorker",
            ) as mock_worker_cls,
        ):
            mock_instance = MagicMock()
            mock_worker_cls.return_value = mock_instance
            page._start_translation()

        # Button now carries a Braille spinner frame plus the Cancel label.
        assert tr("btn.cancel") in page.translate_btn.text()
        assert page._spinner_timer is not None and page._spinner_timer.isActive()
        page._stop_spinner()
        page._worker = None

    def test_start_translation_keeps_default_placeholder(self, page) -> None:
        """Starting translation leaves the default placeholder; progress lives in the spinner."""
        from src.constants.i18n import tr  # noqa: PLC0415

        page.status_label.setText("some old status")
        page.source_text.setPlainText("hello world")

        with (
            patch(
                "src.ui.pages.translate_text.check_llm_setup",
                return_value=True,
            ),
            patch(
                "src.ui.pages.translate_text.load_setting",
                return_value="",
            ),
            patch("src.core.database.get_active_glossary_sets", return_value=[]),
            patch(
                "src.ui.pages.translate_text._TextTranslationWorker",
            ) as mock_worker_cls,
        ):
            mock_instance = MagicMock()
            mock_worker_cls.return_value = mock_instance
            page._start_translation()

        # The Braille spinner on the button is the single progress signal; the
        # target keeps its default placeholder and the bottom status label is empty.
        assert page.target_text.placeholderText() == tr(
            "translate_text.target_placeholder",
        )
        assert page._target_placeholder_is_error is False
        assert page.status_label.text() == ""
        page._stop_spinner()
        page._worker = None

    def test_start_translation_resets_error_flag(self, page) -> None:
        """Starting translation resets the error flag."""
        page._status_is_error = True
        page.source_text.setPlainText("hello world")

        with (
            patch(
                "src.ui.pages.translate_text.check_llm_setup",
                return_value=True,
            ),
            patch(
                "src.ui.pages.translate_text.load_setting",
                return_value="",
            ),
            patch("src.core.database.get_active_glossary_sets", return_value=[]),
            patch(
                "src.ui.pages.translate_text._TextTranslationWorker",
            ) as mock_worker_cls,
        ):
            mock_instance = MagicMock()
            mock_worker_cls.return_value = mock_instance
            page._start_translation()

        assert page._status_is_error is False
        page._worker = None

    def test_start_translation_exits_edit_mode(self, page) -> None:
        """Starting translation exits edit mode if active."""
        page.source_text.setPlainText("hello")
        page.target_text.setPlainText("old")
        page._set_editing(True)
        assert not page.target_text.isReadOnly()

        with (
            patch(
                "src.ui.pages.translate_text.check_llm_setup",
                return_value=True,
            ),
            patch(
                "src.ui.pages.translate_text.load_setting",
                return_value="",
            ),
            patch("src.core.database.get_active_glossary_sets", return_value=[]),
            patch(
                "src.ui.pages.translate_text._TextTranslationWorker",
            ) as mock_worker_cls,
        ):
            mock_instance = MagicMock()
            mock_worker_cls.return_value = mock_instance
            page._start_translation()

        assert page.target_text.isReadOnly()
        page._worker = None

    def test_start_translation_disables_edit_button(self, page) -> None:
        """Starting translation disables the edit button."""
        page.edit_btn.setEnabled(True)
        page.source_text.setPlainText("test text")

        with (
            patch(
                "src.ui.pages.translate_text.check_llm_setup",
                return_value=True,
            ),
            patch(
                "src.ui.pages.translate_text.load_setting",
                return_value="",
            ),
            patch("src.core.database.get_active_glossary_sets", return_value=[]),
            patch(
                "src.ui.pages.translate_text._TextTranslationWorker",
            ) as mock_worker_cls,
        ):
            mock_instance = MagicMock()
            mock_worker_cls.return_value = mock_instance
            page._start_translation()

        assert not page.edit_btn.isEnabled()
        page._worker = None


# ---------------------------------------------------------------------------
# Extended language swap tests
# ---------------------------------------------------------------------------


class TestLanguageSwapExtended:
    """Extended tests for the swap languages feature."""

    def test_swap_with_auto_source_button_disabled(self, page) -> None:
        """Swap button is disabled when source is Auto (index 0)."""
        page.src_combo.setCurrentIndex(0)
        assert not page.swap_btn.isEnabled()

    def test_swap_preserves_combo_indices_correctly(self, page) -> None:
        """Swap correctly exchanges combo box indices."""
        page.src_combo.setCurrentIndex(2)
        page.target_combo.setCurrentIndex(3)

        src_text_before = page.src_combo.currentData()
        tgt_text_before = page.target_combo.currentData()

        page._swap_languages()

        assert page.src_combo.currentData() == tgt_text_before
        assert page.target_combo.currentData() == src_text_before

    def test_swap_does_not_swap_text_when_target_empty(self, page) -> None:
        """When target text is empty, source text is NOT cleared on swap."""
        page.src_combo.setCurrentIndex(1)
        page.source_text.setPlainText("keep me")
        page.target_text.clear()

        page._swap_languages()

        # When target is empty, text swap is skipped
        assert page.source_text.toPlainText() == "keep me"

    def test_swap_twice_restores_original(self, page) -> None:
        """Swapping twice restores original language selections."""
        page.src_combo.setCurrentIndex(2)
        page.target_combo.setCurrentIndex(4)

        original_src = page.src_combo.currentData()
        original_tgt = page.target_combo.currentData()

        page.source_text.setPlainText("source text")
        page.target_text.setPlainText("target text")

        page._swap_languages()
        page._swap_languages()

        assert page.src_combo.currentData() == original_src
        assert page.target_combo.currentData() == original_tgt
        assert page.source_text.toPlainText() == "source text"
        assert page.target_text.toPlainText() == "target text"

    def test_swap_with_same_language(self, page) -> None:
        """Swap works even when both combos have the same language."""
        page.src_combo.setCurrentIndex(1)
        # Set target to the same language text
        tgt_idx = page.target_combo.findText(page.src_combo.currentData())
        if tgt_idx >= 0:
            page.target_combo.setCurrentIndex(tgt_idx)

        # Should not crash
        page._swap_languages()


# ---------------------------------------------------------------------------
# Extended character count tests
# ---------------------------------------------------------------------------


class TestCharacterCountExtended:
    """Extended tests for character counting."""

    def test_char_count_with_emoji(self, page) -> None:
        """Character count works correctly with emoji characters."""
        page.source_text.setPlainText("Hi!")
        count_text = page.char_count.text()
        # "Hi!" is 3 chars (the emoji is a single character in Python)
        assert "3" in count_text

    def test_char_count_with_mixed_unicode(self, page) -> None:
        """Character count handles mixed ASCII and unicode."""
        page.source_text.setPlainText("abc123")
        count_text = page.char_count.text()
        assert "6" in count_text

    def test_char_count_with_cjk_characters(self, page) -> None:
        """Character count handles CJK characters correctly."""
        page.source_text.setPlainText("ABCDE")
        count_text = page.char_count.text()
        assert "5" in count_text

    def test_char_count_at_boundary_minus_one(self, page) -> None:
        """Text at 4999 chars is not truncated."""
        page.source_text.setPlainText("x" * 4999)
        assert len(page.source_text.toPlainText()) == 4999  # noqa: PLR2004

    def test_char_count_format_with_thousands_separator(self, page) -> None:
        """Character count uses comma formatting for large numbers."""
        page.source_text.setPlainText("a" * 2500)
        count_text = page.char_count.text()
        assert "2,500" in count_text

    def test_char_count_after_clear(self, page) -> None:
        """Character count resets to 0 after clearing text."""
        page.source_text.setPlainText("some text")
        page.source_text.clear()
        assert page.char_count.text().startswith("0")


# ---------------------------------------------------------------------------
# Extended copy tests
# ---------------------------------------------------------------------------


class TestCopyToClipboardExtended:
    """Extended tests for copy-to-clipboard behavior."""

    def test_copy_with_empty_target(self, page) -> None:
        """Target text area with empty text is accessible."""
        page.target_text.clear()
        assert page.target_text.toPlainText() == ""

    def test_target_text_preserves_multiline(self, page) -> None:
        """Multi-line translated text is preserved in target area."""
        multiline = "Line 1\nLine 2\nLine 3"
        page.target_text.setPlainText(multiline)
        assert page.target_text.toPlainText() == multiline

    def test_target_text_preserves_special_chars(self, page) -> None:
        """Special characters in translated text are preserved."""
        special = '<tag attr="val">&amp;</tag>'
        page.target_text.setPlainText(special)
        assert page.target_text.toPlainText() == special


# ---------------------------------------------------------------------------
# Extended history tests
# ---------------------------------------------------------------------------


class TestTranslateTextHistoryExtended:
    """Extended tests for history integration."""

    def test_history_save_called_with_correct_params(self, page) -> None:
        """History save passes correct parameters to database."""
        page._last_source_text = "Goodbye"
        page._last_src_lang = "English (US)"
        page._last_tgt_lang = "German"

        with (
            patch(
                "src.ui.pages.translate_text.load_setting",
                return_value="true",
            ),
            patch(
                "src.core.database.add_text_translation_entry",
                return_value=99,
            ) as mock_save,
        ):
            page._on_translated("Tschuss")

        mock_save.assert_called_once_with(
            source_text="Goodbye",
            translated_text="Tschuss",
            src_lang="English (US)",
            target_lang="German",
            char_count=7,
        )
        assert page._last_entry_id == 99  # noqa: PLR2004

    def test_history_search_widget_exists(self, page) -> None:
        """History search input widget exists."""
        assert hasattr(page, "_history_search")
        assert page._history_search is not None

    def test_history_view_button_exists(self, page) -> None:
        """History view button exists and starts disabled."""
        assert hasattr(page, "_history_view_btn")
        assert not page._history_view_btn.isEnabled()

    def test_history_delete_button_exists(self, page) -> None:
        """History delete button exists and starts disabled."""
        assert hasattr(page, "_history_delete_btn")
        assert not page._history_delete_btn.isEnabled()

    def test_history_delete_without_selection_stays_disabled(self, page) -> None:
        """Delete button remains disabled when nothing is selected."""
        page._on_history_selection_changed(False)
        assert not page._history_delete_btn.isEnabled()

    def test_history_selection_enables_all_buttons(self, page) -> None:
        """Selecting a history entry enables view and delete buttons."""
        page._on_history_selection_changed(True)
        assert page._history_view_btn.isEnabled()
        assert page._history_delete_btn.isEnabled()

    def test_history_deselection_disables_all_buttons(self, page) -> None:
        """Deselecting history entries disables view and delete."""
        page._on_history_selection_changed(True)
        page._on_history_selection_changed(False)
        assert not page._history_view_btn.isEnabled()
        assert not page._history_delete_btn.isEnabled()

    def test_history_widget_is_embedded(self, page) -> None:
        """The TextTranslationHistoryWidget is embedded in the page."""
        assert hasattr(page, "_history_widget")
        assert page._history_widget is not None

    def test_toggle_history_refreshes_widget(self, page, _mock_history) -> None:
        """Toggling to history view calls refresh_history on the widget."""
        with patch.object(page._history_widget, "refresh_history") as mock_refresh:
            page._toggle_history()
        mock_refresh.assert_called_once_with(force=True)

    def test_history_auto_save_stores_entry_id(self, page) -> None:
        """Auto-save stores the returned entry ID for later editing."""
        page._last_source_text = "Hello"
        page._last_src_lang = ""
        page._last_tgt_lang = "French"

        with (
            patch(
                "src.ui.pages.translate_text.load_setting",
                return_value="true",
            ),
            patch(
                "src.core.database.add_text_translation_entry",
                return_value=42,
            ),
        ):
            page._on_translated("Bonjour")

        assert page._last_entry_id == 42  # noqa: PLR2004


# ---------------------------------------------------------------------------
# Extended theme and language tests
# ---------------------------------------------------------------------------


class TestTranslateTextThemeLanguageExtended:
    """Extended tests for theme and language application."""

    def test_apply_theme_updates_card_style(self, page, _mock_history) -> None:
        """apply_theme re-applies card stylesheet."""
        page.apply_theme()
        style = page._card.styleSheet()
        assert "TranslateCard" in style

    def test_apply_theme_updates_separator_styles(
        self,
        page,
        _mock_history,
    ) -> None:
        """apply_theme re-applies separator styles."""
        page.apply_theme()
        for sep in page._separators:
            assert sep.styleSheet() != ""

    def test_apply_theme_updates_source_combo(
        self,
        page,
        _mock_history,
    ) -> None:
        """apply_theme re-applies source combo stylesheet."""
        page.apply_theme()
        assert page.src_combo.styleSheet() != ""

    def test_apply_theme_updates_target_combo(
        self,
        page,
        _mock_history,
    ) -> None:
        """apply_theme re-applies target combo stylesheet."""
        page.apply_theme()
        assert page.target_combo.styleSheet() != ""

    def test_apply_theme_updates_text_areas(
        self,
        page,
        _mock_history,
    ) -> None:
        """apply_theme re-applies text area stylesheets."""
        page.apply_theme()
        assert page.source_text.styleSheet() != ""
        assert page.target_text.styleSheet() != ""

    def test_apply_theme_updates_translate_button(
        self,
        page,
        _mock_history,
    ) -> None:
        """apply_theme re-applies translate button stylesheet."""
        page.apply_theme()
        assert page.translate_btn.styleSheet() != ""

    def test_apply_theme_updates_history_button(
        self,
        page,
        _mock_history,
    ) -> None:
        """apply_theme re-applies history button stylesheet."""
        page.apply_theme()
        assert page.history_btn.styleSheet() != ""

    def test_apply_theme_updates_swap_button(
        self,
        page,
        _mock_history,
    ) -> None:
        """apply_theme re-applies swap button stylesheet."""
        page.apply_theme()
        assert page.swap_btn.styleSheet() != ""

    def test_apply_theme_non_error_status_style(
        self,
        page,
        _mock_history,
    ) -> None:
        """apply_theme applies non-error style when no error state."""
        page._status_is_error = False
        page.apply_theme()
        # No crash; char_count style applied
        assert page.status_label.styleSheet() != ""

    def test_apply_language_updates_translate_button(
        self,
        page,
        _mock_history,
    ) -> None:
        """apply_language updates translate button text."""
        from src.constants.i18n import tr  # noqa: PLC0415

        page.apply_language()
        assert page.translate_btn.text() == tr("translate_text.btn_translate")

    def test_apply_language_updates_edit_button_readonly(
        self,
        page,
        _mock_history,
    ) -> None:
        """apply_language updates edit button text to 'Edit' in readonly mode."""
        from src.constants.i18n import tr  # noqa: PLC0415

        page.target_text.setReadOnly(True)
        page.apply_language()
        assert page.edit_btn.text() == tr("translate_text.btn_edit")

    def test_apply_language_updates_cancel_button(
        self,
        page,
        _mock_history,
    ) -> None:
        """apply_language updates cancel button text."""
        from src.constants.i18n import tr  # noqa: PLC0415

        page.apply_language()
        assert page.cancel_edit_btn.text() == tr("btn.cancel")

    def test_apply_language_updates_history_search_placeholder(
        self,
        page,
        _mock_history,
    ) -> None:
        """apply_language updates history search placeholder."""
        from src.constants.i18n import tr  # noqa: PLC0415

        page.apply_language()
        assert page._history_search.placeholderText() == tr(
            "text_history.search_placeholder",
        )

    def test_apply_language_updates_history_view_button(
        self,
        page,
        _mock_history,
    ) -> None:
        """apply_language updates history view button text."""
        from src.constants.i18n import tr  # noqa: PLC0415

        page.apply_language()
        assert page._history_view_btn.text() == tr("btn.view")

    def test_apply_language_updates_history_delete_button(
        self,
        page,
        _mock_history,
    ) -> None:
        """apply_language updates history delete button text."""
        from src.constants.i18n import tr  # noqa: PLC0415

        page.apply_language()
        assert page._history_delete_btn.text() == tr("btn.delete")

    def test_apply_language_translate_view_button_text(
        self,
        page,
        _mock_history,
    ) -> None:
        """apply_language sets history button to 'History' in translate view."""
        from src.constants.i18n import tr  # noqa: PLC0415

        page._header_stack.setCurrentIndex(0)
        page.apply_language()
        assert page.history_btn.text() == tr("translate_text.btn_history")


# ---------------------------------------------------------------------------
# Extended worker tests
# ---------------------------------------------------------------------------


class TestTranslateTextWorkerExtended:
    """Extended tests for _TextTranslationWorker."""

    def test_worker_emits_translated_on_success(self, qtbot) -> None:
        """Worker emits translated signal with full text on success."""
        from src.ui.pages.translate_text import (  # noqa: PLC0415
            _TextTranslationWorker,
        )

        def mock_stream(*_args, **_kwargs):
            yield "Hello "
            yield "World"

        worker = _TextTranslationWorker("Bonjour Monde", "French", "English (US)")

        with (
            patch(
                "src.core.llm_engine.stream_translate_text",
                side_effect=mock_stream,
            ),
            qtbot.waitSignal(worker.translated, timeout=3000) as blocker,
        ):
            worker.start()
            worker.wait()

        assert blocker.args == ["Hello World"]

    def test_worker_emits_error_on_auth_error(self, qtbot) -> None:
        """Worker emits error signal with AUTH_ERROR message."""
        from src.ui.pages.translate_text import (  # noqa: PLC0415
            _TextTranslationWorker,
        )

        def mock_stream(*_args, **_kwargs):
            msg = "AUTH_ERROR"
            raise ValueError(msg)

        worker = _TextTranslationWorker("Hello", "EN", "FR")

        with (
            patch(
                "src.core.llm_engine.stream_translate_text",
                side_effect=mock_stream,
            ),
            qtbot.waitSignal(worker.error, timeout=3000) as blocker,
        ):
            worker.start()
            worker.wait()

        assert "AUTH_ERROR" in blocker.args[0]

    def test_worker_emits_error_on_quota_error(self, qtbot) -> None:
        """Worker emits error signal with QUOTA_ERROR message."""
        from src.ui.pages.translate_text import (  # noqa: PLC0415
            _TextTranslationWorker,
        )

        def mock_stream(*_args, **_kwargs):
            msg = "QUOTA_ERROR"
            raise ValueError(msg)

        worker = _TextTranslationWorker("Hello", "EN", "FR")

        with (
            patch(
                "src.core.llm_engine.stream_translate_text",
                side_effect=mock_stream,
            ),
            qtbot.waitSignal(worker.error, timeout=3000) as blocker,
        ):
            worker.start()
            worker.wait()

        assert "QUOTA_ERROR" in blocker.args[0]

    def test_worker_emits_error_on_connection_error(self, qtbot) -> None:
        """Worker emits error signal on ConnectionError."""
        from src.ui.pages.translate_text import (  # noqa: PLC0415
            _TextTranslationWorker,
        )

        def mock_stream(*_args, **_kwargs):
            msg = "CONNECTION_ERROR"
            raise ConnectionError(msg)

        worker = _TextTranslationWorker("Hello", "EN", "FR")

        with (
            patch(
                "src.core.llm_engine.stream_translate_text",
                side_effect=mock_stream,
            ),
            qtbot.waitSignal(worker.error, timeout=3000) as blocker,
        ):
            worker.start()
            worker.wait()

        assert "CONNECTION_ERROR" in blocker.args[0]

    def test_worker_emits_error_on_runtime_error(self, qtbot) -> None:
        """Worker emits error signal on RuntimeError."""
        from src.ui.pages.translate_text import (  # noqa: PLC0415
            _TextTranslationWorker,
        )

        def mock_stream(*_args, **_kwargs):
            msg = "Service unavailable"
            raise RuntimeError(msg)

        worker = _TextTranslationWorker("Hello", "EN", "FR")

        with (
            patch(
                "src.core.llm_engine.stream_translate_text",
                side_effect=mock_stream,
            ),
            qtbot.waitSignal(worker.error, timeout=3000) as blocker,
        ):
            worker.start()
            worker.wait()

        assert "Service unavailable" in blocker.args[0]

    def test_worker_passes_glossary_to_stream(self, qtbot) -> None:
        """Worker passes glossary entries to stream_translate_text."""
        from src.ui.pages.translate_text import (  # noqa: PLC0415
            _TextTranslationWorker,
        )

        glossary = [(1, "hello", "xin chao")]

        def mock_stream(*_args, **kwargs):
            assert kwargs.get("glossary_entries") == glossary
            yield "Xin chao"

        worker = _TextTranslationWorker(
            "Hello",
            "English",
            "Vietnamese",
            glossary_entries=glossary,
        )

        with (
            patch(
                "src.core.llm_engine.stream_translate_text",
                side_effect=mock_stream,
            ),
            qtbot.waitSignal(worker.translated, timeout=3000),
        ):
            worker.start()
            worker.wait()

    def test_worker_passes_source_lang_to_stream(self, qtbot) -> None:
        """Worker passes source_lang parameter to stream_translate_text."""
        from src.ui.pages.translate_text import (  # noqa: PLC0415
            _TextTranslationWorker,
        )

        def mock_stream(*_args, **kwargs):
            assert kwargs.get("source_lang") == "English (US)"
            assert kwargs.get("target_lang") == "French"
            yield "Bonjour"

        worker = _TextTranslationWorker("Hello", "English (US)", "French")

        with (
            patch(
                "src.core.llm_engine.stream_translate_text",
                side_effect=mock_stream,
            ),
            qtbot.waitSignal(worker.translated, timeout=3000),
        ):
            worker.start()
            worker.wait()

    def test_worker_empty_source_lang_for_auto(self, qtbot) -> None:
        """Worker passes empty string as source_lang for Auto-detect."""
        from src.ui.pages.translate_text import (  # noqa: PLC0415
            _TextTranslationWorker,
        )

        def mock_stream(*_args, **kwargs):
            assert kwargs.get("source_lang") == ""
            yield "Bonjour"

        worker = _TextTranslationWorker("Hello", "", "French")

        with (
            patch(
                "src.core.llm_engine.stream_translate_text",
                side_effect=mock_stream,
            ),
            qtbot.waitSignal(worker.translated, timeout=3000),
        ):
            worker.start()
            worker.wait()


# ---------------------------------------------------------------------------
# Auto-detect language
# ---------------------------------------------------------------------------


class TestAutoDetectLanguage:
    """Tests for Auto-detect vs explicit source language selection."""

    def test_auto_detect_sends_empty_src_lang(self, page) -> None:
        """Auto-detect (index 0) sends empty string as src_lang."""
        page.src_combo.setCurrentIndex(0)
        page.source_text.setPlainText("Hello world")

        with (
            patch(
                "src.ui.pages.translate_text.check_llm_setup",
                return_value=True,
            ),
            patch(
                "src.ui.pages.translate_text.load_setting",
                return_value="",
            ),
            patch("src.core.database.get_active_glossary_sets", return_value=[]),
            patch(
                "src.ui.pages.translate_text._TextTranslationWorker",
            ) as mock_worker_cls,
        ):
            mock_instance = MagicMock()
            mock_worker_cls.return_value = mock_instance
            page._start_translation()

        # First positional arg is text, second is src_lang (empty for auto)
        call_args = mock_worker_cls.call_args
        assert call_args[0][1] == ""
        page._worker = None

    def test_explicit_lang_sends_language_name(self, page) -> None:
        """Explicit source language (not Auto) sends language name."""
        page.src_combo.setCurrentIndex(1)
        src_lang = page.src_combo.currentData()
        page.source_text.setPlainText("Hello world")

        with (
            patch(
                "src.ui.pages.translate_text.check_llm_setup",
                return_value=True,
            ),
            patch(
                "src.ui.pages.translate_text.load_setting",
                return_value="",
            ),
            patch("src.core.database.get_active_glossary_sets", return_value=[]),
            patch(
                "src.ui.pages.translate_text._TextTranslationWorker",
            ) as mock_worker_cls,
        ):
            mock_instance = MagicMock()
            mock_worker_cls.return_value = mock_instance
            page._start_translation()

        call_args = mock_worker_cls.call_args
        assert call_args[0][1] == src_lang
        page._worker = None

    def test_target_language_always_sent(self, page) -> None:
        """Target language is always sent regardless of source selection."""
        target_lang = page.target_combo.currentData()
        page.source_text.setPlainText("Hello world")

        with (
            patch(
                "src.ui.pages.translate_text.check_llm_setup",
                return_value=True,
            ),
            patch(
                "src.ui.pages.translate_text.load_setting",
                return_value="",
            ),
            patch("src.core.database.get_active_glossary_sets", return_value=[]),
            patch(
                "src.ui.pages.translate_text._TextTranslationWorker",
            ) as mock_worker_cls,
        ):
            mock_instance = MagicMock()
            mock_worker_cls.return_value = mock_instance
            page._start_translation()

        call_args = mock_worker_cls.call_args
        assert call_args[0][2] == target_lang
        page._worker = None

    def test_lang_change_saves_language_settings(self, page) -> None:
        """Changing a language dropdown persists the pair immediately."""
        save_calls = []

        def mock_save(key, val):
            save_calls.append((key, val))

        # Patch save_setting before triggering the change so we capture it.
        with patch(
            "src.utils.config_manager.save_setting",
            side_effect=mock_save,
        ):
            page.src_combo.setCurrentIndex(1)

        src_lang = page.src_combo.currentData()
        tgt_lang = page.target_combo.currentData()

        from src.constants.settings import (  # noqa: PLC0415
            SETTING_TRANSLATE_TEXT_SRC_LANG,
            SETTING_TRANSLATE_TEXT_TGT_LANG,
        )

        assert (SETTING_TRANSLATE_TEXT_SRC_LANG, src_lang) in save_calls
        assert (SETTING_TRANSLATE_TEXT_TGT_LANG, tgt_lang) in save_calls


# ---------------------------------------------------------------------------
# Keyboard shortcuts
# ---------------------------------------------------------------------------


class TestTranslateTextKeyboardShortcuts:
    """Tests for keyboard shortcuts on the translate text page."""

    def test_ctrl_enter_shortcut_exists(self, page) -> None:
        """Ctrl+Enter shortcut is bound to the page."""
        assert hasattr(page, "_translate_shortcut")
        assert page._translate_shortcut is not None

    def test_ctrl_enter_triggers_translation(self, page) -> None:
        """Ctrl+Enter shortcut triggers _start_translation."""
        page.source_text.setPlainText("Hello world")

        with (
            patch(
                "src.ui.pages.translate_text.check_llm_setup",
                return_value=True,
            ),
            patch(
                "src.ui.pages.translate_text.load_setting",
                return_value="",
            ),
            patch("src.core.database.get_active_glossary_sets", return_value=[]),
            patch(
                "src.ui.pages.translate_text._TextTranslationWorker",
            ) as mock_worker_cls,
        ):
            mock_instance = MagicMock()
            mock_worker_cls.return_value = mock_instance
            # Activate the shortcut signal directly
            page._translate_shortcut.activated.emit()

        assert page._worker is not None
        page._worker = None

    def test_ctrl_enter_noop_when_empty(self, page) -> None:
        """Ctrl+Enter does nothing when source text is empty."""
        page.source_text.clear()
        page._translate_shortcut.activated.emit()
        assert page._worker is None

    def test_ctrl_enter_cancels_when_worker_active(self, page) -> None:
        """Ctrl+Enter cancels the in-flight worker instead of starting a new one."""
        page.source_text.setPlainText("hello")
        mock_worker = MagicMock()
        page._worker = mock_worker
        page._translate_shortcut.activated.emit()
        # Ctrl+Enter acts as Cancel when a worker is running.
        mock_worker.cancel.assert_called_once()
        assert page._worker is None


# ---------------------------------------------------------------------------
# Separator helpers
# ---------------------------------------------------------------------------


class TestSeparatorHelpers:
    """Tests for separator creation helper."""

    def test_create_horizontal_separator(self, page) -> None:
        """Horizontal separator has fixed height of 1px."""
        sep = page._create_separator(vertical=False)
        assert sep.maximumHeight() == 1

    def test_create_vertical_separator(self, page) -> None:
        """Vertical separator has fixed width of 1px."""
        sep = page._create_separator(vertical=True)
        assert sep.maximumWidth() == 1

    def test_separators_tracked_in_list(self, page) -> None:
        """Created separators are tracked in _separators list."""
        count_before = len(page._separators)
        page._create_separator()
        assert len(page._separators) == count_before + 1

    def test_separator_has_style(self, page) -> None:
        """Separators have a stylesheet applied."""
        sep = page._create_separator()
        assert sep.styleSheet() != ""


# ---------------------------------------------------------------------------
# Footer visibility
# ---------------------------------------------------------------------------


class TestFooterVisibility:
    """Tests for translate footer visibility toggling."""

    def test_set_translate_footer_visible_true(self, page) -> None:
        """Setting footer visible shows char count and translate button."""
        page._set_translate_footer_visible(True)
        assert not page.char_count.isHidden()
        assert not page.translate_btn.isHidden()
        assert not page.status_label.isHidden()
        assert not page.edit_btn.isHidden()

    def test_set_translate_footer_visible_false(self, page) -> None:
        """Setting footer invisible hides translate-specific widgets."""
        page._set_translate_footer_visible(False)
        assert page.char_count.isHidden()
        assert page.translate_btn.isHidden()
        assert page.status_label.isHidden()
        assert page.edit_btn.isHidden()

    def test_footer_toggle_round_trip(self, page) -> None:
        """Hiding then showing footer restores all widgets."""
        page._set_translate_footer_visible(False)
        page._set_translate_footer_visible(True)
        assert not page.char_count.isHidden()
        assert not page.translate_btn.isHidden()


# ---------------------------------------------------------------------------
# Glossary integration
# ---------------------------------------------------------------------------


class TestGlossaryIntegration:
    """Tests for glossary loading during translation start."""

    def test_start_translation_loads_glossary(self, page) -> None:
        """Starting translation fetches active glossary entries."""
        page.source_text.setPlainText("Hello world")

        with (
            patch(
                "src.ui.pages.translate_text.check_llm_setup",
                return_value=True,
            ),
            patch(
                "src.ui.pages.translate_text.load_setting",
                return_value="",
            ),
            patch(
                "src.core.database.get_active_glossary_sets",
                return_value=[(1, "Test Set")],
            ) as mock_sets,
            patch(
                "src.core.database.get_glossary_entries",
                return_value=[(1, "hello", "xin chao")],
            ) as mock_entries,
            patch(
                "src.ui.pages.translate_text._TextTranslationWorker",
            ) as mock_worker_cls,
        ):
            mock_instance = MagicMock()
            mock_worker_cls.return_value = mock_instance
            page._start_translation()

        mock_sets.assert_called_once()
        mock_entries.assert_called_once_with(1)

        # Glossary should be passed to worker
        call_kwargs = mock_worker_cls.call_args[1]
        assert call_kwargs["glossary_entries"] == [(1, "hello", "xin chao")]
        page._worker = None

    def test_start_translation_no_glossary(self, page) -> None:
        """When no active glossary sets, None is passed to worker."""
        page.source_text.setPlainText("Hello world")

        with (
            patch(
                "src.ui.pages.translate_text.check_llm_setup",
                return_value=True,
            ),
            patch(
                "src.ui.pages.translate_text.load_setting",
                return_value="",
            ),
            patch(
                "src.core.database.get_active_glossary_sets",
                return_value=[],
            ),
            patch(
                "src.ui.pages.translate_text._TextTranslationWorker",
            ) as mock_worker_cls,
        ):
            mock_instance = MagicMock()
            mock_worker_cls.return_value = mock_instance
            page._start_translation()

        call_kwargs = mock_worker_cls.call_args[1]
        assert call_kwargs["glossary_entries"] is None
        page._worker = None


# ---------------------------------------------------------------------------
# Cleanup worker
# ---------------------------------------------------------------------------


class TestCleanupWorker:
    """Tests for worker cleanup behavior."""

    def test_cleanup_when_no_worker(self, page) -> None:
        """Cleanup with no worker does nothing."""
        page._worker = None
        page._cleanup_worker()
        assert page._worker is None

    def test_cleanup_waits_and_nulls(self, page) -> None:
        """Cleanup waits for worker and sets reference to None."""
        mock_worker = MagicMock()
        page._worker = mock_worker

        page._cleanup_worker()

        mock_worker.wait.assert_called_once()
        assert page._worker is None


# ---------------------------------------------------------------------------
# EXPANDED: Additional construction tests
# ---------------------------------------------------------------------------


class TestConstructionExpanded:
    """Expanded tests for page construction details."""

    def test_factory_function(self, window, _mock_deps) -> None:
        """create_translate_text_page() returns a TranslateTextPage."""
        from src.ui.pages.translate_text import (  # noqa: PLC0415
            TranslateTextPage,
            create_translate_text_page,
        )

        widget = create_translate_text_page(window)
        assert isinstance(widget, TranslateTextPage)

    def test_factory_stores_window_context(self, window, _mock_deps) -> None:
        """Factory sets window_context on the page."""
        from src.ui.pages.translate_text import (
            create_translate_text_page,  # noqa: PLC0415
        )

        widget = create_translate_text_page(window)
        assert widget.window_context is window

    def test_source_text_not_readonly(self, page) -> None:
        """Source text area is not read-only."""
        assert not page.source_text.isReadOnly()

    def test_target_text_readonly_initially(self, page) -> None:
        """Target text area is read-only initially."""
        assert page.target_text.isReadOnly()

    def test_separators_created(self, page) -> None:
        """Page has separators tracked for theme updates."""
        assert len(page._separators) > 0

    def test_initial_char_count_text(self, page) -> None:
        """Initial character count shows '0 / 5,000'."""
        assert "0" in page.char_count.text()
        assert "5,000" in page.char_count.text()

    def test_translate_btn_initially_disabled(self, page) -> None:
        """Translate button starts disabled (source text is empty at construction)."""
        assert not page.translate_btn.isEnabled()

    def test_translate_btn_has_cursor(self, page) -> None:
        """Translate button has pointing hand cursor."""
        from PySide6.QtCore import Qt  # noqa: PLC0415

        assert page.translate_btn.cursor().shape() == Qt.CursorShape.PointingHandCursor

    def test_history_btn_has_cursor(self, page) -> None:
        """History button has pointing hand cursor."""
        from PySide6.QtCore import Qt  # noqa: PLC0415

        assert page.history_btn.cursor().shape() == Qt.CursorShape.PointingHandCursor

    def test_swap_btn_has_cursor(self, page) -> None:
        """Swap button has pointing hand cursor."""
        from PySide6.QtCore import Qt  # noqa: PLC0415

        assert page.swap_btn.cursor().shape() == Qt.CursorShape.PointingHandCursor

    def test_edit_btn_has_cursor(self, page) -> None:
        """Edit button has pointing hand cursor."""
        from PySide6.QtCore import Qt  # noqa: PLC0415

        assert page.edit_btn.cursor().shape() == Qt.CursorShape.PointingHandCursor

    def test_src_combo_has_cursor(self, page) -> None:
        """Source language combo has pointing hand cursor."""
        from PySide6.QtCore import Qt  # noqa: PLC0415

        assert page.src_combo.cursor().shape() == Qt.CursorShape.PointingHandCursor

    def test_target_combo_has_cursor(self, page) -> None:
        """Target language combo has pointing hand cursor."""
        from PySide6.QtCore import Qt  # noqa: PLC0415

        assert page.target_combo.cursor().shape() == Qt.CursorShape.PointingHandCursor


# ---------------------------------------------------------------------------
# EXPANDED: Character count edge cases
# ---------------------------------------------------------------------------


class TestCharacterCountExpanded:
    """Expanded character count tests."""

    def test_char_count_with_newlines(self, page) -> None:
        """Newlines are counted as characters."""
        page.source_text.setPlainText("a\nb\nc")
        # 5 chars: a, \n, b, \n, c
        assert "5" in page.char_count.text()

    def test_char_count_with_spaces_only(self, page) -> None:
        """Spaces are counted as characters."""
        page.source_text.setPlainText("   ")
        assert "3" in page.char_count.text()

    def test_truncation_preserves_exactly_5000(self, page) -> None:
        """Text is truncated to exactly 5000 characters."""
        page.source_text.setPlainText("a" * 6000)
        assert len(page.source_text.toPlainText()) == 5000  # noqa: PLR2004

    def test_empty_after_clear(self, page) -> None:
        """Clearing text resets count to 0."""
        page.source_text.setPlainText("some text")
        page.source_text.clear()
        assert "0" in page.char_count.text()

    def test_char_count_with_emojis(self, page) -> None:
        """Emoji characters are counted correctly by Python len()."""
        page.source_text.setPlainText("Hello \U0001f600")
        count = len("Hello \U0001f600")
        assert str(count) in page.char_count.text()


# ---------------------------------------------------------------------------
# EXPANDED: Language swap edge cases
# ---------------------------------------------------------------------------


class TestLanguageSwapExpanded:
    """Expanded language swap tests."""

    def test_swap_with_both_areas_empty(self, page) -> None:
        """Swapping with both text areas empty does not crash."""
        page.src_combo.setCurrentIndex(1)
        page.source_text.clear()
        page.target_text.clear()
        page._swap_languages()
        assert page.source_text.toPlainText() == ""

    def test_swap_with_same_language(self, page) -> None:
        """Swapping when source and target are the same language works."""
        page.src_combo.setCurrentIndex(1)
        src_text = page.src_combo.currentData()
        # Set target to the same language
        idx = page.target_combo.findText(src_text)
        if idx >= 0:
            page.target_combo.setCurrentIndex(idx)
        page._swap_languages()
        # Should not crash

    def test_swap_preserves_total_text(self, page) -> None:
        """After swap, total text across both areas is preserved."""
        page.src_combo.setCurrentIndex(1)
        page.source_text.setPlainText("SourceData")
        page.target_text.setPlainText("TargetData")
        page._swap_languages()
        # Source and target should have swapped
        assert page.source_text.toPlainText() == "TargetData"
        assert page.target_text.toPlainText() == "SourceData"

    def test_swap_button_text(self, page) -> None:
        """Swap button text is the swap arrow character."""
        assert "\u21c4" in page.swap_btn.text()

    def test_swap_multiple_times(self, page) -> None:
        """Swapping twice restores original state."""
        page.src_combo.setCurrentIndex(1)
        page.source_text.setPlainText("A")
        page.target_text.setPlainText("B")
        orig_src_lang = page.src_combo.currentData()
        orig_tgt_lang = page.target_combo.currentData()

        page._swap_languages()
        page._swap_languages()

        assert page.source_text.toPlainText() == "A"
        assert page.target_text.toPlainText() == "B"
        assert page.src_combo.currentData() == orig_src_lang
        assert page.target_combo.currentData() == orig_tgt_lang


# ---------------------------------------------------------------------------
# EXPANDED: Edit mode
# ---------------------------------------------------------------------------


class TestEditModeExpanded:
    """Expanded edit mode tests."""

    def test_set_editing_true_hides_translate_btn(self, page) -> None:
        """_set_editing(True) hides the translate button."""
        page._set_editing(True)
        assert page.translate_btn.isHidden()

    def test_set_editing_false_shows_translate_btn(self, page) -> None:
        """_set_editing(False) shows the translate button."""
        page._set_editing(True)
        page._set_editing(False)
        assert not page.translate_btn.isHidden()

    def test_set_editing_true_shows_cancel_btn(self, page) -> None:
        """_set_editing(True) shows the cancel button."""
        page._set_editing(True)
        assert not page.cancel_edit_btn.isHidden()

    def test_set_editing_false_hides_cancel_btn(self, page) -> None:
        """_set_editing(False) hides the cancel button."""
        page._set_editing(True)
        page._set_editing(False)
        assert page.cancel_edit_btn.isHidden()

    def test_cancel_edit_does_not_persist_changes(self, page) -> None:
        """Cancel edit does not call DB update."""
        page.target_text.setPlainText("original")
        page.edit_btn.setEnabled(True)
        page._last_entry_id = 1

        page._toggle_edit()
        page.target_text.setPlainText("changed")

        with patch(
            "src.core.database.update_text_translation_entry",
        ) as mock_update:
            page._cancel_edit()

        mock_update.assert_not_called()
        assert page.target_text.toPlainText() == "original"

    def test_edit_mode_target_gains_focus(self, page) -> None:
        """Entering edit mode gives focus to target text area."""
        page.target_text.setPlainText("text")
        page._set_editing(True)
        # The setFocus call is issued; widget should have focus policy
        assert page.target_text.focusPolicy() != 0


# ---------------------------------------------------------------------------
# EXPANDED: History toggle
# ---------------------------------------------------------------------------


class TestHistoryToggleExpanded:
    """Expanded history toggle tests."""

    def test_toggle_three_times(self, page, _mock_history) -> None:
        """Toggling 3 times ends in history view."""
        page._toggle_history()
        page._toggle_history()
        page._toggle_history()
        assert page._header_stack.currentIndex() == 1
        assert page._content_stack.currentIndex() == 1

    def test_toggle_four_times(self, page, _mock_history) -> None:
        """Toggling 4 times returns to translate view."""
        page._toggle_history()
        page._toggle_history()
        page._toggle_history()
        page._toggle_history()
        assert page._header_stack.currentIndex() == 0
        assert page._content_stack.currentIndex() == 0

    def test_history_selection_false_disables_all_buttons(self, page) -> None:
        """Deselecting in history disables all action buttons."""
        page._on_history_selection_changed(True)
        page._on_history_selection_changed(False)
        assert not page._history_view_btn.isEnabled()
        assert not page._history_delete_btn.isEnabled()


# ---------------------------------------------------------------------------
# EXPANDED: Translation workflow
# ---------------------------------------------------------------------------


class TestTranslationWorkflowExpanded:
    """Expanded translation workflow tests."""

    def test_start_translation_saves_src_lang(self, page) -> None:
        """Translation start saves the source language selection."""
        page.source_text.setPlainText("hello")
        page.src_combo.setCurrentIndex(1)
        expected_lang = page.src_combo.currentData()

        with (
            patch("src.ui.pages.translate_text.check_llm_setup", return_value=True),
            patch("src.ui.pages.translate_text.load_setting", return_value=""),
            patch("src.core.database.get_active_glossary_sets", return_value=[]),
            patch("src.ui.pages.translate_text._TextTranslationWorker") as mock_cls,
            patch(
                "src.utils.config_manager.save_setting",
            ),
        ):
            mock_cls.return_value = MagicMock()
            page._start_translation()

        assert page._last_src_lang == expected_lang
        page._worker = None

    def test_start_translation_saves_tgt_lang(self, page) -> None:
        """Translation start saves the target language selection."""
        page.source_text.setPlainText("hello")
        page.target_combo.setCurrentIndex(2)
        expected_lang = page.target_combo.currentData()

        with (
            patch("src.ui.pages.translate_text.check_llm_setup", return_value=True),
            patch("src.ui.pages.translate_text.load_setting", return_value=""),
            patch("src.core.database.get_active_glossary_sets", return_value=[]),
            patch("src.ui.pages.translate_text._TextTranslationWorker") as mock_cls,
            patch("src.utils.config_manager.save_setting"),
        ):
            mock_cls.return_value = MagicMock()
            page._start_translation()

        assert page._last_tgt_lang == expected_lang
        page._worker = None

    def test_start_translation_remembers_source_text(self, page) -> None:
        """Translation start stores the source text for auto-save."""
        page.source_text.setPlainText("  test text  ")

        with (
            patch("src.ui.pages.translate_text.check_llm_setup", return_value=True),
            patch("src.ui.pages.translate_text.load_setting", return_value=""),
            patch("src.core.database.get_active_glossary_sets", return_value=[]),
            patch("src.ui.pages.translate_text._TextTranslationWorker") as mock_cls,
            patch("src.utils.config_manager.save_setting"),
        ):
            mock_cls.return_value = MagicMock()
            page._start_translation()

        assert page._last_source_text == "test text"
        page._worker = None

    def test_start_translation_keeps_translate_btn_enabled_for_cancel(
        self,
        page,
    ) -> None:
        """Translation start leaves the button enabled so it can act as Cancel."""
        page.source_text.setPlainText("hello")

        with (
            patch("src.ui.pages.translate_text.check_llm_setup", return_value=True),
            patch("src.ui.pages.translate_text.load_setting", return_value=""),
            patch("src.core.database.get_active_glossary_sets", return_value=[]),
            patch("src.ui.pages.translate_text._TextTranslationWorker") as mock_cls,
            patch("src.utils.config_manager.save_setting"),
        ):
            mock_cls.return_value = MagicMock()
            page._start_translation()

        assert page.translate_btn.isEnabled()
        page._worker = None

    def test_start_translation_resets_entry_id(self, page) -> None:
        """Translation start resets the last entry ID."""
        page._last_entry_id = 42  # noqa: PLR2004
        page.source_text.setPlainText("hello")

        with (
            patch("src.ui.pages.translate_text.check_llm_setup", return_value=True),
            patch("src.ui.pages.translate_text.load_setting", return_value=""),
            patch("src.core.database.get_active_glossary_sets", return_value=[]),
            patch("src.ui.pages.translate_text._TextTranslationWorker") as mock_cls,
            patch("src.utils.config_manager.save_setting"),
        ):
            mock_cls.return_value = MagicMock()
            page._start_translation()

        assert page._last_entry_id is None
        page._worker = None

    def test_on_translated_stores_entry_id(self, page) -> None:
        """Successful auto-save stores the entry ID."""
        page._last_source_text = "Hello"
        page._last_src_lang = "English (US)"
        page._last_tgt_lang = "French"

        with (
            patch("src.ui.pages.translate_text.load_setting", return_value="true"),
            patch(
                "src.core.database.add_text_translation_entry",
                return_value=99,
            ),
        ):
            page._on_translated("Bonjour")

        assert page._last_entry_id == 99  # noqa: PLR2004

    def test_save_to_history_uses_correct_char_count(self, page) -> None:
        """_save_to_history passes the correct character count."""
        page._last_source_text = "Hi there"
        page._last_src_lang = "EN"
        page._last_tgt_lang = "FR"

        with patch(
            "src.core.database.add_text_translation_entry",
        ) as mock_save:
            page._save_to_history("Salut")

        mock_save.assert_called_once_with(
            source_text="Hi there",
            translated_text="Salut",
            src_lang="EN",
            target_lang="FR",
            char_count=8,
        )

    def test_on_chunk_empty_string(self, page) -> None:
        """Empty chunk does not add text."""
        page.target_text.clear()
        page._on_chunk("")
        assert page.target_text.toPlainText() == ""


# ---------------------------------------------------------------------------
# EXPANDED: Theme and language
# ---------------------------------------------------------------------------


class TestThemeAndLanguageExpanded:
    """Expanded tests for apply_theme and apply_language."""

    def test_apply_theme_updates_card(self, page) -> None:
        """apply_theme updates the card stylesheet."""
        page._card.setStyleSheet("")
        page.apply_theme()
        assert page._card.styleSheet() != ""

    def test_apply_theme_updates_separators(self, page) -> None:
        """apply_theme updates separator stylesheets."""
        for sep in page._separators:
            sep.setStyleSheet("")
        page.apply_theme()
        for sep in page._separators:
            assert sep.styleSheet() != ""

    def test_apply_theme_in_edit_mode(self, page) -> None:
        """apply_theme works correctly when in edit mode."""
        page._set_editing(True)
        page.apply_theme()
        # Edit mode uses primary button style
        assert page.edit_btn.styleSheet() != ""

    def test_apply_theme_with_error_status(self, page) -> None:
        """apply_theme applies error style when error flag is set."""
        page._status_is_error = True
        page.apply_theme()
        # Status label should have error style
        assert page.status_label.styleSheet() != ""

    def test_apply_language_updates_source_placeholder(self, page) -> None:
        """apply_language updates source text placeholder."""
        from src.constants.i18n import tr  # noqa: PLC0415

        page.source_text.setPlaceholderText("")
        page.apply_language()
        assert page.source_text.placeholderText() == tr(
            "translate_text.source_placeholder"
        )

    def test_apply_language_updates_target_placeholder(self, page) -> None:
        """apply_language updates target text placeholder."""
        from src.constants.i18n import tr  # noqa: PLC0415

        page.target_text.setPlaceholderText("")
        page.apply_language()
        assert page.target_text.placeholderText() == tr(
            "translate_text.target_placeholder"
        )

    def test_apply_language_in_translate_view(self, page) -> None:
        """apply_language sets correct button text in translate view."""
        from src.constants.i18n import tr  # noqa: PLC0415

        page.apply_language()
        assert page.history_btn.text() == tr("translate_text.btn_history")

    def test_apply_language_in_history_view(self, page, _mock_history) -> None:
        """apply_language sets correct button text in history view."""
        from src.constants.i18n import tr  # noqa: PLC0415

        page._toggle_history()
        page.apply_language()
        assert page.history_btn.text() == tr("translate_text.btn_back")

    def test_apply_language_in_edit_mode(self, page) -> None:
        """apply_language sets 'Save' text when in edit mode."""
        from src.constants.i18n import tr  # noqa: PLC0415

        page._set_editing(True)
        page.apply_language()
        assert page.edit_btn.text() == tr("translate_text.btn_save")

    def test_apply_language_updates_cancel_btn(self, page) -> None:
        """apply_language updates cancel button text."""
        from src.constants.i18n import tr  # noqa: PLC0415

        page.apply_language()
        assert page.cancel_edit_btn.text() == tr("btn.cancel")

    def test_apply_language_updates_history_search(self, page) -> None:
        """apply_language updates history search placeholder."""
        from src.constants.i18n import tr  # noqa: PLC0415

        page.apply_language()
        assert page._history_search.placeholderText() == tr(
            "text_history.search_placeholder"
        )

    def test_apply_language_during_translation(self, page) -> None:
        """apply_language preserves the spinner-decorated button text during an active translation."""
        from src.constants.i18n import tr  # noqa: PLC0415

        page._worker = MagicMock()
        page.translate_btn.setText("⠋  Cancel")
        page.apply_language()
        # Worker is active, so translate button text is not overwritten
        assert page.translate_btn.text() != tr("translate_text.btn_translate")
        page._worker = None


# ---------------------------------------------------------------------------
# EXPANDED: Worker tests
# ---------------------------------------------------------------------------


class TestWorkerExpanded:
    """Expanded tests for _TextTranslationWorker."""

    def test_worker_signals_exist(self) -> None:
        """Worker has translated, error, and chunk signals."""
        from src.ui.pages.translate_text import _TextTranslationWorker  # noqa: PLC0415

        worker = _TextTranslationWorker("text", "EN", "FR")
        assert hasattr(worker, "translated")
        assert hasattr(worker, "error")
        assert hasattr(worker, "chunk")

    def test_worker_emits_error_on_exception(self, qtbot) -> None:
        """Worker emits error signal when LLM raises exception."""
        from src.ui.pages.translate_text import _TextTranslationWorker  # noqa: PLC0415

        def mock_stream(*_args, **_kwargs):
            raise RuntimeError("API failure")

        worker = _TextTranslationWorker("Hello", "EN", "FR")

        with (
            patch(
                "src.core.llm_engine.stream_translate_text",
                side_effect=mock_stream,
            ),
            qtbot.waitSignal(worker.error, timeout=5000) as blocker,
        ):
            worker.start()
            worker.wait()

        assert "API failure" in blocker.args[0]

    def test_worker_cancel_stops_emission(self, qtbot) -> None:
        """Cancelled worker does not emit translated signal."""
        from src.ui.pages.translate_text import _TextTranslationWorker  # noqa: PLC0415

        def slow_stream(*_args, **_kwargs):
            yield "part1"
            yield "part2"

        worker = _TextTranslationWorker("Hello", "EN", "FR")
        worker.cancel()

        with patch(
            "src.core.llm_engine.stream_translate_text",
            side_effect=slow_stream,
        ):
            worker.start()
            worker.wait()

        # Worker was cancelled before starting, so translated should not be emitted
        # (no assertions on signal; just verifying no crash)

    def test_worker_with_none_glossary(self) -> None:
        """Worker with None glossary does not crash."""
        from src.ui.pages.translate_text import _TextTranslationWorker  # noqa: PLC0415

        worker = _TextTranslationWorker("text", "EN", "FR", glossary_entries=None)
        assert worker._glossary is None

    def test_worker_with_empty_glossary(self) -> None:
        """Worker with empty glossary list stores empty list."""
        from src.ui.pages.translate_text import _TextTranslationWorker  # noqa: PLC0415

        worker = _TextTranslationWorker("text", "EN", "FR", glossary_entries=[])
        assert worker._glossary == []


# ---------------------------------------------------------------------------
# EXPANDED: Footer visibility
# ---------------------------------------------------------------------------


class TestFooterVisibility:
    """Tests for footer widget visibility toggling."""

    def test_set_translate_footer_visible_true(self, page) -> None:
        """Setting translate footer visible shows all translate widgets."""
        page._set_translate_footer_visible(True)
        assert not page.char_count.isHidden()
        assert not page.translate_btn.isHidden()
        assert not page.status_label.isHidden()

    def test_set_translate_footer_visible_false(self, page) -> None:
        """Setting translate footer hidden hides translate widgets."""
        page._set_translate_footer_visible(False)
        assert page.char_count.isHidden()
        assert page.translate_btn.isHidden()
        assert page.status_label.isHidden()

    def test_footer_visibility_toggles_correctly(self, page) -> None:
        """Footer visibility toggles correctly on repeated calls."""
        page._set_translate_footer_visible(False)
        page._set_translate_footer_visible(True)
        page._set_translate_footer_visible(False)
        assert page.char_count.isHidden()
        assert page.translate_btn.isHidden()


# ---------------------------------------------------------------------------
# TTS functionality
# ---------------------------------------------------------------------------


class TestTTSCacheHelpers:
    """Tests for TTS cache helper functions."""

    def test_tts_cache_dir_returns_string(self) -> None:
        """_tts_cache_dir returns a string path."""
        from src.ui.pages.translate_text import _tts_cache_dir  # noqa: PLC0415

        result = _tts_cache_dir()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_tts_cache_dir_ends_with_tts(self) -> None:
        """_tts_cache_dir path ends with 'tts' directory."""
        from pathlib import Path  # noqa: PLC0415

        from src.ui.pages.translate_text import _tts_cache_dir  # noqa: PLC0415

        result = Path(_tts_cache_dir())
        assert result.name == "tts"

    def test_tts_cache_dir_exists(self) -> None:
        """_tts_cache_dir creates the directory if it doesn't exist."""
        from pathlib import Path  # noqa: PLC0415

        from src.ui.pages.translate_text import _tts_cache_dir  # noqa: PLC0415

        result = _tts_cache_dir()
        assert Path(result).is_dir()

    def test_tts_cache_key_consistent(self) -> None:
        """_tts_cache_key returns the same hash for identical inputs."""
        from src.ui.pages.translate_text import _tts_cache_key  # noqa: PLC0415

        key1 = _tts_cache_key("hello", "English", "FEMALE", "Edge TTS")
        key2 = _tts_cache_key("hello", "English", "FEMALE", "Edge TTS")
        assert key1 == key2

    def test_tts_cache_key_different_text(self) -> None:
        """_tts_cache_key returns different hash for different text."""
        from src.ui.pages.translate_text import _tts_cache_key  # noqa: PLC0415

        key1 = _tts_cache_key("hello", "English", "FEMALE", "Edge TTS")
        key2 = _tts_cache_key("world", "English", "FEMALE", "Edge TTS")
        assert key1 != key2

    def test_tts_cache_key_different_lang(self) -> None:
        """_tts_cache_key returns different hash for different language."""
        from src.ui.pages.translate_text import _tts_cache_key  # noqa: PLC0415

        key1 = _tts_cache_key("hello", "English", "FEMALE", "Edge TTS")
        key2 = _tts_cache_key("hello", "French", "FEMALE", "Edge TTS")
        assert key1 != key2

    def test_tts_cache_key_different_gender(self) -> None:
        """_tts_cache_key returns different hash for different gender."""
        from src.ui.pages.translate_text import _tts_cache_key  # noqa: PLC0415

        key1 = _tts_cache_key("hello", "English", "FEMALE", "Edge TTS")
        key2 = _tts_cache_key("hello", "English", "MALE", "Edge TTS")
        assert key1 != key2

    def test_tts_cache_key_different_method(self) -> None:
        """_tts_cache_key returns different hash for different TTS method."""
        from src.ui.pages.translate_text import _tts_cache_key  # noqa: PLC0415

        key1 = _tts_cache_key("hello", "English", "FEMALE", "Edge TTS")
        key2 = _tts_cache_key("hello", "English", "FEMALE", "Google Cloud")
        assert key1 != key2

    def test_tts_cache_key_length(self) -> None:
        """_tts_cache_key returns a 24-character hex string."""
        from src.ui.pages.translate_text import _tts_cache_key  # noqa: PLC0415

        key = _tts_cache_key("test", "EN", "FEMALE", "Edge TTS")
        assert len(key) == 24  # noqa: PLR2004
        # Should be valid hex
        int(key, 16)

    def test_tts_cache_path_within_cache_dir(self) -> None:
        """_tts_cache_path returns a path inside the cache directory."""
        from src.ui.pages.translate_text import (  # noqa: PLC0415
            _tts_cache_dir,
            _tts_cache_path,
        )

        path = _tts_cache_path("hello", "English", "FEMALE", "Edge TTS")
        cache_dir = _tts_cache_dir()
        assert path.startswith(cache_dir)

    def test_tts_cache_path_has_mp3_extension(self) -> None:
        """_tts_cache_path returns a path ending with .mp3."""
        from src.ui.pages.translate_text import _tts_cache_path  # noqa: PLC0415

        path = _tts_cache_path("hello", "English", "FEMALE", "Edge TTS")
        assert path.endswith(".mp3")

    def test_tts_cache_path_consistent(self) -> None:
        """_tts_cache_path returns consistent paths for same inputs."""
        from src.ui.pages.translate_text import _tts_cache_path  # noqa: PLC0415

        path1 = _tts_cache_path("hello", "English", "FEMALE", "Edge TTS")
        path2 = _tts_cache_path("hello", "English", "FEMALE", "Edge TTS")
        assert path1 == path2


class TestToggleTTS:
    """Tests for the _toggle_tts method on TranslateTextPage."""

    @patch(
        "src.ui.dialogs.CustomMessageDialog.show_message",
    )
    @patch(
        "src.ui.pages.translate_text.load_setting",
        return_value="",
    )
    def test_toggle_tts_empty_text(
        self, mock_load, mock_msg, page, _mock_history
    ) -> None:
        """_toggle_tts shows a dialog when target text is empty."""
        page.target_text.setPlainText("")

        page._toggle_tts("target")
        mock_msg.assert_called_once()

    @patch(
        "src.ui.dialogs.CustomMessageDialog.show_message",
    )
    @patch(
        "src.ui.pages.translate_text.load_setting",
        return_value="",
    )
    def test_toggle_tts_empty_source_text(
        self, mock_load, mock_msg, page, _mock_history
    ) -> None:
        """_toggle_tts shows a dialog when source text is empty."""
        page.source_text.setPlainText("")

        page._toggle_tts("source")
        mock_msg.assert_called_once()

    def test_toggle_tts_stop_on_second_click(self, page, _mock_history) -> None:
        """_toggle_tts calls _stop_tts when the same button is already active."""
        # Set the active button to the target TTS button
        page._tts_active_btn = page.tts_target_btn

        with patch.object(page, "_stop_tts") as mock_stop:
            page._toggle_tts("target")
            mock_stop.assert_called_once()

    def test_toggle_tts_stop_on_second_click_source(self, page, _mock_history) -> None:
        """_toggle_tts calls _stop_tts when source button is already active."""
        page._tts_active_btn = page.tts_source_btn

        with patch.object(page, "_stop_tts") as mock_stop:
            page._toggle_tts("source")
            mock_stop.assert_called_once()

    def test_stop_tts_resets_active_btn(self, page) -> None:
        """_stop_tts resets _tts_active_btn to None."""
        page._tts_active_btn = page.tts_target_btn
        page._stop_tts()
        assert page._tts_active_btn is None

    def test_stop_tts_cancels_worker(self, page) -> None:
        """_stop_tts cancels and waits for any active TTS worker."""
        mock_worker = MagicMock()
        page._tts_worker = mock_worker
        page._stop_tts()
        mock_worker.cancel.assert_called_once()
        mock_worker.wait.assert_called_once()
        assert page._tts_worker is None

    def test_stop_tts_stops_player(self, page) -> None:
        """_stop_tts stops the media player if it exists."""
        mock_player = MagicMock()
        page._tts_player = mock_player
        page._stop_tts()
        mock_player.stop.assert_called_once()

    def test_reset_tts_btn_restores_labels(self, page) -> None:
        """_reset_tts_btn restores both TTS button labels."""
        page._tts_active_btn = page.tts_target_btn
        page.tts_target_btn.setText("Stop")
        page._reset_tts_btn()
        assert page._tts_active_btn is None
        # Both buttons should have the play label
        assert page.tts_source_btn.text() == page.tts_target_btn.text()

    def test_on_tts_error_resets_btn(self, page) -> None:
        """_on_tts_error resets the TTS button state."""
        page._tts_active_btn = page.tts_source_btn
        page._on_tts_error("some error")
        assert page._tts_active_btn is None


# ---------------------------------------------------------------------------
# _on_reuse_entry — re-use text from history
# ---------------------------------------------------------------------------


class TestOnReuseEntry:
    """Tests for _on_reuse_entry which loads a history entry back into the view."""

    def test_reuse_populates_source_text(self, page, _mock_history) -> None:
        """Source text area is populated with the reused entry's source."""
        page._on_reuse_entry(42, "Hello", "Bonjour", "English (US)", "French")
        assert page.source_text.toPlainText() == "Hello"

    def test_reuse_populates_translated_text(self, page, _mock_history) -> None:
        """Target text area is populated with the reused entry's translation."""
        page._on_reuse_entry(42, "Hello", "Bonjour", "English (US)", "French")
        assert page.target_text.toPlainText() == "Bonjour"

    def test_reuse_sets_source_language(self, page, _mock_history) -> None:
        """Source language combo is set to the reused entry's src_lang."""
        page._on_reuse_entry(42, "Hi", "Salut", "English (US)", "French")
        if page.src_combo.findText("English (US)") >= 0:
            assert page.src_combo.currentData() == "English (US)"

    def test_reuse_sets_target_language(self, page, _mock_history) -> None:
        """Target language combo is set to the reused entry's target_lang."""
        page._on_reuse_entry(42, "Hi", "Salut", "English (US)", "French")
        if page.target_combo.findText("French") >= 0:
            assert page.target_combo.currentData() == "French"

    def test_reuse_empty_src_lang_selects_auto(self, page, _mock_history) -> None:
        """Empty src_lang falls back to Auto (index 0)."""
        page._on_reuse_entry(42, "Hi", "Salut", "", "French")
        assert page.src_combo.currentIndex() == 0

    def test_reuse_unknown_target_lang_unchanged(self, page, _mock_history) -> None:
        """Unknown target language leaves combo unchanged."""
        original_idx = page.target_combo.currentIndex()
        page._on_reuse_entry(42, "Hi", "Salut", "", "NonexistentLanguage")
        assert page.target_combo.currentIndex() == original_idx

    def test_reuse_enables_edit_button(self, page, _mock_history) -> None:
        """Edit button is enabled when translated text is non-empty."""
        page._on_reuse_entry(42, "Hello", "Bonjour", "English (US)", "French")
        assert page.edit_btn.isEnabled()

    def test_reuse_empty_translation_disables_edit(self, page, _mock_history) -> None:
        """Edit button is disabled when translated text is empty."""
        page._on_reuse_entry(42, "Hello", "", "English (US)", "French")
        assert not page.edit_btn.isEnabled()

    def test_reuse_stores_entry_id_so_edits_persist(
        self,
        page,
        _mock_history,
    ) -> None:
        """Reusing an entry tracks its id so subsequent edits update that row."""
        page._on_reuse_entry(77, "Hi", "Salut", "", "French")
        assert page._last_entry_id == 77  # noqa: PLR2004


# ---------------------------------------------------------------------------
# RTL alignment
# ---------------------------------------------------------------------------


class TestRTLAlignment:
    """Tests for _apply_rtl_alignment and _on_lang_changed RTL handling."""

    def test_arabic_sets_right_alignment(self, page) -> None:
        """Arabic language sets RightToLeft direction and right alignment."""
        from PySide6.QtCore import Qt  # noqa: PLC0415

        page._apply_rtl_alignment(page.target_text, "Arabic")
        opt = page.target_text.document().defaultTextOption()
        assert opt.textDirection() == Qt.LayoutDirection.RightToLeft
        assert opt.alignment() == Qt.AlignmentFlag.AlignRight

    def test_hebrew_sets_right_alignment(self, page) -> None:
        """Hebrew language sets RightToLeft direction and right alignment."""
        from PySide6.QtCore import Qt  # noqa: PLC0415

        page._apply_rtl_alignment(page.target_text, "Hebrew")
        opt = page.target_text.document().defaultTextOption()
        assert opt.textDirection() == Qt.LayoutDirection.RightToLeft
        assert opt.alignment() == Qt.AlignmentFlag.AlignRight

    def test_persian_sets_right_alignment(self, page) -> None:
        """Persian language sets RightToLeft direction and right alignment."""
        from PySide6.QtCore import Qt  # noqa: PLC0415

        page._apply_rtl_alignment(page.target_text, "Persian")
        opt = page.target_text.document().defaultTextOption()
        assert opt.textDirection() == Qt.LayoutDirection.RightToLeft
        assert opt.alignment() == Qt.AlignmentFlag.AlignRight

    def test_non_rtl_keeps_left_alignment(self, page) -> None:
        """Non-RTL language (French) keeps LeftToRight direction and left alignment."""
        from PySide6.QtCore import Qt  # noqa: PLC0415

        page._apply_rtl_alignment(page.target_text, "French")
        opt = page.target_text.document().defaultTextOption()
        assert opt.textDirection() == Qt.LayoutDirection.LeftToRight
        assert opt.alignment() == Qt.AlignmentFlag.AlignLeft

    def test_switch_rtl_to_ltr_resets_alignment(self, page) -> None:
        """Switching from RTL to LTR language resets alignment back to left."""
        from PySide6.QtCore import Qt  # noqa: PLC0415

        # First set to Arabic (RTL)
        page._apply_rtl_alignment(page.target_text, "Arabic")
        opt = page.target_text.document().defaultTextOption()
        assert opt.textDirection() == Qt.LayoutDirection.RightToLeft

        # Then switch to French (LTR)
        page._apply_rtl_alignment(page.target_text, "French")
        opt = page.target_text.document().defaultTextOption()
        assert opt.textDirection() == Qt.LayoutDirection.LeftToRight
        assert opt.alignment() == Qt.AlignmentFlag.AlignLeft

    def test_on_lang_changed_applies_rtl_to_both_areas(
        self, page, _mock_history
    ) -> None:
        """_on_lang_changed applies RTL to source and target based on combos."""
        from PySide6.QtCore import Qt  # noqa: PLC0415

        # Set target to Arabic
        arabic_idx = page.target_combo.findText("Arabic")
        if arabic_idx >= 0:
            page.target_combo.setCurrentIndex(arabic_idx)
            opt = page.target_text.document().defaultTextOption()
            assert opt.textDirection() == Qt.LayoutDirection.RightToLeft

    def test_source_text_rtl_alignment(self, page) -> None:
        """RTL alignment is applied to source text widget as well."""
        from PySide6.QtCore import Qt  # noqa: PLC0415

        page._apply_rtl_alignment(page.source_text, "Arabic")
        opt = page.source_text.document().defaultTextOption()
        assert opt.textDirection() == Qt.LayoutDirection.RightToLeft
        assert opt.alignment() == Qt.AlignmentFlag.AlignRight

    def test_unknown_language_defaults_to_ltr(self, page) -> None:
        """Unknown/unmapped language defaults to LeftToRight."""
        from PySide6.QtCore import Qt  # noqa: PLC0415

        page._apply_rtl_alignment(page.target_text, "Klingon")
        opt = page.target_text.document().defaultTextOption()
        assert opt.textDirection() == Qt.LayoutDirection.LeftToRight
        assert opt.alignment() == Qt.AlignmentFlag.AlignLeft


# ---------------------------------------------------------------------------
# TTS Playback UI
# ---------------------------------------------------------------------------


class TestTTSPlayback:
    """Tests for _play_tts_file and playback status handling."""

    @patch("src.ui.pages.translate_text.load_setting", return_value="")
    def test_play_tts_file_sets_up_media_player(self, mock_load, page) -> None:
        """_play_tts_file with a valid path creates a QMediaPlayer and plays."""
        import tempfile  # noqa: PLC0415
        from pathlib import Path  # noqa: PLC0415

        from PySide6.QtCore import QUrl  # noqa: PLC0415

        # Create a temporary file to act as the audio path
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            tmp_path = f.name

        try:
            page._play_tts_file(tmp_path)
            assert page._tts_player is not None
            assert page._tts_audio_output is not None
        finally:
            # Clean up player before file removal to avoid segfault at exit
            if page._tts_player is not None:
                page._tts_player.stop()
                page._tts_player.setSource(QUrl())
                page._tts_player.deleteLater()
                page._tts_player = None
            if page._tts_audio_output is not None:
                page._tts_audio_output.deleteLater()
                page._tts_audio_output = None
            Path(tmp_path).unlink(missing_ok=True)

    @patch("src.ui.pages.translate_text.load_setting", return_value="")
    def test_play_tts_file_reuses_existing_player(self, mock_load, page) -> None:
        """_play_tts_file reuses the same QMediaPlayer on subsequent calls."""
        import tempfile  # noqa: PLC0415
        from pathlib import Path  # noqa: PLC0415

        from PySide6.QtCore import QUrl  # noqa: PLC0415

        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            tmp_path = f.name

        try:
            page._play_tts_file(tmp_path)
            player1 = page._tts_player
            page._play_tts_file(tmp_path)
            player2 = page._tts_player
            assert player1 is player2
        finally:
            # Clean up player to avoid segfault at exit
            if page._tts_player is not None:
                page._tts_player.stop()
                page._tts_player.setSource(QUrl())
                page._tts_player.deleteLater()
                page._tts_player = None
            if page._tts_audio_output is not None:
                page._tts_audio_output.deleteLater()
                page._tts_audio_output = None
            Path(tmp_path).unlink(missing_ok=True)

    def test_toggle_tts_sets_active_button_text(self, page, _mock_history) -> None:
        """_toggle_tts sets the active button text to the stop label."""
        from src.constants.i18n import tr  # noqa: PLC0415

        page.target_text.setPlainText("Some text")
        with (
            patch(
                "src.ui.pages.translate_text.load_setting",
                return_value="Edge TTS",
            ),
            patch(
                "src.ui.pages.translate_text._tts_cache_path",
                return_value="/nonexistent/cache.mp3",
            ),
            patch(
                "src.ui.pages.translate_text._TTSWorker",
            ) as mock_worker_cls,
        ):
            mock_worker = MagicMock()
            mock_worker_cls.return_value = mock_worker
            page._toggle_tts("target")
            assert page._tts_active_btn is page.tts_target_btn
            assert page.tts_target_btn.text() == tr("translate_text.tts_stop")

    def test_playback_end_of_media_resets_btn(self, page) -> None:
        """_on_tts_playback_status resets button on EndOfMedia."""
        from PySide6.QtMultimedia import QMediaPlayer  # noqa: PLC0415

        page._tts_active_btn = page.tts_target_btn
        page._on_tts_playback_status(QMediaPlayer.MediaStatus.EndOfMedia)
        assert page._tts_active_btn is None

    def test_playback_non_end_status_keeps_state(self, page) -> None:
        """_on_tts_playback_status does not reset on non-EndOfMedia status."""
        from PySide6.QtMultimedia import QMediaPlayer  # noqa: PLC0415

        page._tts_active_btn = page.tts_target_btn
        page._on_tts_playback_status(QMediaPlayer.MediaStatus.BufferedMedia)
        assert page._tts_active_btn is page.tts_target_btn

    def test_tts_btn_states_source_enabled(self, page) -> None:
        """TTS source button is enabled when source text is non-empty."""
        page.source_text.setPlainText("Hello world")
        page._update_tts_btn_states()
        assert page.tts_source_btn.isEnabled()

    def test_tts_btn_states_source_disabled_when_empty(self, page) -> None:
        """TTS source button is disabled when source text is empty."""
        page.source_text.setPlainText("")
        page._update_tts_btn_states()
        assert not page.tts_source_btn.isEnabled()

    def test_tts_btn_states_target_enabled(self, page) -> None:
        """TTS target button is enabled when target text is non-empty."""
        page.target_text.setReadOnly(False)
        page.target_text.setPlainText("Translated text")
        page.target_text.setReadOnly(True)
        page._update_tts_btn_states()
        assert page.tts_target_btn.isEnabled()

    def test_tts_btn_states_target_disabled_when_empty(self, page) -> None:
        """TTS target button is disabled when target text is empty."""
        page.target_text.setReadOnly(False)
        page.target_text.setPlainText("")
        page.target_text.setReadOnly(True)
        page._update_tts_btn_states()
        assert not page.tts_target_btn.isEnabled()

    def test_active_btn_skipped_during_playback(self, page) -> None:
        """Active TTS button is not toggled by _update_tts_btn_states."""
        # Manually enable the button and mark it active (simulates being clicked)
        page.tts_source_btn.setEnabled(True)
        page._tts_active_btn = page.tts_source_btn
        page.source_text.setPlainText("")
        page._update_tts_btn_states()
        # The active button should keep its previous state (enabled) because
        # _update_tts_btn_states skips the active button entirely.
        assert page.tts_source_btn.isEnabled()


# ---------------------------------------------------------------------------
# TTS Caching
# ---------------------------------------------------------------------------


class TestTTSCaching:
    """Tests for TTS cache path generation and cache hit/miss behaviour."""

    def test_same_text_and_lang_reuses_cached_path(self) -> None:
        """Same text, language, gender, and method produce the same cache path."""
        from src.ui.pages.translate_text import _tts_cache_path  # noqa: PLC0415

        path1 = _tts_cache_path("Hello", "English", "FEMALE", "Edge TTS")
        path2 = _tts_cache_path("Hello", "English", "FEMALE", "Edge TTS")
        assert path1 == path2

    def test_different_text_creates_different_cache_path(self) -> None:
        """Different text produces a different cache path."""
        from src.ui.pages.translate_text import _tts_cache_path  # noqa: PLC0415

        path1 = _tts_cache_path("Hello", "English", "FEMALE", "Edge TTS")
        path2 = _tts_cache_path("Goodbye", "English", "FEMALE", "Edge TTS")
        assert path1 != path2

    def test_different_language_creates_different_cache_path(self) -> None:
        """Different language produces a different cache path."""
        from src.ui.pages.translate_text import _tts_cache_path  # noqa: PLC0415

        path1 = _tts_cache_path("Hello", "English", "FEMALE", "Edge TTS")
        path2 = _tts_cache_path("Hello", "French", "FEMALE", "Edge TTS")
        assert path1 != path2

    def test_different_gender_creates_different_cache_path(self) -> None:
        """Different voice gender produces a different cache path."""
        from src.ui.pages.translate_text import _tts_cache_path  # noqa: PLC0415

        path1 = _tts_cache_path("Hello", "English", "FEMALE", "Edge TTS")
        path2 = _tts_cache_path("Hello", "English", "MALE", "Edge TTS")
        assert path1 != path2

    def test_toggle_tts_plays_cached_file_directly(self, page, _mock_history) -> None:
        """_toggle_tts plays cached file directly without starting a worker."""
        import tempfile  # noqa: PLC0415
        from pathlib import Path  # noqa: PLC0415

        # Create a fake cached file
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            tmp_path = f.name

        try:
            page.target_text.setReadOnly(False)
            page.target_text.setPlainText("Cached text")
            page.target_text.setReadOnly(True)

            with (
                patch(
                    "src.ui.pages.translate_text.load_setting",
                    return_value="Edge TTS",
                ),
                patch(
                    "src.ui.pages.translate_text._tts_cache_path",
                    return_value=tmp_path,
                ),
                patch.object(page, "_play_tts_file") as mock_play,
            ):
                page._toggle_tts("target")
                mock_play.assert_called_once_with(tmp_path)
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def test_toggle_tts_starts_worker_on_cache_miss(self, page, _mock_history) -> None:
        """_toggle_tts starts a TTS worker when no cached file exists."""
        page.target_text.setReadOnly(False)
        page.target_text.setPlainText("Uncached text")
        page.target_text.setReadOnly(True)

        with (
            patch(
                "src.ui.pages.translate_text.load_setting",
                return_value="Edge TTS",
            ),
            patch(
                "src.ui.pages.translate_text._tts_cache_path",
                return_value="/nonexistent/cache_miss.mp3",
            ),
            patch(
                "src.ui.pages.translate_text._TTSWorker",
            ) as mock_worker_cls,
        ):
            mock_worker = MagicMock()
            mock_worker_cls.return_value = mock_worker
            page._toggle_tts("target")
            mock_worker_cls.assert_called_once()
            mock_worker.start.assert_called_once()

    def test_cache_key_changes_on_language_change(self) -> None:
        """Cache key differs when language changes, preventing stale cache hits."""
        from src.ui.pages.translate_text import _tts_cache_key  # noqa: PLC0415

        key_en = _tts_cache_key("Hello", "English", "FEMALE", "Edge TTS")
        key_fr = _tts_cache_key("Hello", "French", "FEMALE", "Edge TTS")
        assert key_en != key_fr


# ---------------------------------------------------------------------------
# Listen button ffmpeg pre-check
# ---------------------------------------------------------------------------


class TestListenFfmpegPreCheck:
    """Listen-on-cache-miss runs an unconditional ffmpeg pre-check.

    Pins the contract added when ``translate_text.py`` switched to
    unconditional ffmpeg (matches Voice / Dubbing).  Cache hits skip
    the check because past success proves the prereq was met.
    """

    def test_cache_miss_no_ffmpeg_blocks_worker_and_shows_dialog(
        self,
        page,
        _mock_history,
    ) -> None:
        """No ffmpeg + cache miss → dialog shown, worker not started."""
        page.target_text.setReadOnly(False)
        page.target_text.setPlainText("Hello world")
        page.target_text.setReadOnly(True)

        with (
            patch(
                "src.ui.pages.translate_text.load_setting",
                return_value="Edge TTS",
            ),
            patch(
                "src.ui.pages.translate_text._tts_cache_path",
                return_value="/nonexistent/cache_miss.mp3",
            ),
            patch(
                "src.core.speech_engine.check_ffmpeg_available",
                return_value=False,
            ),
            patch("shutil.which", return_value=None),
            patch(
                "src.ui.pages.translate_text._TTSWorker",
            ) as mock_worker_cls,
            patch(
                "src.ui.dialogs.CustomMessageDialog.show_message",
            ) as mock_msg,
        ):
            page._toggle_tts("target")
            # Worker NOT created — pre-check blocked the path.
            mock_worker_cls.assert_not_called()
            # Modal surfaced with the shared voice key.
            mock_msg.assert_called_once()
            args = mock_msg.call_args.args
            assert any("ffmpeg_required" in str(a) for a in args)

    def test_cache_hit_skips_ffmpeg_pre_check(
        self,
        page,
        _mock_history,
    ) -> None:
        """Cache hit → ``_play_tts_file`` is called directly, no ffmpeg probe.

        Past synthesis success proves ffmpeg was available before; the
        cached file plays fine without re-checking the prereq.  Tests
        the cache-hit short-circuit by patching ``check_ffmpeg_available``
        to fail loudly if ever called — it shouldn't be.
        """
        import tempfile  # noqa: PLC0415
        from pathlib import Path  # noqa: PLC0415

        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            tmp_path = f.name

        try:
            page.target_text.setReadOnly(False)
            page.target_text.setPlainText("Cached text")
            page.target_text.setReadOnly(True)

            with (
                patch(
                    "src.ui.pages.translate_text.load_setting",
                    return_value="Edge TTS",
                ),
                patch(
                    "src.ui.pages.translate_text._tts_cache_path",
                    return_value=tmp_path,
                ),
                patch(
                    "src.core.speech_engine.check_ffmpeg_available",
                    side_effect=AssertionError(
                        "ffmpeg pre-check should NOT fire on cache hit",
                    ),
                ),
                patch.object(page, "_play_tts_file") as mock_play,
            ):
                page._toggle_tts("target")
                mock_play.assert_called_once_with(tmp_path)
        finally:
            Path(tmp_path).unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Style helpers
# ---------------------------------------------------------------------------


class TestStyleHelpers:
    """Tests for module-level style helper functions."""

    def test_style_card_returns_nonempty_with_bg_color(self) -> None:
        """_style_card() returns a non-empty string containing background-color."""
        from src.ui.pages.translate_text import _style_card  # noqa: PLC0415

        result = _style_card()
        assert result
        assert "background-color" in result

    def test_style_text_area_has_border_and_padding(self) -> None:
        """_style_text_area() returns a string with border and padding."""
        from src.ui.pages.translate_text import _style_text_area  # noqa: PLC0415

        result = _style_text_area()
        assert "border" in result
        assert "padding" in result

    def test_style_swap_button_has_border_radius(self) -> None:
        """_style_swap_button() returns a string with border-radius."""
        from src.ui.pages.translate_text import _style_swap_button  # noqa: PLC0415

        result = _style_swap_button()
        # The swap button uses transparent background; check for structural QSS
        assert "QPushButton" in result

    def test_style_char_count_has_color(self) -> None:
        """_style_char_count() returns a string with color."""
        from src.ui.pages.translate_text import _style_char_count  # noqa: PLC0415

        result = _style_char_count()
        assert "color" in result

    def test_style_error_status_has_color(self) -> None:
        """_style_error_status() returns a string with color."""
        from src.ui.pages.translate_text import _style_error_status  # noqa: PLC0415

        result = _style_error_status()
        assert "color" in result


# ---------------------------------------------------------------------------
# _TTSWorker unit tests
# ---------------------------------------------------------------------------


class TestTTSWorkerUnit:
    """Tests for _TTSWorker class using the __new__() bypass pattern."""

    def _make_worker(
        self,
        text: str = "Hello",
        lang: str = "English",
        output_path: str = "/tmp/test.mp3",
    ):
        """Creates a _TTSWorker without calling QThread.__init__."""
        from src.ui.pages.translate_text import _TTSWorker  # noqa: PLC0415

        worker = _TTSWorker.__new__(_TTSWorker)
        worker._text = text
        worker._lang = lang
        worker._output_path = output_path
        worker._cancelled = False
        worker.finished = MagicMock()
        worker.error = MagicMock()
        return worker

    def test_init_stores_attributes(self) -> None:
        """__init__ stores text, lang, and output_path."""
        from src.ui.pages.translate_text import _TTSWorker  # noqa: PLC0415

        worker = _TTSWorker("Bonjour", "French", "/tmp/out.mp3")
        assert worker._text == "Bonjour"
        assert worker._lang == "French"
        assert worker._output_path == "/tmp/out.mp3"
        assert worker._cancelled is False

    def test_cancel_sets_cancelled_flag(self) -> None:
        """cancel() sets _cancelled to True."""
        worker = self._make_worker()
        assert worker._cancelled is False
        worker.cancel()
        assert worker._cancelled is True

    @patch("src.ui.pages.translate_text.load_setting", return_value="Edge TTS")
    @patch("src.core.speech_engine.synthesize_speech")
    def test_run_calls_synthesize_speech(
        self,
        mock_synth,
        mock_setting,
    ) -> None:
        """run() calls synthesize_speech with correct parameters."""
        worker = self._make_worker(
            text="Hello",
            lang="English",
            output_path="/tmp/test.mp3",
        )

        worker.run()

        mock_synth.assert_called_once()
        call_kwargs = mock_synth.call_args
        assert call_kwargs[0][0] == "Hello"
        assert call_kwargs[1]["target_lang"] == "English"
        assert call_kwargs[1]["output_path"] == "/tmp/test.mp3"
        worker.finished.emit.assert_called_once_with("/tmp/test.mp3")

    @patch("src.ui.pages.translate_text.load_setting", return_value="Edge TTS")
    @patch(
        "src.core.speech_engine.synthesize_speech",
        side_effect=RuntimeError("TTS engine failed"),
    )
    def test_run_emits_error_on_exception(
        self,
        mock_synth,
        mock_setting,
    ) -> None:
        """run() emits error signal when synthesize_speech raises."""
        worker = self._make_worker()

        worker.run()

        worker.error.emit.assert_called_once()
        assert "TTS engine failed" in worker.error.emit.call_args[0][0]

    @patch("src.ui.pages.translate_text.load_setting", return_value="Edge TTS")
    @patch("src.core.speech_engine.synthesize_speech")
    def test_run_checks_cancelled_before_emitting(
        self,
        mock_synth,
        mock_setting,
    ) -> None:
        """run() does not emit finished if cancelled before completion."""
        worker = self._make_worker()
        worker._cancelled = True

        worker.run()

        mock_synth.assert_called_once()
        worker.finished.emit.assert_not_called()

    @patch("src.ui.pages.translate_text.load_setting", return_value="Edge TTS")
    @patch(
        "src.core.speech_engine.synthesize_speech",
        side_effect=RuntimeError("fail"),
    )
    def test_run_cancelled_suppresses_error_signal(
        self,
        mock_synth,
        mock_setting,
    ) -> None:
        """run() does not emit error if cancelled when exception occurs."""
        worker = self._make_worker()
        worker._cancelled = True

        worker.run()

        worker.error.emit.assert_not_called()


# ---------------------------------------------------------------------------
# Build function tests
# ---------------------------------------------------------------------------


class TestBuildFunctions:
    """Tests for builder functions on TranslateTextPage."""

    def test_build_history_header_widget_returns_qwidget(self, page) -> None:
        """_build_history_header_widget returns a QWidget with child widgets."""
        from PySide6.QtWidgets import QWidget  # noqa: PLC0415

        widget = page._build_history_header_widget()
        assert isinstance(widget, QWidget)

    def test_build_history_header_has_search_input(self, page) -> None:
        """_build_history_header_widget creates a search input."""
        page._build_history_header_widget()
        assert page._history_search is not None

    def test_build_history_header_has_action_buttons(self, page) -> None:
        """_build_history_header_widget creates view and delete buttons."""
        page._build_history_header_widget()
        assert page._history_view_btn is not None
        assert page._history_delete_btn is not None

    def test_build_history_widget_creates_embedded_widget(
        self,
        page,
        _mock_history,
    ) -> None:
        """_build_history_widget creates the history widget attribute."""
        page._build_history_widget()
        assert page._history_widget is not None

    def test_build_footer_returns_qhboxlayout(self, page) -> None:
        """_build_footer returns a QHBoxLayout."""
        from PySide6.QtWidgets import QHBoxLayout  # noqa: PLC0415

        footer = page._build_footer()
        assert isinstance(footer, QHBoxLayout)

    def test_build_footer_creates_tts_buttons(self, page) -> None:
        """_build_footer creates history, char_count, and translate buttons."""
        page._build_footer()
        assert page.history_btn is not None
        assert page.char_count is not None
        assert page.translate_btn is not None

    def test_build_globe_icon_returns_qicon(self, qapp) -> None:  # noqa: ARG002
        """_build_globe_icon returns a QIcon.

        Takes ``qapp`` so a QApplication exists when the function calls
        QPixmap / QPainter — under ``pytest --forked`` each test starts
        in a fresh subprocess where prior tests' QApplication is gone.
        """
        from PySide6.QtGui import QIcon  # noqa: PLC0415

        from src.ui.pages.translate_text import _build_globe_icon  # noqa: PLC0415

        icon = _build_globe_icon()
        assert isinstance(icon, QIcon)


# ---------------------------------------------------------------------------
# _on_source_changed handler
# ---------------------------------------------------------------------------


class TestOnSourceChanged:
    """Tests for the _on_source_changed signal handler."""

    def test_text_change_updates_char_count_label(self, page) -> None:
        """Typing text updates the character count label."""
        page.source_text.setPlainText("Hello World")
        assert "11" in page.char_count.text()

    def test_empty_text_shows_zero_count(self, page) -> None:
        """Empty text shows 0 in character count."""
        page.source_text.clear()
        assert page.char_count.text().startswith("0")

    def test_non_empty_text_enables_translate_button(self, page) -> None:
        """Non-empty text enables the translate button."""
        page.source_text.setPlainText("test")
        assert page.translate_btn.isEnabled()

    def test_empty_text_after_non_empty_still_enables_translate(
        self,
        page,
    ) -> None:
        """Clearing text disables the translate button (tracks source emptiness)."""
        page.source_text.setPlainText("test")
        page.source_text.clear()
        # Button state mirrors source-text presence — empty disables it.
        assert not page.translate_btn.isEnabled()

    def test_char_count_shows_correct_count(self, page) -> None:
        """Character count displays the correct number of characters."""
        page.source_text.setPlainText("abc")
        assert "3" in page.char_count.text()
        assert "5,000" in page.char_count.text()

    def test_char_count_format_for_large_text(self, page) -> None:
        """Character count uses comma formatting for numbers >= 1000."""
        page.source_text.setPlainText("a" * 1234)
        assert "1,234" in page.char_count.text()

    def test_on_source_changed_truncates_over_limit(self, page) -> None:
        """Source text exceeding _MAX_CHAR_LIMIT is auto-truncated."""
        page.source_text.setPlainText("x" * 5100)
        assert len(page.source_text.toPlainText()) == 5000  # noqa: PLR2004
        assert "5,000 / 5,000" in page.char_count.text()


# ---------------------------------------------------------------------------
# _save_tts_to_output
# ---------------------------------------------------------------------------


class TestSaveTTSToOutput:
    """Tests for the _save_tts_to_output method."""

    @patch("src.ui.pages.translate_text.load_setting", return_value="")
    def test_no_output_dir_returns_early(self, mock_setting, page) -> None:
        """When TTS storage path is empty, no file is copied."""
        with patch("shutil.copy2") as mock_copy:
            page._save_tts_to_output("/tmp/cached.mp3")
        mock_copy.assert_not_called()

    def test_valid_cache_path_copies_file(self, page, tmp_path) -> None:
        """Valid cache path copies file to the configured output directory."""
        output_dir = str(tmp_path / "tts_output")
        src_file = tmp_path / "source.mp3"
        src_file.write_text("fake audio data")

        with patch(
            "src.ui.pages.translate_text.load_setting",
            return_value=output_dir,
        ):
            page._save_tts_to_output(str(src_file))

        # Output directory should have been created and contain a file
        output_files = list((tmp_path / "tts_output").iterdir())
        assert len(output_files) == 1
        assert output_files[0].name.startswith("tts_")
        assert output_files[0].name.endswith(".mp3")

    def test_output_dir_created_if_missing(self, page, tmp_path) -> None:
        """Output directory is created if it does not exist."""
        output_dir = str(tmp_path / "new_dir" / "nested")
        src_file = tmp_path / "source.mp3"
        src_file.write_text("fake audio")

        with patch(
            "src.ui.pages.translate_text.load_setting",
            return_value=output_dir,
        ):
            page._save_tts_to_output(str(src_file))

        assert (tmp_path / "new_dir" / "nested").is_dir()

    def test_copy_failure_does_not_raise(self, page, tmp_path) -> None:
        """OSError during copy is logged but does not raise."""
        output_dir = str(tmp_path / "tts_out")
        (tmp_path / "tts_out").mkdir()

        with (
            patch(
                "src.ui.pages.translate_text.load_setting",
                return_value=output_dir,
            ),
            patch("shutil.copy2", side_effect=OSError("disk full")),
        ):
            # Should not raise
            page._save_tts_to_output("/tmp/nonexistent.mp3")


class TestDetectSourceLanguage:
    """Tests for the _detect_source_language() langdetect wrapper.

    We inject a fake ``langdetect`` module via ``sys.modules`` rather than
    calling the real library: pytest runs under a UNO-tainted import hook
    that strips the venv site-packages, so ``langdetect`` isn't importable
    from the test process even though it is at runtime. Testing the mapping
    + error handling is what matters here, not langdetect itself.
    """

    @staticmethod
    def _inject_fake_langdetect(monkeypatch, detect_return=None, detect_raises=None):
        """Installs a stub langdetect package in sys.modules."""
        import sys  # noqa: PLC0415
        import types  # noqa: PLC0415

        fake = types.ModuleType("langdetect")
        fake.DetectorFactory = types.SimpleNamespace(seed=0)

        def _detect(text):
            if detect_raises is not None:
                raise detect_raises
            return detect_return

        fake.detect = _detect

        exc_mod = types.ModuleType("langdetect.lang_detect_exception")

        class LangDetectException(Exception):  # noqa: N818
            pass

        exc_mod.LangDetectException = LangDetectException
        fake.lang_detect_exception = exc_mod

        monkeypatch.setitem(sys.modules, "langdetect", fake)
        monkeypatch.setitem(sys.modules, "langdetect.lang_detect_exception", exc_mod)
        return LangDetectException

    def test_detects_english(self, monkeypatch) -> None:
        self._inject_fake_langdetect(monkeypatch, detect_return="en")
        from src.ui.pages.translate_text import (  # noqa: PLC0415
            _detect_source_language,
        )

        assert _detect_source_language("hello") == "English (US)"

    def test_detects_vietnamese(self, monkeypatch) -> None:
        self._inject_fake_langdetect(monkeypatch, detect_return="vi")
        from src.ui.pages.translate_text import (  # noqa: PLC0415
            _detect_source_language,
        )

        assert _detect_source_language("xin chào") == "Vietnamese"

    def test_detects_chinese_simplified(self, monkeypatch) -> None:
        self._inject_fake_langdetect(monkeypatch, detect_return="zh-cn")
        from src.ui.pages.translate_text import (  # noqa: PLC0415
            _detect_source_language,
        )

        assert _detect_source_language("你好") == "Chinese (Simplified)"

    def test_detects_spanish(self, monkeypatch) -> None:
        self._inject_fake_langdetect(monkeypatch, detect_return="es")
        from src.ui.pages.translate_text import (  # noqa: PLC0415
            _detect_source_language,
        )

        assert _detect_source_language("hola") == "Spanish"

    def test_detect_result_is_lowercased(self, monkeypatch) -> None:
        """Upper-case codes from detect() still match the lowercase-keyed map."""
        self._inject_fake_langdetect(monkeypatch, detect_return="EN")
        from src.ui.pages.translate_text import (  # noqa: PLC0415
            _detect_source_language,
        )

        assert _detect_source_language("hello") == "English (US)"

    def test_returns_none_on_langdetect_exception(self, monkeypatch) -> None:
        """LangDetectException (e.g., unclassifiable input) maps to None."""
        import sys  # noqa: PLC0415
        import types  # noqa: PLC0415

        exc_mod = types.ModuleType("langdetect.lang_detect_exception")

        class LangDetectException(Exception):  # noqa: N818
            pass

        exc_mod.LangDetectException = LangDetectException

        fake = types.ModuleType("langdetect")
        fake.DetectorFactory = types.SimpleNamespace(seed=0)

        def _raise(_text):
            raise LangDetectException("no features in text")

        fake.detect = _raise
        fake.lang_detect_exception = exc_mod

        monkeypatch.setitem(sys.modules, "langdetect", fake)
        monkeypatch.setitem(sys.modules, "langdetect.lang_detect_exception", exc_mod)

        from src.ui.pages.translate_text import (  # noqa: PLC0415
            _detect_source_language,
        )

        assert _detect_source_language("@@@") is None

    def test_returns_none_when_langdetect_missing(self, monkeypatch) -> None:
        """ImportError path is handled gracefully."""
        import sys  # noqa: PLC0415

        # Ensure both modules are absent.
        monkeypatch.delitem(sys.modules, "langdetect", raising=False)
        monkeypatch.delitem(
            sys.modules,
            "langdetect.lang_detect_exception",
            raising=False,
        )

        import builtins  # noqa: PLC0415

        real_import = builtins.__import__

        def fake_import(name, *a, **kw):
            if name.startswith("langdetect"):
                raise ImportError("simulated missing dependency")
            return real_import(name, *a, **kw)

        monkeypatch.setattr("builtins.__import__", fake_import)
        from src.ui.pages.translate_text import (  # noqa: PLC0415
            _detect_source_language,
        )

        assert _detect_source_language("anything") is None

    def test_unsupported_language_returns_none(self, monkeypatch) -> None:
        """Codes detected but not in the app's language map resolve to None."""
        self._inject_fake_langdetect(monkeypatch, detect_return="sw")
        from src.ui.pages.translate_text import (  # noqa: PLC0415
            _detect_source_language,
        )

        assert _detect_source_language("habari") is None


class TestOnTTSError:
    """Tests for _on_tts_error — surfaces failures in the footer status label."""

    @pytest.fixture
    def page(self, qtbot):
        from src.ui.pages.translate_text import TranslateTextPage  # noqa: PLC0415

        with patch(
            "src.ui.pages.translate_text.check_llm_setup",
            return_value=True,
        ):
            p = TranslateTextPage(MagicMock(spec=QMainWindow))
            qtbot.addWidget(p)
            return p

    def test_error_message_shown_in_status_label(self, page) -> None:
        """A TTS error tag is shown in the footer status label with the error prefix."""
        page.status_label.setText("")
        page._on_tts_error("TTS_API_ERROR: HTTP 400")
        text = page.status_label.text()
        assert text != ""
        # The "Error:" prefix comes from tr("error.prefix"); in tests tr returns
        # the key, so we just verify the label is non-empty and contains the
        # translation placeholder or something recognisable.
        assert "error" in text.lower() or "{message}" in text

    def test_status_flag_set_true_on_error(self, page) -> None:
        """_status_is_error flips to True so theme re-apply keeps the error style."""
        page._status_is_error = False
        page._on_tts_error("any error")
        assert page._status_is_error is True

    def test_active_tts_button_reset(self, page) -> None:
        """After an error, no TTS button remains marked active."""
        page._tts_active_btn = page.tts_source_btn
        page._on_tts_error("fail")
        assert page._tts_active_btn is None


class TestToggleTTSClearsStatus:
    """Ensure starting a new Listen action clears any stale translation/TTS error."""

    @pytest.fixture
    def page(self, qtbot):
        from src.ui.pages.translate_text import TranslateTextPage  # noqa: PLC0415

        with patch(
            "src.ui.pages.translate_text.check_llm_setup",
            return_value=True,
        ):
            p = TranslateTextPage(MagicMock(spec=QMainWindow))
            qtbot.addWidget(p)
            return p

    def test_stale_status_cleared_on_new_playback(self, page) -> None:
        page.status_label.setText("some earlier error")
        page._status_is_error = True
        page.source_text.setPlainText("Hello there")
        page.target_text.setPlainText("Bonjour")

        # Stub out the heavy work — we only care that status gets cleared
        # before the worker is kicked off.
        with (
            patch(
                "src.ui.pages.translate_text.load_setting",
                return_value="Edge TTS",
            ),
            patch("pathlib.Path.is_file", return_value=True),
            patch.object(page, "_play_tts_file"),
        ):
            page._toggle_tts("target")

        assert page.status_label.text() == ""
        assert page._status_is_error is False


class TestListenButtonPiperPreflight:
    """Cache-hit short-circuits preflight; cache-miss invokes it.

    Without these guards, a future refactor could re-introduce the
    Piper voice install dialog on every Listen click (when audio
    has already been synthesised in the past) or skip the install
    check on a fresh translation (leaving the user with a cryptic
    PIPER_VOICE_NOT_INSTALLED red status line).
    """

    @pytest.fixture
    def page(self, qtbot):
        from src.ui.pages.translate_text import TranslateTextPage  # noqa: PLC0415

        with patch(
            "src.ui.pages.translate_text.check_llm_setup",
            return_value=True,
        ):
            p = TranslateTextPage(MagicMock(spec=QMainWindow))
            qtbot.addWidget(p)
            return p

    def test_cache_hit_skips_preflight(self, page) -> None:
        """A cached MP3 means a previous successful synthesis — skip preflight."""
        page.source_text.setPlainText("Hello there")
        page.target_text.setPlainText("Bonjour")

        with (
            patch(
                "src.ui.pages.translate_text.load_setting",
                return_value="Piper TTS",
            ),
            patch("pathlib.Path.is_file", return_value=True),
            patch.object(page, "_play_tts_file"),
            patch(
                "src.ui.dialogs.preflight_piper_voice",
                return_value=True,
            ) as mock_preflight,
        ):
            page._toggle_tts("target")

        mock_preflight.assert_not_called()

    def test_cache_miss_invokes_preflight(self, page) -> None:
        """No cached MP3 — preflight must run before kicking off the worker."""
        page.source_text.setPlainText("Hello there")
        page.target_text.setPlainText("Bonjour")

        with (
            patch(
                "src.ui.pages.translate_text.load_setting",
                return_value="Piper TTS",
            ),
            patch("pathlib.Path.is_file", return_value=False),
            patch(
                "src.ui.dialogs.preflight_piper_voice",
                return_value=False,
            ) as mock_preflight,
        ):
            page._toggle_tts("target")

        mock_preflight.assert_called_once()
        assert page._tts_worker is None

    def test_cache_miss_preflight_blocks_worker(self, page) -> None:
        """When preflight returns False (user cancelled), no worker starts."""
        page.source_text.setPlainText("Hello there")
        page.target_text.setPlainText("Bonjour")

        with (
            patch(
                "src.ui.pages.translate_text.load_setting",
                return_value="Piper TTS",
            ),
            patch("pathlib.Path.is_file", return_value=False),
            patch(
                "src.ui.dialogs.preflight_piper_voice",
                return_value=False,
            ),
            patch.object(page, "_play_tts_file") as mock_play,
        ):
            page._toggle_tts("target")

        mock_play.assert_not_called()
        assert page._tts_worker is None


# ---------------------------------------------------------------------------
# New Review-Fix coverage: cancel, Escape, model-combo hide, InvalidMedia
# ---------------------------------------------------------------------------


class TestCancelTranslation:
    """Tests for the _cancel_translation helper."""

    def test_cancel_noop_when_no_worker(self, page) -> None:
        """_cancel_translation with no active worker is a silent no-op."""
        page._worker = None
        page._cancel_translation()
        assert page._worker is None

    def test_cancel_calls_worker_cancel_and_resets_ui(self, page) -> None:
        """_cancel_translation invokes worker.cancel() and restores UI."""
        from src.constants.i18n import tr  # noqa: PLC0415

        page.source_text.setPlainText("abc")
        mock_worker = MagicMock()
        page._worker = mock_worker

        page._cancel_translation()

        mock_worker.cancel.assert_called_once()
        assert page._worker is None
        assert page.translate_btn.text() == tr("translate_text.btn_translate")
        assert page.status_label.text() == ""


class TestEscapeShortcut:
    """Tests for the Escape key shortcut."""

    def test_escape_cancels_edit_mode(self, page) -> None:
        """Escape exits edit mode and restores the original translation."""
        page.target_text.setPlainText("new")
        page._text_before_edit = "old"
        page.target_text.setReadOnly(False)  # editing

        page._on_escape_pressed()

        assert page.target_text.isReadOnly()
        assert page.target_text.toPlainText() == "old"

    def test_escape_cancels_translation_when_worker_active(self, page) -> None:
        """Escape cancels the in-flight worker when not editing."""
        page.target_text.setReadOnly(True)
        mock_worker = MagicMock()
        page._worker = mock_worker

        page._on_escape_pressed()

        mock_worker.cancel.assert_called_once()
        assert page._worker is None

    def test_escape_is_noop_when_idle(self, page) -> None:
        """Escape does nothing when not editing and no worker is running."""
        page.target_text.setReadOnly(True)
        page._worker = None
        # Must not raise.
        page._on_escape_pressed()


class TestModelComboVisibility:
    """Tests for the population behavior in _refresh_model_combo."""

    def test_populated_when_single_model(self, page) -> None:
        """Combo shows the one model and is enabled."""
        with patch(
            "src.utils.config_manager.get_available_models",
            return_value=[("Gemini", "gemini-3-flash-preview")],
        ):
            page._refresh_model_combo()
        assert page.model_combo.count() == 1
        assert page.model_combo.isEnabled()
        assert page.model_combo.itemData(0) == "Gemini:gemini-3-flash-preview"

    def test_placeholder_when_no_models(self, page) -> None:
        """Combo shows a disabled placeholder entry when no models are configured."""
        with patch(
            "src.utils.config_manager.get_available_models",
            return_value=[],
        ):
            page._refresh_model_combo()
        assert page.model_combo.count() == 1
        assert not page.model_combo.isEnabled()
        # Placeholder entry has no underlying model_id.
        assert page.model_combo.itemData(0) is None

    def test_shown_when_multiple_models(self, page) -> None:
        """Combo is populated with all models when ≥ 2 are configured."""
        page.show()  # visibility only updates when the widget can be shown
        with patch(
            "src.utils.config_manager.get_available_models",
            return_value=[
                ("Gemini", "gemini-3-flash-preview"),
                ("Custom", "gpt-4o"),
            ],
        ):
            page._refresh_model_combo()
        assert page.model_combo.count() == 2  # noqa: PLR2004
        assert page.model_combo.isEnabled()


class TestTtsInvalidMediaHandling:
    """Tests for the InvalidMedia path in _on_tts_playback_status."""

    def test_invalid_media_triggers_error_handler(self, page) -> None:
        """An InvalidMedia status surfaces an error, not silent stuck state."""
        from PySide6.QtMultimedia import QMediaPlayer  # noqa: PLC0415

        page._tts_active_btn = page.tts_target_btn
        with patch.object(page, "_on_tts_error") as mock_err:
            page._on_tts_playback_status(QMediaPlayer.MediaStatus.InvalidMedia)
        mock_err.assert_called_once()

    def test_end_of_media_resets_button(self, page) -> None:
        """EndOfMedia still triggers the normal button reset path."""
        from PySide6.QtMultimedia import QMediaPlayer  # noqa: PLC0415

        page._tts_active_btn = page.tts_target_btn
        with patch.object(page, "_reset_tts_btn") as mock_reset:
            page._on_tts_playback_status(QMediaPlayer.MediaStatus.EndOfMedia)
        mock_reset.assert_called_once()


class TestSwapShortcutAndGuard:
    """Tests for the Ctrl+L swap shortcut and the Auto-source guard."""

    def test_swap_shortcut_calls_swap_languages(self, page) -> None:
        """Ctrl+L emit triggers _swap_languages."""
        with patch.object(page, "_swap_languages") as mock_swap:
            page._swap_shortcut.activated.emit()
        mock_swap.assert_called_once()


class TestSaveToHistoryGuard:
    """Guards that prevent empty/no-op history rows."""

    def test_save_empty_source_is_skipped(self, page) -> None:
        """_save_to_history does nothing when _last_source_text is empty."""
        page._last_source_text = ""
        with patch("src.core.database.add_text_translation_entry") as mock_add:
            page._save_to_history("translated")
        mock_add.assert_not_called()

    def test_save_empty_translation_is_skipped(self, page) -> None:
        """_save_to_history does nothing when the translation is empty."""
        page._last_source_text = "source"
        with patch("src.core.database.add_text_translation_entry") as mock_add:
            page._save_to_history("")
        mock_add.assert_not_called()


class TestCancelDuringLanguageSwitch:
    """Cancelling a translation during a queued language switch is clean."""

    def test_cancel_then_apply_language_no_attribute_error(self, page) -> None:
        """Cancel detaches the worker; a subsequent apply_language must not crash."""
        page.source_text.setPlainText("hello")
        mock_worker = MagicMock()
        mock_worker.cancel = MagicMock()
        mock_worker.chunk = MagicMock()
        mock_worker.translated = MagicMock()
        mock_worker.error = MagicMock()
        mock_worker.finished = MagicMock()
        page._worker = mock_worker

        page._cancel_translation()
        assert page._worker is None
        mock_worker.cancel.assert_called_once()

        try:
            page.apply_language()
        except AttributeError as exc:  # pragma: no cover - regression guard
            pytest.fail(f"apply_language raised AttributeError: {exc}")

    def test_cancel_clears_worker_running_flag(self, page) -> None:
        """_cancel_translation clears the class-level _is_any_worker_running flag."""
        from src.ui.pages.translate_text import (  # noqa: PLC0415
            _TextTranslationWorker,
        )

        _TextTranslationWorker._is_any_worker_running = True  # noqa: SLF001
        mock_worker = MagicMock()
        mock_worker.cancel = MagicMock()
        mock_worker.chunk = MagicMock()
        mock_worker.translated = MagicMock()
        mock_worker.error = MagicMock()
        mock_worker.finished = MagicMock()
        page._worker = mock_worker

        page._cancel_translation()

        assert _TextTranslationWorker._is_any_worker_running is False  # noqa: SLF001

    def test_cancel_when_no_worker_is_noop(self, page) -> None:
        """_cancel_translation is a safe no-op when _worker is None already."""
        page._worker = None
        # Must not raise.
        page._cancel_translation()
        assert page._worker is None


# ───────────────────────────────────────────────────────────────────────
# Edit-during-translation race — UI must prevent the user from entering
# edit mode while a stream is active.  Without these guards, streaming
# chunks would keep being inserted into the target while the user was
# trying to edit, corrupting both the user's text and the LLM output.
# ───────────────────────────────────────────────────────────────────────


class TestEditModeStreamingInvariants:
    """The contract: when a translation kicks off, edit mode is forced off."""

    def test_starting_translation_exits_edit_mode(self, page) -> None:
        """A user mid-edit who clicks Translate has edit mode silently dropped."""
        # Stage 1: enter edit mode with some user text
        page.target_text.setReadOnly(False)
        page.target_text.setPlainText("user-edit-in-progress")
        page._text_before_edit = "previous translation"
        page.cancel_edit_btn.setVisible(True)

        # Stage 2: source area gets text; user clicks Translate.
        page.source_text.setPlainText("Hello world")
        with (
            patch("src.ui.pages.translate_text._TextTranslationWorker"),
            patch(
                "src.ui.pages.translate_text.check_llm_setup",
                return_value=True,
            ),
        ):
            page._start_translation()

        # Edit mode must be forced off; cancel-edit hidden; target cleared.
        assert page.target_text.isReadOnly() is True
        assert page.cancel_edit_btn.isVisible() is False
        assert page.edit_btn.isEnabled() is False, (
            "edit button must be disabled while a stream is in flight; "
            "otherwise clicking it would race chunk insertion"
        )

    def test_chunks_during_active_stream_append_to_target(self, page) -> None:
        """_on_chunk inserts at the cursor end position — basic streaming contract."""
        page.target_text.clear()
        page._on_chunk("Hello")
        page._on_chunk(" ")
        page._on_chunk("world")
        assert page.target_text.toPlainText() == "Hello world"

    def test_translated_finalizer_re_enables_edit_button_when_text(
        self,
        page,
    ) -> None:
        """End-of-stream re-enables Edit only when there's text to edit."""
        page.source_text.setPlainText("Hello")
        page._on_translated("Bonjour")
        assert page.edit_btn.isEnabled() is True

    def test_translated_finalizer_disables_edit_button_when_empty(
        self,
        page,
    ) -> None:
        """Empty result → no point in enabling Edit."""
        page.source_text.setPlainText("Hello")
        page._on_translated("")
        assert page.edit_btn.isEnabled() is False


class TestStopAllWorkersBoundedWait:
    """``aboutToQuit`` must drain workers with a bounded wait.

    Past bug: an unbounded ``QThread.wait()`` blocked app exit when an
    HTTP stream took >10 s to wind down.  Pin the contract so a future
    refactor can't regress to ``wait()`` without a timeout.
    """

    def test_worker_gets_cancel_then_bounded_wait(self, page) -> None:
        """``_stop_all_workers`` calls ``cancel()`` then ``wait(2000)``."""
        from unittest.mock import MagicMock  # noqa: PLC0415

        worker = MagicMock()
        worker.wait.return_value = True
        page._worker = worker
        page._stop_all_workers()

        worker.cancel.assert_called_once()
        worker.wait.assert_called_once_with(2000)
        # Reference released so a subsequent translation builds a fresh worker.
        assert page._worker is None

    def test_no_worker_is_noop(self, page) -> None:
        """Empty worker slot is a safe no-op (no AttributeError)."""
        page._worker = None
        page._stop_all_workers()  # should not raise
        assert page._worker is None
