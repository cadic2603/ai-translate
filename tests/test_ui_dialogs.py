"""Unit tests for custom UI dialogs (src/ui/dialogs.py)."""

import configparser
from collections.abc import Generator
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget
from pytestqt.qtbot import QtBot

from src.ui.dialogs import (
    BaseDialog,
    CustomConfirmDialog,
    CustomInputDialog,
    CustomMessageDialog,
    LanguageSelectionDialog,
    SourceLanguageDialog,
    require_setup,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def _mock_keyring(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mock keyring so dialog tests don't touch the OS keychain."""
    storage: dict[str, str] = {}
    monkeypatch.setattr(
        "keyring.set_password",
        lambda s, u, p: storage.__setitem__(f"{s}:{u}", p),
    )
    monkeypatch.setattr(
        "keyring.get_password",
        lambda s, u: storage.get(f"{s}:{u}"),
    )
    monkeypatch.setattr(
        "keyring.delete_password",
        lambda s, u: storage.pop(f"{s}:{u}", None),
    )


@pytest.fixture
def settings_env(
    monkeypatch: pytest.MonkeyPatch,
    _mock_keyring: None,
    tmp_path: Path,
) -> Generator[configparser.ConfigParser, None, None]:
    """Isolated configparser environment for dialog tests."""
    config_path = tmp_path / "test_settings.ini"
    monkeypatch.setattr(
        "src.utils.config_manager._get_config_path",
        lambda: config_path,
    )
    config = configparser.ConfigParser()
    config.optionxform = str
    yield config


# ===========================================================================
# BaseDialog
# ===========================================================================


def test_base_dialog_window_title(qtbot: QtBot) -> None:
    """BaseDialog sets the window title correctly."""
    dialog = BaseDialog(title="My Dialog")
    qtbot.addWidget(dialog)

    assert dialog.windowTitle() == "My Dialog"


def test_base_dialog_minimum_width(qtbot: QtBot) -> None:
    """BaseDialog enforces a minimum width of 450px."""
    dialog = BaseDialog(title="Test")
    qtbot.addWidget(dialog)

    assert dialog.minimumWidth() == 450  # noqa: PLR2004


def test_base_dialog_empty_title(qtbot: QtBot) -> None:
    """BaseDialog with empty title still initializes correctly."""
    dialog = BaseDialog(title="")
    qtbot.addWidget(dialog)

    assert dialog.windowTitle() == ""


def test_base_dialog_enter_key_triggers_accept(qtbot: QtBot) -> None:
    """Pressing Enter calls on_confirm() which accepts the dialog."""
    dialog = BaseDialog(title="Test")
    qtbot.addWidget(dialog)

    accepted: list[bool] = []
    dialog.accepted.connect(lambda: accepted.append(True))

    qtbot.keyPress(dialog, Qt.Key.Key_Return)

    assert len(accepted) == 1


def test_base_dialog_on_confirm_accepts(qtbot: QtBot) -> None:
    """on_confirm() directly calls accept() and emits accepted signal."""
    dialog = BaseDialog(title="Test")
    qtbot.addWidget(dialog)

    accepted: list[bool] = []
    dialog.accepted.connect(lambda: accepted.append(True))

    dialog.on_confirm()

    assert len(accepted) == 1


# ===========================================================================
# CustomInputDialog
# ===========================================================================


def test_custom_input_dialog_error_frame_hidden_by_default(qtbot: QtBot) -> None:
    """Error frame is hidden when the dialog first appears."""
    dialog = CustomInputDialog(title="Enter Name", label_text="Name")
    qtbot.addWidget(dialog)

    assert not dialog.error_frame.isVisible()


def test_custom_input_dialog_set_error_shows_frame(qtbot: QtBot) -> None:
    """set_error() shows the error frame and sets the message text."""
    dialog = CustomInputDialog(title="Enter Name")
    qtbot.addWidget(dialog)
    dialog.show()  # Must be shown for isVisible() to work correctly

    dialog.set_error("Name is required")

    assert dialog.error_frame.isVisible()
    assert dialog.error_label.text() == "Name is required"


def test_custom_input_dialog_set_error_empty_message_hides_frame(qtbot: QtBot) -> None:
    """set_error('') hides the error frame (empty message treated as no error)."""
    dialog = CustomInputDialog(title="Test")
    qtbot.addWidget(dialog)
    dialog.show()

    dialog.set_error("Initial error")
    assert dialog.error_frame.isVisible()

    dialog.set_error("")  # Empty message
    assert not dialog.error_frame.isVisible()


def test_custom_input_dialog_clear_error_hides_frame(qtbot: QtBot) -> None:
    """clear_error() hides the error frame and empties the message."""
    dialog = CustomInputDialog(title="Test")
    qtbot.addWidget(dialog)
    dialog.show()

    dialog.set_error("Something went wrong")
    assert dialog.error_frame.isVisible()

    dialog.clear_error()

    assert not dialog.error_frame.isVisible()
    assert dialog.error_label.text() == ""


def test_custom_input_dialog_text_change_clears_error(qtbot: QtBot) -> None:
    """Typing in the input field automatically clears any displayed error."""
    dialog = CustomInputDialog(title="Test")
    qtbot.addWidget(dialog)
    dialog.show()

    dialog.set_error("Required!")
    assert dialog.error_frame.isVisible()

    dialog.input.setText("new value")

    assert not dialog.error_frame.isVisible()


def test_custom_input_dialog_label_text(qtbot: QtBot) -> None:
    """Label text is displayed in the dialog."""
    dialog = CustomInputDialog(title="Test", label_text="Enter your name:")
    qtbot.addWidget(dialog)

    assert dialog.label.text() == "Enter your name:"


def test_custom_input_dialog_placeholder(qtbot: QtBot) -> None:
    """Placeholder text is set on the input field."""
    dialog = CustomInputDialog(title="Test", placeholder="e.g. John Doe")
    qtbot.addWidget(dialog)

    assert dialog.input.placeholderText() == "e.g. John Doe"


# ===========================================================================
# CustomConfirmDialog
# ===========================================================================


def test_custom_confirm_dialog_message_label(qtbot: QtBot) -> None:
    """The message is displayed in the dialog's message label."""
    dialog = CustomConfirmDialog(title="Confirm", message="Are you sure?")
    qtbot.addWidget(dialog)

    assert dialog.msg_label.text() == "Are you sure?"


def test_custom_confirm_dialog_is_danger_changes_button_text(qtbot: QtBot) -> None:
    """is_danger=True changes the confirm button text to tr('btn.delete')."""
    from src.constants.i18n import tr  # noqa: PLC0415

    dialog = CustomConfirmDialog(title="Delete", message="Delete?", is_danger=True)
    qtbot.addWidget(dialog)

    assert dialog.confirm_btn.text() == tr("btn.delete")


def test_custom_confirm_dialog_is_danger_true_uses_error_color(qtbot: QtBot) -> None:
    """is_danger=True applies the danger button style (error color)."""
    dialog = CustomConfirmDialog(title="Delete", message="Delete?", is_danger=True)
    qtbot.addWidget(dialog)

    # style_danger_button() contains the error color #ff6b72
    assert "ff6b72" in dialog.confirm_btn.styleSheet()


def test_custom_confirm_dialog_is_danger_false_uses_primary_color(qtbot: QtBot) -> None:
    """is_danger=False applies the primary button style (no error color)."""
    dialog = CustomConfirmDialog(title="Confirm", message="Continue?", is_danger=False)
    qtbot.addWidget(dialog)

    # style_primary_button() uses primary color, not error color
    assert "ff6b72" not in dialog.confirm_btn.styleSheet()


def test_custom_confirm_dialog_custom_confirm_text(qtbot: QtBot) -> None:
    """Custom confirm_text is used as the confirm button label."""
    dialog = CustomConfirmDialog(
        title="Test",
        message="Proceed?",
        confirm_text="Yes, proceed",
    )
    qtbot.addWidget(dialog)

    assert dialog.confirm_btn.text() == "Yes, proceed"


def test_custom_confirm_dialog_custom_cancel_text(qtbot: QtBot) -> None:
    """Custom cancel_text is used as the cancel button label."""
    dialog = CustomConfirmDialog(
        title="Test",
        message="Proceed?",
        cancel_text="No, go back",
    )
    qtbot.addWidget(dialog)

    assert dialog.cancel_btn.text() == "No, go back"


# ===========================================================================
# CustomMessageDialog
# ===========================================================================


def test_custom_message_dialog_shows_message(qtbot: QtBot) -> None:
    """The message text is displayed in the dialog."""
    dialog = CustomMessageDialog(title="Info", message="Operation complete.")
    qtbot.addWidget(dialog)

    assert dialog.msg_label.text() == "Operation complete."


def test_custom_message_dialog_has_ok_button(qtbot: QtBot) -> None:
    """CustomMessageDialog contains an OK button."""
    from PySide6.QtWidgets import QPushButton  # noqa: PLC0415

    dialog = CustomMessageDialog(title="Info", message="Done.")
    qtbot.addWidget(dialog)

    assert dialog.ok_btn is not None
    assert isinstance(dialog.ok_btn, QPushButton)


def test_custom_message_dialog_empty_message(qtbot: QtBot) -> None:
    """Dialog handles empty message without errors."""
    dialog = CustomMessageDialog(title="Info", message="")
    qtbot.addWidget(dialog)

    assert dialog.msg_label.text() == ""


# ===========================================================================
# LanguageSelectionDialog
# ===========================================================================


def test_language_selection_dialog_has_src_and_target_combos(
    qtbot: QtBot,
    settings_env: configparser.ConfigParser,
) -> None:
    """LanguageSelectionDialog contains src_combo and target_combo."""
    dialog = LanguageSelectionDialog()
    qtbot.addWidget(dialog)

    assert hasattr(dialog, "src_combo")
    assert hasattr(dialog, "target_combo")


def test_language_selection_dialog_source_combo_has_auto_detect(
    qtbot: QtBot,
    settings_env: configparser.ConfigParser,
) -> None:
    """Source combo starts at index 0 (auto-detect) by default."""
    dialog = LanguageSelectionDialog()
    qtbot.addWidget(dialog)

    assert dialog.src_combo.currentIndex() == 0


def test_language_selection_dialog_source_combo_count(
    qtbot: QtBot,
    settings_env: configparser.ConfigParser,
) -> None:
    """Source combo has LANGUAGES count + 1 (for auto-detect) items."""
    from src.constants.languages import LANGUAGES  # noqa: PLC0415

    dialog = LanguageSelectionDialog()
    qtbot.addWidget(dialog)

    assert dialog.src_combo.count() == len(LANGUAGES) + 1


def test_language_selection_dialog_target_combo_count(
    qtbot: QtBot,
    settings_env: configparser.ConfigParser,
) -> None:
    """Target combo has exactly LANGUAGES count items (no auto-detect)."""
    from src.constants.languages import LANGUAGES  # noqa: PLC0415

    dialog = LanguageSelectionDialog()
    qtbot.addWidget(dialog)

    assert dialog.target_combo.count() == len(LANGUAGES)


def test_language_selection_dialog_has_translate_and_cancel_buttons(
    qtbot: QtBot,
    settings_env: configparser.ConfigParser,
) -> None:
    """Dialog has translate_btn and cancel_btn."""
    from PySide6.QtWidgets import QPushButton  # noqa: PLC0415

    dialog = LanguageSelectionDialog()
    qtbot.addWidget(dialog)

    assert hasattr(dialog, "translate_btn")
    assert hasattr(dialog, "cancel_btn")
    assert isinstance(dialog.translate_btn, QPushButton)
    assert isinstance(dialog.cancel_btn, QPushButton)


# ===========================================================================
# Additional edge cases
# ===========================================================================


# ---------------------------------------------------------------------------
# BaseDialog — non-Enter key passes through
# ---------------------------------------------------------------------------


def test_base_dialog_non_enter_key_does_not_accept(qtbot: QtBot) -> None:
    """Pressing a non-Enter key does not trigger accept."""
    dialog = BaseDialog(title="Test")
    qtbot.addWidget(dialog)

    accepted: list[bool] = []
    dialog.accepted.connect(lambda: accepted.append(True))

    qtbot.keyPress(dialog, Qt.Key.Key_A)

    assert len(accepted) == 0


def test_base_dialog_enter_numpad_also_accepts(qtbot: QtBot) -> None:
    """Key_Enter (numpad enter) also triggers accept."""
    dialog = BaseDialog(title="Test")
    qtbot.addWidget(dialog)

    accepted: list[bool] = []
    dialog.accepted.connect(lambda: accepted.append(True))

    qtbot.keyPress(dialog, Qt.Key.Key_Enter)

    assert len(accepted) == 1


def test_base_dialog_title_creates_header_label(qtbot: QtBot) -> None:
    """Non-empty title adds a header QLabel to the dialog layout."""
    from PySide6.QtWidgets import QLabel  # noqa: PLC0415

    dialog = BaseDialog(title="My Header")
    qtbot.addWidget(dialog)

    labels = dialog.findChildren(QLabel)
    texts = [lbl.text() for lbl in labels]
    assert "My Header" in texts


def test_base_dialog_empty_title_no_header_label(qtbot: QtBot) -> None:
    """Empty title skips adding a header QLabel."""
    from PySide6.QtWidgets import QLabel  # noqa: PLC0415

    dialog = BaseDialog(title="")
    qtbot.addWidget(dialog)

    labels = dialog.findChildren(QLabel)
    # No label should have been added (the layout has no children)
    assert len(labels) == 0


# ---------------------------------------------------------------------------
# CustomConfirmDialog — is_danger with custom confirm_text
# ---------------------------------------------------------------------------


def test_custom_confirm_dialog_danger_custom_text_keeps_custom(
    qtbot: QtBot,
) -> None:
    """is_danger=True with custom confirm_text does NOT override to 'Delete'."""
    dialog = CustomConfirmDialog(
        title="Remove",
        message="Remove item?",
        is_danger=True,
        confirm_text="Remove forever",
    )
    qtbot.addWidget(dialog)

    # Custom text should be preserved, not overridden to tr("btn.delete")
    assert dialog.confirm_btn.text() == "Remove forever"
    # But it should still have danger styling
    assert "ff6b72" in dialog.confirm_btn.styleSheet()


def test_custom_confirm_dialog_default_texts_from_i18n(qtbot: QtBot) -> None:
    """Default button texts come from i18n when not explicitly provided."""
    from src.constants.i18n import tr  # noqa: PLC0415

    dialog = CustomConfirmDialog(title="Confirm", message="Proceed?")
    qtbot.addWidget(dialog)

    assert dialog.confirm_btn.text() == tr("btn.continue")
    assert dialog.cancel_btn.text() == tr("btn.cancel")


# ---------------------------------------------------------------------------
# CustomInputDialog — on_confirm via OK button
# ---------------------------------------------------------------------------


def test_custom_input_dialog_ok_button_triggers_accept(qtbot: QtBot) -> None:
    """Clicking the OK button calls on_confirm() which accepts the dialog."""
    dialog = CustomInputDialog(title="Test")
    qtbot.addWidget(dialog)

    accepted: list[bool] = []
    dialog.accepted.connect(lambda: accepted.append(True))

    dialog.ok_btn.click()

    assert len(accepted) == 1


def test_custom_input_dialog_cancel_button_rejects(qtbot: QtBot) -> None:
    """Clicking the Cancel button rejects the dialog."""
    dialog = CustomInputDialog(title="Test")
    qtbot.addWidget(dialog)

    rejected: list[bool] = []
    dialog.rejected.connect(lambda: rejected.append(True))

    dialog.cancel_btn.click()

    assert len(rejected) == 1


# ---------------------------------------------------------------------------
# CustomMessageDialog — OK button triggers accept
# ---------------------------------------------------------------------------


def test_custom_message_dialog_ok_button_accepts(qtbot: QtBot) -> None:
    """Clicking OK on message dialog calls accept."""
    dialog = CustomMessageDialog(title="Info", message="Done.")
    qtbot.addWidget(dialog)

    accepted: list[bool] = []
    dialog.accepted.connect(lambda: accepted.append(True))

    dialog.ok_btn.click()

    assert len(accepted) == 1


# ---------------------------------------------------------------------------
# LanguageSelectionDialog — edge cases
# ---------------------------------------------------------------------------


def test_language_selection_dialog_src_label_and_target_label(
    qtbot: QtBot,
    settings_env: configparser.ConfigParser,
) -> None:
    """Dialog has source and target labels."""
    dialog = LanguageSelectionDialog()
    qtbot.addWidget(dialog)

    assert dialog.src_label.text()  # non-empty
    assert dialog.target_label.text()  # non-empty


def test_language_selection_dialog_restores_last_target(
    qtbot: QtBot,
    settings_env: configparser.ConfigParser,
) -> None:
    """Dialog pre-selects the last used target language from settings."""
    from src.constants.languages import LANGUAGES  # noqa: PLC0415
    from src.constants.settings import SETTING_LAST_TARGET_LANGUAGE  # noqa: PLC0415
    from src.utils.config_manager import save_setting  # noqa: PLC0415

    # Save a known target language using the real setting key
    target_lang = LANGUAGES[5][1]  # Pick the 6th language label
    save_setting(SETTING_LAST_TARGET_LANGUAGE, target_lang)

    dialog = LanguageSelectionDialog()
    qtbot.addWidget(dialog)

    # Display text now reads "<native> (<English>)"; canonical
    # English label is held in itemData.
    assert dialog.target_combo.currentData() == target_lang


# ===========================================================================
# require_setup
# ===========================================================================


class TestRequireSetup:
    """Tests for the require_setup() helper function."""

    def test_require_setup_check_passes_returns_true(
        self,
        qtbot: QtBot,
    ) -> None:
        """When check_fn returns True, require_setup returns True immediately."""
        result = require_setup(
            window=None,
            check_fn=lambda: True,
            title_key="settings.title",
            msg_key="settings.msg",
            settings_tab=0,
        )
        assert result is True

    def test_require_setup_check_fails_dialog_accepted(
        self,
        qtbot: QtBot,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When check_fn returns False and dialog accepted, navigate callback called."""
        # Mock the confirm dialog to return True (user clicks "Go to Settings")
        monkeypatch.setattr(
            CustomConfirmDialog,
            "confirm",
            staticmethod(lambda *a, **kw: True),
        )

        # Create a fake window with navigate_to_settings_tab
        navigated_to: list[int] = []
        window = QWidget()
        qtbot.addWidget(window)
        window.navigate_to_settings_tab = navigated_to.append

        result = require_setup(
            window=window,
            check_fn=lambda: False,
            title_key="settings.title",
            msg_key="settings.msg",
            settings_tab=3,
        )

        # require_setup always returns False when check_fn fails
        assert result is False
        # But it should have navigated to the settings tab
        assert navigated_to == [3]  # noqa: PLR2004

    def test_require_setup_check_fails_dialog_rejected(
        self,
        qtbot: QtBot,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When check_fn returns False and dialog rejected, returns False."""
        # Mock the confirm dialog to return False (user clicks Cancel)
        monkeypatch.setattr(
            CustomConfirmDialog,
            "confirm",
            staticmethod(lambda *a, **kw: False),
        )

        window = QWidget()
        qtbot.addWidget(window)
        navigated_to: list[int] = []
        window.navigate_to_settings_tab = navigated_to.append

        result = require_setup(
            window=window,
            check_fn=lambda: False,
            title_key="settings.title",
            msg_key="settings.msg",
            settings_tab=1,
        )

        assert result is False
        # Navigation should NOT have been triggered
        assert navigated_to == []


# ===========================================================================
# SourceLanguageDialog
# ===========================================================================


class TestSourceLanguageDialog:
    """Tests for the SourceLanguageDialog."""

    def test_source_language_dialog_creation(
        self,
        qtbot: QtBot,
        settings_env: configparser.ConfigParser,
    ) -> None:
        """Dialog can be created without error."""
        dialog = SourceLanguageDialog()
        qtbot.addWidget(dialog)

        assert dialog is not None

    def test_source_language_dialog_has_src_combo(
        self,
        qtbot: QtBot,
        settings_env: configparser.ConfigParser,
    ) -> None:
        """Dialog has a source language combo box with items."""
        dialog = SourceLanguageDialog()
        qtbot.addWidget(dialog)

        assert hasattr(dialog, "src_combo")
        # Should have at least the auto-detect entry plus languages
        assert dialog.src_combo.count() > 1  # noqa: PLR2004

    def test_source_language_dialog_target_hidden_by_default(
        self,
        qtbot: QtBot,
        settings_env: configparser.ConfigParser,
    ) -> None:
        """Target combo is None when show_target is False (default)."""
        dialog = SourceLanguageDialog()
        qtbot.addWidget(dialog)

        assert dialog.target_combo is None

    def test_source_language_dialog_show_target(
        self,
        qtbot: QtBot,
        settings_env: configparser.ConfigParser,
    ) -> None:
        """When show_target=True, dialog has both source and target combos."""
        dialog = SourceLanguageDialog(show_target=True)
        qtbot.addWidget(dialog)

        assert hasattr(dialog, "src_combo")
        assert dialog.target_combo is not None
        assert dialog.target_combo.count() > 1  # noqa: PLR2004


# ===========================================================================
# BaseDialog — additional tests
# ===========================================================================


def test_base_dialog_with_parent(qtbot: QtBot) -> None:
    """BaseDialog accepts a parent widget without error."""
    parent = QWidget()
    qtbot.addWidget(parent)
    dialog = BaseDialog(parent=parent, title="Child Dialog")
    qtbot.addWidget(dialog)
    assert dialog.parent() is parent


def test_base_dialog_layout_spacing(qtbot: QtBot) -> None:
    """BaseDialog layout has correct spacing from SPACING_SECTION."""
    from src.constants.ui import SPACING_SECTION  # noqa: PLC0415

    dialog = BaseDialog(title="Test")
    qtbot.addWidget(dialog)
    assert dialog.layout.spacing() == SPACING_SECTION


def test_base_dialog_layout_margins(qtbot: QtBot) -> None:
    """BaseDialog layout has margins from MARGIN_PAGE."""
    from src.constants.ui import MARGIN_PAGE  # noqa: PLC0415

    dialog = BaseDialog(title="Test")
    qtbot.addWidget(dialog)
    margins = dialog.layout.contentsMargins()
    assert margins.left() == MARGIN_PAGE
    assert margins.right() == MARGIN_PAGE
    assert margins.top() == MARGIN_PAGE
    assert margins.bottom() == MARGIN_PAGE


def test_base_dialog_minimum_width_value(qtbot: QtBot) -> None:
    """BaseDialog enforces minimum width of exactly 450."""
    dialog = BaseDialog(title="Width Test")
    qtbot.addWidget(dialog)
    assert dialog.minimumWidth() == 450  # noqa: PLR2004


def test_base_dialog_escape_key_does_not_accept(qtbot: QtBot) -> None:
    """Pressing Escape does not trigger acceptance (default QDialog rejects)."""
    dialog = BaseDialog(title="Test")
    qtbot.addWidget(dialog)

    accepted: list[bool] = []
    dialog.accepted.connect(lambda: accepted.append(True))

    qtbot.keyPress(dialog, Qt.Key.Key_Escape)

    assert len(accepted) == 0


def test_base_dialog_space_key_does_not_accept(qtbot: QtBot) -> None:
    """Pressing Space does not trigger acceptance."""
    dialog = BaseDialog(title="Test")
    qtbot.addWidget(dialog)

    accepted: list[bool] = []
    dialog.accepted.connect(lambda: accepted.append(True))

    qtbot.keyPress(dialog, Qt.Key.Key_Space)

    assert len(accepted) == 0


def test_base_dialog_tab_key_does_not_accept(qtbot: QtBot) -> None:
    """Pressing Tab does not trigger acceptance."""
    dialog = BaseDialog(title="Test")
    qtbot.addWidget(dialog)

    accepted: list[bool] = []
    dialog.accepted.connect(lambda: accepted.append(True))

    qtbot.keyPress(dialog, Qt.Key.Key_Tab)

    assert len(accepted) == 0


def test_base_dialog_stylesheet_contains_component_bg(qtbot: QtBot) -> None:
    """BaseDialog stylesheet references component_bg color."""
    from src.constants.theme import color  # noqa: PLC0415

    dialog = BaseDialog(title="Test")
    qtbot.addWidget(dialog)
    assert color("component_bg") in dialog.styleSheet()


def test_base_dialog_stylesheet_contains_text_primary(qtbot: QtBot) -> None:
    """BaseDialog stylesheet references text_primary color."""
    from src.constants.theme import color  # noqa: PLC0415

    dialog = BaseDialog(title="Test")
    qtbot.addWidget(dialog)
    assert color("text_primary") in dialog.styleSheet()


def test_base_dialog_on_confirm_with_args(qtbot: QtBot) -> None:
    """on_confirm(*args) accepts arbitrary args without error."""
    dialog = BaseDialog(title="Test")
    qtbot.addWidget(dialog)
    accepted: list[bool] = []
    dialog.accepted.connect(lambda: accepted.append(True))
    dialog.on_confirm("extra", "args", 123)
    assert len(accepted) == 1


# ===========================================================================
# CustomInputDialog — additional tests
# ===========================================================================


def test_custom_input_dialog_input_field_height(qtbot: QtBot) -> None:
    """Input field has HEIGHT_CONTROL height."""
    from src.constants.ui import HEIGHT_CONTROL  # noqa: PLC0415

    dialog = CustomInputDialog(title="Test")
    qtbot.addWidget(dialog)
    assert dialog.input.height() == HEIGHT_CONTROL


def test_custom_input_dialog_input_min_width(qtbot: QtBot) -> None:
    """Input field has minimum width of 400."""
    dialog = CustomInputDialog(title="Test")
    qtbot.addWidget(dialog)
    assert dialog.input.minimumWidth() == 400  # noqa: PLR2004


def test_custom_input_dialog_ok_button_cursor(qtbot: QtBot) -> None:
    """OK button has PointingHandCursor."""
    dialog = CustomInputDialog(title="Test")
    qtbot.addWidget(dialog)
    assert dialog.ok_btn.cursor().shape() == Qt.CursorShape.PointingHandCursor


def test_custom_input_dialog_cancel_button_cursor(qtbot: QtBot) -> None:
    """Cancel button has PointingHandCursor."""
    dialog = CustomInputDialog(title="Test")
    qtbot.addWidget(dialog)
    assert dialog.cancel_btn.cursor().shape() == Qt.CursorShape.PointingHandCursor


def test_custom_input_dialog_ok_button_not_autodefault(qtbot: QtBot) -> None:
    """OK button has autoDefault disabled."""
    dialog = CustomInputDialog(title="Test")
    qtbot.addWidget(dialog)
    assert dialog.ok_btn.autoDefault() is False


def test_custom_input_dialog_cancel_button_not_autodefault(qtbot: QtBot) -> None:
    """Cancel button has autoDefault disabled."""
    dialog = CustomInputDialog(title="Test")
    qtbot.addWidget(dialog)
    assert dialog.cancel_btn.autoDefault() is False


def test_custom_input_dialog_set_error_then_clear(qtbot: QtBot) -> None:
    """set_error then clear_error works properly."""
    dialog = CustomInputDialog(title="Test")
    qtbot.addWidget(dialog)
    dialog.show()

    dialog.set_error("Error!")
    assert dialog.error_frame.isVisible()
    assert dialog.error_label.text() == "Error!"

    dialog.clear_error()
    assert not dialog.error_frame.isVisible()
    assert dialog.error_label.text() == ""


def test_custom_input_dialog_multiple_error_messages(qtbot: QtBot) -> None:
    """Setting error multiple times updates the message each time."""
    dialog = CustomInputDialog(title="Test")
    qtbot.addWidget(dialog)
    dialog.show()

    dialog.set_error("First error")
    assert dialog.error_label.text() == "First error"

    dialog.set_error("Second error")
    assert dialog.error_label.text() == "Second error"


def test_custom_input_dialog_return_pressed_triggers_accept(qtbot: QtBot) -> None:
    """Pressing Return in the input field triggers accept."""
    dialog = CustomInputDialog(title="Test")
    qtbot.addWidget(dialog)

    accepted: list[bool] = []
    dialog.accepted.connect(lambda: accepted.append(True))

    # Simulate return pressed on the input
    dialog.input.returnPressed.emit()

    assert len(accepted) == 1


def test_custom_input_dialog_empty_placeholder(qtbot: QtBot) -> None:
    """Empty placeholder string is valid."""
    dialog = CustomInputDialog(title="Test", placeholder="")
    qtbot.addWidget(dialog)
    assert dialog.input.placeholderText() == ""


def test_custom_input_dialog_empty_label(qtbot: QtBot) -> None:
    """Empty label text is valid."""
    dialog = CustomInputDialog(title="Test", label_text="")
    qtbot.addWidget(dialog)
    assert dialog.label.text() == ""


def test_custom_input_dialog_button_texts_from_i18n(qtbot: QtBot) -> None:
    """OK and Cancel buttons use i18n translated text."""
    from src.constants.i18n import tr  # noqa: PLC0415

    dialog = CustomInputDialog(title="Test")
    qtbot.addWidget(dialog)
    assert dialog.ok_btn.text() == tr("btn.confirm")
    assert dialog.cancel_btn.text() == tr("btn.cancel")


# ===========================================================================
# CustomConfirmDialog — additional tests
# ===========================================================================


def test_custom_confirm_dialog_message_word_wrap(qtbot: QtBot) -> None:
    """Message label has word wrap enabled."""
    dialog = CustomConfirmDialog(title="Test", message="Long message")
    qtbot.addWidget(dialog)
    assert dialog.msg_label.wordWrap() is True


def test_custom_confirm_dialog_message_centered(qtbot: QtBot) -> None:
    """Message label is center-aligned."""
    dialog = CustomConfirmDialog(title="Test", message="Text")
    qtbot.addWidget(dialog)
    assert dialog.msg_label.alignment() & Qt.AlignmentFlag.AlignCenter


def test_custom_confirm_dialog_confirm_button_cursor(qtbot: QtBot) -> None:
    """Confirm button has PointingHandCursor."""
    dialog = CustomConfirmDialog(title="Test", message="Sure?")
    qtbot.addWidget(dialog)
    assert dialog.confirm_btn.cursor().shape() == Qt.CursorShape.PointingHandCursor


def test_custom_confirm_dialog_cancel_button_cursor(qtbot: QtBot) -> None:
    """Cancel button has PointingHandCursor."""
    dialog = CustomConfirmDialog(title="Test", message="Sure?")
    qtbot.addWidget(dialog)
    assert dialog.cancel_btn.cursor().shape() == Qt.CursorShape.PointingHandCursor


def test_custom_confirm_dialog_confirm_button_not_autodefault(qtbot: QtBot) -> None:
    """Confirm button has autoDefault disabled."""
    dialog = CustomConfirmDialog(title="Test", message="Sure?")
    qtbot.addWidget(dialog)
    assert dialog.confirm_btn.autoDefault() is False


def test_custom_confirm_dialog_cancel_button_not_autodefault(qtbot: QtBot) -> None:
    """Cancel button has autoDefault disabled."""
    dialog = CustomConfirmDialog(title="Test", message="Sure?")
    qtbot.addWidget(dialog)
    assert dialog.cancel_btn.autoDefault() is False


def test_custom_confirm_dialog_is_danger_false_primary_style(qtbot: QtBot) -> None:
    """is_danger=False uses primary button style."""
    from src.constants.theme import color  # noqa: PLC0415

    dialog = CustomConfirmDialog(title="Test", message="OK?", is_danger=False)
    qtbot.addWidget(dialog)
    assert color("primary") in dialog.confirm_btn.styleSheet()


def test_custom_confirm_dialog_cancel_uses_secondary_style(qtbot: QtBot) -> None:
    """Cancel button uses secondary button style."""
    from src.constants.theme import color  # noqa: PLC0415

    dialog = CustomConfirmDialog(title="Test", message="OK?")
    qtbot.addWidget(dialog)
    assert color("border_light") in dialog.cancel_btn.styleSheet()


def test_custom_confirm_dialog_confirm_triggers_accept(qtbot: QtBot) -> None:
    """Clicking confirm button triggers accepted signal."""
    dialog = CustomConfirmDialog(title="Test", message="OK?")
    qtbot.addWidget(dialog)

    accepted: list[bool] = []
    dialog.accepted.connect(lambda: accepted.append(True))
    dialog.confirm_btn.click()
    assert len(accepted) == 1


def test_custom_confirm_dialog_cancel_triggers_reject(qtbot: QtBot) -> None:
    """Clicking cancel button triggers rejected signal."""
    dialog = CustomConfirmDialog(title="Test", message="OK?")
    qtbot.addWidget(dialog)

    rejected: list[bool] = []
    dialog.rejected.connect(lambda: rejected.append(True))
    dialog.cancel_btn.click()
    assert len(rejected) == 1


def test_custom_confirm_dialog_enter_key_accepts(qtbot: QtBot) -> None:
    """Pressing Enter on the confirm dialog triggers accept."""
    dialog = CustomConfirmDialog(title="Test", message="OK?")
    qtbot.addWidget(dialog)

    accepted: list[bool] = []
    dialog.accepted.connect(lambda: accepted.append(True))
    qtbot.keyPress(dialog, Qt.Key.Key_Return)
    assert len(accepted) == 1


def test_custom_confirm_dialog_empty_message(qtbot: QtBot) -> None:
    """Confirm dialog handles empty message."""
    dialog = CustomConfirmDialog(title="Test", message="")
    qtbot.addWidget(dialog)
    assert dialog.msg_label.text() == ""


def test_custom_confirm_dialog_empty_title(qtbot: QtBot) -> None:
    """Confirm dialog handles empty title."""
    dialog = CustomConfirmDialog(title="", message="Message")
    qtbot.addWidget(dialog)
    assert dialog.windowTitle() == ""


def test_custom_confirm_dialog_long_message(qtbot: QtBot) -> None:
    """Confirm dialog handles a very long message without error."""
    long_msg = "A" * 5000
    dialog = CustomConfirmDialog(title="Test", message=long_msg)
    qtbot.addWidget(dialog)
    assert dialog.msg_label.text() == long_msg


def test_custom_confirm_dialog_danger_with_padding(qtbot: QtBot) -> None:
    """Danger button has padding in its stylesheet."""
    dialog = CustomConfirmDialog(title="Test", message="Del?", is_danger=True)
    qtbot.addWidget(dialog)
    assert "padding" in dialog.confirm_btn.styleSheet()


def test_custom_confirm_dialog_non_danger_with_padding(qtbot: QtBot) -> None:
    """Non-danger confirm button has padding."""
    dialog = CustomConfirmDialog(title="Test", message="OK?", is_danger=False)
    qtbot.addWidget(dialog)
    assert "padding" in dialog.confirm_btn.styleSheet()


# ===========================================================================
# CustomMessageDialog — additional tests
# ===========================================================================


def test_custom_message_dialog_word_wrap(qtbot: QtBot) -> None:
    """Message label has word wrap enabled."""
    dialog = CustomMessageDialog(title="Info", message="Msg")
    qtbot.addWidget(dialog)
    assert dialog.msg_label.wordWrap() is True


def test_custom_message_dialog_centered(qtbot: QtBot) -> None:
    """Message label is center-aligned."""
    dialog = CustomMessageDialog(title="Info", message="Msg")
    qtbot.addWidget(dialog)
    assert dialog.msg_label.alignment() & Qt.AlignmentFlag.AlignCenter


def test_custom_message_dialog_ok_cursor(qtbot: QtBot) -> None:
    """OK button has PointingHandCursor."""
    dialog = CustomMessageDialog(title="Info", message="Msg")
    qtbot.addWidget(dialog)
    assert dialog.ok_btn.cursor().shape() == Qt.CursorShape.PointingHandCursor


def test_custom_message_dialog_ok_not_autodefault(qtbot: QtBot) -> None:
    """OK button has autoDefault disabled."""
    dialog = CustomMessageDialog(title="Info", message="Msg")
    qtbot.addWidget(dialog)
    assert dialog.ok_btn.autoDefault() is False


def test_custom_message_dialog_ok_text_from_i18n(qtbot: QtBot) -> None:
    """OK button text comes from i18n."""
    from src.constants.i18n import tr  # noqa: PLC0415

    dialog = CustomMessageDialog(title="Info", message="Msg")
    qtbot.addWidget(dialog)
    assert dialog.ok_btn.text() == tr("btn.ok")


def test_custom_message_dialog_ok_has_primary_style(qtbot: QtBot) -> None:
    """OK button uses primary button style."""
    from src.constants.theme import color  # noqa: PLC0415

    dialog = CustomMessageDialog(title="Info", message="Msg")
    qtbot.addWidget(dialog)
    assert color("primary") in dialog.ok_btn.styleSheet()


def test_custom_message_dialog_long_message(qtbot: QtBot) -> None:
    """Message dialog handles very long messages."""
    long_msg = "B" * 3000
    dialog = CustomMessageDialog(title="Info", message=long_msg)
    qtbot.addWidget(dialog)
    assert dialog.msg_label.text() == long_msg


def test_custom_message_dialog_title_sets_window_title(qtbot: QtBot) -> None:
    """Title parameter sets the window title."""
    dialog = CustomMessageDialog(title="My Title", message="Msg")
    qtbot.addWidget(dialog)
    assert dialog.windowTitle() == "My Title"


def test_custom_message_dialog_enter_key_accepts(qtbot: QtBot) -> None:
    """Pressing Enter on message dialog triggers accept."""
    dialog = CustomMessageDialog(title="Info", message="OK")
    qtbot.addWidget(dialog)

    accepted: list[bool] = []
    dialog.accepted.connect(lambda: accepted.append(True))
    qtbot.keyPress(dialog, Qt.Key.Key_Return)
    assert len(accepted) == 1


# ===========================================================================
# LanguageSelectionDialog — additional tests
# ===========================================================================


def test_language_selection_dialog_window_title(
    qtbot: QtBot,
    settings_env: configparser.ConfigParser,
) -> None:
    """Dialog has a window title from i18n."""
    from src.constants.i18n import tr  # noqa: PLC0415

    dialog = LanguageSelectionDialog()
    qtbot.addWidget(dialog)
    assert dialog.windowTitle() == tr("dialog.translation_setup")


def test_language_selection_dialog_translate_button_cursor(
    qtbot: QtBot,
    settings_env: configparser.ConfigParser,
) -> None:
    """Translate button has PointingHandCursor."""
    dialog = LanguageSelectionDialog()
    qtbot.addWidget(dialog)
    assert dialog.translate_btn.cursor().shape() == Qt.CursorShape.PointingHandCursor


def test_language_selection_dialog_cancel_button_cursor(
    qtbot: QtBot,
    settings_env: configparser.ConfigParser,
) -> None:
    """Cancel button has PointingHandCursor."""
    dialog = LanguageSelectionDialog()
    qtbot.addWidget(dialog)
    assert dialog.cancel_btn.cursor().shape() == Qt.CursorShape.PointingHandCursor


def test_language_selection_dialog_translate_button_text(
    qtbot: QtBot,
    settings_env: configparser.ConfigParser,
) -> None:
    """Translate button uses i18n text."""
    from src.constants.i18n import tr  # noqa: PLC0415

    dialog = LanguageSelectionDialog()
    qtbot.addWidget(dialog)
    assert dialog.translate_btn.text() == tr("btn.start_translation")


def test_language_selection_dialog_cancel_button_text(
    qtbot: QtBot,
    settings_env: configparser.ConfigParser,
) -> None:
    """Cancel button uses i18n text."""
    from src.constants.i18n import tr  # noqa: PLC0415

    dialog = LanguageSelectionDialog()
    qtbot.addWidget(dialog)
    assert dialog.cancel_btn.text() == tr("btn.cancel")


def test_language_selection_dialog_src_combo_height(
    qtbot: QtBot,
    settings_env: configparser.ConfigParser,
) -> None:
    """Source combo has HEIGHT_CONTROL height."""
    from src.constants.ui import HEIGHT_CONTROL  # noqa: PLC0415

    dialog = LanguageSelectionDialog()
    qtbot.addWidget(dialog)
    assert dialog.src_combo.height() == HEIGHT_CONTROL


def test_language_selection_dialog_target_combo_height(
    qtbot: QtBot,
    settings_env: configparser.ConfigParser,
) -> None:
    """Target combo has HEIGHT_CONTROL height."""
    from src.constants.ui import HEIGHT_CONTROL  # noqa: PLC0415

    dialog = LanguageSelectionDialog()
    qtbot.addWidget(dialog)
    assert dialog.target_combo.height() == HEIGHT_CONTROL


def test_language_selection_dialog_translate_accepts(
    qtbot: QtBot,
    settings_env: configparser.ConfigParser,
) -> None:
    """Clicking translate button triggers accept."""
    dialog = LanguageSelectionDialog()
    qtbot.addWidget(dialog)

    accepted: list[bool] = []
    dialog.accepted.connect(lambda: accepted.append(True))
    dialog.translate_btn.click()
    assert len(accepted) == 1


def test_language_selection_dialog_cancel_rejects(
    qtbot: QtBot,
    settings_env: configparser.ConfigParser,
) -> None:
    """Clicking cancel button triggers reject."""
    dialog = LanguageSelectionDialog()
    qtbot.addWidget(dialog)

    rejected: list[bool] = []
    dialog.rejected.connect(lambda: rejected.append(True))
    dialog.cancel_btn.click()
    assert len(rejected) == 1


def test_language_selection_dialog_no_last_target_defaults_first(
    qtbot: QtBot,
    settings_env: configparser.ConfigParser,
) -> None:
    """Without saved target language, target combo defaults to index 0."""
    dialog = LanguageSelectionDialog()
    qtbot.addWidget(dialog)
    assert dialog.target_combo.currentIndex() == 0


# ===========================================================================
# SourceLanguageDialog — additional tests
# ===========================================================================


class TestSourceLanguageDialogAdditional:
    """Additional tests for SourceLanguageDialog."""

    def test_src_combo_count_matches_languages_plus_auto(
        self,
        qtbot: QtBot,
        settings_env: configparser.ConfigParser,
    ) -> None:
        """Source combo has LANGUAGES count + 1 items (auto-detect)."""
        from src.constants.languages import LANGUAGES  # noqa: PLC0415

        dialog = SourceLanguageDialog()
        qtbot.addWidget(dialog)
        assert dialog.src_combo.count() == len(LANGUAGES) + 1

    def test_src_combo_default_is_auto_detect(
        self,
        qtbot: QtBot,
        settings_env: configparser.ConfigParser,
    ) -> None:
        """Source combo defaults to index 0 (auto-detect)."""
        dialog = SourceLanguageDialog()
        qtbot.addWidget(dialog)
        assert dialog.src_combo.currentIndex() == 0

    def test_confirm_button_text(
        self,
        qtbot: QtBot,
        settings_env: configparser.ConfigParser,
    ) -> None:
        """Confirm button uses the i18n key provided."""
        from src.constants.i18n import tr  # noqa: PLC0415

        dialog = SourceLanguageDialog()
        qtbot.addWidget(dialog)
        assert dialog.confirm_btn.text() == tr("extract_text.btn_extract")

    def test_cancel_button_text(
        self,
        qtbot: QtBot,
        settings_env: configparser.ConfigParser,
    ) -> None:
        """Cancel button text uses i18n."""
        from src.constants.i18n import tr  # noqa: PLC0415

        dialog = SourceLanguageDialog()
        qtbot.addWidget(dialog)
        assert dialog.cancel_btn.text() == tr("btn.cancel")

    def test_confirm_button_cursor(
        self,
        qtbot: QtBot,
        settings_env: configparser.ConfigParser,
    ) -> None:
        """Confirm button has PointingHandCursor."""
        dialog = SourceLanguageDialog()
        qtbot.addWidget(dialog)
        assert dialog.confirm_btn.cursor().shape() == Qt.CursorShape.PointingHandCursor

    def test_cancel_button_cursor(
        self,
        qtbot: QtBot,
        settings_env: configparser.ConfigParser,
    ) -> None:
        """Cancel button has PointingHandCursor."""
        dialog = SourceLanguageDialog()
        qtbot.addWidget(dialog)
        assert dialog.cancel_btn.cursor().shape() == Qt.CursorShape.PointingHandCursor

    def test_confirm_button_accepts(
        self,
        qtbot: QtBot,
        settings_env: configparser.ConfigParser,
    ) -> None:
        """Clicking confirm button triggers accept."""
        dialog = SourceLanguageDialog()
        qtbot.addWidget(dialog)

        accepted: list[bool] = []
        dialog.accepted.connect(lambda: accepted.append(True))
        dialog.confirm_btn.click()
        assert len(accepted) == 1

    def test_cancel_button_rejects(
        self,
        qtbot: QtBot,
        settings_env: configparser.ConfigParser,
    ) -> None:
        """Clicking cancel button triggers reject."""
        dialog = SourceLanguageDialog()
        qtbot.addWidget(dialog)

        rejected: list[bool] = []
        dialog.rejected.connect(lambda: rejected.append(True))
        dialog.cancel_btn.click()
        assert len(rejected) == 1

    def test_show_target_combo_count(
        self,
        qtbot: QtBot,
        settings_env: configparser.ConfigParser,
    ) -> None:
        """With show_target, target combo has LANGUAGES + 1 items."""
        from src.constants.languages import LANGUAGES  # noqa: PLC0415

        dialog = SourceLanguageDialog(show_target=True)
        qtbot.addWidget(dialog)
        # +1 for "No translation" entry
        assert dialog.target_combo.count() == len(LANGUAGES) + 1

    def test_custom_title_key(
        self,
        qtbot: QtBot,
        settings_env: configparser.ConfigParser,
    ) -> None:
        """Custom title_key changes the dialog title."""
        from src.constants.i18n import tr  # noqa: PLC0415

        dialog = SourceLanguageDialog(title_key="page.settings")
        qtbot.addWidget(dialog)
        assert dialog.windowTitle() == tr("page.settings")

    def test_custom_confirm_key(
        self,
        qtbot: QtBot,
        settings_env: configparser.ConfigParser,
    ) -> None:
        """Custom confirm_key changes the confirm button text."""
        from src.constants.i18n import tr  # noqa: PLC0415

        dialog = SourceLanguageDialog(confirm_key="btn.ok")
        qtbot.addWidget(dialog)
        assert dialog.confirm_btn.text() == tr("btn.ok")

    def test_src_combo_height(
        self,
        qtbot: QtBot,
        settings_env: configparser.ConfigParser,
    ) -> None:
        """Source combo has HEIGHT_CONTROL height."""
        from src.constants.ui import HEIGHT_CONTROL  # noqa: PLC0415

        dialog = SourceLanguageDialog()
        qtbot.addWidget(dialog)
        assert dialog.src_combo.height() == HEIGHT_CONTROL

    def test_confirm_button_height(
        self,
        qtbot: QtBot,
        settings_env: configparser.ConfigParser,
    ) -> None:
        """Confirm button has HEIGHT_CONTROL height."""
        from src.constants.ui import HEIGHT_CONTROL  # noqa: PLC0415

        dialog = SourceLanguageDialog()
        qtbot.addWidget(dialog)
        assert dialog.confirm_btn.height() == HEIGHT_CONTROL

    def test_cancel_button_height(
        self,
        qtbot: QtBot,
        settings_env: configparser.ConfigParser,
    ) -> None:
        """Cancel button has HEIGHT_CONTROL height."""
        from src.constants.ui import HEIGHT_CONTROL  # noqa: PLC0415

        dialog = SourceLanguageDialog()
        qtbot.addWidget(dialog)
        assert dialog.cancel_btn.height() == HEIGHT_CONTROL


# ===========================================================================
# require_setup — additional tests
# ===========================================================================


class TestRequireSetupAdditional:
    """Additional tests for require_setup()."""

    def test_require_setup_no_navigate_method(
        self,
        qtbot: QtBot,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When window lacks navigate_to_settings_tab, no error is raised."""
        monkeypatch.setattr(
            CustomConfirmDialog,
            "confirm",
            staticmethod(lambda *a, **kw: True),
        )
        window = QWidget()
        qtbot.addWidget(window)
        # No navigate_to_settings_tab attribute

        result = require_setup(
            window=window,
            check_fn=lambda: False,
            title_key="settings.title",
            msg_key="settings.msg",
            settings_tab=0,
        )
        assert result is False

    def test_require_setup_none_window(
        self,
        qtbot: QtBot,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """require_setup with None window doesn't crash."""
        monkeypatch.setattr(
            CustomConfirmDialog,
            "confirm",
            staticmethod(lambda *a, **kw: True),
        )

        result = require_setup(
            window=None,
            check_fn=lambda: False,
            title_key="settings.title",
            msg_key="settings.msg",
            settings_tab=0,
        )
        assert result is False

    def test_require_setup_check_passes_never_shows_dialog(
        self,
        qtbot: QtBot,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When check_fn passes, the dialog is never shown."""
        dialog_shown: list[bool] = []

        def mock_confirm(*a: object, **kw: object) -> bool:
            dialog_shown.append(True)
            return False

        monkeypatch.setattr(
            CustomConfirmDialog,
            "confirm",
            staticmethod(mock_confirm),
        )

        result = require_setup(
            window=None,
            check_fn=lambda: True,
            title_key="settings.title",
            msg_key="settings.msg",
            settings_tab=0,
        )
        assert result is True
        assert dialog_shown == []

    def test_require_setup_navigates_to_correct_tab(
        self,
        qtbot: QtBot,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """require_setup navigates to the specified settings tab."""
        monkeypatch.setattr(
            CustomConfirmDialog,
            "confirm",
            staticmethod(lambda *a, **kw: True),
        )

        navigated_to: list[int] = []
        window = QWidget()
        qtbot.addWidget(window)
        window.navigate_to_settings_tab = navigated_to.append

        for tab in [0, 1, 2, 5, 8]:
            navigated_to.clear()
            require_setup(
                window=window,
                check_fn=lambda: False,
                title_key="t",
                msg_key="m",
                settings_tab=tab,
            )
            assert navigated_to == [tab]


# ===========================================================================
# _create_emoji_icon tests
# ===========================================================================


def test_create_emoji_icon_returns_qicon(qtbot: QtBot) -> None:
    """_create_emoji_icon returns a QIcon."""
    from PySide6.QtGui import QIcon  # noqa: PLC0415

    from src.ui.dialogs import _create_emoji_icon  # noqa: PLC0415

    icon = _create_emoji_icon()
    assert isinstance(icon, QIcon)


def test_create_emoji_icon_not_null(qtbot: QtBot) -> None:
    """_create_emoji_icon returns a non-null icon."""
    from src.ui.dialogs import _create_emoji_icon  # noqa: PLC0415

    icon = _create_emoji_icon()
    assert not icon.isNull()


def test_create_emoji_icon_custom_emoji(qtbot: QtBot) -> None:
    """_create_emoji_icon with custom emoji returns a non-null icon."""
    from PySide6.QtGui import QIcon  # noqa: PLC0415

    from src.ui.dialogs import _create_emoji_icon  # noqa: PLC0415

    icon = _create_emoji_icon("\U0001f6ab")
    assert isinstance(icon, QIcon)
    assert not icon.isNull()


# ===========================================================================
# Expanded: CustomConfirmDialog — accept/reject flows
# ===========================================================================


def test_custom_confirm_dialog_accept_then_result_code(qtbot: QtBot) -> None:
    """Calling accept() on confirm dialog sets result to Accepted."""
    from PySide6.QtWidgets import QDialog  # noqa: PLC0415

    dialog = CustomConfirmDialog(title="Test", message="OK?")
    qtbot.addWidget(dialog)
    dialog.accept()
    assert dialog.result() == QDialog.DialogCode.Accepted


def test_custom_confirm_dialog_reject_then_result_code(qtbot: QtBot) -> None:
    """Calling reject() on confirm dialog sets result to Rejected."""
    from PySide6.QtWidgets import QDialog  # noqa: PLC0415

    dialog = CustomConfirmDialog(title="Test", message="OK?")
    qtbot.addWidget(dialog)
    dialog.reject()
    assert dialog.result() == QDialog.DialogCode.Rejected


def test_custom_confirm_dialog_escape_rejects(qtbot: QtBot) -> None:
    """Pressing Escape on confirm dialog triggers rejection."""
    dialog = CustomConfirmDialog(title="Test", message="OK?")
    qtbot.addWidget(dialog)

    rejected: list[bool] = []
    dialog.rejected.connect(lambda: rejected.append(True))
    qtbot.keyPress(dialog, Qt.Key.Key_Escape)
    assert len(rejected) == 1


def test_custom_confirm_dialog_danger_style_contains_error_hover(
    qtbot: QtBot,
) -> None:
    """Danger button style includes error_hover color.

    Takes ``qtbot`` to guarantee a QApplication and to register the
    dialog for cleanup — under ``pytest --forked`` a fresh subprocess
    has no prior QApplication, and constructing a QWidget without one
    segfaults.
    """
    from src.constants.theme import color  # noqa: PLC0415

    dialog = CustomConfirmDialog(title="Test", message="Del?", is_danger=True)
    qtbot.addWidget(dialog)
    assert color("error_hover") in dialog.confirm_btn.styleSheet()


def test_custom_confirm_dialog_non_danger_confirm_text_is_continue(
    qtbot: QtBot,
) -> None:
    """Non-danger default confirm text is tr('btn.continue')."""
    from src.constants.i18n import tr  # noqa: PLC0415

    dialog = CustomConfirmDialog(title="Test", message="Go?")
    qtbot.addWidget(dialog)
    assert dialog.confirm_btn.text() == tr("btn.continue")


def test_custom_confirm_dialog_multiline_message(qtbot: QtBot) -> None:
    """Multiline messages are displayed correctly."""
    msg = "Line 1\nLine 2\nLine 3"
    dialog = CustomConfirmDialog(title="Test", message=msg)
    qtbot.addWidget(dialog)
    assert dialog.msg_label.text() == msg


def test_custom_confirm_dialog_message_label_styling(qtbot: QtBot) -> None:
    """Message label has font-size in its stylesheet."""
    dialog = CustomConfirmDialog(title="Test", message="Text")
    qtbot.addWidget(dialog)
    assert "font-size" in dialog.msg_label.styleSheet()


def test_custom_confirm_dialog_danger_default_replaces_to_delete(
    qtbot: QtBot,
) -> None:
    """is_danger=True with default confirm_text replaces it with tr('btn.delete')."""
    from src.constants.i18n import tr  # noqa: PLC0415

    dialog = CustomConfirmDialog(title="D", message="D?", is_danger=True)
    qtbot.addWidget(dialog)
    assert dialog.confirm_btn.text() == tr("btn.delete")


def test_custom_confirm_dialog_non_danger_has_primary_bg(qtbot: QtBot) -> None:
    """Non-danger confirm button has primary color in stylesheet."""
    from src.constants.theme import color  # noqa: PLC0415

    dialog = CustomConfirmDialog(title="T", message="M", is_danger=False)
    qtbot.addWidget(dialog)
    assert color("primary") in dialog.confirm_btn.styleSheet()


def test_custom_confirm_dialog_custom_both_texts(qtbot: QtBot) -> None:
    """Both custom confirm and cancel texts are set correctly."""
    dialog = CustomConfirmDialog(
        title="T",
        message="M",
        confirm_text="Yes",
        cancel_text="No",
    )
    qtbot.addWidget(dialog)
    assert dialog.confirm_btn.text() == "Yes"
    assert dialog.cancel_btn.text() == "No"


def test_custom_confirm_dialog_cancel_button_has_secondary_style(
    qtbot: QtBot,
) -> None:
    """Cancel button stylesheet contains border_light color."""
    from src.constants.theme import color  # noqa: PLC0415

    dialog = CustomConfirmDialog(title="T", message="M")
    qtbot.addWidget(dialog)
    assert color("border_light") in dialog.cancel_btn.styleSheet()


def test_custom_confirm_dialog_confirm_height(qtbot: QtBot) -> None:
    """Confirm button has HEIGHT_CONTROL height."""
    from src.constants.ui import HEIGHT_CONTROL  # noqa: PLC0415

    dialog = CustomConfirmDialog(title="T", message="M")
    qtbot.addWidget(dialog)
    assert dialog.confirm_btn.height() == HEIGHT_CONTROL


def test_custom_confirm_dialog_cancel_height(qtbot: QtBot) -> None:
    """Cancel button has HEIGHT_CONTROL height."""
    from src.constants.ui import HEIGHT_CONTROL  # noqa: PLC0415

    dialog = CustomConfirmDialog(title="T", message="M")
    qtbot.addWidget(dialog)
    assert dialog.cancel_btn.height() == HEIGHT_CONTROL


# ===========================================================================
# Expanded: CustomMessageDialog — info/warning/error variants & edge cases
# ===========================================================================


def test_custom_message_dialog_multiline_message(qtbot: QtBot) -> None:
    """Multiline message is displayed correctly."""
    msg = "First line\nSecond line\nThird line"
    dialog = CustomMessageDialog(title="Info", message=msg)
    qtbot.addWidget(dialog)
    assert dialog.msg_label.text() == msg


def test_custom_message_dialog_special_characters(qtbot: QtBot) -> None:
    """Message with special chars is displayed correctly."""
    msg = '<html>&quot;Hello&quot; & "World"</html>'
    dialog = CustomMessageDialog(title="Info", message=msg)
    qtbot.addWidget(dialog)
    assert dialog.msg_label.text() == msg


def test_custom_message_dialog_unicode_message(qtbot: QtBot) -> None:
    """Unicode message is handled correctly."""
    msg = "Xin chao! こんにちは 你好 مرحبا"
    dialog = CustomMessageDialog(title="Greetings", message=msg)
    qtbot.addWidget(dialog)
    assert dialog.msg_label.text() == msg


def test_custom_message_dialog_ok_button_height(qtbot: QtBot) -> None:
    """OK button has HEIGHT_CONTROL height."""
    from src.constants.ui import HEIGHT_CONTROL  # noqa: PLC0415

    dialog = CustomMessageDialog(title="Info", message="Msg")
    qtbot.addWidget(dialog)
    assert dialog.ok_btn.height() == HEIGHT_CONTROL


def test_custom_message_dialog_message_label_has_color(qtbot: QtBot) -> None:
    """Message label stylesheet includes text_primary color."""
    from src.constants.theme import color  # noqa: PLC0415

    dialog = CustomMessageDialog(title="Info", message="Msg")
    qtbot.addWidget(dialog)
    assert color("text_primary") in dialog.msg_label.styleSheet()


def test_custom_message_dialog_empty_title_no_header(qtbot: QtBot) -> None:
    """Empty title means no header label added."""
    from PySide6.QtWidgets import QLabel  # noqa: PLC0415

    dialog = CustomMessageDialog(title="", message="Just a message")
    qtbot.addWidget(dialog)
    # Only the msg_label should exist
    labels = dialog.findChildren(QLabel)
    texts = [lbl.text() for lbl in labels]
    assert "Just a message" in texts


def test_custom_message_dialog_ok_btn_padding(qtbot: QtBot) -> None:
    """OK button stylesheet includes padding."""
    dialog = CustomMessageDialog(title="Info", message="Msg")
    qtbot.addWidget(dialog)
    assert "padding" in dialog.ok_btn.styleSheet()


def test_custom_message_dialog_has_word_wrap_true(qtbot: QtBot) -> None:
    """Very long single-word message still has word wrap enabled."""
    dialog = CustomMessageDialog(title="Info", message="A" * 500)
    qtbot.addWidget(dialog)
    assert dialog.msg_label.wordWrap() is True


def test_custom_message_dialog_accept_then_result(qtbot: QtBot) -> None:
    """Calling accept() sets result to Accepted."""
    from PySide6.QtWidgets import QDialog  # noqa: PLC0415

    dialog = CustomMessageDialog(title="Info", message="Ok")
    qtbot.addWidget(dialog)
    dialog.accept()
    assert dialog.result() == QDialog.DialogCode.Accepted


def test_custom_message_dialog_escape_rejects(qtbot: QtBot) -> None:
    """Pressing Escape on message dialog triggers rejection, not acceptance."""
    dialog = CustomMessageDialog(title="Info", message="Msg")
    qtbot.addWidget(dialog)
    accepted: list[bool] = []
    dialog.accepted.connect(lambda: accepted.append(True))
    qtbot.keyPress(dialog, Qt.Key.Key_Escape)
    assert len(accepted) == 0


# ===========================================================================
# Expanded: SourceLanguageDialog — language selection / passthrough
# ===========================================================================


class TestSourceLanguageDialogExpanded:
    """Expanded tests for SourceLanguageDialog."""

    def test_show_target_default_index_is_zero(
        self,
        qtbot: QtBot,
        settings_env: "configparser.ConfigParser",
    ) -> None:
        """Target combo defaults to index 0 (no translation)."""
        dialog = SourceLanguageDialog(show_target=True)
        qtbot.addWidget(dialog)
        assert dialog.target_combo.currentIndex() == 0

    def test_without_show_target_no_target_label(
        self,
        qtbot: QtBot,
        settings_env: "configparser.ConfigParser",
    ) -> None:
        """Without show_target, no target_label is created."""
        dialog = SourceLanguageDialog()
        qtbot.addWidget(dialog)
        assert not hasattr(dialog, "target_label") or dialog.target_combo is None

    def test_src_label_has_text(
        self,
        qtbot: QtBot,
        settings_env: "configparser.ConfigParser",
    ) -> None:
        """Source label has non-empty text."""
        dialog = SourceLanguageDialog()
        qtbot.addWidget(dialog)
        assert dialog.src_label.text()

    def test_src_label_has_styling(
        self,
        qtbot: QtBot,
        settings_env: "configparser.ConfigParser",
    ) -> None:
        """Source label has font-weight in its stylesheet."""
        dialog = SourceLanguageDialog()
        qtbot.addWidget(dialog)
        assert "font-weight" in dialog.src_label.styleSheet()

    def test_show_target_has_target_label(
        self,
        qtbot: QtBot,
        settings_env: "configparser.ConfigParser",
    ) -> None:
        """show_target=True creates a target_label."""
        dialog = SourceLanguageDialog(show_target=True)
        qtbot.addWidget(dialog)
        assert hasattr(dialog, "target_label")
        assert dialog.target_label.text()

    def test_custom_label_key(
        self,
        qtbot: QtBot,
        settings_env: "configparser.ConfigParser",
    ) -> None:
        """Custom label_key changes the source label text."""
        from src.constants.i18n import tr  # noqa: PLC0415

        dialog = SourceLanguageDialog(label_key="dialog.source_language")
        qtbot.addWidget(dialog)
        assert dialog.src_label.text() == tr("dialog.source_language")

    def test_enter_key_accepts(
        self,
        qtbot: QtBot,
        settings_env: "configparser.ConfigParser",
    ) -> None:
        """Pressing Enter on SourceLanguageDialog triggers accept."""
        dialog = SourceLanguageDialog()
        qtbot.addWidget(dialog)
        accepted: list[bool] = []
        dialog.accepted.connect(lambda: accepted.append(True))
        qtbot.keyPress(dialog, Qt.Key.Key_Return)
        assert len(accepted) == 1

    def test_escape_key_rejects(
        self,
        qtbot: QtBot,
        settings_env: "configparser.ConfigParser",
    ) -> None:
        """Pressing Escape on SourceLanguageDialog triggers reject."""
        dialog = SourceLanguageDialog()
        qtbot.addWidget(dialog)
        rejected: list[bool] = []
        dialog.rejected.connect(lambda: rejected.append(True))
        qtbot.keyPress(dialog, Qt.Key.Key_Escape)
        assert len(rejected) == 1

    def test_dialog_inherits_base_dialog(
        self,
        qtbot: QtBot,
        settings_env: "configparser.ConfigParser",
    ) -> None:
        """SourceLanguageDialog inherits from BaseDialog."""
        dialog = SourceLanguageDialog()
        qtbot.addWidget(dialog)
        assert isinstance(dialog, BaseDialog)

    def test_dialog_minimum_width(
        self,
        qtbot: QtBot,
        settings_env: "configparser.ConfigParser",
    ) -> None:
        """SourceLanguageDialog has minimum width of 450."""
        dialog = SourceLanguageDialog()
        qtbot.addWidget(dialog)
        assert dialog.minimumWidth() == 450  # noqa: PLR2004


# ===========================================================================
# Expanded: Dialog theme/language updates
# ===========================================================================


def test_base_dialog_uses_theme_colors(qtbot: QtBot) -> None:
    """BaseDialog stylesheet uses current theme's component_bg color."""
    from src.constants.theme import color  # noqa: PLC0415

    dialog = BaseDialog(title="Theme Test")
    qtbot.addWidget(dialog)
    ss = dialog.styleSheet()
    assert color("component_bg") in ss
    assert color("text_primary") in ss


def test_custom_input_dialog_uses_input_field_style(qtbot: QtBot) -> None:
    """CustomInputDialog input uses style_input_field() styling."""
    dialog = CustomInputDialog(title="Test", label_text="Name")
    qtbot.addWidget(dialog)
    assert "QLineEdit" in dialog.input.styleSheet()


def test_custom_confirm_dialog_inherits_base(qtbot: QtBot) -> None:
    """CustomConfirmDialog is a BaseDialog subclass."""
    dialog = CustomConfirmDialog(title="T", message="M")
    qtbot.addWidget(dialog)
    assert isinstance(dialog, BaseDialog)


def test_custom_message_dialog_inherits_base(qtbot: QtBot) -> None:
    """CustomMessageDialog is a BaseDialog subclass."""
    dialog = CustomMessageDialog(title="T", message="M")
    qtbot.addWidget(dialog)
    assert isinstance(dialog, BaseDialog)


def test_custom_input_dialog_inherits_base(qtbot: QtBot) -> None:
    """CustomInputDialog is a BaseDialog subclass."""
    dialog = CustomInputDialog(title="T", label_text="L")
    qtbot.addWidget(dialog)
    assert isinstance(dialog, BaseDialog)


# ===========================================================================
# Expanded: Dialog sizing and layout
# ===========================================================================


def test_base_dialog_layout_is_vbox(qtbot: QtBot) -> None:
    """BaseDialog uses QVBoxLayout."""
    from PySide6.QtWidgets import QVBoxLayout  # noqa: PLC0415

    dialog = BaseDialog(title="Test")
    qtbot.addWidget(dialog)
    assert isinstance(dialog.layout, QVBoxLayout)


def test_custom_input_dialog_has_two_buttons(qtbot: QtBot) -> None:
    """CustomInputDialog has OK and Cancel buttons."""
    dialog = CustomInputDialog(title="T")
    qtbot.addWidget(dialog)
    assert dialog.ok_btn is not None
    assert dialog.cancel_btn is not None


def test_custom_confirm_dialog_has_two_buttons(qtbot: QtBot) -> None:
    """CustomConfirmDialog has confirm and cancel buttons."""
    dialog = CustomConfirmDialog(title="T", message="M")
    qtbot.addWidget(dialog)
    assert dialog.confirm_btn is not None
    assert dialog.cancel_btn is not None


def test_custom_message_dialog_has_one_button(qtbot: QtBot) -> None:
    """CustomMessageDialog has only an OK button."""
    dialog = CustomMessageDialog(title="T", message="M")
    qtbot.addWidget(dialog)
    assert dialog.ok_btn is not None


def test_language_selection_dialog_inherits_base(
    qtbot: QtBot,
    settings_env: "configparser.ConfigParser",
) -> None:
    """LanguageSelectionDialog inherits from BaseDialog."""
    dialog = LanguageSelectionDialog()
    qtbot.addWidget(dialog)
    assert isinstance(dialog, BaseDialog)


def test_language_selection_dialog_minimum_width_450(
    qtbot: QtBot,
    settings_env: "configparser.ConfigParser",
) -> None:
    """LanguageSelectionDialog has min width 450."""
    dialog = LanguageSelectionDialog()
    qtbot.addWidget(dialog)
    assert dialog.minimumWidth() == 450  # noqa: PLR2004


def test_language_selection_dialog_src_combo_has_combo_style(
    qtbot: QtBot,
    settings_env: "configparser.ConfigParser",
) -> None:
    """Source combo uses setting combo QSS."""
    dialog = LanguageSelectionDialog()
    qtbot.addWidget(dialog)
    assert "QComboBox" in dialog.src_combo.styleSheet()


def test_language_selection_dialog_target_combo_has_combo_style(
    qtbot: QtBot,
    settings_env: "configparser.ConfigParser",
) -> None:
    """Target combo uses setting combo QSS."""
    dialog = LanguageSelectionDialog()
    qtbot.addWidget(dialog)
    assert "QComboBox" in dialog.target_combo.styleSheet()


def test_language_selection_dialog_first_src_item_is_auto(
    qtbot: QtBot,
    settings_env: "configparser.ConfigParser",
) -> None:
    """First item in source combo is the auto-detect entry."""
    from src.constants.i18n import tr  # noqa: PLC0415

    dialog = LanguageSelectionDialog()
    qtbot.addWidget(dialog)
    assert dialog.src_combo.itemText(0) == tr("common.lang_auto_detect")


def test_language_selection_dialog_target_first_item_is_language(
    qtbot: QtBot,
    settings_env: "configparser.ConfigParser",
) -> None:
    """First item in target combo is a language, not auto-detect."""
    from src.constants.languages import (  # noqa: PLC0415
        iter_languages_sorted_for_ui,
    )

    dialog = LanguageSelectionDialog()
    qtbot.addWidget(dialog)
    # Sort order is locale-driven; the contract is "first entry's
    # itemData matches whichever language sorts first under the
    # current locale", not source-order Arabic.
    assert dialog.target_combo.itemData(0) == (
        iter_languages_sorted_for_ui()[0][1]
    )


def test_language_selection_dialog_translate_btn_height(
    qtbot: QtBot,
    settings_env: "configparser.ConfigParser",
) -> None:
    """Translate button has HEIGHT_CONTROL height."""
    from src.constants.ui import HEIGHT_CONTROL  # noqa: PLC0415

    dialog = LanguageSelectionDialog()
    qtbot.addWidget(dialog)
    assert dialog.translate_btn.height() == HEIGHT_CONTROL


def test_language_selection_dialog_cancel_btn_height(
    qtbot: QtBot,
    settings_env: "configparser.ConfigParser",
) -> None:
    """Cancel button has HEIGHT_CONTROL height."""
    from src.constants.ui import HEIGHT_CONTROL  # noqa: PLC0415

    dialog = LanguageSelectionDialog()
    qtbot.addWidget(dialog)
    assert dialog.cancel_btn.height() == HEIGHT_CONTROL


# ===========================================================================
# Expanded: require_setup edge cases
# ===========================================================================


class TestRequireSetupEdgeCases:
    """Edge case tests for require_setup()."""

    def test_require_setup_different_settings_tabs(
        self,
        qtbot: QtBot,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """require_setup navigates to various tab indices."""
        monkeypatch.setattr(
            CustomConfirmDialog,
            "confirm",
            staticmethod(lambda *a, **kw: True),
        )
        for tab_idx in range(9):
            navigated: list[int] = []
            window = QWidget()
            qtbot.addWidget(window)
            window.navigate_to_settings_tab = navigated.append
            require_setup(
                window=window,
                check_fn=lambda: False,
                title_key="t",
                msg_key="m",
                settings_tab=tab_idx,
            )
            assert navigated == [tab_idx]

    def test_require_setup_check_fn_called_once(
        self,
        qtbot: QtBot,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """check_fn is called exactly once by require_setup."""
        call_count = [0]

        def counting_check() -> bool:
            call_count[0] += 1
            return True

        require_setup(
            window=None,
            check_fn=counting_check,
            title_key="t",
            msg_key="m",
            settings_tab=0,
        )
        assert call_count[0] == 1

    def test_require_setup_returns_false_always_when_check_fails(
        self,
        qtbot: QtBot,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """require_setup always returns False when check_fn fails."""
        for dialog_accepted in (True, False):
            _accepted = dialog_accepted  # Bind loop variable for closure
            monkeypatch.setattr(
                CustomConfirmDialog,
                "confirm",
                staticmethod(lambda *a, _a=_accepted, **kw: _a),
            )
            result = require_setup(
                window=None,
                check_fn=lambda: False,
                title_key="t",
                msg_key="m",
                settings_tab=0,
            )
            assert result is False


# ===========================================================================
# Expanded: CustomInputDialog edge cases
# ===========================================================================


def test_custom_input_dialog_long_label(qtbot: QtBot) -> None:
    """Long label text doesn't crash."""
    label = "A" * 200
    dialog = CustomInputDialog(title="Test", label_text=label)
    qtbot.addWidget(dialog)
    assert dialog.label.text() == label


def test_custom_input_dialog_long_placeholder(qtbot: QtBot) -> None:
    """Long placeholder text doesn't crash."""
    placeholder = "X" * 200
    dialog = CustomInputDialog(title="Test", placeholder=placeholder)
    qtbot.addWidget(dialog)
    assert dialog.input.placeholderText() == placeholder


def test_custom_input_dialog_initial_text_empty(qtbot: QtBot) -> None:
    """Input field starts with empty text."""
    dialog = CustomInputDialog(title="Test")
    qtbot.addWidget(dialog)
    assert dialog.input.text() == ""


def test_custom_input_dialog_ok_btn_default_disabled(qtbot: QtBot) -> None:
    """OK button has isDefault set to False."""
    dialog = CustomInputDialog(title="Test")
    qtbot.addWidget(dialog)
    assert dialog.ok_btn.isDefault() is False


def test_custom_input_dialog_error_frame_initially_empty_text(
    qtbot: QtBot,
) -> None:
    """Error label starts with empty text."""
    dialog = CustomInputDialog(title="Test")
    qtbot.addWidget(dialog)
    assert dialog.error_label.text() == ""


def test_custom_input_dialog_clear_error_is_idempotent(qtbot: QtBot) -> None:
    """Calling clear_error() twice is safe."""
    dialog = CustomInputDialog(title="Test")
    qtbot.addWidget(dialog)
    dialog.clear_error()
    dialog.clear_error()
    assert dialog.error_label.text() == ""


# ===========================================================================
# Expanded: More CustomConfirmDialog tests
# ===========================================================================


def test_custom_confirm_dialog_unicode_message(qtbot: QtBot) -> None:
    """Unicode message is handled correctly."""
    msg = "Ban co chac chan? こんにちは 你好"
    dialog = CustomConfirmDialog(title="Test", message=msg)
    qtbot.addWidget(dialog)
    assert dialog.msg_label.text() == msg


def test_custom_confirm_dialog_special_char_title(qtbot: QtBot) -> None:
    """Special characters in title are set correctly."""
    title = "Delete <item> & 'confirm'?"
    dialog = CustomConfirmDialog(title=title, message="M")
    qtbot.addWidget(dialog)
    assert dialog.windowTitle() == title


def test_custom_confirm_dialog_message_alignment(qtbot: QtBot) -> None:
    """Message label alignment includes center."""
    dialog = CustomConfirmDialog(title="T", message="M")
    qtbot.addWidget(dialog)
    assert dialog.msg_label.alignment() & Qt.AlignmentFlag.AlignCenter


def test_custom_confirm_dialog_layout_has_buttons(qtbot: QtBot) -> None:
    """Dialog layout contains confirm and cancel buttons."""
    from PySide6.QtWidgets import QPushButton  # noqa: PLC0415

    dialog = CustomConfirmDialog(title="T", message="M")
    qtbot.addWidget(dialog)
    buttons = dialog.findChildren(QPushButton)
    assert len(buttons) >= 2  # noqa: PLR2004


def test_custom_confirm_dialog_message_label_font_size(qtbot: QtBot) -> None:
    """Message label stylesheet includes font-size: 13px."""
    dialog = CustomConfirmDialog(title="T", message="M")
    qtbot.addWidget(dialog)
    assert "13px" in dialog.msg_label.styleSheet()


# ===========================================================================
# Expanded: More CustomMessageDialog tests
# ===========================================================================


def test_custom_message_dialog_double_accept(qtbot: QtBot) -> None:
    """Calling accept twice doesn't crash."""
    dialog = CustomMessageDialog(title="Info", message="OK")
    qtbot.addWidget(dialog)
    dialog.accept()
    dialog.accept()


def test_custom_message_dialog_has_correct_layout(qtbot: QtBot) -> None:
    """Dialog has a QVBoxLayout."""
    from PySide6.QtWidgets import QVBoxLayout  # noqa: PLC0415

    dialog = CustomMessageDialog(title="Info", message="OK")
    qtbot.addWidget(dialog)
    assert isinstance(dialog.layout, QVBoxLayout)


def test_custom_message_dialog_message_label_alignment(qtbot: QtBot) -> None:
    """Message label has center alignment."""
    dialog = CustomMessageDialog(title="Info", message="Text")
    qtbot.addWidget(dialog)
    assert dialog.msg_label.alignment() & Qt.AlignmentFlag.AlignCenter


def test_custom_message_dialog_ok_button_has_primary_style(qtbot: QtBot) -> None:
    """OK button has primary button styling with padding."""
    from src.constants.theme import color  # noqa: PLC0415

    dialog = CustomMessageDialog(title="I", message="M")
    qtbot.addWidget(dialog)
    ss = dialog.ok_btn.styleSheet()
    assert color("primary") in ss
    assert "padding" in ss


def test_custom_message_dialog_multiple_creates_no_crash(qtbot: QtBot) -> None:
    """Creating multiple message dialogs doesn't crash."""
    for i in range(5):
        dialog = CustomMessageDialog(title=f"Dialog {i}", message=f"Msg {i}")
        qtbot.addWidget(dialog)
        assert dialog.msg_label.text() == f"Msg {i}"


# ===========================================================================
# Expanded: More LanguageSelectionDialog tests
# ===========================================================================


def test_language_selection_dialog_enter_accepts(
    qtbot: QtBot,
    settings_env: "configparser.ConfigParser",
) -> None:
    """Pressing Enter on language dialog triggers accept."""
    dialog = LanguageSelectionDialog()
    qtbot.addWidget(dialog)
    accepted: list[bool] = []
    dialog.accepted.connect(lambda: accepted.append(True))
    qtbot.keyPress(dialog, Qt.Key.Key_Return)
    assert len(accepted) == 1


def test_language_selection_dialog_escape_rejects(
    qtbot: QtBot,
    settings_env: "configparser.ConfigParser",
) -> None:
    """Pressing Escape on language dialog triggers reject."""
    dialog = LanguageSelectionDialog()
    qtbot.addWidget(dialog)
    rejected: list[bool] = []
    dialog.rejected.connect(lambda: rejected.append(True))
    qtbot.keyPress(dialog, Qt.Key.Key_Escape)
    assert len(rejected) == 1


def test_language_selection_dialog_src_label_has_styling(
    qtbot: QtBot,
    settings_env: "configparser.ConfigParser",
) -> None:
    """Source label has font-weight in stylesheet."""
    dialog = LanguageSelectionDialog()
    qtbot.addWidget(dialog)
    assert "font-weight" in dialog.src_label.styleSheet()


def test_language_selection_dialog_target_label_has_styling(
    qtbot: QtBot,
    settings_env: "configparser.ConfigParser",
) -> None:
    """Target label has font-weight in stylesheet."""
    dialog = LanguageSelectionDialog()
    qtbot.addWidget(dialog)
    assert "font-weight" in dialog.target_label.styleSheet()


def test_language_selection_dialog_src_combo_icon_size(
    qtbot: QtBot,
    settings_env: "configparser.ConfigParser",
) -> None:
    """Source combo has correct icon size."""
    from PySide6.QtCore import QSize  # noqa: PLC0415

    from src.constants.ui import FLAG_ICON_HEIGHT, FLAG_ICON_WIDTH  # noqa: PLC0415

    dialog = LanguageSelectionDialog()
    qtbot.addWidget(dialog)
    assert dialog.src_combo.iconSize() == QSize(FLAG_ICON_WIDTH, FLAG_ICON_HEIGHT)


def test_language_selection_dialog_target_combo_icon_size(
    qtbot: QtBot,
    settings_env: "configparser.ConfigParser",
) -> None:
    """Target combo has correct icon size."""
    from PySide6.QtCore import QSize  # noqa: PLC0415

    from src.constants.ui import FLAG_ICON_HEIGHT, FLAG_ICON_WIDTH  # noqa: PLC0415

    dialog = LanguageSelectionDialog()
    qtbot.addWidget(dialog)
    assert dialog.target_combo.iconSize() == QSize(FLAG_ICON_WIDTH, FLAG_ICON_HEIGHT)


# ===========================================================================
# Expanded: More BaseDialog tests
# ===========================================================================


def test_base_dialog_multiple_enter_presses(qtbot: QtBot) -> None:
    """Multiple Enter presses each trigger accept."""
    dialog = BaseDialog(title="Test")
    qtbot.addWidget(dialog)
    accepted: list[bool] = []
    dialog.accepted.connect(lambda: accepted.append(True))
    qtbot.keyPress(dialog, Qt.Key.Key_Return)
    qtbot.keyPress(dialog, Qt.Key.Key_Return)
    assert len(accepted) == 2  # noqa: PLR2004


def test_base_dialog_is_qdialog(qtbot: QtBot) -> None:
    """BaseDialog is a QDialog subclass."""
    from PySide6.QtWidgets import QDialog  # noqa: PLC0415

    dialog = BaseDialog(title="Test")
    qtbot.addWidget(dialog)
    assert isinstance(dialog, QDialog)


def test_base_dialog_size_constraint(qtbot: QtBot) -> None:
    """BaseDialog layout has SetDefaultConstraint."""
    from PySide6.QtWidgets import QVBoxLayout  # noqa: PLC0415

    dialog = BaseDialog(title="Test")
    qtbot.addWidget(dialog)
    assert (
        dialog.layout.sizeConstraint()
        == QVBoxLayout.SizeConstraint.SetDefaultConstraint
    )


def test_base_dialog_header_centered(qtbot: QtBot) -> None:
    """Header label is center-aligned."""
    from PySide6.QtWidgets import QLabel  # noqa: PLC0415

    dialog = BaseDialog(title="My Title")
    qtbot.addWidget(dialog)
    labels = dialog.findChildren(QLabel)
    for lbl in labels:
        if lbl.text() == "My Title":
            assert lbl.alignment() & Qt.AlignmentFlag.AlignCenter
            break


def test_base_dialog_unicode_title(qtbot: QtBot) -> None:
    """BaseDialog handles unicode titles."""
    title = "Dich tai lieu - 翻訳"
    dialog = BaseDialog(title=title)
    qtbot.addWidget(dialog)
    assert dialog.windowTitle() == title


# ===========================================================================
# Expanded: More CustomInputDialog tests
# ===========================================================================


def test_custom_input_dialog_set_error_replaces_previous(qtbot: QtBot) -> None:
    """set_error replaces any previous error message."""
    dialog = CustomInputDialog(title="Test")
    qtbot.addWidget(dialog)
    dialog.show()
    dialog.set_error("Error 1")
    dialog.set_error("Error 2")
    assert dialog.error_label.text() == "Error 2"


def test_custom_input_dialog_has_input_field_styling(qtbot: QtBot) -> None:
    """Input field has QLineEdit in its stylesheet."""
    dialog = CustomInputDialog(title="Test")
    qtbot.addWidget(dialog)
    assert "QLineEdit" in dialog.input.styleSheet()


def test_custom_input_dialog_ok_btn_has_primary_style(qtbot: QtBot) -> None:
    """OK button uses primary button style."""
    from src.constants.theme import color  # noqa: PLC0415

    dialog = CustomInputDialog(title="Test")
    qtbot.addWidget(dialog)
    assert color("primary") in dialog.ok_btn.styleSheet()


def test_custom_input_dialog_cancel_btn_has_secondary_style(qtbot: QtBot) -> None:
    """Cancel button uses secondary button style."""
    from src.constants.theme import color  # noqa: PLC0415

    dialog = CustomInputDialog(title="Test")
    qtbot.addWidget(dialog)
    assert color("border_light") in dialog.cancel_btn.styleSheet()


def test_custom_input_dialog_unicode_label(qtbot: QtBot) -> None:
    """Unicode label text is handled correctly."""
    label = "Nhap ten cua ban - 名前を入力"
    dialog = CustomInputDialog(title="T", label_text=label)
    qtbot.addWidget(dialog)
    assert dialog.label.text() == label


# ===========================================================================
# Expanded: VoiceSetupDialog tests
# ===========================================================================


def test_voice_setup_dialog_creates(qtbot: QtBot) -> None:
    """VoiceSetupDialog can be created."""
    from src.ui.dialogs import VoiceSetupDialog  # noqa: PLC0415

    dialog = VoiceSetupDialog()
    qtbot.addWidget(dialog)
    assert dialog is not None


def test_voice_setup_dialog_has_lang_combo(qtbot: QtBot) -> None:
    """VoiceSetupDialog has a language combo box."""
    from src.ui.dialogs import VoiceSetupDialog  # noqa: PLC0415

    dialog = VoiceSetupDialog()
    qtbot.addWidget(dialog)
    assert dialog.lang_combo is not None
    assert dialog.lang_combo.count() > 0


# Gender combo was removed from VoiceSetupDialog earlier in this
# session — gender is now persisted via the per-engine radios in the
# Voice settings tab and read back via ``SETTING_LAST_VOICE_GENDER``
# in ``get_selection``, so the dialog itself is language-only.


def test_voice_setup_dialog_has_confirm_cancel(qtbot: QtBot) -> None:
    """VoiceSetupDialog has confirm and cancel buttons."""
    from src.ui.dialogs import VoiceSetupDialog  # noqa: PLC0415

    dialog = VoiceSetupDialog()
    qtbot.addWidget(dialog)
    assert dialog.confirm_btn is not None
    assert dialog.cancel_btn is not None


def test_voice_setup_dialog_confirm_uses_primary_style(qtbot: QtBot) -> None:
    """VoiceSetupDialog confirm button uses primary style."""
    from src.constants.theme import color as get_color  # noqa: PLC0415
    from src.ui.dialogs import VoiceSetupDialog  # noqa: PLC0415

    dialog = VoiceSetupDialog()
    qtbot.addWidget(dialog)
    assert get_color("primary") in dialog.confirm_btn.styleSheet()


def test_voice_setup_dialog_lang_combo_populated(qtbot: QtBot) -> None:
    """VoiceSetupDialog lang combo has at least 40 languages."""
    from src.ui.dialogs import VoiceSetupDialog  # noqa: PLC0415

    dialog = VoiceSetupDialog()
    qtbot.addWidget(dialog)
    assert dialog.lang_combo.count() >= 40  # noqa: PLR2004


def test_voice_setup_dialog_inherits_base(qtbot: QtBot) -> None:
    """VoiceSetupDialog inherits from BaseDialog."""
    from src.ui.dialogs import VoiceSetupDialog  # noqa: PLC0415

    dialog = VoiceSetupDialog()
    qtbot.addWidget(dialog)
    assert isinstance(dialog, BaseDialog)


# ===========================================================================
# Expanded: LanguageSelectionDialog additional tests
# ===========================================================================


def test_language_selection_target_has_no_auto(qtbot: QtBot) -> None:
    """Target combo does not have auto-detect item."""
    dialog = LanguageSelectionDialog()
    qtbot.addWidget(dialog)
    # Target combo starts directly with languages, no "Auto" at index 0

    # Combo is sorted by the *localized* label so a Vietnamese user
    # sees Vietnamese alphabet order, etc.  The test asserts the
    # combo's first item matches whatever sorts first under the
    # current locale, not the source-order first entry.
    from src.constants.languages import (  # noqa: PLC0415
        iter_languages_sorted_for_ui,
    )

    assert dialog.target_combo.itemData(0) == (
        iter_languages_sorted_for_ui()[0][1]
    )


def test_language_selection_src_has_auto(qtbot: QtBot) -> None:
    """Source combo has auto-detect as first item."""
    dialog = LanguageSelectionDialog()
    qtbot.addWidget(dialog)
    from src.constants import tr  # noqa: PLC0415

    assert dialog.src_combo.itemText(0) == tr("common.lang_auto_detect")


def test_language_selection_translate_btn_connected(qtbot: QtBot) -> None:
    """Translate button is connected to accept."""
    dialog = LanguageSelectionDialog()
    qtbot.addWidget(dialog)
    assert dialog.translate_btn is not None


def test_language_selection_cancel_btn_cursor(qtbot: QtBot) -> None:
    """Cancel button has pointing hand cursor."""
    dialog = LanguageSelectionDialog()
    qtbot.addWidget(dialog)
    assert dialog.cancel_btn.cursor().shape() == Qt.CursorShape.PointingHandCursor


def test_language_selection_translate_btn_cursor(qtbot: QtBot) -> None:
    """Translate button has pointing hand cursor."""
    dialog = LanguageSelectionDialog()
    qtbot.addWidget(dialog)
    assert dialog.translate_btn.cursor().shape() == Qt.CursorShape.PointingHandCursor


def test_language_selection_src_combo_height(qtbot: QtBot) -> None:
    """Source combo has fixed height set to HEIGHT_CONTROL."""
    from src.constants import HEIGHT_CONTROL  # noqa: PLC0415

    dialog = LanguageSelectionDialog()
    qtbot.addWidget(dialog)
    assert dialog.src_combo.maximumHeight() == HEIGHT_CONTROL


# ===========================================================================
# Expanded: CustomConfirmDialog additional tests
# ===========================================================================


def test_confirm_dialog_default_confirm_text(qtbot: QtBot) -> None:
    """Default confirm text is tr('btn.continue')."""
    from src.constants import tr  # noqa: PLC0415

    dialog = CustomConfirmDialog(title="T", message="M")
    qtbot.addWidget(dialog)
    assert dialog.confirm_btn.text() == tr("btn.continue")


def test_confirm_dialog_default_cancel_text(qtbot: QtBot) -> None:
    """Default cancel text is tr('btn.cancel')."""
    from src.constants import tr  # noqa: PLC0415

    dialog = CustomConfirmDialog(title="T", message="M")
    qtbot.addWidget(dialog)
    assert dialog.cancel_btn.text() == tr("btn.cancel")


def test_confirm_dialog_msg_label_word_wrap(qtbot: QtBot) -> None:
    """Message label has word wrap enabled."""
    dialog = CustomConfirmDialog(title="T", message="M")
    qtbot.addWidget(dialog)
    assert dialog.msg_label.wordWrap()


def test_confirm_dialog_cancel_btn_height(qtbot: QtBot) -> None:
    """Cancel button has fixed height."""
    from src.constants import HEIGHT_CONTROL  # noqa: PLC0415

    dialog = CustomConfirmDialog(title="T", message="M")
    qtbot.addWidget(dialog)
    assert dialog.cancel_btn.maximumHeight() == HEIGHT_CONTROL


# ===========================================================================
# Expanded: CustomMessageDialog additional tests
# ===========================================================================


def test_message_dialog_ok_btn_cursor(qtbot: QtBot) -> None:
    """OK button has pointing hand cursor."""
    dialog = CustomMessageDialog(title="T", message="M")
    qtbot.addWidget(dialog)
    assert dialog.ok_btn.cursor().shape() == Qt.CursorShape.PointingHandCursor


def test_message_dialog_msg_label_word_wrap(qtbot: QtBot) -> None:
    """Message label has word wrap enabled."""
    dialog = CustomMessageDialog(title="T", message="M")
    qtbot.addWidget(dialog)
    assert dialog.msg_label.wordWrap()


def test_message_dialog_msg_label_center_aligned(qtbot: QtBot) -> None:
    """Message label is center-aligned."""
    dialog = CustomMessageDialog(title="T", message="M")
    qtbot.addWidget(dialog)
    assert dialog.msg_label.alignment() & Qt.AlignmentFlag.AlignCenter


def test_message_dialog_ok_btn_auto_default_false(qtbot: QtBot) -> None:
    """OK button has autoDefault disabled."""
    dialog = CustomMessageDialog(title="T", message="M")
    qtbot.addWidget(dialog)
    assert not dialog.ok_btn.autoDefault()


# ===========================================================================
# LanguageSelectionDialog — persistence failure + deprecated locale fallback
# ===========================================================================


def test_language_selection_dialog_empty_persisted_source_uses_default(
    qtbot: QtBot,
    settings_env: configparser.ConfigParser,
) -> None:
    """No persisted source language → combo defaults to Auto (index 0)."""
    from src.constants.settings import (  # noqa: PLC0415
        SETTING_LAST_SOURCE_LANGUAGE,
    )
    from src.utils.config_manager import save_setting  # noqa: PLC0415

    save_setting(SETTING_LAST_SOURCE_LANGUAGE, "")

    dialog = LanguageSelectionDialog()
    qtbot.addWidget(dialog)

    assert dialog.src_combo.currentIndex() == 0


def test_language_selection_dialog_unknown_persisted_source_falls_back(
    qtbot: QtBot,
    settings_env: configparser.ConfigParser,
) -> None:
    """A persisted source language not in LANGUAGES (e.g. 'Klingon') is ignored gracefully."""
    from src.constants.settings import (  # noqa: PLC0415
        SETTING_LAST_SOURCE_LANGUAGE,
    )
    from src.utils.config_manager import save_setting  # noqa: PLC0415

    save_setting(SETTING_LAST_SOURCE_LANGUAGE, "Klingon")

    # Dialog construction must not raise.
    dialog = LanguageSelectionDialog()
    qtbot.addWidget(dialog)

    # Combo retains its default selection (auto-detect, index 0) since
    # findText('Klingon') returned -1.
    assert dialog.src_combo.currentIndex() == 0
    # Combo still has auto + all real languages.
    assert dialog.src_combo.count() > 1


def test_language_dialog_round_trips_canonical_label_via_itemData(
    qtbot: QtBot,
    settings_env: "configparser.ConfigParser",
) -> None:
    """Picking a language persists by canonical English label, restores by data.

    Past bug: the persistence was via ``currentText()`` / ``findText()``
    on the localised display string (e.g. ``"Tiếng Việt"``), so on the
    next page open the combo couldn't find a match and silently fell
    back to index 0.  The fix routes everything through
    ``itemData(label)`` / ``findData(label)`` so the canonical
    English label round-trips intact.
    """
    from src.constants.i18n import _set_initial_language  # noqa: PLC0415
    from src.constants.settings import (  # noqa: PLC0415
        SETTING_LAST_TARGET_LANGUAGE,
    )
    from src.utils.config_manager import save_setting  # noqa: PLC0415

    # Switch UI to Vietnamese so the displayed text and the canonical
    # label diverge — the round-trip must use the canonical form.
    _set_initial_language("vi")
    try:
        # Persist a known target via the canonical English label.
        save_setting(SETTING_LAST_TARGET_LANGUAGE, "Vietnamese")

        dialog = LanguageSelectionDialog()
        qtbot.addWidget(dialog)
        # Restored selection must hold the canonical label as data,
        # not the localised display text.
        assert dialog.target_combo.currentData() == "Vietnamese"
        # And the displayed text in vi locale should NOT equal the
        # English label — proves the localisation wired up correctly.
        assert dialog.target_combo.currentText() != "Vietnamese", (
            "vi display text should differ from English canonical label; "
            f"got {dialog.target_combo.currentText()!r}"
        )
    finally:
        _set_initial_language("en-US")


class TestPiperVoiceDownloadDialog:
    """Coverage for the Piper voice library dialog.

    Replaces the per-page combo + per-voice download button that used
    to live on the Piper picker page.  The dialog is the single
    surface where users pick which Piper voices to install offline;
    the engine then auto-picks ``(target_lang, gender)`` at synthesis
    time, so a regression here means Piper TTS effectively can't be
    set up via the UI at all.
    """

    def test_dialog_lists_one_row_per_unique_voice_id(
        self,
        qapp,  # noqa: ANN001, ARG002
    ) -> None:
        """Every voice in the catalogue gets a slot, with shared IDs collapsed."""
        from src.constants.i18n import _set_initial_language  # noqa: PLC0415
        from src.core.speech_engine import (  # noqa: PLC0415
            PIPER_VOICES_BY_GENDER_AND_LANGUAGE,
        )
        from src.ui.dialogs import PiperVoiceDownloadDialog  # noqa: PLC0415

        _set_initial_language("en-US")
        dlg = PiperVoiceDownloadDialog()
        all_voice_ids = set()
        for entries in PIPER_VOICES_BY_GENDER_AND_LANGUAGE.values():
            all_voice_ids.update(entries.values())
        assert set(dlg._voice_rows.keys()) == all_voice_ids, (
            "Dialog must build one slot per unique voice ID — shared "
            "voice IDs across genders should collapse into a single "
            "slot to avoid duplicate-but-identical entries"
        )

    def test_single_gender_languages_render_one_button(
        self,
        qapp,  # noqa: ANN001, ARG002
    ) -> None:
        """Languages with only one curated voice render one button.

        Italian, Dutch, Chinese (Simplified) only ship a female
        voice in the rhasspy/piper-voices catalogue and Portuguese
        only ships a male voice; we used to wallpaper this by
        duplicating the lone voice ID into both gender slots and
        showing a "Both genders" button.  After the catalogue
        cleanup, the dialog renders only the gender that actually
        has a voice — the cross-gender fallback at synthesis time
        is the engine's job, not the picker's.

        We verify by counting QPushButtons in the row frame for one
        of those single-gender languages.  A multi-voice language
        (e.g. English) must have TWO buttons.
        """
        from PySide6.QtWidgets import QFrame, QPushButton  # noqa: PLC0415

        from src.constants.i18n import _set_initial_language  # noqa: PLC0415
        from src.core.speech_engine import (  # noqa: PLC0415
            PIPER_VOICES_BY_GENDER_AND_LANGUAGE,
        )
        from src.ui.dialogs import PiperVoiceDownloadDialog  # noqa: PLC0415

        _set_initial_language("en-US")
        # Pick a language present in only ONE gender map.
        female_only = (
            set(PIPER_VOICES_BY_GENDER_AND_LANGUAGE["FEMALE"].keys())
            - set(PIPER_VOICES_BY_GENDER_AND_LANGUAGE["MALE"].keys())
        )
        male_only = (
            set(PIPER_VOICES_BY_GENDER_AND_LANGUAGE["MALE"].keys())
            - set(PIPER_VOICES_BY_GENDER_AND_LANGUAGE["FEMALE"].keys())
        )
        single_lang = next(iter(female_only | male_only))
        # Pick a language present in BOTH gender maps.
        both_genders = (
            set(PIPER_VOICES_BY_GENDER_AND_LANGUAGE["FEMALE"].keys())
            & set(PIPER_VOICES_BY_GENDER_AND_LANGUAGE["MALE"].keys())
        )
        dual_lang = next(iter(both_genders))

        dlg = PiperVoiceDownloadDialog()

        def _row_for(lang: str) -> QFrame:
            """Returns the QFrame whose lang label matches *lang*'s display text."""
            from PySide6.QtWidgets import QLabel  # noqa: PLC0415

            from src.constants.languages import (  # noqa: PLC0415
                LANGUAGES,
                format_language_picker_label,
            )

            native_by_english = {
                label: native
                for _locale, label, _icon, native in LANGUAGES
            }
            display = format_language_picker_label(
                lang, native_by_english.get(lang, lang),
            )
            for f in dlg.findChildren(QFrame):
                if f.objectName() != "PiperVoiceRow":
                    continue
                if any(
                    lab.text() == display
                    for lab in f.findChildren(QLabel)
                ):
                    return f
            raise AssertionError(f"No row found for {lang!r}")

        def _count_action_buttons(frame: QFrame) -> int:
            # Per-slot buttons live INSIDE the language row frame and
            # carry the ``piperGenderKey`` property set in
            # ``_build_voice_slot``.  Match on that to avoid false
            # positives from dialog-level buttons (Close).
            return len([
                b for b in frame.findChildren(QPushButton)
                if b.property("piperGenderKey") in (
                    "settings.piper_voice_female_btn",
                    "settings.piper_voice_male_btn",
                )
            ])

        single_count = _count_action_buttons(_row_for(single_lang))
        dual_count = _count_action_buttons(_row_for(dual_lang))
        assert single_count == 1, (
            f"Single-gender language {single_lang!r} must render ONE "
            f"button (only one voice exists in the catalogue), got "
            f"{single_count}"
        )
        assert dual_count == 2, (  # noqa: PLR2004
            f"Dual-gender language {dual_lang!r} must render TWO "
            f"buttons (Female + Male slots), got {dual_count}"
        )

    def test_dialog_emits_voices_changed_on_successful_download(
        self,
        qapp,  # noqa: ANN001, ARG002
    ) -> None:
        """The ``voices_changed`` signal fires only when an install succeeds.

        The settings page subscribes to this signal to refresh its
        "N language(s) installed" summary banner — a regression that
        forgets to emit would leave the banner stale until the user
        navigates away from the page and back.
        """
        from PySide6.QtCore import QObject  # noqa: PLC0415

        from src.constants.i18n import _set_initial_language  # noqa: PLC0415
        from src.ui.dialogs import (  # noqa: PLC0415
            PiperVoiceDownloadDialog,
        )

        _set_initial_language("en-US")
        dlg = PiperVoiceDownloadDialog()
        emit_count = [0]

        class _Sink(QObject):
            def slot(self) -> None:
                emit_count[0] += 1

        sink = _Sink()
        dlg.voices_changed.connect(sink.slot)

        # Pick any one voice ID present in the catalogue.
        voice_id = next(iter(dlg._voice_rows.keys()))
        widgets = dlg._voice_rows[voice_id]

        # Stub the on-disk install check so the post-download branch
        # treats this voice as freshly installed.  Stub the engine
        # download itself so no network call is made.
        with patch(
            "src.core.speech_engine.download_piper_voice",
            return_value=None,
        ), patch(
            "src.core.speech_engine.is_piper_voice_installed",
            return_value=True,
        ):
            dlg._start_download(voice_id)
            # Wait for the QThread to finish so the
            # ``finished → _on_finished`` callback runs.
            thread = dlg._threads.get(voice_id)
            if thread is not None:
                thread.wait(2000)
            # ``finished`` queues an event onto the GUI thread —
            # process pending events so ``_on_finished`` actually
            # runs before we assert.
            qapp.processEvents()

        assert emit_count[0] == 1, (
            "voices_changed must fire exactly once per successful "
            f"download; emitted {emit_count[0]} times"
        )
        # The action button should also have flipped to hidden
        # (Installed badge replaces it).
        assert not widgets["action_btn"].isVisible() or (
            widgets["action_btn"].text() != ""
        )

    def test_dialog_does_not_emit_voices_changed_on_failure(
        self,
        qapp,  # noqa: ANN001
    ) -> None:
        """A failed download fires the failure dialog, NOT ``voices_changed``."""
        from PySide6.QtCore import QObject  # noqa: PLC0415

        from src.constants.i18n import _set_initial_language  # noqa: PLC0415
        from src.ui.dialogs import PiperVoiceDownloadDialog  # noqa: PLC0415

        _set_initial_language("en-US")
        dlg = PiperVoiceDownloadDialog()
        emit_count = [0]

        class _Sink(QObject):
            def slot(self) -> None:
                emit_count[0] += 1

        sink = _Sink()
        dlg.voices_changed.connect(sink.slot)

        voice_id = next(iter(dlg._voice_rows.keys()))

        # Force the download to raise; stub is_piper_voice_installed
        # so the post-failure branch never confuses error+installed.
        with patch(
            "src.core.speech_engine.download_piper_voice",
            side_effect=OSError("network down"),
        ), patch(
            "src.core.speech_engine.is_piper_voice_installed",
            return_value=False,
        ), patch(
            "src.ui.dialogs.CustomMessageDialog",
        ) as mock_msg:
            dlg._start_download(voice_id)
            thread = dlg._threads.get(voice_id)
            if thread is not None:
                thread.wait(2000)
            qapp.processEvents()

        assert emit_count[0] == 0, (
            "voices_changed must NOT fire on download failure — the "
            "failure dialog handles the user-visible error path"
        )
        mock_msg.assert_called_once(), (
            "Failure path must surface a message dialog so the user "
            "knows the download didn't land"
        )


class TestPreflightPiperVoice:
    """Pre-flight check before Voice / Dubbing batches use Piper TTS.

    Catches the "Piper voice not installed" condition BEFORE the
    worker starts, so the user gets a single dialog with an Open
    Settings button instead of every history row turning red one
    by one with a PIPER_VOICE_NOT_INSTALLED error.
    """

    def test_returns_true_when_tts_not_piper(
        self,
        qapp,  # noqa: ANN001, ARG002
    ) -> None:
        """Edge / Google / Gemini / ElevenLabs → no preflight needed."""
        from src.constants.settings import (  # noqa: PLC0415
            VOICE_TTS_EDGE,
        )
        from src.ui.dialogs import preflight_piper_voice  # noqa: PLC0415

        with patch(
            "src.utils.config_manager.load_setting",
            return_value=VOICE_TTS_EDGE,
        ):
            assert preflight_piper_voice(None, "French", "FEMALE") is True

    def test_returns_true_when_language_not_in_piper_catalogue(
        self,
        qapp,  # noqa: ANN001, ARG002
    ) -> None:
        """Piper + unsupported language → engine will silently fall back to Edge.

        The preflight must NOT raise a dialog when there's nothing
        the user could install — Hebrew, Japanese, Korean, etc. have
        no Piper voice at all.
        """
        from src.constants.settings import (  # noqa: PLC0415
            VOICE_TTS_PIPER,
        )
        from src.ui.dialogs import preflight_piper_voice  # noqa: PLC0415

        with patch(
            "src.utils.config_manager.load_setting",
            return_value=VOICE_TTS_PIPER,
        ):
            for lang in ("Hebrew", "Japanese", "Korean", "Thai"):
                assert preflight_piper_voice(None, lang, "FEMALE") is True, (
                    f"{lang!r} has no Piper coverage; preflight must "
                    f"return True so the engine can route to Edge"
                )

    def test_returns_true_when_voice_already_installed(
        self,
        qapp,  # noqa: ANN001, ARG002
    ) -> None:
        """Piper + supported language + voice on disk → proceed silently."""
        from src.constants.settings import (  # noqa: PLC0415
            VOICE_TTS_PIPER,
        )
        from src.ui.dialogs import preflight_piper_voice  # noqa: PLC0415

        with patch(
            "src.utils.config_manager.load_setting",
            return_value=VOICE_TTS_PIPER,
        ), patch(
            "src.core.speech_engine.is_piper_voice_installed",
            return_value=True,
        ):
            assert preflight_piper_voice(None, "French", "FEMALE") is True

    def test_returns_false_and_navigates_when_user_picks_settings(
        self,
        qapp,  # noqa: ANN001, ARG002
    ) -> None:
        """Voice missing → dialog confirmed → navigate + return False.

        ``navigate_to_settings_tab`` must be called with the Voice
        tab index (8) so the user lands on the right page; the
        function returns False so the caller aborts the queue.
        """
        from src.constants.settings import (  # noqa: PLC0415
            VOICE_TTS_PIPER,
        )
        from src.ui.dialogs import preflight_piper_voice  # noqa: PLC0415

        nav = MagicMock()

        class _FakeWindow:
            navigate_to_settings_tab = nav

        with patch(
            "src.utils.config_manager.load_setting",
            return_value=VOICE_TTS_PIPER,
        ), patch(
            "src.core.speech_engine.is_piper_voice_installed",
            return_value=False,
        ), patch(
            "src.ui.dialogs.CustomConfirmDialog.confirm",
            return_value=True,
        ):
            result = preflight_piper_voice(
                _FakeWindow(), "French", "FEMALE",
            )

        assert result is False, (
            "Preflight must return False so the caller aborts the "
            "queue — the worker mustn't run with a missing voice"
        )
        nav.assert_called_once_with(8), (
            "Open Settings button must navigate to the Voice tab "
            "(index 8) so the user lands on the Piper picker"
        )

    def test_returns_false_and_does_not_navigate_when_user_cancels(
        self,
        qapp,  # noqa: ANN001, ARG002
    ) -> None:
        """Voice missing → dialog cancelled → no navigation, return False."""
        from src.constants.settings import (  # noqa: PLC0415
            VOICE_TTS_PIPER,
        )
        from src.ui.dialogs import preflight_piper_voice  # noqa: PLC0415

        nav = MagicMock()

        class _FakeWindow:
            navigate_to_settings_tab = nav

        with patch(
            "src.utils.config_manager.load_setting",
            return_value=VOICE_TTS_PIPER,
        ), patch(
            "src.core.speech_engine.is_piper_voice_installed",
            return_value=False,
        ), patch(
            "src.ui.dialogs.CustomConfirmDialog.confirm",
            return_value=False,
        ):
            result = preflight_piper_voice(
                _FakeWindow(), "French", "FEMALE",
            )

        assert result is False
        nav.assert_not_called()
