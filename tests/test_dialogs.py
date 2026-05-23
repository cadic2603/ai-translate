"""Unit tests for src/ui/dialogs.py.

Covers:
- BaseDialog — construction, keyPressEvent, on_confirm
- CustomInputDialog — construction, set_error/clear_error, input field, buttons
- CustomConfirmDialog — construction, danger mode, button text
- CustomMessageDialog — construction, OK button
- LanguageSelectionDialog — construction, combo boxes, language population
- SourceLanguageDialog — construction, optional target combo
- VoiceSetupDialog — construction, language and gender combos
- require_setup() — prerequisite check helper
"""

from unittest.mock import MagicMock, patch

from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QLabel,
    QLineEdit,
    QPushButton,
    QWidget,
)

# ---------------------------------------------------------------------------
# BaseDialog tests
# ---------------------------------------------------------------------------


class TestBaseDialog:
    """Tests for the BaseDialog base class."""

    def test_construction_with_title(self, qapp: QApplication) -> None:
        """BaseDialog with a title adds a header label."""
        from src.ui.dialogs import BaseDialog  # noqa: PLC0415

        dlg = BaseDialog(title="Test Title")
        assert dlg.windowTitle() == "Test Title"

    def test_construction_without_title(self, qapp: QApplication) -> None:
        """BaseDialog without a title skips the header label."""
        from src.ui.dialogs import BaseDialog  # noqa: PLC0415

        dlg = BaseDialog()
        assert dlg.windowTitle() == ""

    def test_minimum_width(self, qapp: QApplication) -> None:
        """BaseDialog has minimum width of 450."""
        from src.ui.dialogs import BaseDialog  # noqa: PLC0415

        dlg = BaseDialog()
        assert dlg.minimumWidth() == 450  # noqa: PLR2004

    def test_stylesheet_applied(self, qapp: QApplication) -> None:
        """BaseDialog has a non-empty stylesheet."""
        from src.ui.dialogs import BaseDialog  # noqa: PLC0415

        dlg = BaseDialog()
        assert dlg.styleSheet()

    def test_layout_is_vbox(self, qapp: QApplication) -> None:
        """BaseDialog uses a QVBoxLayout."""
        from PySide6.QtWidgets import QVBoxLayout  # noqa: PLC0415

        from src.ui.dialogs import BaseDialog  # noqa: PLC0415

        dlg = BaseDialog()
        assert isinstance(dlg.layout, QVBoxLayout)

    def test_on_confirm_accepts(self, qapp: QApplication) -> None:
        """Default on_confirm calls accept()."""
        from src.ui.dialogs import BaseDialog  # noqa: PLC0415

        dlg = BaseDialog()
        dlg.accept = MagicMock()
        dlg.on_confirm()
        dlg.accept.assert_called_once()

    def test_header_centered(self, qapp: QApplication) -> None:
        """Title header label is center-aligned."""
        from src.ui.dialogs import BaseDialog  # noqa: PLC0415

        dlg = BaseDialog(title="Centered")
        # Find the header label
        labels = dlg.findChildren(QLabel)
        header = None
        for lbl in labels:
            if lbl.text() == "Centered":
                header = lbl
                break
        assert header is not None
        assert header.alignment() & Qt.AlignmentFlag.AlignCenter


# ---------------------------------------------------------------------------
# CustomInputDialog tests
# ---------------------------------------------------------------------------


class TestCustomInputDialog:
    """Tests for the CustomInputDialog class."""

    def test_construction(self, qapp: QApplication) -> None:
        """CustomInputDialog constructs with expected widgets."""
        from src.ui.dialogs import CustomInputDialog  # noqa: PLC0415

        dlg = CustomInputDialog(title="Input", label_text="Enter name:")
        assert dlg.windowTitle() == "Input"
        assert isinstance(dlg.input, QLineEdit)
        assert isinstance(dlg.ok_btn, QPushButton)
        assert isinstance(dlg.cancel_btn, QPushButton)

    def test_placeholder(self, qapp: QApplication) -> None:
        """Placeholder text is set on the input field."""
        from src.ui.dialogs import CustomInputDialog  # noqa: PLC0415

        dlg = CustomInputDialog(placeholder="Type here...")
        assert dlg.input.placeholderText() == "Type here..."

    def test_input_fixed_height(self, qapp: QApplication) -> None:
        """Input field has a fixed height matching HEIGHT_CONTROL."""
        from src.constants import HEIGHT_CONTROL  # noqa: PLC0415
        from src.ui.dialogs import CustomInputDialog  # noqa: PLC0415

        dlg = CustomInputDialog()
        assert dlg.input.height() == HEIGHT_CONTROL

    def test_set_error_shows_message(self, qapp: QApplication) -> None:
        """set_error makes the error frame visible with the message."""
        from src.ui.dialogs import CustomInputDialog  # noqa: PLC0415

        dlg = CustomInputDialog()
        dlg.set_error("Something went wrong")
        assert not dlg.error_frame.isHidden()
        assert dlg.error_label.text() == "Something went wrong"

    def test_set_error_empty_hides(self, qapp: QApplication) -> None:
        """set_error with empty string hides the error frame."""
        from src.ui.dialogs import CustomInputDialog  # noqa: PLC0415

        dlg = CustomInputDialog()
        dlg.set_error("Error!")
        dlg.set_error("")
        assert dlg.error_frame.isHidden()

    def test_clear_error(self, qapp: QApplication) -> None:
        """clear_error hides the error frame and clears text."""
        from src.ui.dialogs import CustomInputDialog  # noqa: PLC0415

        dlg = CustomInputDialog()
        dlg.set_error("Oops")
        dlg.clear_error()
        assert dlg.error_frame.isHidden()
        assert dlg.error_label.text() == ""

    def test_error_hidden_initially(self, qapp: QApplication) -> None:
        """Error frame is hidden on construction."""
        from src.ui.dialogs import CustomInputDialog  # noqa: PLC0415

        dlg = CustomInputDialog()
        assert dlg.error_frame.isHidden()

    def test_ok_btn_cursor(self, qapp: QApplication) -> None:
        """OK button has PointingHandCursor."""
        from src.ui.dialogs import CustomInputDialog  # noqa: PLC0415

        dlg = CustomInputDialog()
        assert dlg.ok_btn.cursor().shape() == Qt.CursorShape.PointingHandCursor

    def test_cancel_btn_cursor(self, qapp: QApplication) -> None:
        """Cancel button has PointingHandCursor."""
        from src.ui.dialogs import CustomInputDialog  # noqa: PLC0415

        dlg = CustomInputDialog()
        assert dlg.cancel_btn.cursor().shape() == Qt.CursorShape.PointingHandCursor

    def test_ok_btn_not_autodefault(self, qapp: QApplication) -> None:
        """OK button is not set as autoDefault."""
        from src.ui.dialogs import CustomInputDialog  # noqa: PLC0415

        dlg = CustomInputDialog()
        assert not dlg.ok_btn.autoDefault()

    def test_cancel_btn_not_autodefault(self, qapp: QApplication) -> None:
        """Cancel button is not set as autoDefault."""
        from src.ui.dialogs import CustomInputDialog  # noqa: PLC0415

        dlg = CustomInputDialog()
        assert not dlg.cancel_btn.autoDefault()

    def test_label_text(self, qapp: QApplication) -> None:
        """Input label text matches the provided label_text."""
        from src.ui.dialogs import CustomInputDialog  # noqa: PLC0415

        dlg = CustomInputDialog(label_text="Your Name:")
        assert dlg.label.text() == "Your Name:"

    def test_input_min_width(self, qapp: QApplication) -> None:
        """Input field has minimum width of 400."""
        from src.ui.dialogs import CustomInputDialog  # noqa: PLC0415

        dlg = CustomInputDialog()
        assert dlg.input.minimumWidth() == 400  # noqa: PLR2004

    def test_text_changed_clears_error(self, qapp: QApplication) -> None:
        """Typing in the input field clears any error."""
        from src.ui.dialogs import CustomInputDialog  # noqa: PLC0415

        dlg = CustomInputDialog()
        dlg.set_error("Error!")
        assert not dlg.error_frame.isHidden()
        # Simulate text change
        dlg.input.setText("something")
        assert dlg.error_frame.isHidden()


# ---------------------------------------------------------------------------
# CustomConfirmDialog tests
# ---------------------------------------------------------------------------


class TestCustomConfirmDialog:
    """Tests for the CustomConfirmDialog class."""

    def test_construction(self, qapp: QApplication) -> None:
        """CustomConfirmDialog constructs with message and buttons."""
        from src.ui.dialogs import CustomConfirmDialog  # noqa: PLC0415

        dlg = CustomConfirmDialog(title="Confirm", message="Are you sure?")
        assert dlg.windowTitle() == "Confirm"
        assert isinstance(dlg.confirm_btn, QPushButton)
        assert isinstance(dlg.cancel_btn, QPushButton)

    def test_message_text(self, qapp: QApplication) -> None:
        """Message label displays the given text."""
        from src.ui.dialogs import CustomConfirmDialog  # noqa: PLC0415

        dlg = CustomConfirmDialog(message="Proceed?")
        assert dlg.msg_label.text() == "Proceed?"

    def test_message_word_wrap(self, qapp: QApplication) -> None:
        """Message label has word wrap enabled."""
        from src.ui.dialogs import CustomConfirmDialog  # noqa: PLC0415

        dlg = CustomConfirmDialog(message="text")
        assert dlg.msg_label.wordWrap()

    def test_message_centered(self, qapp: QApplication) -> None:
        """Message label is center-aligned."""
        from src.ui.dialogs import CustomConfirmDialog  # noqa: PLC0415

        dlg = CustomConfirmDialog(message="text")
        assert dlg.msg_label.alignment() & Qt.AlignmentFlag.AlignCenter

    def test_danger_mode_changes_button_style(self, qapp: QApplication) -> None:
        """Danger mode uses danger button styling."""
        from src.ui.dialogs import CustomConfirmDialog  # noqa: PLC0415

        dlg = CustomConfirmDialog(is_danger=True)
        # In danger mode, default confirm text becomes "Delete"
        from src.constants import tr  # noqa: PLC0415

        assert dlg.confirm_btn.text() == tr("btn.delete")

    def test_custom_confirm_text(self, qapp: QApplication) -> None:
        """Custom confirm text is used on the button."""
        from src.ui.dialogs import CustomConfirmDialog  # noqa: PLC0415

        dlg = CustomConfirmDialog(confirm_text="Do it!")
        assert dlg.confirm_btn.text() == "Do it!"

    def test_custom_cancel_text(self, qapp: QApplication) -> None:
        """Custom cancel text is used on the cancel button."""
        from src.ui.dialogs import CustomConfirmDialog  # noqa: PLC0415

        dlg = CustomConfirmDialog(cancel_text="Nope")
        assert dlg.cancel_btn.text() == "Nope"

    def test_danger_with_custom_confirm_text(self, qapp: QApplication) -> None:
        """Danger mode with custom confirm text keeps the custom text."""
        from src.ui.dialogs import CustomConfirmDialog  # noqa: PLC0415

        dlg = CustomConfirmDialog(is_danger=True, confirm_text="Remove All")
        assert dlg.confirm_btn.text() == "Remove All"

    def test_confirm_btn_cursor(self, qapp: QApplication) -> None:
        """Confirm button has PointingHandCursor."""
        from src.ui.dialogs import CustomConfirmDialog  # noqa: PLC0415

        dlg = CustomConfirmDialog()
        assert dlg.confirm_btn.cursor().shape() == Qt.CursorShape.PointingHandCursor

    def test_cancel_btn_cursor(self, qapp: QApplication) -> None:
        """Cancel button has PointingHandCursor."""
        from src.ui.dialogs import CustomConfirmDialog  # noqa: PLC0415

        dlg = CustomConfirmDialog()
        assert dlg.cancel_btn.cursor().shape() == Qt.CursorShape.PointingHandCursor

    def test_default_button_texts(self, qapp: QApplication) -> None:
        """Default button texts come from i18n."""
        from src.constants import tr  # noqa: PLC0415
        from src.ui.dialogs import CustomConfirmDialog  # noqa: PLC0415

        dlg = CustomConfirmDialog()
        assert dlg.confirm_btn.text() == tr("btn.continue")
        assert dlg.cancel_btn.text() == tr("btn.cancel")


# ---------------------------------------------------------------------------
# CustomMessageDialog tests
# ---------------------------------------------------------------------------


class TestCustomMessageDialog:
    """Tests for the CustomMessageDialog class."""

    def test_construction(self, qapp: QApplication) -> None:
        """CustomMessageDialog constructs with message and OK button."""
        from src.ui.dialogs import CustomMessageDialog  # noqa: PLC0415

        dlg = CustomMessageDialog(title="Info", message="All done!")
        assert dlg.windowTitle() == "Info"
        assert isinstance(dlg.ok_btn, QPushButton)

    def test_message_text(self, qapp: QApplication) -> None:
        """Message label displays the given text."""
        from src.ui.dialogs import CustomMessageDialog  # noqa: PLC0415

        dlg = CustomMessageDialog(message="Complete!")
        assert dlg.msg_label.text() == "Complete!"

    def test_message_word_wrap(self, qapp: QApplication) -> None:
        """Message label has word wrap enabled."""
        from src.ui.dialogs import CustomMessageDialog  # noqa: PLC0415

        dlg = CustomMessageDialog(message="text")
        assert dlg.msg_label.wordWrap()

    def test_message_centered(self, qapp: QApplication) -> None:
        """Message label is center-aligned."""
        from src.ui.dialogs import CustomMessageDialog  # noqa: PLC0415

        dlg = CustomMessageDialog(message="text")
        assert dlg.msg_label.alignment() & Qt.AlignmentFlag.AlignCenter

    def test_ok_btn_cursor(self, qapp: QApplication) -> None:
        """OK button has PointingHandCursor."""
        from src.ui.dialogs import CustomMessageDialog  # noqa: PLC0415

        dlg = CustomMessageDialog()
        assert dlg.ok_btn.cursor().shape() == Qt.CursorShape.PointingHandCursor

    def test_ok_btn_text(self, qapp: QApplication) -> None:
        """OK button text comes from i18n."""
        from src.constants import tr  # noqa: PLC0415
        from src.ui.dialogs import CustomMessageDialog  # noqa: PLC0415

        dlg = CustomMessageDialog()
        assert dlg.ok_btn.text() == tr("btn.ok")

    def test_message_supports_rich_text_autodetect(self, qapp: QApplication) -> None:
        """msg_label uses AutoText for rich-text rendering.

        HTML markup from build_ffmpeg_install_message renders as rich
        text instead of being shown literally.
        """
        from src.ui.dialogs import CustomMessageDialog  # noqa: PLC0415

        dlg = CustomMessageDialog(
            message="<b>FFmpeg</b> is required. <a href='https://x'>Download</a>"
        )
        assert dlg.msg_label.textFormat() == Qt.TextFormat.AutoText

    def test_message_opens_external_links(self, qapp: QApplication) -> None:
        """openExternalLinks() is True for browser-routed <a href>.

        No extra wiring required from callers.
        """
        from src.ui.dialogs import CustomMessageDialog  # noqa: PLC0415

        dlg = CustomMessageDialog(message="<a href='https://x'>x</a>")
        assert dlg.msg_label.openExternalLinks() is True


# ---------------------------------------------------------------------------
# LanguageSelectionDialog tests
# ---------------------------------------------------------------------------


class TestLanguageSelectionDialog:
    """Tests for the LanguageSelectionDialog class."""

    @patch("src.ui.dialogs.load_setting", return_value="")
    def test_construction(self, mock_load: MagicMock, qapp: QApplication) -> None:
        """LanguageSelectionDialog constructs with src and target combos."""
        from src.ui.dialogs import LanguageSelectionDialog  # noqa: PLC0415

        dlg = LanguageSelectionDialog()
        assert isinstance(dlg.src_combo, QComboBox)
        assert isinstance(dlg.target_combo, QComboBox)

    @patch("src.ui.dialogs.load_setting", return_value="")
    def test_source_combo_has_auto_detect(
        self, mock_load: MagicMock, qapp: QApplication
    ) -> None:
        """Source combo has auto-detect as first item (index 0)."""
        from src.ui.dialogs import LanguageSelectionDialog  # noqa: PLC0415

        dlg = LanguageSelectionDialog()
        # Index 0 is the auto-detect item
        assert dlg.src_combo.count() > 1

    @patch("src.ui.dialogs.load_setting", return_value="")
    def test_target_combo_has_languages(
        self, mock_load: MagicMock, qapp: QApplication
    ) -> None:
        """Target combo is populated with LANGUAGES list."""
        from src.constants import LANGUAGES  # noqa: PLC0415
        from src.ui.dialogs import LanguageSelectionDialog  # noqa: PLC0415

        dlg = LanguageSelectionDialog()
        assert dlg.target_combo.count() == len(LANGUAGES)

    @patch("src.ui.dialogs.load_setting", return_value="")
    def test_source_combo_more_than_target(
        self, mock_load: MagicMock, qapp: QApplication
    ) -> None:
        """Source combo has one more item than target (auto-detect)."""
        from src.ui.dialogs import LanguageSelectionDialog  # noqa: PLC0415

        dlg = LanguageSelectionDialog()
        assert dlg.src_combo.count() == dlg.target_combo.count() + 1

    @patch("src.ui.dialogs.load_setting", return_value="")
    def test_buttons_exist(self, mock_load: MagicMock, qapp: QApplication) -> None:
        """Dialog has translate and cancel buttons."""
        from src.ui.dialogs import LanguageSelectionDialog  # noqa: PLC0415

        dlg = LanguageSelectionDialog()
        assert isinstance(dlg.translate_btn, QPushButton)
        assert isinstance(dlg.cancel_btn, QPushButton)

    @patch("src.ui.dialogs.load_setting", return_value="")
    def test_translate_btn_cursor(
        self, mock_load: MagicMock, qapp: QApplication
    ) -> None:
        """Translate button has PointingHandCursor."""
        from src.ui.dialogs import LanguageSelectionDialog  # noqa: PLC0415

        dlg = LanguageSelectionDialog()
        assert dlg.translate_btn.cursor().shape() == Qt.CursorShape.PointingHandCursor

    @patch("src.ui.dialogs.load_setting", return_value="")
    def test_cancel_btn_cursor(self, mock_load: MagicMock, qapp: QApplication) -> None:
        """Cancel button has PointingHandCursor."""
        from src.ui.dialogs import LanguageSelectionDialog  # noqa: PLC0415

        dlg = LanguageSelectionDialog()
        assert dlg.cancel_btn.cursor().shape() == Qt.CursorShape.PointingHandCursor

    @patch("src.ui.dialogs.load_setting", return_value="French")
    def test_restores_last_target_language(
        self, mock_load: MagicMock, qapp: QApplication
    ) -> None:
        """Restores the last used target language from settings."""
        from src.ui.dialogs import LanguageSelectionDialog  # noqa: PLC0415

        dlg = LanguageSelectionDialog()
        # If French is in the combo, it should be selected
        idx = dlg.target_combo.findText("French")
        if idx >= 0:
            assert dlg.target_combo.currentIndex() == idx


# ---------------------------------------------------------------------------
# SourceLanguageDialog tests
# ---------------------------------------------------------------------------


class TestSourceLanguageDialog:
    """Tests for the SourceLanguageDialog class."""

    @patch("src.ui.dialogs.load_setting", return_value="")
    def test_construction(self, mock_load: MagicMock, qapp: QApplication) -> None:
        """SourceLanguageDialog constructs with source combo and buttons."""
        from src.ui.dialogs import SourceLanguageDialog  # noqa: PLC0415

        dlg = SourceLanguageDialog()
        assert isinstance(dlg.src_combo, QComboBox)
        assert isinstance(dlg.confirm_btn, QPushButton)
        assert isinstance(dlg.cancel_btn, QPushButton)

    @patch("src.ui.dialogs.load_setting", return_value="")
    def test_no_target_by_default(
        self, mock_load: MagicMock, qapp: QApplication
    ) -> None:
        """Target combo is None when show_target is False (default)."""
        from src.ui.dialogs import SourceLanguageDialog  # noqa: PLC0415

        dlg = SourceLanguageDialog()
        assert dlg.target_combo is None

    @patch("src.ui.dialogs.load_setting", return_value="")
    def test_with_target_combo(self, mock_load: MagicMock, qapp: QApplication) -> None:
        """Target combo is created when show_target=True."""
        from src.ui.dialogs import SourceLanguageDialog  # noqa: PLC0415

        dlg = SourceLanguageDialog(show_target=True)
        assert dlg.target_combo is not None
        assert isinstance(dlg.target_combo, QComboBox)

    @patch(
        "src.utils.config_manager.get_available_models",
        return_value=[("Gemini", "gemini-3-flash-preview")],
    )
    @patch("src.ui.dialogs.load_setting", return_value="")
    def test_model_picker_hidden_when_no_translation_initial(
        self,
        mock_load: MagicMock,
        mock_models: MagicMock,
        qapp: QApplication,
    ) -> None:
        """Model picker hidden when target is 'No translation' on first paint.

        Pins the dead-UI hide: when target_combo index 0 is selected
        (the "No translation" sentinel), the Model label + combo are
        invisible because no LLM call will be made.
        """
        from src.ui.dialogs import SourceLanguageDialog  # noqa: PLC0415

        dlg = SourceLanguageDialog(show_target=True)
        # Index 0 = "No translation" by construction.
        assert dlg.target_combo.currentIndex() == 0
        assert dlg.model_combo is not None
        assert not dlg.model_combo.isVisibleTo(dlg)
        assert dlg._model_label is not None
        assert not dlg._model_label.isVisibleTo(dlg)

    @patch(
        "src.utils.config_manager.get_available_models",
        return_value=[("Gemini", "gemini-3-flash-preview")],
    )
    @patch("src.ui.dialogs.load_setting", return_value="")
    def test_model_picker_shown_when_real_target_selected(
        self,
        mock_load: MagicMock,
        mock_models: MagicMock,
        qapp: QApplication,
    ) -> None:
        """Switching from 'No translation' to a real target reveals the Model picker."""
        from src.ui.dialogs import SourceLanguageDialog  # noqa: PLC0415

        dlg = SourceLanguageDialog(show_target=True)
        # Start at index 0 — picker hidden.
        assert not dlg.model_combo.isVisibleTo(dlg)
        # Pick any non-zero target index (a real language).
        dlg.target_combo.setCurrentIndex(1)
        assert dlg.model_combo.isVisibleTo(dlg)
        assert dlg._model_label.isVisibleTo(dlg)

    @patch(
        "src.utils.config_manager.get_available_models",
        return_value=[("Gemini", "gemini-3-flash-preview")],
    )
    @patch("src.ui.dialogs.load_setting", return_value="")
    def test_model_picker_hides_when_user_reverts_to_no_translation(
        self,
        mock_load: MagicMock,
        mock_models: MagicMock,
        qapp: QApplication,
    ) -> None:
        """Switching BACK to 'No translation' re-hides the Model picker."""
        from src.ui.dialogs import SourceLanguageDialog  # noqa: PLC0415

        dlg = SourceLanguageDialog(show_target=True)
        dlg.target_combo.setCurrentIndex(1)
        assert dlg.model_combo.isVisibleTo(dlg)
        # User reverts to "No translation" — picker hides again.
        dlg.target_combo.setCurrentIndex(0)
        assert not dlg.model_combo.isVisibleTo(dlg)
        assert not dlg._model_label.isVisibleTo(dlg)

    @patch("src.ui.dialogs.load_setting", return_value="")
    def test_no_target_picker_no_sync_wired(
        self,
        mock_load: MagicMock,
        qapp: QApplication,
    ) -> None:
        """``show_target=False`` (Extract Text path) — no sync, model always shown.

        Extract Text uses ``SourceLanguageDialog`` without the
        target picker; the Model picker should remain visible
        unconditionally because the LLM is always called for
        extraction.
        """
        from src.ui.dialogs import SourceLanguageDialog  # noqa: PLC0415

        dlg = SourceLanguageDialog(show_target=False)
        assert dlg.target_combo is None
        # Model picker visibility is independent of the missing
        # target combo — either visible (model configured) or
        # absent (no models).  Either way, no NoneType crash.
        if dlg.model_combo is not None:
            assert dlg.model_combo.isVisibleTo(dlg)

    @patch(
        "src.utils.config_manager.get_available_models",
        return_value=[("Gemini", "gemini-3-flash-preview")],
    )
    @patch("src.ui.dialogs.load_setting")
    def test_dialog_shrinks_when_switching_to_no_translation(
        self,
        mock_load: MagicMock,
        mock_models: MagicMock,
        qapp: QApplication,
    ) -> None:
        """Dialog shrinks when user switches from real target → No translation.

        Without an ``adjustSize()`` in the visibility sync, a dialog
        that opened sized for "Model visible" (because the last
        used target was a real language) keeps that larger height
        when the user switches to "No translation" — leaving ~100px
        of dead empty space at the bottom.  Pins the size collapse.
        """
        # Simulate stored "Vietnamese" target so dialog opens with model visible.
        mock_load.side_effect = lambda k, d: "Vietnamese" if "target" in k else d

        from src.ui.dialogs import SourceLanguageDialog  # noqa: PLC0415

        dlg = SourceLanguageDialog(
            show_target=True,
            target_setting_key="last/target",
        )
        dlg.show()
        qapp.processEvents()

        initial_height = dlg.size().height()
        assert dlg.model_combo.isVisibleTo(dlg)
        # The dialog should be sized to fit the Model picker initially.

        # User switches to "No translation"
        dlg.target_combo.setCurrentIndex(0)
        qapp.processEvents()

        shrunk_height = dlg.size().height()
        # Dialog must have shrunk; no dead space at the bottom.
        assert shrunk_height < initial_height, (
            f"Expected shrink: {initial_height} → smaller, got {shrunk_height}"
        )
        assert shrunk_height == dlg.sizeHint().height(), (
            f"Dialog size ({shrunk_height}) doesn't match sizeHint "
            f"({dlg.sizeHint().height()}) — dead space at bottom."
        )

        # Switching BACK to a real language re-grows the dialog.
        dlg.target_combo.setCurrentIndex(5)
        qapp.processEvents()
        regrown_height = dlg.size().height()
        assert regrown_height > shrunk_height
        assert regrown_height == dlg.sizeHint().height()

    @patch(
        "src.utils.config_manager.get_available_models",
        return_value=[("Gemini", "gemini-3-flash-preview")],
    )
    @patch("src.ui.dialogs.load_setting", return_value="")
    def test_model_appears_below_target_in_layout(
        self,
        mock_load: MagicMock,
        mock_models: MagicMock,
        qapp: QApplication,
    ) -> None:
        """Model picker sits BELOW the target combo in the layout.

        Reading order: source → target → (if translating) model.
        Putting the conditional Model row at the bottom means
        show/hide only changes the dialog's final row — the source
        + target rows stay anchored regardless of translation state.
        """
        from src.ui.dialogs import SourceLanguageDialog  # noqa: PLC0415

        dlg = SourceLanguageDialog(show_target=True)
        layout = dlg.layout
        indexes = {}
        for i in range(layout.count()):
            w = layout.itemAt(i).widget()
            if w is dlg.src_combo:
                indexes["src"] = i
            elif w is dlg.target_combo:
                indexes["target"] = i
            elif w is dlg.model_combo:
                indexes["model"] = i

        assert "src" in indexes
        assert "target" in indexes
        assert "model" in indexes
        # Anchor the ordering: source < target < model.
        assert indexes["src"] < indexes["target"] < indexes["model"], (
            f"Expected layout order src < target < model, got {indexes}"
        )

    @patch("src.ui.dialogs.load_setting", return_value="")
    def test_source_has_auto_detect(
        self, mock_load: MagicMock, qapp: QApplication
    ) -> None:
        """Source combo has auto-detect as first item."""
        from src.ui.dialogs import SourceLanguageDialog  # noqa: PLC0415

        dlg = SourceLanguageDialog()
        assert dlg.src_combo.count() > 1

    @patch("src.ui.dialogs.load_setting", return_value="")
    def test_confirm_btn_cursor(self, mock_load: MagicMock, qapp: QApplication) -> None:
        """Confirm button has PointingHandCursor."""
        from src.ui.dialogs import SourceLanguageDialog  # noqa: PLC0415

        dlg = SourceLanguageDialog()
        assert dlg.confirm_btn.cursor().shape() == Qt.CursorShape.PointingHandCursor

    @patch("src.ui.dialogs.load_setting", return_value="")
    def test_cancel_btn_cursor(self, mock_load: MagicMock, qapp: QApplication) -> None:
        """Cancel button has PointingHandCursor."""
        from src.ui.dialogs import SourceLanguageDialog  # noqa: PLC0415

        dlg = SourceLanguageDialog()
        assert dlg.cancel_btn.cursor().shape() == Qt.CursorShape.PointingHandCursor

    @patch("src.ui.dialogs.load_setting", return_value="")
    def test_custom_title_key(self, mock_load: MagicMock, qapp: QApplication) -> None:
        """Custom title_key sets the dialog title from i18n."""
        from src.constants import tr  # noqa: PLC0415
        from src.ui.dialogs import SourceLanguageDialog  # noqa: PLC0415

        dlg = SourceLanguageDialog(title_key="extract_text.extraction_setup")
        assert dlg.windowTitle() == tr("extract_text.extraction_setup")


# ---------------------------------------------------------------------------
# VoiceSetupDialog tests
# ---------------------------------------------------------------------------


class TestVoiceSetupDialog:
    """Tests for the VoiceSetupDialog class.

    The dialog only asks for the target language now — voice gender
    (Edge), voice name (Google / Gemini), and voice ID (ElevenLabs)
    all live in Settings → Generate Voice.  The dialog does NOT
    expose a gender combo; ``get_selection`` reads gender from
    ``SETTING_LAST_VOICE_GENDER`` (the Edge gender radio).
    """

    @patch("src.ui.dialogs.load_setting", return_value="")
    def test_construction(self, mock_load: MagicMock, qapp: QApplication) -> None:
        """VoiceSetupDialog constructs with the language combo + buttons."""
        from src.ui.dialogs import VoiceSetupDialog  # noqa: PLC0415

        dlg = VoiceSetupDialog()
        assert isinstance(dlg.lang_combo, QComboBox)
        assert isinstance(dlg.confirm_btn, QPushButton)
        assert isinstance(dlg.cancel_btn, QPushButton)

    @patch("src.ui.dialogs.load_setting", return_value="")
    def test_no_gender_combo(self, mock_load: MagicMock, qapp: QApplication) -> None:
        """Dialog must NOT carry a gender combo — gender lives in Settings."""
        from src.ui.dialogs import VoiceSetupDialog  # noqa: PLC0415

        dlg = VoiceSetupDialog()
        assert not hasattr(dlg, "gender_combo")

    @patch("src.ui.dialogs.load_setting", return_value="")
    def test_language_combo_populated(
        self, mock_load: MagicMock, qapp: QApplication
    ) -> None:
        """Language combo is populated with all LANGUAGES."""
        from src.constants import LANGUAGES  # noqa: PLC0415
        from src.ui.dialogs import VoiceSetupDialog  # noqa: PLC0415

        dlg = VoiceSetupDialog()
        assert dlg.lang_combo.count() == len(LANGUAGES)

    @patch("src.ui.dialogs.load_setting", return_value="")
    def test_confirm_btn_cursor(self, mock_load: MagicMock, qapp: QApplication) -> None:
        """Confirm button has PointingHandCursor."""
        from src.ui.dialogs import VoiceSetupDialog  # noqa: PLC0415

        dlg = VoiceSetupDialog()
        assert dlg.confirm_btn.cursor().shape() == Qt.CursorShape.PointingHandCursor

    @patch("src.ui.dialogs.load_setting", return_value="")
    def test_cancel_btn_cursor(self, mock_load: MagicMock, qapp: QApplication) -> None:
        """Cancel button has PointingHandCursor."""
        from src.ui.dialogs import VoiceSetupDialog  # noqa: PLC0415

        dlg = VoiceSetupDialog()
        assert dlg.cancel_btn.cursor().shape() == Qt.CursorShape.PointingHandCursor

    @patch("src.ui.dialogs.load_setting", return_value="")
    def test_lang_combo_cursor(self, mock_load: MagicMock, qapp: QApplication) -> None:
        """Language combo has PointingHandCursor."""
        from src.ui.dialogs import VoiceSetupDialog  # noqa: PLC0415

        dlg = VoiceSetupDialog()
        assert dlg.lang_combo.cursor().shape() == Qt.CursorShape.PointingHandCursor


# ---------------------------------------------------------------------------
# require_setup tests
# ---------------------------------------------------------------------------


class TestRequireSetup:
    """Tests for the require_setup() helper function."""

    def test_returns_true_when_check_passes(self, qapp: QApplication) -> None:
        """Returns True when check_fn returns True (no dialog shown)."""
        from src.ui.dialogs import require_setup  # noqa: PLC0415

        result = require_setup(None, lambda: True, "title", "msg", settings_tab=0)
        assert result is True

    @patch("src.ui.dialogs.CustomConfirmDialog.confirm", return_value=False)
    def test_returns_false_when_check_fails_and_declined(
        self, mock_confirm: MagicMock, qapp: QApplication
    ) -> None:
        """Returns False when check fails and user declines."""
        from src.ui.dialogs import require_setup  # noqa: PLC0415

        result = require_setup(None, lambda: False, "title", "msg", settings_tab=0)
        assert result is False

    @patch("src.ui.dialogs.CustomConfirmDialog.confirm", return_value=True)
    def test_navigates_to_settings_when_confirmed(
        self, mock_confirm: MagicMock, qapp: QApplication
    ) -> None:
        """Navigates to settings tab when user confirms."""
        from src.ui.dialogs import require_setup  # noqa: PLC0415

        window = MagicMock()
        window.navigate_to_settings_tab = MagicMock()
        result = require_setup(window, lambda: False, "title", "msg", settings_tab=3)
        assert result is False
        window.navigate_to_settings_tab.assert_called_once_with(3)  # noqa: PLR2004

    @patch("src.ui.dialogs.CustomConfirmDialog.confirm", return_value=True)
    def test_no_navigation_without_method(
        self, mock_confirm: MagicMock, qapp: QApplication
    ) -> None:
        """No error when window lacks navigate_to_settings_tab."""
        from src.ui.dialogs import require_setup  # noqa: PLC0415

        window = QWidget()
        result = require_setup(window, lambda: False, "title", "msg", settings_tab=0)
        assert result is False


# ---------------------------------------------------------------------------
# Signal connection tests
# ---------------------------------------------------------------------------


class TestDialogSignalConnections:
    """Tests that dialog buttons are connected to the correct slots."""

    def test_input_dialog_cancel_rejects(self, qapp: QApplication) -> None:
        """Cancel button on input dialog calls reject."""
        from src.ui.dialogs import CustomInputDialog  # noqa: PLC0415

        dlg = CustomInputDialog()
        dlg.reject = MagicMock()
        dlg.cancel_btn.click()
        dlg.reject.assert_called()

    def test_input_dialog_ok_calls_on_confirm(self, qapp: QApplication) -> None:
        """OK button on input dialog calls on_confirm."""
        from src.ui.dialogs import CustomInputDialog  # noqa: PLC0415

        dlg = CustomInputDialog()
        dlg.on_confirm = MagicMock()
        dlg.ok_btn.click()
        dlg.on_confirm.assert_called()

    def test_confirm_dialog_cancel_rejects(self, qapp: QApplication) -> None:
        """Cancel button on confirm dialog calls reject."""
        from src.ui.dialogs import CustomConfirmDialog  # noqa: PLC0415

        dlg = CustomConfirmDialog()
        dlg.reject = MagicMock()
        dlg.cancel_btn.click()
        dlg.reject.assert_called()

    def test_confirm_dialog_confirm_calls_on_confirm(self, qapp: QApplication) -> None:
        """Confirm button calls on_confirm."""
        from src.ui.dialogs import CustomConfirmDialog  # noqa: PLC0415

        dlg = CustomConfirmDialog()
        dlg.on_confirm = MagicMock()
        dlg.confirm_btn.click()
        dlg.on_confirm.assert_called()

    def test_message_dialog_ok_calls_on_confirm(self, qapp: QApplication) -> None:
        """OK button on message dialog calls on_confirm."""
        from src.ui.dialogs import CustomMessageDialog  # noqa: PLC0415

        dlg = CustomMessageDialog()
        dlg.on_confirm = MagicMock()
        dlg.ok_btn.click()
        dlg.on_confirm.assert_called()

    @patch("src.ui.dialogs.load_setting", return_value="")
    def test_language_dialog_cancel_rejects(
        self, mock_load: MagicMock, qapp: QApplication
    ) -> None:
        """Cancel button on language dialog calls reject."""
        from src.ui.dialogs import LanguageSelectionDialog  # noqa: PLC0415

        dlg = LanguageSelectionDialog()
        dlg.reject = MagicMock()
        dlg.cancel_btn.click()
        dlg.reject.assert_called()

    @patch("src.ui.dialogs.load_setting", return_value="")
    def test_language_dialog_translate_accepts(
        self, mock_load: MagicMock, qapp: QApplication
    ) -> None:
        """Translate button on language dialog calls accept."""
        from src.ui.dialogs import LanguageSelectionDialog  # noqa: PLC0415

        dlg = LanguageSelectionDialog()
        dlg.accept = MagicMock()
        dlg.translate_btn.click()
        dlg.accept.assert_called()

    @patch("src.ui.dialogs.load_setting", return_value="")
    def test_source_dialog_cancel_rejects(
        self, mock_load: MagicMock, qapp: QApplication
    ) -> None:
        """Cancel button on source dialog calls reject."""
        from src.ui.dialogs import SourceLanguageDialog  # noqa: PLC0415

        dlg = SourceLanguageDialog()
        dlg.reject = MagicMock()
        dlg.cancel_btn.click()
        dlg.reject.assert_called()

    @patch("src.ui.dialogs.load_setting", return_value="")
    def test_source_dialog_confirm_accepts(
        self, mock_load: MagicMock, qapp: QApplication
    ) -> None:
        """Confirm button on source dialog calls accept."""
        from src.ui.dialogs import SourceLanguageDialog  # noqa: PLC0415

        dlg = SourceLanguageDialog()
        dlg.accept = MagicMock()
        dlg.confirm_btn.click()
        dlg.accept.assert_called()

    @patch("src.ui.dialogs.load_setting", return_value="")
    def test_voice_dialog_cancel_rejects(
        self, mock_load: MagicMock, qapp: QApplication
    ) -> None:
        """Cancel button on voice dialog calls reject."""
        from src.ui.dialogs import VoiceSetupDialog  # noqa: PLC0415

        dlg = VoiceSetupDialog()
        dlg.reject = MagicMock()
        dlg.cancel_btn.click()
        dlg.reject.assert_called()

    @patch("src.ui.dialogs.load_setting", return_value="")
    def test_voice_dialog_confirm_accepts(
        self, mock_load: MagicMock, qapp: QApplication
    ) -> None:
        """Confirm button on voice dialog calls accept."""
        from src.ui.dialogs import VoiceSetupDialog  # noqa: PLC0415

        dlg = VoiceSetupDialog()
        dlg.accept = MagicMock()
        dlg.confirm_btn.click()
        dlg.accept.assert_called()


# ---------------------------------------------------------------------------
# CustomConfirmDialog extended tests
# ---------------------------------------------------------------------------


class TestCustomConfirmDialogExtended:
    """Extended tests for CustomConfirmDialog — accept/reject, styling, keys."""

    def test_confirm_returns_true_on_accept(self, qapp: QApplication) -> None:
        """Clicking confirm button calls accept (would return Accepted)."""
        from src.ui.dialogs import CustomConfirmDialog  # noqa: PLC0415

        dlg = CustomConfirmDialog(title="Test", message="Sure?")
        dlg.accept = MagicMock()
        dlg.confirm_btn.click()
        dlg.accept.assert_called_once()

    def test_reject_on_cancel(self, qapp: QApplication) -> None:
        """Clicking cancel button calls reject."""
        from src.ui.dialogs import CustomConfirmDialog  # noqa: PLC0415

        dlg = CustomConfirmDialog(title="Test", message="Sure?")
        dlg.reject = MagicMock()
        dlg.cancel_btn.click()
        dlg.reject.assert_called()

    def test_danger_styling_uses_danger_button(self, qapp: QApplication) -> None:
        """Danger mode applies danger button style to confirm button."""
        from src.ui.dialogs import CustomConfirmDialog  # noqa: PLC0415

        dlg = CustomConfirmDialog(is_danger=True)
        # Danger button style should contain "padding" from the extra styling
        assert "padding" in dlg.confirm_btn.styleSheet()

    def test_enter_key_triggers_on_confirm(self, qapp: QApplication) -> None:
        """Enter key press triggers on_confirm via BaseDialog.keyPressEvent."""
        from PySide6.QtGui import QKeyEvent  # noqa: PLC0415

        from src.ui.dialogs import CustomConfirmDialog  # noqa: PLC0415

        dlg = CustomConfirmDialog(message="Test")
        dlg.on_confirm = MagicMock()
        key_event = QKeyEvent(
            QEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier
        )
        dlg.keyPressEvent(key_event)
        dlg.on_confirm.assert_called_once()

    def test_escape_key_does_not_trigger_confirm(self, qapp: QApplication) -> None:
        """Escape key does not trigger on_confirm."""
        from PySide6.QtGui import QKeyEvent  # noqa: PLC0415

        from src.ui.dialogs import CustomConfirmDialog  # noqa: PLC0415

        dlg = CustomConfirmDialog(message="Test")
        dlg.on_confirm = MagicMock()
        key_event = QKeyEvent(
            QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier
        )
        dlg.keyPressEvent(key_event)
        dlg.on_confirm.assert_not_called()

    def test_title_and_message_display(self, qapp: QApplication) -> None:
        """Title and message are correctly displayed."""
        from src.ui.dialogs import CustomConfirmDialog  # noqa: PLC0415

        dlg = CustomConfirmDialog(title="My Title", message="My Message")
        assert dlg.windowTitle() == "My Title"
        assert dlg.msg_label.text() == "My Message"

    def test_non_danger_styling(self, qapp: QApplication) -> None:
        """Non-danger mode applies primary button style."""
        from src.ui.dialogs import CustomConfirmDialog  # noqa: PLC0415

        dlg = CustomConfirmDialog(is_danger=False, confirm_text="OK")
        assert "padding" in dlg.confirm_btn.styleSheet()

    def test_confirm_btn_height(self, qapp: QApplication) -> None:
        """Confirm button has HEIGHT_CONTROL fixed height."""
        from src.constants import HEIGHT_CONTROL  # noqa: PLC0415
        from src.ui.dialogs import CustomConfirmDialog  # noqa: PLC0415

        dlg = CustomConfirmDialog()
        assert dlg.confirm_btn.height() == HEIGHT_CONTROL

    def test_cancel_btn_height(self, qapp: QApplication) -> None:
        """Cancel button has HEIGHT_CONTROL fixed height."""
        from src.constants import HEIGHT_CONTROL  # noqa: PLC0415
        from src.ui.dialogs import CustomConfirmDialog  # noqa: PLC0415

        dlg = CustomConfirmDialog()
        assert dlg.cancel_btn.height() == HEIGHT_CONTROL


# ---------------------------------------------------------------------------
# CustomInputDialog extended tests
# ---------------------------------------------------------------------------


class TestCustomInputDialogExtended:
    """Extended tests for CustomInputDialog — text return, initial value, etc."""

    def test_input_text_accessible(self, qapp: QApplication) -> None:
        """Input text can be set and read back."""
        from src.ui.dialogs import CustomInputDialog  # noqa: PLC0415

        dlg = CustomInputDialog(title="Name", label_text="Enter name:")
        dlg.input.setText("Alice")
        assert dlg.input.text() == "Alice"

    def test_on_confirm_calls_accept(self, qapp: QApplication) -> None:
        """on_confirm calls accept on the dialog."""
        from src.ui.dialogs import CustomInputDialog  # noqa: PLC0415

        dlg = CustomInputDialog()
        dlg.accept = MagicMock()
        dlg.on_confirm()
        dlg.accept.assert_called_once()

    def test_enter_key_triggers_on_confirm(self, qapp: QApplication) -> None:
        """Enter key triggers on_confirm via BaseDialog."""
        from PySide6.QtGui import QKeyEvent  # noqa: PLC0415

        from src.ui.dialogs import CustomInputDialog  # noqa: PLC0415

        dlg = CustomInputDialog()
        dlg.on_confirm = MagicMock()
        key_event = QKeyEvent(
            QEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier
        )
        dlg.keyPressEvent(key_event)
        dlg.on_confirm.assert_called_once()

    def test_empty_input_text(self, qapp: QApplication) -> None:
        """Empty input returns empty string."""
        from src.ui.dialogs import CustomInputDialog  # noqa: PLC0415

        dlg = CustomInputDialog()
        assert dlg.input.text() == ""

    def test_input_return_pressed_triggers_confirm(self, qapp: QApplication) -> None:
        """The returnPressed signal on input triggers on_confirm."""
        from src.ui.dialogs import CustomInputDialog  # noqa: PLC0415

        dlg = CustomInputDialog()
        dlg.on_confirm = MagicMock()
        dlg.input.returnPressed.emit()
        dlg.on_confirm.assert_called()

    def test_error_frame_initially_hidden(self, qapp: QApplication) -> None:
        """Error frame is hidden at construction."""
        from src.ui.dialogs import CustomInputDialog  # noqa: PLC0415

        dlg = CustomInputDialog()
        assert dlg.error_frame.isHidden()
        assert dlg.error_label.text() == ""

    def test_set_error_then_type_clears(self, qapp: QApplication) -> None:
        """Setting error then typing new text clears the error."""
        from src.ui.dialogs import CustomInputDialog  # noqa: PLC0415

        dlg = CustomInputDialog()
        dlg.set_error("Bad input")
        assert not dlg.error_frame.isHidden()
        dlg.input.setText("new value")
        assert dlg.error_frame.isHidden()

    def test_ok_btn_not_default(self, qapp: QApplication) -> None:
        """OK button is not set as default."""
        from src.ui.dialogs import CustomInputDialog  # noqa: PLC0415

        dlg = CustomInputDialog()
        assert not dlg.ok_btn.isDefault()

    def test_input_stylesheet(self, qapp: QApplication) -> None:
        """Input field has a non-empty stylesheet."""
        from src.ui.dialogs import CustomInputDialog  # noqa: PLC0415

        dlg = CustomInputDialog()
        assert dlg.input.styleSheet()


# ---------------------------------------------------------------------------
# Dialog styling tests
# ---------------------------------------------------------------------------


class TestDialogStyling:
    """Tests that dialogs have correct styling properties."""

    def test_base_dialog_background_color(self, qapp: QApplication) -> None:
        """BaseDialog stylesheet contains background-color."""
        from src.ui.dialogs import BaseDialog  # noqa: PLC0415

        dlg = BaseDialog(title="Styled")
        assert "background-color" in dlg.styleSheet()

    def test_base_dialog_text_color(self, qapp: QApplication) -> None:
        """BaseDialog stylesheet contains color for text."""
        from src.ui.dialogs import BaseDialog  # noqa: PLC0415

        dlg = BaseDialog()
        assert "color" in dlg.styleSheet()

    def test_confirm_dialog_buttons_styled(self, qapp: QApplication) -> None:
        """Confirm dialog buttons have non-empty stylesheets."""
        from src.ui.dialogs import CustomConfirmDialog  # noqa: PLC0415

        dlg = CustomConfirmDialog(message="test")
        assert dlg.confirm_btn.styleSheet()
        assert dlg.cancel_btn.styleSheet()

    def test_danger_button_uses_danger_style(self, qapp: QApplication) -> None:
        """Danger confirm button uses danger button style."""
        from src.constants import style_danger_button  # noqa: PLC0415
        from src.ui.dialogs import CustomConfirmDialog  # noqa: PLC0415

        dlg = CustomConfirmDialog(is_danger=True)
        danger_style = style_danger_button()
        # The button's style should contain the danger style
        assert danger_style in dlg.confirm_btn.styleSheet()

    def test_input_dialog_ok_btn_styled(self, qapp: QApplication) -> None:
        """Input dialog OK button has primary button styling."""
        from src.ui.dialogs import CustomInputDialog  # noqa: PLC0415

        dlg = CustomInputDialog()
        assert dlg.ok_btn.styleSheet()

    def test_input_dialog_cancel_btn_styled(self, qapp: QApplication) -> None:
        """Input dialog cancel button has secondary button styling."""
        from src.ui.dialogs import CustomInputDialog  # noqa: PLC0415

        dlg = CustomInputDialog()
        assert dlg.cancel_btn.styleSheet()

    def test_message_dialog_ok_btn_styled(self, qapp: QApplication) -> None:
        """Message dialog OK button has primary styling with padding."""
        from src.ui.dialogs import CustomMessageDialog  # noqa: PLC0415

        dlg = CustomMessageDialog(message="Test")
        assert "padding" in dlg.ok_btn.styleSheet()

    def test_base_dialog_spacing(self, qapp: QApplication) -> None:
        """BaseDialog layout uses SPACING_SECTION spacing."""
        from src.constants import SPACING_SECTION  # noqa: PLC0415
        from src.ui.dialogs import BaseDialog  # noqa: PLC0415

        dlg = BaseDialog()
        assert dlg.layout.spacing() == SPACING_SECTION


# ---------------------------------------------------------------------------
# Dialog edge case tests
# ---------------------------------------------------------------------------


class TestDialogEdgeCases:
    """Tests for edge cases in dialog construction."""

    def test_very_long_message(self, qapp: QApplication) -> None:
        """Confirm dialog handles very long message text."""
        from src.ui.dialogs import CustomConfirmDialog  # noqa: PLC0415

        long_text = "A" * 10000
        dlg = CustomConfirmDialog(message=long_text)
        assert dlg.msg_label.text() == long_text
        assert dlg.msg_label.wordWrap()

    def test_html_in_message(self, qapp: QApplication) -> None:
        """Message with HTML tags stores them as-is in the label."""
        from src.ui.dialogs import CustomConfirmDialog  # noqa: PLC0415

        html_msg = "<b>Bold</b> and <i>italic</i>"
        dlg = CustomConfirmDialog(message=html_msg)
        assert dlg.msg_label.text() == html_msg

    def test_unicode_in_title_and_message(self, qapp: QApplication) -> None:
        """Dialog handles unicode characters in title and message."""
        from src.ui.dialogs import CustomConfirmDialog  # noqa: PLC0415

        dlg = CustomConfirmDialog(
            title="\u7ffb\u8bd1\u786e\u8ba4",
            message="\u4f60\u786e\u5b9a\u8981\u7ee7\u7eed\u5417\uff1f",
        )
        assert dlg.windowTitle() == "\u7ffb\u8bd1\u786e\u8ba4"
        expected = "\u4f60\u786e\u5b9a\u8981\u7ee7\u7eed\u5417\uff1f"
        assert dlg.msg_label.text() == expected

    def test_none_parent_widget(self, qapp: QApplication) -> None:
        """Dialog constructs successfully with None parent."""
        from src.ui.dialogs import CustomConfirmDialog  # noqa: PLC0415

        dlg = CustomConfirmDialog(parent=None, title="Test", message="msg")
        assert dlg.parent() is None

    def test_empty_title_no_header(self, qapp: QApplication) -> None:
        """BaseDialog with empty title does not add a header label."""
        from src.ui.dialogs import BaseDialog  # noqa: PLC0415

        dlg = BaseDialog(title="")
        # The layout should have no widgets (no header added for empty title)
        assert dlg.layout.count() == 0

    def test_message_dialog_long_text(self, qapp: QApplication) -> None:
        """Message dialog handles long text without error."""
        from src.ui.dialogs import CustomMessageDialog  # noqa: PLC0415

        long_text = "Word " * 500
        dlg = CustomMessageDialog(title="Info", message=long_text)
        assert long_text in dlg.msg_label.text()

    def test_input_dialog_unicode_placeholder(self, qapp: QApplication) -> None:
        """Input dialog handles unicode placeholder text."""
        from src.ui.dialogs import CustomInputDialog  # noqa: PLC0415

        dlg = CustomInputDialog(placeholder="\u8f93\u5165\u540d\u79f0...")
        assert dlg.input.placeholderText() == "\u8f93\u5165\u540d\u79f0..."

    def test_confirm_dialog_with_all_empty_strings(self, qapp: QApplication) -> None:
        """Confirm dialog handles all empty string arguments."""
        from src.ui.dialogs import CustomConfirmDialog  # noqa: PLC0415

        dlg = CustomConfirmDialog(title="", message="", confirm_text="", cancel_text="")
        assert dlg.windowTitle() == ""
        assert dlg.msg_label.text() == ""


# ---------------------------------------------------------------------------
# BaseDialog key press extended tests
# ---------------------------------------------------------------------------


class TestBaseDialogKeyPressExtended:
    """Extended tests for BaseDialog keyboard handling."""

    def test_numpad_enter_triggers_confirm(self, qapp: QApplication) -> None:
        """Numpad Enter (Key_Enter) also triggers on_confirm."""
        from PySide6.QtGui import QKeyEvent  # noqa: PLC0415

        from src.ui.dialogs import BaseDialog  # noqa: PLC0415

        dlg = BaseDialog()
        dlg.on_confirm = MagicMock()
        key_event = QKeyEvent(
            QEvent.Type.KeyPress, Qt.Key.Key_Enter, Qt.KeyboardModifier.NoModifier
        )
        dlg.keyPressEvent(key_event)
        dlg.on_confirm.assert_called_once()

    def test_regular_key_passes_through(self, qapp: QApplication) -> None:
        """Non-Enter keys do not trigger on_confirm."""
        from PySide6.QtGui import QKeyEvent  # noqa: PLC0415

        from src.ui.dialogs import BaseDialog  # noqa: PLC0415

        dlg = BaseDialog()
        dlg.on_confirm = MagicMock()
        key_event = QKeyEvent(
            QEvent.Type.KeyPress, Qt.Key.Key_A, Qt.KeyboardModifier.NoModifier
        )
        dlg.keyPressEvent(key_event)
        dlg.on_confirm.assert_not_called()

    def test_tab_key_does_not_trigger_confirm(self, qapp: QApplication) -> None:
        """Tab key does not trigger on_confirm."""
        from PySide6.QtGui import QKeyEvent  # noqa: PLC0415

        from src.ui.dialogs import BaseDialog  # noqa: PLC0415

        dlg = BaseDialog()
        dlg.on_confirm = MagicMock()
        key_event = QKeyEvent(
            QEvent.Type.KeyPress, Qt.Key.Key_Tab, Qt.KeyboardModifier.NoModifier
        )
        dlg.keyPressEvent(key_event)
        dlg.on_confirm.assert_not_called()


# ---------------------------------------------------------------------------
# CustomMessageDialog extended tests
# ---------------------------------------------------------------------------


class TestCustomMessageDialogExtended:
    """Extended tests for CustomMessageDialog."""

    def test_ok_btn_not_autodefault(self, qapp: QApplication) -> None:
        """OK button is not set as autoDefault."""
        from src.ui.dialogs import CustomMessageDialog  # noqa: PLC0415

        dlg = CustomMessageDialog()
        assert not dlg.ok_btn.autoDefault()

    def test_message_label_stylesheet(self, qapp: QApplication) -> None:
        """Message label has a non-empty stylesheet with font-size."""
        from src.ui.dialogs import CustomMessageDialog  # noqa: PLC0415

        dlg = CustomMessageDialog(message="Test")
        assert "font-size" in dlg.msg_label.styleSheet()

    def test_ok_btn_height(self, qapp: QApplication) -> None:
        """OK button has HEIGHT_CONTROL height."""
        from src.constants import HEIGHT_CONTROL  # noqa: PLC0415
        from src.ui.dialogs import CustomMessageDialog  # noqa: PLC0415

        dlg = CustomMessageDialog()
        assert dlg.ok_btn.height() == HEIGHT_CONTROL


# ---------------------------------------------------------------------------
# require_setup extended tests
# ---------------------------------------------------------------------------


class TestRequireSetupExtended:
    """Extended tests for the require_setup() helper."""

    def test_does_not_show_dialog_when_check_passes(self, qapp: QApplication) -> None:
        """No dialog is shown when check_fn returns True."""
        from src.ui.dialogs import require_setup  # noqa: PLC0415

        # If check passes, CustomConfirmDialog.confirm should never be called
        with patch("src.ui.dialogs.CustomConfirmDialog.confirm") as mock_confirm:
            result = require_setup(None, lambda: True, "title", "msg", settings_tab=0)
            assert result is True
            mock_confirm.assert_not_called()

    @patch("src.ui.dialogs.CustomConfirmDialog.confirm", return_value=True)
    def test_returns_false_even_when_navigated(
        self, mock_confirm: MagicMock, qapp: QApplication
    ) -> None:
        """Returns False when check fails, even after navigation."""
        from src.ui.dialogs import require_setup  # noqa: PLC0415

        window = MagicMock()
        result = require_setup(window, lambda: False, "title", "msg", settings_tab=2)
        assert result is False


# ---------------------------------------------------------------------------
# CustomMessageDialog copy_text tests
# ---------------------------------------------------------------------------


class TestCustomMessageDialogCopyText:
    """Tests for the CustomMessageDialog copy_text feature."""

    def test_no_copy_button_without_copy_text(self, qapp: QApplication) -> None:
        """Dialog created without copy_text has no copy button."""
        from src.ui.dialogs import CustomMessageDialog  # noqa: PLC0415

        dlg = CustomMessageDialog(title="Info", message="No copy")
        assert not hasattr(dlg, "copy_btn")

    def test_has_copy_button_with_copy_text(self, qapp: QApplication) -> None:
        """Dialog created with copy_text has a copy button."""
        from src.ui.dialogs import CustomMessageDialog  # noqa: PLC0415

        dlg = CustomMessageDialog(
            title="Info",
            message="Copy me",
            copy_text="pip install foo",
        )
        assert hasattr(dlg, "copy_btn")
        assert isinstance(dlg.copy_btn, QPushButton)

    def test_copy_button_text_is_translated(self, qapp: QApplication) -> None:
        """Copy button text matches the btn.copy_command translation key."""
        from src.constants import tr  # noqa: PLC0415
        from src.ui.dialogs import CustomMessageDialog  # noqa: PLC0415

        dlg = CustomMessageDialog(
            title="Info",
            message="Copy me",
            copy_text="pip install foo",
        )
        assert dlg.copy_btn.text() == tr("btn.copy_command")

    def test_copy_to_clipboard_sets_text(self, qapp: QApplication) -> None:
        """_copy_to_clipboard copies the copy_text to the system clipboard."""
        from src.ui.dialogs import CustomMessageDialog  # noqa: PLC0415

        command = "pip install ai-translate"
        dlg = CustomMessageDialog(
            title="Info",
            message="Copy me",
            copy_text=command,
        )

        mock_clipboard = MagicMock()
        with patch(
            "PySide6.QtWidgets.QApplication.clipboard",
            return_value=mock_clipboard,
        ):
            dlg._copy_to_clipboard()

        mock_clipboard.setText.assert_called_once_with(command)

    def test_reset_copy_btn_reverts_text(self, qapp: QApplication) -> None:
        """_reset_copy_btn restores original button text."""
        from src.ui.dialogs import CustomMessageDialog  # noqa: PLC0415

        dlg = CustomMessageDialog(None, "T", "M", copy_text="cmd")
        dlg.copy_btn.setText("Changed")
        dlg._reset_copy_btn()
        assert dlg.copy_btn.text() != "Changed"

    def test_reset_copy_btn_reverts_style(self, qapp: QApplication) -> None:
        """_reset_copy_btn restores default button stylesheet."""
        from src.ui.dialogs import CustomMessageDialog  # noqa: PLC0415

        dlg = CustomMessageDialog(None, "T", "M", copy_text="cmd")
        original_style = dlg._copy_default_style
        dlg.copy_btn.setStyleSheet("color: red;")
        dlg._reset_copy_btn()
        assert dlg.copy_btn.styleSheet() == original_style


# ---------------------------------------------------------------------------
# LanguageSelectionDialog.get_selection() tests
# ---------------------------------------------------------------------------


class TestLanguageSelectionDialogGetSelection:
    """Tests for the LanguageSelectionDialog.get_selection() static method."""

    @patch("src.ui.dialogs.save_setting")
    @patch("src.ui.dialogs.load_setting", return_value="")
    def test_accepted_returns_source_target_true(
        self, mock_load: MagicMock, mock_save: MagicMock, qapp: QApplication
    ) -> None:
        """get_selection returns (source, target, True) when dialog is accepted."""
        from PySide6.QtWidgets import QDialog  # noqa: PLC0415

        from src.ui.dialogs import LanguageSelectionDialog  # noqa: PLC0415

        with patch.object(
            LanguageSelectionDialog, "exec", return_value=QDialog.DialogCode.Accepted
        ):
            src, target, _model_id, accepted = LanguageSelectionDialog.get_selection(
                None
            )

        assert accepted is True
        # target should be a non-empty language name (first language in combo)
        assert isinstance(target, str)
        assert len(target) > 0

    @patch("src.ui.dialogs.save_setting")
    @patch("src.ui.dialogs.load_setting", return_value="")
    def test_rejected_returns_empty_strings_false(
        self, mock_load: MagicMock, mock_save: MagicMock, qapp: QApplication
    ) -> None:
        """get_selection returns (src, target, False) when dialog is cancelled."""
        from PySide6.QtWidgets import QDialog  # noqa: PLC0415

        from src.ui.dialogs import LanguageSelectionDialog  # noqa: PLC0415

        with patch.object(
            LanguageSelectionDialog, "exec", return_value=QDialog.DialogCode.Rejected
        ):
            src, target, _model_id, accepted = LanguageSelectionDialog.get_selection(
                None
            )

        assert accepted is False

    @patch("src.ui.dialogs.save_setting")
    @patch("src.ui.dialogs.load_setting", return_value="")
    def test_auto_detect_returns_empty_source(
        self, mock_load: MagicMock, mock_save: MagicMock, qapp: QApplication
    ) -> None:
        """get_selection returns empty source when auto-detect (index 0) is selected."""
        from PySide6.QtWidgets import QDialog  # noqa: PLC0415

        from src.ui.dialogs import LanguageSelectionDialog  # noqa: PLC0415

        with patch.object(
            LanguageSelectionDialog, "exec", return_value=QDialog.DialogCode.Accepted
        ):
            # Don't pre-select any source language — index 0 is auto-detect
            src, target, _model_id, accepted = LanguageSelectionDialog.get_selection(
                None
            )

        assert accepted is True
        # Source should be empty string for auto-detect
        assert src == ""

    @patch("src.ui.dialogs.save_setting")
    @patch("src.ui.dialogs.load_setting", return_value="")
    def test_pre_selected_source_returned(
        self, mock_load: MagicMock, mock_save: MagicMock, qapp: QApplication
    ) -> None:
        """get_selection returns the pre-selected source language when specified."""
        from PySide6.QtWidgets import QDialog  # noqa: PLC0415

        from src.ui.dialogs import LanguageSelectionDialog  # noqa: PLC0415

        with patch.object(
            LanguageSelectionDialog, "exec", return_value=QDialog.DialogCode.Accepted
        ):
            src, target, _model_id, accepted = LanguageSelectionDialog.get_selection(
                None, source_lang="French", target_lang="German"
            )

        assert accepted is True
        assert src == "French"
        assert target == "German"

    @patch("src.ui.dialogs.save_setting")
    @patch("src.ui.dialogs.load_setting", return_value="")
    def test_accepted_saves_settings(
        self, mock_load: MagicMock, mock_save: MagicMock, qapp: QApplication
    ) -> None:
        """get_selection saves source and target to settings when accepted."""
        from PySide6.QtWidgets import QDialog  # noqa: PLC0415

        from src.ui.dialogs import LanguageSelectionDialog  # noqa: PLC0415

        with patch.object(
            LanguageSelectionDialog, "exec", return_value=QDialog.DialogCode.Accepted
        ):
            LanguageSelectionDialog.get_selection(
                None, source_lang="Spanish", target_lang="English"
            )

        # save_setting should have been called for both source and target
        assert mock_save.call_count >= 2  # noqa: PLR2004

    @patch("src.ui.dialogs.save_setting")
    @patch("src.ui.dialogs.load_setting", return_value="")
    def test_rejected_does_not_save_settings(
        self, mock_load: MagicMock, mock_save: MagicMock, qapp: QApplication
    ) -> None:
        """get_selection does not save settings when dialog is rejected."""
        from PySide6.QtWidgets import QDialog  # noqa: PLC0415

        from src.ui.dialogs import LanguageSelectionDialog  # noqa: PLC0415

        with patch.object(
            LanguageSelectionDialog, "exec", return_value=QDialog.DialogCode.Rejected
        ):
            LanguageSelectionDialog.get_selection(None)

        mock_save.assert_not_called()


# ---------------------------------------------------------------------------
# SourceLanguageDialog.get_selection() tests
# ---------------------------------------------------------------------------


class TestSourceLanguageDialogGetSelection:
    """Tests for the SourceLanguageDialog.get_selection() static method."""

    @patch("src.ui.dialogs.save_setting")
    @patch("src.ui.dialogs.load_setting", return_value="")
    def test_accepted_returns_source_and_true(
        self, mock_load: MagicMock, mock_save: MagicMock, qapp: QApplication
    ) -> None:
        """get_selection returns (source, target, True) when accepted."""
        from PySide6.QtWidgets import QDialog  # noqa: PLC0415

        from src.ui.dialogs import SourceLanguageDialog  # noqa: PLC0415

        with patch.object(
            SourceLanguageDialog, "exec", return_value=QDialog.DialogCode.Accepted
        ):
            src, target, _model_id, accepted = SourceLanguageDialog.get_selection(None)

        assert accepted is True
        # Without show_target, source at index 0 is auto-detect (empty)
        assert src == ""
        # Target should be empty when show_target is False
        assert target == ""

    @patch("src.ui.dialogs.save_setting")
    @patch("src.ui.dialogs.load_setting", return_value="")
    def test_rejected_returns_false(
        self, mock_load: MagicMock, mock_save: MagicMock, qapp: QApplication
    ) -> None:
        """get_selection returns (src, target, False) when cancelled."""
        from PySide6.QtWidgets import QDialog  # noqa: PLC0415

        from src.ui.dialogs import SourceLanguageDialog  # noqa: PLC0415

        with patch.object(
            SourceLanguageDialog, "exec", return_value=QDialog.DialogCode.Rejected
        ):
            src, target, _model_id, accepted = SourceLanguageDialog.get_selection(None)

        assert accepted is False

    @patch("src.ui.dialogs.save_setting")
    @patch("src.ui.dialogs.load_setting", return_value="")
    def test_pre_selected_source_lang(
        self, mock_load: MagicMock, mock_save: MagicMock, qapp: QApplication
    ) -> None:
        """get_selection returns the pre-selected source language."""
        from PySide6.QtWidgets import QDialog  # noqa: PLC0415

        from src.ui.dialogs import SourceLanguageDialog  # noqa: PLC0415

        with patch.object(
            SourceLanguageDialog, "exec", return_value=QDialog.DialogCode.Accepted
        ):
            src, target, _model_id, accepted = SourceLanguageDialog.get_selection(
                None, source_lang="Japanese"
            )

        assert accepted is True
        assert src == "Japanese"

    @patch("src.ui.dialogs.save_setting")
    @patch("src.ui.dialogs.load_setting", return_value="")
    def test_with_target_combo_returns_target(
        self, mock_load: MagicMock, mock_save: MagicMock, qapp: QApplication
    ) -> None:
        """get_selection with show_target=True returns both source and target."""
        from PySide6.QtWidgets import QDialog  # noqa: PLC0415

        from src.ui.dialogs import SourceLanguageDialog  # noqa: PLC0415

        with patch.object(
            SourceLanguageDialog, "exec", return_value=QDialog.DialogCode.Accepted
        ):
            src, target, _model_id, accepted = SourceLanguageDialog.get_selection(
                None,
                source_lang="Korean",
                show_target=True,
                target_setting_key="test_target_key",
            )

        assert accepted is True
        assert src == "Korean"
        # target_combo index 0 is "No translation", so target is empty by default
        assert target == ""

    @patch("src.ui.dialogs.save_setting")
    @patch("src.ui.dialogs.load_setting", return_value="")
    def test_accepted_saves_source_setting(
        self, mock_load: MagicMock, mock_save: MagicMock, qapp: QApplication
    ) -> None:
        """get_selection saves source language to settings when accepted."""
        from PySide6.QtWidgets import QDialog  # noqa: PLC0415

        from src.ui.dialogs import SourceLanguageDialog  # noqa: PLC0415

        with patch.object(
            SourceLanguageDialog, "exec", return_value=QDialog.DialogCode.Accepted
        ):
            SourceLanguageDialog.get_selection(None, source_lang="Chinese")

        # At least the source setting should be saved
        assert mock_save.call_count >= 1

    @patch("src.ui.dialogs.save_setting")
    @patch("src.ui.dialogs.load_setting", return_value="")
    def test_rejected_does_not_save(
        self, mock_load: MagicMock, mock_save: MagicMock, qapp: QApplication
    ) -> None:
        """get_selection does not save settings when rejected."""
        from PySide6.QtWidgets import QDialog  # noqa: PLC0415

        from src.ui.dialogs import SourceLanguageDialog  # noqa: PLC0415

        with patch.object(
            SourceLanguageDialog, "exec", return_value=QDialog.DialogCode.Rejected
        ):
            SourceLanguageDialog.get_selection(None)

        mock_save.assert_not_called()


# ---------------------------------------------------------------------------
# VoiceSetupDialog.get_selection() tests
# ---------------------------------------------------------------------------


class TestVoiceSetupDialogGetSelection:
    """Tests for VoiceSetupDialog.get_selection() static method.

    The dialog's constructor can cause segfaults in offscreen CI environments
    when specific PySide6 signal connections interact with the offscreen
    platform. We mock the VoiceSetupDialog constructor to set up minimal
    combo widgets and test the get_selection logic in isolation.
    """

    @staticmethod
    def _make_fake_init(exec_result):
        """Returns a replacement __init__ that sets up minimal combos.

        Each ``addItem(text, data)`` call sets BOTH the display
        text AND the underlying data — production reads
        ``currentData()`` (where the actual language label / locale
        code lives) rather than ``currentText()`` (which carries
        the localised display label).  Passing only text leaves
        data as ``None`` and ``get_selection`` returns empty string.
        """

        def _fake_init(self, parent=None):
            from PySide6.QtWidgets import QComboBox, QDialog  # noqa: PLC0415

            QDialog.__init__(self, parent)
            self.lang_combo = QComboBox(self)
            self.lang_combo.addItem("English", "English")
            self.lang_combo.addItem("French", "French")
            # Note: no gender_combo — VoiceSetupDialog dropped that
            # field; gender now lives in Settings → Generate Voice.

        return _fake_init

    @patch("src.ui.dialogs.save_setting")
    def test_accepted_returns_language_gender_true(
        self, mock_save: MagicMock, qapp: QApplication
    ) -> None:
        """get_selection returns (language, gender, True) when accepted."""
        from PySide6.QtWidgets import QDialog  # noqa: PLC0415

        from src.ui.dialogs import VoiceSetupDialog  # noqa: PLC0415

        with (
            patch.object(
                VoiceSetupDialog,
                "__init__",
                self._make_fake_init(QDialog.DialogCode.Accepted),
            ),
            patch.object(
                VoiceSetupDialog,
                "exec",
                return_value=QDialog.DialogCode.Accepted,
            ),
        ):
            lang, gender, _model_id, accepted = VoiceSetupDialog.get_selection(None)

        assert accepted is True
        assert isinstance(lang, str)
        assert lang == "English"
        assert gender == "FEMALE"

    @patch("src.ui.dialogs.save_setting")
    def test_accepted_saves_language_only(
        self, mock_save: MagicMock, qapp: QApplication
    ) -> None:
        """get_selection saves ONLY the language when accepted.

        Gender is now read from settings (set on the Generate Voice
        TTS tab), not chosen per-generation, so the dialog no longer
        writes ``SETTING_LAST_VOICE_GENDER`` on accept.
        """
        from PySide6.QtWidgets import QDialog  # noqa: PLC0415

        from src.ui.dialogs import VoiceSetupDialog  # noqa: PLC0415

        with (
            patch.object(
                VoiceSetupDialog,
                "__init__",
                self._make_fake_init(QDialog.DialogCode.Accepted),
            ),
            patch.object(
                VoiceSetupDialog,
                "exec",
                return_value=QDialog.DialogCode.Accepted,
            ),
        ):
            VoiceSetupDialog.get_selection(None)

        # One save call: the language only.
        assert mock_save.call_count == 1
        # And the value is the dialog's selected language label.
        assert mock_save.call_args.args[1] == "English"

    @patch("src.ui.dialogs.save_setting")
    def test_rejected_returns_false(
        self, mock_save: MagicMock, qapp: QApplication
    ) -> None:
        """get_selection returns (lang, gender, False) when rejected."""
        from PySide6.QtWidgets import QDialog  # noqa: PLC0415

        from src.ui.dialogs import VoiceSetupDialog  # noqa: PLC0415

        with (
            patch.object(
                VoiceSetupDialog,
                "__init__",
                self._make_fake_init(QDialog.DialogCode.Rejected),
            ),
            patch.object(
                VoiceSetupDialog,
                "exec",
                return_value=QDialog.DialogCode.Rejected,
            ),
        ):
            lang, gender, _model_id, accepted = VoiceSetupDialog.get_selection(None)

        assert accepted is False

    @patch("src.ui.dialogs.save_setting")
    def test_rejected_does_not_save_settings(
        self, mock_save: MagicMock, qapp: QApplication
    ) -> None:
        """get_selection does NOT call save_setting when rejected."""
        from PySide6.QtWidgets import QDialog  # noqa: PLC0415

        from src.ui.dialogs import VoiceSetupDialog  # noqa: PLC0415

        with (
            patch.object(
                VoiceSetupDialog,
                "__init__",
                self._make_fake_init(QDialog.DialogCode.Rejected),
            ),
            patch.object(
                VoiceSetupDialog,
                "exec",
                return_value=QDialog.DialogCode.Rejected,
            ),
        ):
            VoiceSetupDialog.get_selection(None)

        mock_save.assert_not_called()

    @patch("src.ui.dialogs.save_setting")
    def test_accepted_returns_tuple_of_three(
        self, mock_save: MagicMock, qapp: QApplication
    ) -> None:
        """get_selection always returns a 3-tuple."""
        from PySide6.QtWidgets import QDialog  # noqa: PLC0415

        from src.ui.dialogs import VoiceSetupDialog  # noqa: PLC0415

        with (
            patch.object(
                VoiceSetupDialog,
                "__init__",
                self._make_fake_init(QDialog.DialogCode.Accepted),
            ),
            patch.object(
                VoiceSetupDialog,
                "exec",
                return_value=QDialog.DialogCode.Accepted,
            ),
        ):
            result = VoiceSetupDialog.get_selection(None)

        assert isinstance(result, tuple)
        # (lang, gender, model_id, accepted) — model_id is always "" for this dialog.
        assert len(result) == 4  # noqa: PLR2004

    @patch("src.ui.dialogs.save_setting")
    def test_rejected_still_returns_lang_and_gender(
        self, mock_save: MagicMock, qapp: QApplication
    ) -> None:
        """get_selection returns language and gender strings even when rejected."""
        from PySide6.QtWidgets import QDialog  # noqa: PLC0415

        from src.ui.dialogs import VoiceSetupDialog  # noqa: PLC0415

        with (
            patch.object(
                VoiceSetupDialog,
                "__init__",
                self._make_fake_init(QDialog.DialogCode.Rejected),
            ),
            patch.object(
                VoiceSetupDialog,
                "exec",
                return_value=QDialog.DialogCode.Rejected,
            ),
        ):
            lang, gender, _model_id, accepted = VoiceSetupDialog.get_selection(None)

        # Language and gender should still be populated from the combos
        assert isinstance(lang, str)
        assert lang == "English"
        assert isinstance(gender, str)
        assert gender == "FEMALE"
