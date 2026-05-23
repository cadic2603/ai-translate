"""Custom stylized dialogs for the AI Translate application."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QKeyEvent

if TYPE_CHECKING:
    from PySide6.QtGui import QIcon
    from PySide6.QtWidgets import QComboBox

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from src.constants import (
    FLAG_ICON_HEIGHT,
    FLAG_ICON_WIDTH,
    FLAGS_DIR,
    HEIGHT_CONTROL,
    MARGIN_PAGE,
    SETTING_LAST_SOURCE_LANGUAGE,
    SETTING_LAST_TARGET_LANGUAGE,
    SPACING_SECTION,
    color,
    format_language_picker_label,
    iter_languages_sorted_for_ui,
    style_danger_button,
    style_input_field,
    style_outlined_primary_button,
    style_page_header,
    style_primary_button,
    style_secondary_button,
    style_setting_combo,
    tr,
)
from src.ui.components import create_banner
from src.utils.config_manager import load_setting, save_setting


def _create_emoji_icon(emoji: str = "\U0001f310") -> QIcon:
    """Renders an emoji as a QIcon matching flag icon dimensions."""
    from PySide6.QtGui import QFont, QIcon, QPainter, QPixmap  # noqa: PLC0415

    pixmap = QPixmap(24, 18)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setFont(QFont("", 14))
    painter.drawText(pixmap.rect(), Qt.AlignmentFlag.AlignCenter, emoji)
    painter.end()
    return QIcon(pixmap)


class BaseDialog(QDialog):
    """Base class for styled dialogs with consistent look and feel."""

    def __init__(self, parent: QWidget | None = None, title: str = "") -> None:
        """Initializes the BaseDialog.

        Args:
            parent: Optional parent widget.
            title: Title of the dialog.
        """
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(450)
        self.setStyleSheet(
            f"background-color: {color('component_bg')};"
            f" color: {color('text_primary')};"
        )
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(
            MARGIN_PAGE, MARGIN_PAGE, MARGIN_PAGE, MARGIN_PAGE
        )
        self.layout.setSpacing(SPACING_SECTION)
        self.layout.setSizeConstraint(QVBoxLayout.SizeConstraint.SetDefaultConstraint)

        if title:
            header = QLabel(title)
            header.setStyleSheet(style_page_header())
            header.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.layout.addWidget(header)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        """Override Enter key to trigger confirmation logic."""
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.on_confirm()
        else:
            super().keyPressEvent(event)

    def on_confirm(self, *args: Any) -> None:  # noqa: ANN401
        """Called when OK/Confirm button or Enter is pressed.

        Can be overridden for validation in subclasses.
        """
        self.accept()


class CustomInputDialog(BaseDialog):
    """A larger, better-looking input dialog."""

    def __init__(
        self,
        parent: QWidget | None = None,
        title: str = "",
        label_text: str = "",
        placeholder: str = "",
    ) -> None:
        """Initializes the CustomInputDialog.

        Args:
            parent: Optional parent widget.
            title: Dialog title.
            label_text: Text for the input label.
            placeholder: Placeholder for the input field.
        """
        super().__init__(parent, title)

        self.label = QLabel(label_text)
        self.layout.addWidget(self.label)

        self.input = QLineEdit()
        self.input.setPlaceholderText(placeholder)
        self.input.setFixedHeight(HEIGHT_CONTROL)
        self.input.setMinimumWidth(400)
        self.input.setStyleSheet(style_input_field())
        self.layout.addWidget(self.input)

        # Inline Error Label (hidden by default)
        self.error_frame, self.error_label = create_banner("", variant="error")
        self.error_frame.setVisible(False)
        self.layout.addWidget(self.error_frame)

        # Buttons
        btn_layout = QHBoxLayout()
        self.ok_btn = QPushButton(tr("btn.confirm"))
        self.ok_btn.setFixedHeight(HEIGHT_CONTROL)
        self.ok_btn.setStyleSheet(style_primary_button())
        self.ok_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.ok_btn.setAutoDefault(False)
        self.ok_btn.setDefault(False)

        self.cancel_btn = QPushButton(tr("btn.cancel"))
        self.cancel_btn.setFixedHeight(HEIGHT_CONTROL)
        self.cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_btn.setStyleSheet(style_secondary_button())
        self.cancel_btn.setAutoDefault(False)

        btn_layout.addStretch()
        btn_layout.addWidget(self.cancel_btn)
        btn_layout.addWidget(self.ok_btn)
        self.layout.addLayout(btn_layout)

        self.ok_btn.clicked.connect(self.on_confirm)
        self.cancel_btn.clicked.connect(self.reject)
        self.input.returnPressed.connect(self.on_confirm)
        self.input.textChanged.connect(self.clear_error)

    def set_error(self, message: str) -> None:
        """Displays an error message below the input field."""
        self.error_label.setText(message)
        self.error_frame.setVisible(bool(message))

    def clear_error(self) -> None:
        """Clears and hides the error message."""
        self.error_label.setText("")
        self.error_frame.setVisible(False)

    @staticmethod
    def get_text(
        parent: QWidget | None, title: str, label: str, placeholder: str = ""
    ) -> tuple[str, bool]:
        """Shows the dialog and returns the text and success status."""
        dialog = CustomInputDialog(parent, title, label, placeholder)
        result = dialog.exec()
        return dialog.input.text(), result == QDialog.DialogCode.Accepted


class CustomConfirmDialog(BaseDialog):
    """A larger, better-looking confirmation dialog."""

    def __init__(  # noqa: PLR0913
        self,
        parent: QWidget | None = None,
        title: str = "",
        message: str = "",
        is_danger: bool = False,
        confirm_text: str = "",
        cancel_text: str = "",
    ) -> None:
        """Initializes the CustomConfirmDialog.

        Args:
            parent: Optional parent widget.
            title: Dialog title.
            message: Confirmation message.
            is_danger: If True, uses a red "Delete" button.
            confirm_text: Text for the confirm button.
            cancel_text: Text for the cancel button.
        """
        super().__init__(parent, title)

        # Default button texts from i18n
        if not confirm_text:
            confirm_text = tr("btn.continue")
        if not cancel_text:
            cancel_text = tr("btn.cancel")

        self.msg_label = QLabel(message)
        self.msg_label.setWordWrap(True)
        self.msg_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.msg_label.setStyleSheet(
            f"font-size: 13px; margin: 10px 0; color: {color('text_primary')};"
        )
        self.layout.addWidget(self.msg_label)

        btn_layout = QHBoxLayout()
        self.confirm_btn = QPushButton(confirm_text)
        self.confirm_btn.setFixedHeight(HEIGHT_CONTROL)
        if is_danger:
            if confirm_text == tr("btn.continue"):
                self.confirm_btn.setText(tr("btn.delete"))
            self.confirm_btn.setStyleSheet(style_danger_button() + "padding: 0 24px;")
        else:
            self.confirm_btn.setStyleSheet(style_primary_button() + "padding: 0 20px;")
        self.confirm_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.confirm_btn.setAutoDefault(False)

        self.cancel_btn = QPushButton(cancel_text)
        self.cancel_btn.setFixedHeight(HEIGHT_CONTROL)
        self.cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_btn.setStyleSheet(style_secondary_button())
        self.cancel_btn.setAutoDefault(False)

        btn_layout.addStretch()
        btn_layout.addWidget(self.cancel_btn)
        btn_layout.addWidget(self.confirm_btn)
        self.layout.addLayout(btn_layout)

        self.confirm_btn.clicked.connect(self.on_confirm)
        self.cancel_btn.clicked.connect(self.reject)

    @staticmethod
    def confirm(  # noqa: PLR0913
        parent: QWidget | None,
        title: str,
        message: str,
        is_danger: bool = False,
        confirm_text: str = "",
        cancel_text: str = "",
    ) -> bool:
        """Shows the dialog and returns True if confirmed."""
        dialog = CustomConfirmDialog(
            parent, title, message, is_danger, confirm_text, cancel_text
        )
        return dialog.exec() == QDialog.DialogCode.Accepted


def require_setup(
    window: QWidget | None,
    check_fn: Callable[[], bool],
    title_key: str,
    msg_key: str,
    settings_tab: int,
) -> bool:
    """Checks a prerequisite and shows a 'Go to Settings' dialog on failure.

    Args:
        window: Parent widget (must have ``navigate_to_settings_tab``).
        check_fn: Callable returning True when the prerequisite is met.
        title_key: i18n key for the dialog title.
        msg_key: i18n key for the dialog message.
        settings_tab: Index of the settings tab to navigate to.

    Returns:
        True if the prerequisite is satisfied, False otherwise.
    """
    if check_fn():
        return True

    confirmed = CustomConfirmDialog.confirm(
        window,
        tr(title_key),
        tr(msg_key),
        confirm_text=tr("btn.go_to_settings"),
    )
    if confirmed and hasattr(window, "navigate_to_settings_tab"):
        window.navigate_to_settings_tab(settings_tab)
    return False


def preflight_piper_voice(
    window: QWidget | None,
    target_lang: str,
    gender: str,
    *,
    settings_tab: int = 8,
) -> bool:
    """Pre-flight check before queueing TTS work that may use Piper.

    Three short-circuits — the function returns True (work can
    proceed) without showing any dialog when:

    - The active TTS method isn't Piper.
    - The active method IS Piper but *target_lang* isn't in the
      Piper catalogue (engine will silently route to Edge TTS at
      synthesis time, no install needed).
    - Piper covers *target_lang* AND the per-gender voice file is
      already on disk.

    Otherwise (Piper covers the language but the voice isn't
    downloaded yet) it shows a confirm dialog with "Open Settings"
    and "Cancel" buttons.  On "Open Settings" it navigates to
    Settings → Voice (default *settings_tab* = 8) so the user can
    click the "Download voices now" button; either way it returns
    False so the caller aborts the queue without burning through
    every task only to mark them all FAILED.

    Args:
        window: Parent widget (must have ``navigate_to_settings_tab``
            for the Open-Settings button to work).
        target_lang: Language label from ``LANGUAGES`` (e.g. "French").
        gender: ``"MALE"`` or ``"FEMALE"`` (case-insensitive).
        settings_tab: Index of the Voice tab in the Settings page.

    Returns:
        True when work can proceed, False when the user must install
        a Piper voice first.
    """
    from src.constants.settings import (  # noqa: PLC0415
        SETTING_VOICE_TTS_METHOD,
        VOICE_TTS_EDGE,
        VOICE_TTS_PIPER,
    )
    from src.core.speech_engine import (  # noqa: PLC0415
        get_piper_voice_for,
        is_piper_voice_installed,
    )
    from src.utils.config_manager import load_setting  # noqa: PLC0415

    if load_setting(SETTING_VOICE_TTS_METHOD, VOICE_TTS_EDGE) != VOICE_TTS_PIPER:
        return True
    voice_id = get_piper_voice_for(target_lang, gender)
    if not voice_id:
        # Language has no Piper coverage — the engine will silently
        # use Edge TTS, so nothing to install up-front.
        return True
    if is_piper_voice_installed(voice_id):
        return True

    confirmed = CustomConfirmDialog.confirm(
        window,
        tr("dialog.piper_voice_required_title"),
        tr(
            "dialog.piper_voice_required_msg",
            target_lang=target_lang,
        ),
        confirm_text=tr("btn.go_to_settings"),
    )
    if confirmed and hasattr(window, "navigate_to_settings_tab"):
        window.navigate_to_settings_tab(settings_tab)
    return False


class CustomMessageDialog(BaseDialog):
    """A larger, better-looking informational dialog."""

    def __init__(
        self,
        parent: QWidget | None = None,
        title: str = "",
        message: str = "",
        copy_text: str = "",
    ) -> None:
        """Initializes the CustomMessageDialog.

        Args:
            parent: Optional parent widget.
            title: Dialog title.
            message: Informational message.
            copy_text: If non-empty, adds a "Copy" button that copies this
                text to the clipboard.
        """
        super().__init__(parent, title)

        self.msg_label = QLabel(message)
        self.msg_label.setWordWrap(True)
        self.msg_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # Auto-detect rich text so callers can pass HTML markup
        # (``<b>``, ``<a href>``) — used by the shared FFmpeg install
        # dialog whose body comes from ``build_ffmpeg_install_message()``.
        # ``setOpenExternalLinks`` makes ``<a href>`` clicks open in
        # the user's browser without per-callsite wiring.
        self.msg_label.setTextFormat(Qt.TextFormat.AutoText)
        self.msg_label.setOpenExternalLinks(True)
        self.msg_label.setStyleSheet(
            f"font-size: 13px; margin: 10px 0; color: {color('text_primary')};"
        )
        self.layout.addWidget(self.msg_label)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        if copy_text:
            self._copy_text = copy_text
            self._copy_default_style = style_secondary_button() + "padding: 0 30px;"
            self.copy_btn = QPushButton(tr("btn.copy_command"))
            self.copy_btn.setFixedHeight(HEIGHT_CONTROL)
            self.copy_btn.setStyleSheet(self._copy_default_style)
            self.copy_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self.copy_btn.setAutoDefault(False)
            self.copy_btn.clicked.connect(self._copy_to_clipboard)
            btn_layout.addWidget(self.copy_btn)

        self.ok_btn = QPushButton(tr("btn.ok"))
        self.ok_btn.setFixedHeight(HEIGHT_CONTROL)
        self.ok_btn.setStyleSheet(style_primary_button() + "padding: 0 30px;")
        self.ok_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.ok_btn.setAutoDefault(False)

        btn_layout.addWidget(self.ok_btn)
        btn_layout.addStretch()
        self.layout.addLayout(btn_layout)

        self.ok_btn.clicked.connect(self.on_confirm)

    def _copy_to_clipboard(self) -> None:
        """Copies the command text to the clipboard and shows confirmation."""
        from PySide6.QtCore import QTimer  # noqa: PLC0415
        from PySide6.QtWidgets import QApplication  # noqa: PLC0415

        clipboard = QApplication.clipboard()
        if clipboard:
            clipboard.setText(self._copy_text)

        # Show "Copied!" feedback with green outlined style
        self.copy_btn.setText(tr("btn.copied"))
        self.copy_btn.setStyleSheet(
            f"QPushButton {{ background: transparent; color: {color('success')};"
            f" border: 1px solid {color('success')}; border-radius: 8px;"
            f" font-size: 14px; font-weight: 600; padding: 0 30px;"
            f" height: {HEIGHT_CONTROL}px; }}"
        )

        # Revert after 1.5 seconds
        QTimer.singleShot(
            1500,
            lambda: self._reset_copy_btn() if hasattr(self, "copy_btn") else None,
        )

    def _reset_copy_btn(self) -> None:
        """Restores the copy button to its default state."""
        self.copy_btn.setText(tr("btn.copy_command"))
        self.copy_btn.setStyleSheet(self._copy_default_style)

    @staticmethod
    def show_message(
        parent: QWidget | None,
        title: str,
        message: str,
        copy_text: str = "",
    ) -> None:
        """Shows the dialog with an informational message."""
        dialog = CustomMessageDialog(parent, title, message, copy_text)
        dialog.exec()


def _create_model_combo(
    parent_layout: QVBoxLayout,
    *,
    model_setting_key: str = "",
) -> tuple[QLabel | None, QComboBox | None]:
    """Creates and populates an LLM model selection QComboBox.

    Returns the label + combo as a tuple so callers can hide both
    pieces together when the dialog's target language is "No
    translation" (the Model picker is dead UI when no LLM call will
    be made).  The label-only variant (when no models are configured)
    returns ``(warning, None)`` so callers can still hide the warning
    on no-translation flows.

    Args:
        parent_layout: The layout to add the label and combo box to.
        model_setting_key: Optional per-feature settings key — when set,
            the combo's initial selection is read from that key (with
            fallback to the global last-used model).  Empty means
            global-only.

    Returns:
        ``(label, combo)`` tuple.  ``combo`` is ``None`` when no
        models are available (the warning label is returned instead).
    """
    from PySide6.QtWidgets import QComboBox  # noqa: PLC0415

    from src.constants.settings import SETTING_LLM_LAST_MODEL  # noqa: PLC0415
    from src.utils.config_manager import (  # noqa: PLC0415
        format_model_id,
        get_available_models,
        load_model_for_feature,
    )

    models = get_available_models()
    if not models:
        warning = QLabel(tr("dialog.no_llm_configured"))
        warning.apply_language = lambda w=warning: w.setText(
            tr("dialog.no_llm_configured"),
        )
        warning.setStyleSheet(
            f"font-size: 13px; color: {color('text_secondary')}; font-weight: 600;"
        )
        parent_layout.addWidget(warning)
        # Return the warning as the "label" half so the caller can
        # still hide it on no-translation flows; combo is None.
        return (warning, None)

    # Label
    label = QLabel(tr("dialog.model_label"))
    label.apply_language = lambda w=label: w.setText(tr("dialog.model_label"))
    label.setStyleSheet(
        f"font-size: 13px; color: {color('text_secondary')}; font-weight: 600;"
    )
    parent_layout.addWidget(label)

    # Combo box
    combo = QComboBox()
    combo.setFixedHeight(HEIGHT_CONTROL)
    combo.setStyleSheet(style_setting_combo())
    combo.setCursor(Qt.CursorShape.PointingHandCursor)

    for provider, model_name in models:
        data = format_model_id(provider, model_name)
        combo.addItem(model_name, data)

    # Restore last selection — feature-specific key if provided, otherwise
    # the legacy global default via the helper.
    last_model = (
        load_model_for_feature(model_setting_key)
        if model_setting_key
        else load_setting(SETTING_LLM_LAST_MODEL, "")
    )
    if last_model:
        for i in range(combo.count()):
            if combo.itemData(i, Qt.ItemDataRole.UserRole) == last_model:
                combo.setCurrentIndex(i)
                break

    parent_layout.addWidget(combo)
    return (label, combo)


class LanguageSelectionDialog(BaseDialog):
    """Dialog for selecting the source and target translation languages."""

    def __init__(  # noqa: PLR0915
        self,
        parent: QWidget | None = None,
        *,
        source_setting_key: str = "",
        target_setting_key: str = "",
        model_setting_key: str = "",
    ) -> None:
        """Initializes the LanguageSelectionDialog.

        Args:
            parent: Parent widget.
            source_setting_key: Settings key to persist source language.
            target_setting_key: Settings key to persist target language.
            model_setting_key: Feature-specific key for the LLM model; the
                dialog restores and saves using this key (with a fallback
                to the global default) so each feature's model pick is
                independent.
        """
        super().__init__(parent, tr("dialog.translation_setup"))
        self._source_setting_key = source_setting_key or SETTING_LAST_SOURCE_LANGUAGE
        self._target_setting_key = target_setting_key or SETTING_LAST_TARGET_LANGUAGE
        self._model_setting_key = model_setting_key

        from PySide6.QtGui import QIcon  # noqa: PLC0415
        from PySide6.QtWidgets import QComboBox  # noqa: PLC0415

        # Model selection
        self._model_label, self.model_combo = _create_model_combo(
            self.layout,
            model_setting_key=model_setting_key,
        )

        # Source Language
        self.src_label = QLabel(tr("dialog.source_language"))
        self.src_label.setStyleSheet(
            f"font-size: 13px; color: {color('text_secondary')}; font-weight: 600;"
        )
        self.layout.addWidget(self.src_label)

        self.src_combo = QComboBox()
        # Auto-detect entry has no userData → callers treat
        # ``currentData() is None`` as the sentinel.
        self.src_combo.addItem(_create_emoji_icon(), tr("common.lang_auto_detect"))
        for _locale, label, icon, native in iter_languages_sorted_for_ui():
            flag = QIcon(f"{FLAGS_DIR}/{icon}.png")
            self.src_combo.addItem(
                flag,
                format_language_picker_label(label, native),
                label,
            )
        self.src_combo.setStyleSheet(style_setting_combo())
        self.src_combo.setFixedHeight(HEIGHT_CONTROL)
        self.src_combo.setIconSize(QSize(FLAG_ICON_WIDTH, FLAG_ICON_HEIGHT))
        # Restore last used source language — match against the
        # canonical English label held in itemData, not the localised
        # display text.
        last_src = load_setting(self._source_setting_key, "")
        if last_src:
            idx = self.src_combo.findData(last_src)
            if idx >= 0:
                self.src_combo.setCurrentIndex(idx)
        self.layout.addWidget(self.src_combo)

        # Target Language
        self.target_label = QLabel(tr("dialog.target_language"))
        self.target_label.setStyleSheet(
            f"font-size: 13px; color: {color('text_secondary')};"
            " font-weight: 600; margin-top: 10px;"
        )
        self.layout.addWidget(self.target_label)

        self.target_combo = QComboBox()
        for _locale, label, icon, native in iter_languages_sorted_for_ui():
            flag = QIcon(f"{FLAGS_DIR}/{icon}.png")
            self.target_combo.addItem(
                flag,
                format_language_picker_label(label, native),
                label,
            )
        self.target_combo.setStyleSheet(style_setting_combo())
        self.target_combo.setFixedHeight(HEIGHT_CONTROL)
        self.target_combo.setIconSize(QSize(FLAG_ICON_WIDTH, FLAG_ICON_HEIGHT))
        # Restore last used target language
        last_target = load_setting(self._target_setting_key, "")
        if last_target:
            idx = self.target_combo.findData(last_target)
            if idx >= 0:
                self.target_combo.setCurrentIndex(idx)
        self.layout.addWidget(self.target_combo)

        # Buttons
        btn_layout = QHBoxLayout()
        self.translate_btn = QPushButton(tr("btn.start_translation"))
        self.translate_btn.setFixedHeight(HEIGHT_CONTROL)
        self.translate_btn.setStyleSheet(style_primary_button() + "padding: 0 24px;")
        self.translate_btn.setCursor(Qt.CursorShape.PointingHandCursor)

        self.cancel_btn = QPushButton(tr("btn.cancel"))
        self.cancel_btn.setFixedHeight(HEIGHT_CONTROL)
        self.cancel_btn.setStyleSheet(style_secondary_button())
        self.cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)

        btn_layout.addStretch()
        btn_layout.addWidget(self.cancel_btn)
        btn_layout.addWidget(self.translate_btn)
        self.layout.addLayout(btn_layout)

        self.translate_btn.clicked.connect(self.accept)
        self.cancel_btn.clicked.connect(self.reject)

    @staticmethod
    def get_selection(  # noqa: PLR0913 — explicit per-feature setting overrides
        parent: QWidget | None,
        source_lang: str = "",
        target_lang: str = "",
        *,
        source_setting_key: str = "",
        target_setting_key: str = "",
        model_setting_key: str = "",
    ) -> tuple[str, str, str, bool]:
        """Shows the dialog and returns (source, target, model_id, success).

        Args:
            parent: Parent widget.
            source_lang: Pre-select this source language.
            target_lang: Pre-select this target language.
            source_setting_key: Settings key to persist source language.
            target_setting_key: Settings key to persist target language.
            model_setting_key: Feature-specific key to persist the picked
                LLM model (e.g. ``SETTING_LLM_MODEL_TRANSLATE_DOCUMENT``).
                Empty string falls back to the legacy global default.
        """
        dialog = LanguageSelectionDialog(
            parent,
            source_setting_key=source_setting_key,
            target_setting_key=target_setting_key,
            model_setting_key=model_setting_key,
        )
        # Pre-select languages if provided (empty = auto-detect, index 0).
        # Match by canonical English label held in itemData, not by
        # localised display text.
        if source_lang:
            idx = dialog.src_combo.findData(source_lang)
            if idx >= 0:
                dialog.src_combo.setCurrentIndex(idx)
        if target_lang:
            idx = dialog.target_combo.findData(target_lang)
            if idx >= 0:
                dialog.target_combo.setCurrentIndex(idx)
        result = dialog.exec()
        accepted = result == QDialog.DialogCode.Accepted
        # Return canonical English labels — that's what the engine,
        # DB, and LLM prompts expect.
        target = dialog.target_combo.currentData() or ""
        src = (
            ""
            if dialog.src_combo.currentIndex() == 0  # noqa: PLR2004
            else (dialog.src_combo.currentData() or "")
        )
        # Selected LLM model
        model_id = ""
        if dialog.model_combo is not None:
            model_id = dialog.model_combo.currentData(Qt.ItemDataRole.UserRole) or ""
        if accepted:
            save_setting(dialog._source_setting_key, src)
            save_setting(dialog._target_setting_key, target)
            if model_id:
                from src.constants.settings import (  # noqa: PLC0415
                    SETTING_LLM_LAST_MODEL,
                )
                from src.utils.config_manager import (  # noqa: PLC0415
                    save_model_for_feature,
                )

                # Feature-specific key when provided; always update the
                # legacy global default so newly opened features inherit.
                if dialog._model_setting_key:
                    save_model_for_feature(
                        dialog._model_setting_key,
                        model_id,
                    )
                else:
                    save_setting(SETTING_LLM_LAST_MODEL, model_id)
        return (src, target, model_id, accepted)


class SourceLanguageDialog(BaseDialog):
    """Dialog for selecting only the source language (used by Extract Text)."""

    def __init__(  # noqa: PLR0913, PLR0915
        self,
        parent: QWidget | None = None,
        *,
        title_key: str = "extract_text.extraction_setup",
        label_key: str = "extract_text.source_language",
        confirm_key: str = "extract_text.btn_extract",
        setting_key: str = "",
        show_target: bool = False,
        target_setting_key: str = "",
        model_setting_key: str = "",
    ) -> None:
        """Initializes the SourceLanguageDialog.

        Args:
            parent: Parent widget.
            title_key: i18n key for the dialog title.
            label_key: i18n key for the source language label.
            confirm_key: i18n key for the confirm button text.
            setting_key: Settings key to persist the last selected language.
            show_target: If True, show an optional target language selector.
            target_setting_key: Settings key for the target language.
            model_setting_key: Feature-specific key for the LLM model;
                empty falls back to the legacy global default.
        """
        super().__init__(parent, tr(title_key))
        self._setting_key = setting_key
        self._target_setting_key = target_setting_key
        self._model_setting_key = model_setting_key
        self._show_target = show_target

        from PySide6.QtGui import QIcon  # noqa: PLC0415
        from PySide6.QtWidgets import QComboBox  # noqa: PLC0415

        # Source language (always present — the primary input of the
        # dialog so it leads the layout).
        self.src_label = QLabel(tr(label_key))
        self.src_label.setStyleSheet(
            f"font-size: 13px; color: {color('text_secondary')}; font-weight: 600;"
        )
        self.layout.addWidget(self.src_label)

        self.src_combo = QComboBox()
        self.src_combo.addItem(_create_emoji_icon(), tr("common.lang_auto_detect"))
        for _locale, label, icon, native in iter_languages_sorted_for_ui():
            flag = QIcon(f"{FLAGS_DIR}/{icon}.png")
            self.src_combo.addItem(
                flag,
                format_language_picker_label(label, native),
                label,
            )
        self.src_combo.setStyleSheet(style_setting_combo())
        self.src_combo.setFixedHeight(HEIGHT_CONTROL)
        self.src_combo.setIconSize(QSize(FLAG_ICON_WIDTH, FLAG_ICON_HEIGHT))
        # Restore last used source language
        if not self._setting_key:
            from src.constants.settings import (  # noqa: PLC0415
                SETTING_LAST_EXTRACT_LANGUAGE,
            )

            self._setting_key = SETTING_LAST_EXTRACT_LANGUAGE

        last_src = load_setting(self._setting_key, "")
        if last_src:
            idx = self.src_combo.findData(last_src)
            if idx >= 0:
                self.src_combo.setCurrentIndex(idx)
        self.layout.addWidget(self.src_combo)

        # Optional target language (for auto-translate).
        self.target_combo = None
        if show_target:
            self.target_label = QLabel(tr("subtitle.target_language"))
            self.target_label.setStyleSheet(
                f"font-size: 13px; color: {color('text_secondary')}; font-weight: 600;"
            )
            self.layout.addWidget(self.target_label)

            self.target_combo = QComboBox()
            self.target_combo.addItem(
                _create_emoji_icon("\U0001f6ab"),
                tr("common.lang_no_translation"),
            )
            for _locale, label, icon, native in iter_languages_sorted_for_ui():
                flag = QIcon(f"{FLAGS_DIR}/{icon}.png")
                self.target_combo.addItem(
                    flag,
                    format_language_picker_label(label, native),
                    label,
                )
            self.target_combo.setStyleSheet(style_setting_combo())
            self.target_combo.setFixedHeight(HEIGHT_CONTROL)
            self.target_combo.setIconSize(
                QSize(FLAG_ICON_WIDTH, FLAG_ICON_HEIGHT),
            )

            # Restore last used target language
            if target_setting_key:
                last_tgt = load_setting(target_setting_key, "")
                if last_tgt:
                    idx = self.target_combo.findData(last_tgt)
                    if idx >= 0:
                        self.target_combo.setCurrentIndex(idx)

            self.layout.addWidget(self.target_combo)

        # Model selection appears LAST so the layout reads source →
        # target → (if translating) which model.  In SourceLanguageDialog
        # the LLM is optional — the model is only used when the target
        # picker is shown AND set to a real language.  Placing it at
        # the bottom means showing/hiding it on "No translation" only
        # changes the dialog's final row, not the position of any
        # other row above it.
        self._model_label, self.model_combo = _create_model_combo(
            self.layout,
            model_setting_key=model_setting_key,
        )

        if show_target:
            # Hide the Model picker when target = "No translation"
            # (index 0).  The Model picker selects the LLM used for
            # translation — when no translation is requested, the
            # picker is dead UI.  Wire the sync AFTER the initial
            # selection is restored so the visibility matches the
            # restored state on first paint.
            def _sync_model_visibility() -> None:
                """Hides Model label + combo when no translation is selected.

                Also calls ``adjustSize()`` so the dialog actually
                shrinks/grows to match — without it, a dialog that
                opened sized for "Model visible" leaves ~100px of
                dead space at the bottom when the user picks
                "No translation".  ``adjustSize()`` is a no-op when
                the dialog hasn't been shown yet, so the initial-sync
                call at the end of ``__init__`` doesn't disrupt the
                pre-show layout.
                """
                show = self.target_combo.currentIndex() != 0
                if self._model_label is not None:
                    self._model_label.setVisible(show)
                if self.model_combo is not None:
                    self.model_combo.setVisible(show)
                # Defer to the next event loop iteration so widget
                # geometry has fully settled before measuring the new
                # sizeHint — calling adjustSize() inline sometimes
                # measures stale geometry under offscreen platforms.
                self.adjustSize()

            self.target_combo.currentIndexChanged.connect(
                lambda _i: _sync_model_visibility(),
            )
            _sync_model_visibility()  # Apply to restored initial state.

        # Buttons
        btn_layout = QHBoxLayout()
        self.confirm_btn = QPushButton(tr(confirm_key))
        self.confirm_btn.setFixedHeight(HEIGHT_CONTROL)
        self.confirm_btn.setStyleSheet(style_primary_button() + "padding: 0 24px;")
        self.confirm_btn.setCursor(Qt.CursorShape.PointingHandCursor)

        self.cancel_btn = QPushButton(tr("btn.cancel"))
        self.cancel_btn.setFixedHeight(HEIGHT_CONTROL)
        self.cancel_btn.setStyleSheet(style_secondary_button())
        self.cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)

        btn_layout.addStretch()
        btn_layout.addWidget(self.cancel_btn)
        btn_layout.addWidget(self.confirm_btn)
        self.layout.addLayout(btn_layout)

        self.confirm_btn.clicked.connect(self.accept)
        self.cancel_btn.clicked.connect(self.reject)

    @staticmethod
    def get_selection(
        parent: QWidget | None,
        source_lang: str = "",
        **kwargs: Any,  # noqa: ANN401
    ) -> tuple[str, str, str, bool]:
        """Shows the dialog and returns (source_lang, target_lang, model_id, accepted).

        Args:
            parent: Parent widget.
            source_lang: Pre-select this source language.
            **kwargs: Forwarded to ``__init__`` (title_key, confirm_key,
                setting_key, show_target, target_setting_key, etc.).

        Returns:
            Tuple of (source_lang, target_lang, model_id, accepted).
            target_lang is empty if show_target is False or "No translation".
        """
        dialog = SourceLanguageDialog(parent, **kwargs)
        if source_lang:
            idx = dialog.src_combo.findData(source_lang)
            if idx >= 0:
                dialog.src_combo.setCurrentIndex(idx)
        result = dialog.exec()
        accepted = result == QDialog.DialogCode.Accepted
        # Index 0 is auto-detect; return empty string.  Other entries
        # carry the canonical English label as itemData.
        src = (
            ""
            if dialog.src_combo.currentIndex() == 0  # noqa: PLR2004
            else (dialog.src_combo.currentData() or "")
        )
        # Target language (index 0 = no translation)
        target = ""
        if dialog.target_combo is not None and dialog.target_combo.currentIndex() > 0:
            target = dialog.target_combo.currentData() or ""

        # Selected LLM model
        model_id = ""
        if dialog.model_combo is not None:
            model_id = dialog.model_combo.currentData(Qt.ItemDataRole.UserRole) or ""

        if accepted:
            save_setting(dialog._setting_key, src)
            if dialog._target_setting_key and target:
                save_setting(dialog._target_setting_key, target)
            if model_id:
                from src.constants.settings import (  # noqa: PLC0415
                    SETTING_LLM_LAST_MODEL,
                )
                from src.utils.config_manager import (  # noqa: PLC0415
                    save_model_for_feature,
                )

                if dialog._model_setting_key:
                    save_model_for_feature(
                        dialog._model_setting_key,
                        model_id,
                    )
                else:
                    save_setting(SETTING_LLM_LAST_MODEL, model_id)

        return (src, target, model_id, accepted)


class VoiceSetupDialog(BaseDialog):
    """Dialog for voice generation language selection.

    Voice gender (Edge), voice name (Google / Gemini), and voice ID
    (ElevenLabs) all live in Settings → Generate Voice now — they
    are stable per-engine preferences, not per-task choices.  The
    only field a user routinely changes per generation is the
    target language.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initializes the VoiceSetupDialog."""
        super().__init__(parent, tr("voice.setup_title"))

        from PySide6.QtGui import QIcon  # noqa: PLC0415
        from PySide6.QtWidgets import QComboBox  # noqa: PLC0415

        # No model selection — TTS does not use LLM
        self.model_combo = None

        # --- Voice Language ---
        self.lang_label = QLabel(tr("voice.language"))
        self.lang_label.setStyleSheet(
            f"font-size: 13px; color: {color('text_secondary')}; font-weight: 600;"
        )
        self.layout.addWidget(self.lang_label)

        self.lang_combo = QComboBox()
        self.lang_combo.setStyleSheet(style_setting_combo())
        self.lang_combo.setCursor(Qt.CursorShape.PointingHandCursor)

        # Populate with flag icons (no auto-detect for TTS)
        for _locale_id, label, icon_name, native_name in iter_languages_sorted_for_ui():
            flag = QIcon(f"{FLAGS_DIR}/{icon_name}.png")
            self.lang_combo.addItem(
                flag,
                format_language_picker_label(label, native_name),
                label,
            )

        self.lang_combo.setFixedHeight(HEIGHT_CONTROL)
        self.lang_combo.setIconSize(QSize(FLAG_ICON_WIDTH, FLAG_ICON_HEIGHT))

        # Restore last used language
        from src.constants.settings import (  # noqa: PLC0415
            SETTING_LAST_VOICE_LANGUAGE,
        )

        last_lang = load_setting(SETTING_LAST_VOICE_LANGUAGE, "")
        if last_lang:
            idx = self.lang_combo.findData(last_lang)
            if idx >= 0:
                self.lang_combo.setCurrentIndex(idx)

        self.layout.addWidget(self.lang_combo)

        # --- Buttons ---
        btn_layout = QHBoxLayout()
        self.confirm_btn = QPushButton(tr("voice.btn_generate"))
        self.confirm_btn.setFixedHeight(HEIGHT_CONTROL)
        self.confirm_btn.setStyleSheet(style_primary_button() + "padding: 0 24px;")
        self.confirm_btn.setCursor(Qt.CursorShape.PointingHandCursor)

        self.cancel_btn = QPushButton(tr("btn.cancel"))
        self.cancel_btn.setFixedHeight(HEIGHT_CONTROL)
        self.cancel_btn.setStyleSheet(style_secondary_button())
        self.cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)

        btn_layout.addStretch()
        btn_layout.addWidget(self.cancel_btn)
        btn_layout.addWidget(self.confirm_btn)
        self.layout.addLayout(btn_layout)

        self.confirm_btn.clicked.connect(self.accept)
        self.cancel_btn.clicked.connect(self.reject)

    @staticmethod
    def get_selection(
        parent: QWidget | None,
    ) -> tuple[str, str, str, bool]:
        """Shows the dialog and returns (language, gender, model_id, accepted).

        ``gender`` is read from settings (``SETTING_LAST_VOICE_GENDER``,
        the Edge TTS gender radio in Settings → Generate Voice) so the
        return-tuple shape stays compatible with existing callers.
        ``model_id`` is empty — TTS doesn't use LLM.
        """
        dialog = VoiceSetupDialog(parent)
        result = dialog.exec()
        accepted = result == QDialog.DialogCode.Accepted

        lang = (dialog.lang_combo.currentData() or "").strip()
        # Read the persisted Edge-TTS gender; defaults to FEMALE.
        from src.constants.settings import (  # noqa: PLC0415
            SETTING_LAST_VOICE_GENDER,
        )

        gender = (
            str(load_setting(SETTING_LAST_VOICE_GENDER, "FEMALE")).upper() or "FEMALE"
        )
        model_id = ""

        if accepted:
            from src.constants.settings import (  # noqa: PLC0415
                SETTING_LAST_VOICE_LANGUAGE,
            )

            save_setting(SETTING_LAST_VOICE_LANGUAGE, lang)
            if model_id:
                from src.constants.settings import (  # noqa: PLC0415
                    SETTING_LLM_LAST_MODEL,
                )

                save_setting(SETTING_LLM_LAST_MODEL, model_id)

        return (lang, gender, model_id, accepted)


def _style_installed_voice_button() -> str:
    """QSS for a disabled "✓ Female voice" / "✓ Male voice" badge button.

    Inverts the standard `style_primary_button` palette to success
    green so the user can scan a row and tell which voices are
    already on disk.  The default `:disabled` state on outlined
    buttons greys the text out — we want to keep the success
    colour visible since the disabled state here means "done", not
    "unavailable".
    """
    success = color("success")
    return f"""
        QPushButton {{
            color: {success};
            border: 1px solid {success};
            background-color: transparent;
            font-size: 14px;
            font-weight: 500;
            padding: 10px 24px;
            border-radius: 8px;
            outline: none;
        }}
        QPushButton:disabled {{
            color: {success};
            border: 1px solid {success};
            background-color: transparent;
        }}
    """


class _PiperDownloadThread(QThread):
    """Per-voice Piper download worker.

    Owns the network call to ``download_piper_voice``; ``error_msg``
    is empty on success and carries the exception text on failure.
    """

    def __init__(self, voice_id: str) -> None:
        """Initializes the download thread for *voice_id*."""
        super().__init__()
        self.voice_id = voice_id
        self.error_msg: str = ""

    def run(self) -> None:  # noqa: D401
        """Runs the blocking HTTP download on the worker thread."""
        from src.core.speech_engine import (  # noqa: PLC0415
            download_piper_voice,
        )

        try:
            download_piper_voice(self.voice_id)
        except (ValueError, OSError) as exc:
            self.error_msg = str(exc)


class PiperVoiceDownloadDialog(BaseDialog):
    """Voice library for the Piper TTS engine.

    Lists one row per language; each row carries up to two
    independent download slots (Female / Male) so the user can see
    at a glance which gender × language combinations they have
    installed.  Languages that only ship a single voice in the
    rhasspy/piper-voices catalogue (Italian, Dutch, Chinese
    (Simplified) → female-only; Portuguese → male-only) render only
    that one slot; the engine's ``get_piper_voice_for`` handles
    cross-gender fallback at synthesis time so a MALE-Italian (or
    FEMALE-Portuguese) request still works.

    Multiple downloads run in parallel (one ``QThread`` per voice
    ID), and the dialog bounded-waits any in-flight thread on close
    so the user can't quit Settings mid-download and crash the app.
    The dialog emits :pyattr:`voices_changed` after every successful
    download so the parent settings page can refresh its install
    summary banner without polling.
    """

    voices_changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initializes the Piper voice library dialog."""
        super().__init__(parent, tr("settings.piper_voices_dialog_title"))
        self.setMinimumWidth(640)
        self.setMinimumHeight(520)

        from src.core.speech_engine import (  # noqa: PLC0415
            PIPER_VOICES_BY_GENDER_AND_LANGUAGE,
            is_piper_voice_installed,
        )

        # Intro text explaining the download size + auto-pick contract.
        intro = QLabel(tr("settings.piper_voices_dialog_intro"))
        intro.apply_language = lambda w=intro: w.setText(
            tr("settings.piper_voices_dialog_intro"),
        )
        intro.setWordWrap(True)
        intro.setStyleSheet(
            f"color: {color('text_secondary')}; font-size: 13px;",
        )
        self.layout.addWidget(intro)

        # Scrollable list of language rows.  ``QScrollArea`` is
        # necessary because the catalogue currently has 12 languages
        # and may grow — a fixed-height column would overflow the
        # dialog on small displays.
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background: transparent; border: none;")
        scroll_body = QWidget()
        scroll_body.setStyleSheet("background: transparent;")
        rows_layout = QVBoxLayout(scroll_body)
        rows_layout.setContentsMargins(0, 0, 0, 0)
        rows_layout.setSpacing(8)
        scroll.setWidget(scroll_body)
        self.layout.addWidget(scroll, 1)

        # ``_voice_rows`` keys per-voice slot widgets by voice_id so
        # the worker-finished callback can update only the affected
        # slot — without touching its sibling slot in the same
        # language row (e.g. finishing the Female download mustn't
        # flip the Male button's state).  ``_threads`` keys
        # in-flight downloads the same way so a second click on the
        # same voice is a no-op (the button is disabled, but the
        # check defends against signal storms).
        self._voice_rows: dict[str, dict[str, QWidget]] = {}
        self._threads: dict[str, _PiperDownloadThread] = {}

        # Pivot ``PIPER_VOICES_BY_GENDER_AND_LANGUAGE`` from
        # ``{gender: {lang: voice_id}}`` to ``{lang: {gender: voice_id}}``
        # so we can build one row per language with up to two
        # gender slots in a single pass.
        from src.constants.languages import LANGUAGES  # noqa: PLC0415

        native_by_english: dict[str, str] = {
            label: native for _locale, label, _icon, native in LANGUAGES
        }
        # English label → flag PNG basename, used to render a flag
        # icon at the start of each language row.  Matches the
        # convention used by every other language picker in the app
        # (LanguageSelectionDialog, voice combos, etc.).
        flag_by_english: dict[str, str] = {
            label: icon for _locale, label, icon, _native in LANGUAGES
        }

        per_lang: dict[str, dict[str, str]] = {}
        for gender_key, by_lang in PIPER_VOICES_BY_GENDER_AND_LANGUAGE.items():
            for language, voice_id in by_lang.items():
                per_lang.setdefault(language, {})[gender_key] = voice_id

        # Sort languages by their localised label (case-insensitive)
        # so the order matches what the user sees in the language
        # pickers across the rest of the app.
        sorted_langs = sorted(
            per_lang.keys(),
            key=lambda lang: format_language_picker_label(
                lang,
                native_by_english.get(lang, lang),
            ).casefold(),
        )

        for language in sorted_langs:
            display_lang = format_language_picker_label(
                language,
                native_by_english.get(language, language),
            )
            voices_for_lang = per_lang[language]
            self._build_language_row(
                display_lang=display_lang,
                flag_basename=flag_by_english.get(language, ""),
                voices=voices_for_lang,
                installed_check=is_piper_voice_installed,
                parent_layout=rows_layout,
            )

        rows_layout.addStretch(1)

        # Footer: single Close button, right-aligned.
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        self.close_btn = QPushButton(tr("btn.close"))
        self.close_btn.setFixedHeight(HEIGHT_CONTROL)
        self.close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_btn.setStyleSheet(style_secondary_button())
        self.close_btn.clicked.connect(self.accept)
        btn_row.addWidget(self.close_btn)
        self.layout.addLayout(btn_row)

    def _build_language_row(
        self,
        *,
        display_lang: str,
        flag_basename: str,
        voices: dict[str, str],
        installed_check,  # noqa: ANN001
        parent_layout: QVBoxLayout,
    ) -> None:
        """Builds one row for *display_lang* with one or two voice slots.

        ``voices`` maps gender ("FEMALE" / "MALE") → voice ID.  Only
        the genders actually present in the catalogue render slots —
        Italian / Dutch / Chinese (Simplified) get a Female slot only,
        Portuguese gets a Male slot only, every other language gets
        both.  Cross-gender fallback at synthesis time is handled by
        ``get_piper_voice_for``.

        ``flag_basename`` is the flag PNG name (without ``.png``) from
        :data:`LANGUAGES`; an empty string skips the flag column.
        """
        from PySide6.QtGui import QPixmap  # noqa: PLC0415

        from src.constants import (  # noqa: PLC0415
            FLAG_ICON_HEIGHT,
            FLAG_ICON_WIDTH,
            FLAGS_DIR,
        )

        frame = QFrame()
        frame.setObjectName("PiperVoiceRow")
        frame.setStyleSheet(
            f"QFrame#PiperVoiceRow {{"
            f" border: 1px solid {color('border_light')};"
            f" border-radius: 8px;"
            f" background-color: {color('component_bg')};"
            f" padding: 6px 10px;"
            f"}}",
        )
        row = QHBoxLayout(frame)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(12)

        if flag_basename:
            flag_label = QLabel()
            pixmap = QPixmap(f"{FLAGS_DIR}/{flag_basename}.png")
            if not pixmap.isNull():
                pixmap = pixmap.scaled(
                    FLAG_ICON_WIDTH,
                    FLAG_ICON_HEIGHT,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                flag_label.setPixmap(pixmap)
                flag_label.setFixedWidth(FLAG_ICON_WIDTH)
                row.addWidget(flag_label)

        lang_label = QLabel(display_lang)
        lang_label.setStyleSheet(
            f"color: {color('text_primary')}; font-weight: 600;",
        )
        row.addWidget(lang_label, 1)

        female_voice = voices.get("FEMALE")
        male_voice = voices.get("MALE")
        if female_voice:
            self._build_voice_slot(
                voice_id=female_voice,
                gender_label_key="settings.piper_voice_female_btn",
                installed=installed_check(female_voice),
                parent_row=row,
            )
        if male_voice:
            self._build_voice_slot(
                voice_id=male_voice,
                gender_label_key="settings.piper_voice_male_btn",
                installed=installed_check(male_voice),
                parent_row=row,
            )

        parent_layout.addWidget(frame)

    def _build_voice_slot(
        self,
        *,
        voice_id: str,
        gender_label_key: str,
        installed: bool,
        parent_row: QHBoxLayout,
    ) -> None:
        """Builds a single per-voice slot — one button that fuses gender + state.

        The button label encodes both the gender ("Female voice" /
        "Male voice") and the current state via a leading glyph
        (``⬇`` to download, ``✓`` when installed).  Style + enabled
        state flip with the install state — see ``_refresh_row``.
        """
        action_btn = QPushButton("")
        action_btn.setFixedHeight(HEIGHT_CONTROL)
        action_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        action_btn.clicked.connect(
            lambda _checked=False, vid=voice_id: self._start_download(vid),
        )
        # Stash the i18n key on the widget so language-switch
        # refresh can rebuild the localised label.
        action_btn.setProperty("piperGenderKey", gender_label_key)
        parent_row.addWidget(action_btn)

        widgets = {
            "action_btn": action_btn,
            "gender_label_key": gender_label_key,
        }
        self._voice_rows[voice_id] = widgets
        self._refresh_row(voice_id, widgets, installed=installed, in_flight=False)

    def _refresh_row(
        self,
        voice_id: str,  # noqa: ARG002
        widgets: dict[str, QWidget],
        *,
        installed: bool,
        in_flight: bool,
    ) -> None:
        """Updates the action button's label + style for a single voice slot."""
        action_btn = widgets["action_btn"]
        gender_text = tr(widgets["gender_label_key"])
        if in_flight:
            # Disabled, secondary style, downloading suffix.
            action_btn.setText(
                f"{gender_text} — {tr('settings.piper_downloading')}",
            )
            action_btn.setEnabled(False)
            action_btn.setStyleSheet(style_secondary_button())
            action_btn.setCursor(Qt.CursorShape.ArrowCursor)
            return
        if installed:
            # Disabled green-outlined "badge" — communicates "done" by
            # inverting the primary/secondary colour palette to success.
            action_btn.setText(f"✓ {gender_text}")
            action_btn.setEnabled(False)
            action_btn.setStyleSheet(_style_installed_voice_button())
            action_btn.setCursor(Qt.CursorShape.ArrowCursor)
            return
        # Default: actionable outlined-primary button with a heavy
        # down-arrow as the download glyph.  ``⬇`` (U+2B07) reads at
        # text weight, not as a colour emoji, and renders bigger than
        # the basic ``↓`` arrow at the same font size.  Outlined
        # (vs. filled primary) reads as "available action" without
        # dominating the row visually — the dialog can show 12+ rows
        # so a wall of solid blue buttons would feel heavy.
        action_btn.setText(f"⬇ {gender_text}")
        action_btn.setEnabled(True)
        action_btn.setStyleSheet(style_outlined_primary_button())
        action_btn.setCursor(Qt.CursorShape.PointingHandCursor)

    def _start_download(self, voice_id: str) -> None:
        """Spawns a download thread for *voice_id* if none is in flight."""
        if voice_id in self._threads:
            return
        widgets = self._voice_rows.get(voice_id)
        if widgets is None:
            return

        thread = _PiperDownloadThread(voice_id)
        self._threads[voice_id] = thread

        def _on_finished() -> None:
            self._threads.pop(voice_id, None)
            from shiboken6 import isValid  # noqa: PLC0415

            from src.core.speech_engine import (  # noqa: PLC0415
                is_piper_voice_installed,
            )

            # The dialog may have been closed (and widgets destroyed)
            # before the thread finished — guard against touching
            # deleted Qt objects.
            if not isValid(widgets["action_btn"]):
                return
            installed = is_piper_voice_installed(voice_id)
            self._refresh_row(
                voice_id,
                widgets,
                installed=installed,
                in_flight=False,
            )
            if thread.error_msg:
                CustomMessageDialog(
                    self,
                    tr("settings.piper_download_failed_title"),
                    tr(
                        "settings.piper_download_failed_msg",
                        voice=voice_id,
                    ),
                ).exec()
            elif installed:
                # Tell the parent settings page to refresh its summary
                # banner — the install count just bumped.
                self.voices_changed.emit()

        thread.finished.connect(_on_finished)
        thread.start()
        self._refresh_row(
            voice_id,
            widgets,
            installed=False,
            in_flight=True,
        )

    def _drain_threads(self) -> None:
        """Bounded-waits every in-flight download before the dialog dies.

        Matches the ``wait(2000)`` shutdown contract documented in
        AGENTS.md for every page-owned ``QThread`` — without it,
        closing the dialog mid-download would surface "QThread
        destroyed while still running" warnings and the urlopen
        socket would be torn down ungracefully.  We don't try to
        cancel the in-flight HTTP request (urllib has no clean
        cancel hook); 2 s is enough for a chunk to land and the
        thread to exit at the next loop iteration in
        ``_download_to_file``.
        """
        for thread in list(self._threads.values()):
            thread.wait(2000)
        self._threads.clear()

    def closeEvent(self, event) -> None:  # noqa: ANN001, N802
        """Wait for downloads on window-close via the system close icon."""
        self._drain_threads()
        super().closeEvent(event)

    def done(self, result: int) -> None:  # noqa: D401
        """Wait for downloads when accept()/reject() programmatically closes us."""
        self._drain_threads()
        super().done(result)
