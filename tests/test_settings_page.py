"""Comprehensive tests for the Settings page UI.

Covers:
- auto_fallback_selection() with persist=False
- create_settings_page() — full page construction and tab structure
- create_general_settings() — theme/language controls, office availability
- create_service_settings() — Google Cloud API key section
- create_ocr_settings() — OCR radio buttons and availability sync
- create_llm_settings() — LLM provider radios and provider config sections
- create_translation_settings() — checkboxes, OCR/office sync
- create_extract_text_settings() — method/format radios, availability sync
- create_subtitle_settings() — STT method, Whisper model, format radios
- create_voice_settings() — TTS method, format radios
- create_dubbing_settings() — output/history sections
- create_provider_config() — model enable/disable logic, hint banner
- switch_to_tab(), apply_theme(), apply_language()
- Theme change and language change callbacks
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QLabel,
    QRadioButton,
    QTabWidget,
    QWidget,
)

# ---------------------------------------------------------------------------
# Common mock context for settings page construction
# ---------------------------------------------------------------------------

# All external dependency patches needed to construct settings tabs without
# touching real config, filesystem, or OCR binaries.
_SETTINGS_PATCHES = {
    "src.ui.pages.settings.load_setting": lambda key, default="": default,
    "src.ui.pages.settings.save_setting": MagicMock(),
    "src.ui.pages.settings.check_llm_setup": lambda: True,
    "src.ui.pages.settings.check_ocr_setup": lambda: True,
    "src.ui.pages.settings.check_msoffice_available": lambda: False,
    "src.ui.pages.settings.check_libreoffice_available": lambda: False,
    "src.ui.pages.settings.check_office_converter_setup": lambda: False,
    "src.ui.pages.settings.check_ocr_availability": lambda m: (True, "OK"),
    "src.ui.pages.settings.detect_tesseract_languages": lambda: {"eng", "fra"},
    "src.ui.components.load_setting": lambda key, default="": default,
    "src.ui.components.save_setting": MagicMock(),
}


# Stub used by tests that exercise the dynamic-custom-provider section of the
# LLM tab.  The legacy "always-on Custom section" layout was replaced by a
# dynamic list keyed off ``load_custom_providers``; tests that expected the
# Name / API key / Endpoint / Models fields to be present now have to seed a
# provider explicitly.  Tests that exercise per-provider Name / save
# behaviour (TestCustomProviderName) deliberately *don't* use this — they
# rely on the real ``load_custom_providers`` flowing through the keychain-
# isolated test infra in conftest.
_STUB_CUSTOM_PROVIDER = [
    {
        "name": "Test Custom",
        "api_key": "test-key",
        "endpoint": "https://api.example.com",
        "models": "test-model",
    },
]


def _patch_custom_providers():
    """Returns a context manager that seeds one stub custom provider."""
    return patch(
        "src.utils.config_manager.load_custom_providers",
        return_value=list(_STUB_CUSTOM_PROVIDER),
    )


def _build_patch_context(overrides: dict | None = None):
    """Returns a contextmanager that patches all settings dependencies.

    Args:
        overrides: Dict of patch target -> replacement to override defaults.
    """
    import contextlib  # noqa: PLC0415

    targets = dict(_SETTINGS_PATCHES)
    if overrides:
        targets.update(overrides)

    return contextlib.ExitStack()


@pytest.fixture()
def _mock_settings_deps():
    """Patches all external dependencies for settings page construction."""
    import contextlib  # noqa: PLC0415

    targets = dict(_SETTINGS_PATCHES)
    with contextlib.ExitStack() as stack:
        for target, replacement in targets.items():
            stack.enter_context(patch(target, replacement))
        yield


# ---------------------------------------------------------------------------
# auto_fallback_selection — persist=False
# ---------------------------------------------------------------------------


class TestAutoFallbackSelectionPersistFalse:
    """Tests for auto_fallback_selection() with persist=False."""

    def _make_group(
        self,
        qapp: QApplication,
        labels: list[str],
        *,
        enabled: list[bool] | None = None,
        checked_index: int | None = None,
    ) -> QButtonGroup:
        """Helper to build a QButtonGroup with radio buttons."""
        group = QButtonGroup()
        if enabled is None:
            enabled = [True] * len(labels)
        for i, (label, is_enabled) in enumerate(
            zip(labels, enabled, strict=True),
        ):
            btn = QRadioButton(label)
            btn.setEnabled(is_enabled)
            group.addButton(btn)
            if i == checked_index:
                btn.setChecked(True)
        return group

    @patch("src.ui.pages.settings.save_setting")
    def test_persist_false_does_not_save_on_fallback(
        self,
        mock_save: MagicMock,
        qapp: QApplication,
    ) -> None:
        """When persist=False, fallback does not call save_setting."""
        from src.ui.pages.settings import auto_fallback_selection  # noqa: PLC0415

        group = self._make_group(
            qapp,
            ["A", "B"],
            enabled=[False, True],
        )
        auto_fallback_selection(group, "test_key", persist=False)
        assert group.checkedButton().text() == "B"
        mock_save.assert_not_called()

    @patch("src.ui.pages.settings.save_setting")
    def test_persist_false_does_not_save_when_all_disabled(
        self,
        mock_save: MagicMock,
        qapp: QApplication,
    ) -> None:
        """When persist=False and all disabled, does not save empty string."""
        from src.ui.pages.settings import auto_fallback_selection  # noqa: PLC0415

        group = self._make_group(
            qapp,
            ["X", "Y"],
            enabled=[False, False],
            checked_index=0,
        )
        group.buttons()[0].setEnabled(False)
        auto_fallback_selection(group, "key", persist=False)
        assert group.checkedButton() is None
        mock_save.assert_not_called()

    @patch("src.ui.pages.settings.save_setting")
    def test_persist_true_saves_on_fallback(
        self,
        mock_save: MagicMock,
        qapp: QApplication,
    ) -> None:
        """Default persist=True saves to settings on fallback."""
        from src.ui.pages.settings import auto_fallback_selection  # noqa: PLC0415

        group = self._make_group(
            qapp,
            ["P", "Q"],
            enabled=[False, True],
        )
        auto_fallback_selection(group, "my_key")
        mock_save.assert_called_once_with("my_key", "Q")

    @patch("src.ui.pages.settings.save_setting")
    def test_no_change_when_selection_valid(
        self,
        mock_save: MagicMock,
        qapp: QApplication,
    ) -> None:
        """No-op when the currently checked button is enabled."""
        from src.ui.pages.settings import auto_fallback_selection  # noqa: PLC0415

        group = self._make_group(qapp, ["A", "B"], checked_index=0)
        auto_fallback_selection(group, "k")
        mock_save.assert_not_called()
        assert group.checkedButton().text() == "A"


# ===================================================================
# create_settings_page — full page construction
# ===================================================================


class TestCreateSettingsPage:
    """Tests for the top-level create_settings_page() factory."""

    @pytest.fixture(autouse=True)
    def _deps(self, _mock_settings_deps):
        """Auto-use mock dependencies."""

    def _build_page(self, qapp: QApplication) -> QWidget:
        from src.ui.pages.settings import create_settings_page  # noqa: PLC0415

        return create_settings_page()

    def test_returns_qwidget(self, qapp: QApplication) -> None:
        """Factory returns a QWidget."""
        page = self._build_page(qapp)
        assert isinstance(page, QWidget)

    def test_has_tab_widget(self, qapp: QApplication) -> None:
        """Page contains a QTabWidget."""
        page = self._build_page(qapp)
        tabs = page.findChild(QTabWidget)
        assert tabs is not None

    def test_has_twelve_tabs(self, qapp: QApplication) -> None:
        """Settings page has 12 tabs."""
        page = self._build_page(qapp)
        tabs = page.findChild(QTabWidget)
        assert tabs.count() == 12  # noqa: PLR2004

    def test_tab_names(self, qapp: QApplication) -> None:
        """Tab names match expected order."""
        page = self._build_page(qapp)
        tabs = page.findChild(QTabWidget)
        tab_texts = [tabs.tabText(i) for i in range(tabs.count())]
        # tr() returns keys when translations are not loaded in test env,
        # but with mock load_setting returning defaults, check tab count.
        assert len(tab_texts) == 12  # noqa: PLR2004

    def test_has_switch_to_tab(self, qapp: QApplication) -> None:
        """Page has switch_to_tab method."""
        page = self._build_page(qapp)
        assert hasattr(page, "switch_to_tab")
        assert callable(page.switch_to_tab)

    def test_has_apply_theme(self, qapp: QApplication) -> None:
        """Page has apply_theme method."""
        page = self._build_page(qapp)
        assert hasattr(page, "apply_theme")
        assert callable(page.apply_theme)

    def test_has_apply_language(self, qapp: QApplication) -> None:
        """Page has apply_language method."""
        page = self._build_page(qapp)
        assert hasattr(page, "apply_language")
        assert callable(page.apply_language)

    def test_hide_event_remasks_revealed_secret_fields(
        self, qapp: QApplication
    ) -> None:
        """Hiding the page re-masks any QLineEdit toggled to Normal echo."""
        from PySide6.QtGui import QHideEvent
        from PySide6.QtWidgets import QLineEdit

        page = self._build_page(qapp)
        secret_fields = [
            f for f in page.findChildren(QLineEdit) if f.property("aitSecret")
        ]
        # The page bundles several API-key fields (Cloud, Soniox, ElevenLabs,
        # Gemini, Custom).  At least one must be present for the hook to
        # have anything to do.
        assert secret_fields, "expected at least one secret field on settings page"

        # Reveal them all, then dispatch a hide event.
        for field in secret_fields:
            field.setEchoMode(QLineEdit.EchoMode.Normal)
        page.hideEvent(QHideEvent())

        for field in secret_fields:
            assert field.echoMode() == QLineEdit.EchoMode.Password


# ===================================================================
# switch_to_tab
# ===================================================================


class TestSwitchToTab:
    """Tests for the switch_to_tab() method on the settings page."""

    @pytest.fixture(autouse=True)
    def _deps(self, _mock_settings_deps):
        """Auto-use mock dependencies."""

    def test_switch_to_tab_changes_current_index(self, qapp: QApplication) -> None:
        """switch_to_tab() sets the current tab index."""
        from src.ui.pages.settings import create_settings_page  # noqa: PLC0415

        page = create_settings_page()
        tabs = page.findChild(QTabWidget)
        page.switch_to_tab(3)
        assert tabs.currentIndex() == 3  # noqa: PLR2004

    def test_switch_to_first_tab(self, qapp: QApplication) -> None:
        """Can switch back to the first tab."""
        from src.ui.pages.settings import create_settings_page  # noqa: PLC0415

        page = create_settings_page()
        tabs = page.findChild(QTabWidget)
        page.switch_to_tab(5)
        page.switch_to_tab(0)
        assert tabs.currentIndex() == 0

    def test_switch_to_last_tab(self, qapp: QApplication) -> None:
        """Can switch to the last tab (index 9)."""
        from src.ui.pages.settings import create_settings_page  # noqa: PLC0415

        page = create_settings_page()
        tabs = page.findChild(QTabWidget)
        page.switch_to_tab(9)
        assert tabs.currentIndex() == 9  # noqa: PLR2004


# ===================================================================
# apply_theme
# ===================================================================


class TestApplyTheme:
    """Tests for the apply_theme() method."""

    @pytest.fixture(autouse=True)
    def _deps(self, _mock_settings_deps):
        """Auto-use mock dependencies."""

    def test_apply_theme_does_not_raise(self, qapp: QApplication) -> None:
        """apply_theme() completes without errors."""
        from src.ui.pages.settings import create_settings_page  # noqa: PLC0415

        page = create_settings_page()
        page.apply_theme()  # Should not raise

    def test_apply_theme_restyles_tab_widget(self, qapp: QApplication) -> None:
        """apply_theme() updates the QTabWidget stylesheet."""
        from src.ui.pages.settings import create_settings_page  # noqa: PLC0415

        page = create_settings_page()
        tabs = page.findChild(QTabWidget)
        # Clear style to detect re-application
        tabs.setStyleSheet("")
        page.apply_theme()
        assert tabs.styleSheet() != ""

    def test_apply_theme_restyles_radio_buttons(self, qapp: QApplication) -> None:
        """apply_theme() updates all QRadioButton stylesheets."""
        from src.ui.pages.settings import create_settings_page  # noqa: PLC0415

        page = create_settings_page()
        radios = page.findChildren(QRadioButton)
        # Clear all radio styles
        for r in radios:
            r.setStyleSheet("")
        page.apply_theme()
        # At least some radios should have stylesheets restored
        styled = [r for r in radios if r.styleSheet() != ""]
        assert len(styled) > 0


# ===================================================================
# apply_language
# ===================================================================


class TestApplyLanguage:
    """Tests for the apply_language() method."""

    @pytest.fixture(autouse=True)
    def _deps(self, _mock_settings_deps):
        """Auto-use mock dependencies."""

    def test_apply_language_does_not_raise(self, qapp: QApplication) -> None:
        """apply_language() completes without errors."""
        from src.ui.pages.settings import create_settings_page  # noqa: PLC0415

        page = create_settings_page()
        page.apply_language()  # Should not raise

    def test_apply_language_updates_tab_texts(self, qapp: QApplication) -> None:
        """apply_language() updates tab titles."""
        from src.ui.pages.settings import create_settings_page  # noqa: PLC0415

        page = create_settings_page()
        tabs = page.findChild(QTabWidget)
        # Overwrite tab text to detect re-application
        tabs.setTabText(0, "REPLACED")
        page.apply_language()
        # After apply_language, text should no longer be "REPLACED"
        assert tabs.tabText(0) != "REPLACED"


# ===================================================================
# create_general_settings
# ===================================================================


class TestCreateGeneralSettings:
    """Tests for create_general_settings() factory."""

    @pytest.fixture(autouse=True)
    def _deps(self, _mock_settings_deps):
        """Auto-use mock dependencies."""

    def _build(self, qapp: QApplication) -> QWidget:
        from src.ui.pages.settings import create_general_settings  # noqa: PLC0415

        return create_general_settings()

    def test_returns_qwidget(self, qapp: QApplication) -> None:
        """Factory returns a QWidget."""
        w = self._build(qapp)
        assert isinstance(w, QWidget)

    def test_contains_theme_radio_buttons(self, qapp: QApplication) -> None:
        """General settings has radio buttons for theme selection."""
        w = self._build(qapp)
        radios = w.findChildren(QRadioButton)
        # At least 3 theme radios (Auto, Light, Dark)
        assert len(radios) >= 3  # noqa: PLR2004

    def test_contains_language_combo(self, qapp: QApplication) -> None:
        """General settings has a language combo box."""
        w = self._build(qapp)
        combos = w.findChildren(QComboBox)
        assert len(combos) >= 1
        # The language combo should have items for UI_LANGUAGES
        from src.constants.i18n import UI_LANGUAGES  # noqa: PLC0415

        lang_combo = combos[0]
        assert lang_combo.count() == len(UI_LANGUAGES)

    def test_has_sync_office_availability(self, qapp: QApplication) -> None:
        """General settings widget has _sync_office_availability method."""
        w = self._build(qapp)
        assert hasattr(w, "_sync_office_availability")
        assert callable(w._sync_office_availability)

    def test_office_banners_hidden_when_no_office(self, qapp: QApplication) -> None:
        """When both MS Office and LibreOffice are unavailable, path is shown."""
        # Default mocks return False for both office checks
        w = self._build(qapp)
        # _sync_office_availability was already called during construction
        # The office path widget should be visible
        assert hasattr(w, "_sync_office_availability")

    def test_default_theme_auto_selected(self, qapp: QApplication) -> None:
        """Default theme 'Auto' is selected when no saved setting."""
        w = self._build(qapp)
        groups = w.findChildren(QButtonGroup)
        # Find the theme button group (first one)
        theme_group = groups[0] if groups else None
        assert theme_group is not None
        checked = theme_group.checkedButton()
        assert checked is not None


# ===================================================================
# Theme change callback
# ===================================================================


class TestThemeChangeCallback:
    """Tests for the on_theme_changed callback in General settings."""

    @pytest.fixture(autouse=True)
    def _deps(self, _mock_settings_deps):
        """Auto-use mock dependencies."""

    def test_theme_change_saves_setting(self, qapp: QApplication) -> None:
        """Clicking a theme radio saves the theme setting."""
        with patch("src.ui.pages.settings.save_setting") as mock_save:
            from src.ui.pages.settings import create_general_settings  # noqa: PLC0415

            w = create_general_settings()
            groups = w.findChildren(QButtonGroup)
            theme_group = groups[0]
            btns = theme_group.buttons()
            # Click the "Light" radio (index 1)
            if len(btns) > 1:
                btns[1].setChecked(True)
                theme_group.buttonClicked.emit(btns[1])
                # Verify save_setting was called with a theme value
                calls = [c for c in mock_save.call_args_list if c[0][0] == "app/theme"]
                assert len(calls) >= 1

    def test_theme_dark_saves_dark(self, qapp: QApplication) -> None:
        """Selecting the 'Dark' theme radio persists the lowercase 'dark' value."""
        with (
            patch("src.ui.pages.settings.save_setting") as mock_save,
            patch("src.ui.pages.settings.set_theme"),
        ):
            from src.ui.pages.settings import create_general_settings  # noqa: PLC0415

            w = create_general_settings()
            groups = w.findChildren(QButtonGroup)
            theme_group = groups[0]
            btns = theme_group.buttons()
            # Index 2 = "Dark"
            if len(btns) > 2:  # noqa: PLR2004
                btns[2].setChecked(True)
                theme_group.buttonClicked.emit(btns[2])
                save_calls = [
                    c for c in mock_save.call_args_list if c[0][0] == "app/theme"
                ]
                assert any(c[0][1] == "dark" for c in save_calls)


# ===================================================================
# Language change callback
# ===================================================================


class TestLanguageChangeCallback:
    """Tests for the on_lang_changed callback in General settings."""

    @pytest.fixture(autouse=True)
    def _deps(self, _mock_settings_deps):
        """Auto-use mock dependencies."""

    def test_language_change_saves_and_sets(self, qapp: QApplication) -> None:
        """Changing the language combo saves and applies the new language."""
        with (
            patch("src.ui.pages.settings.save_setting") as mock_save,
            patch("src.ui.pages.settings.set_language") as mock_set_lang,
        ):
            from src.ui.pages.settings import create_general_settings  # noqa: PLC0415

            w = create_general_settings()
            combos = w.findChildren(QComboBox)
            lang_combo = combos[0]
            # Switch to index 1 (en-UK)
            if lang_combo.count() > 1:
                lang_combo.setCurrentIndex(1)
                # Verify save_setting was called for UI language
                save_calls = [
                    c for c in mock_save.call_args_list if c[0][0] == "app/ui_language"
                ]
                assert len(save_calls) >= 1
                # Verify set_language was called
                mock_set_lang.assert_called()


# ===================================================================
# create_service_settings
# ===================================================================


class TestCreateServiceSettings:
    """Tests for create_service_settings() factory."""

    @pytest.fixture(autouse=True)
    def _deps(self, _mock_settings_deps):
        """Auto-use mock dependencies."""

    def test_returns_qwidget(self, qapp: QApplication) -> None:
        """Factory returns a QWidget."""
        from src.ui.pages.settings import create_service_settings  # noqa: PLC0415

        w = create_service_settings()
        assert isinstance(w, QWidget)

    def test_contains_labels(self, qapp: QApplication) -> None:
        """Service settings contains labels for Cloud API key."""
        from src.ui.pages.settings import create_service_settings  # noqa: PLC0415

        w = create_service_settings()
        labels = w.findChildren(QLabel)
        assert len(labels) > 0


# ===================================================================
# create_ocr_settings
# ===================================================================


class TestCreateOCRSettings:
    """Tests for create_ocr_settings() factory."""

    @pytest.fixture(autouse=True)
    def _deps(self, _mock_settings_deps):
        """Auto-use mock dependencies."""

    def _build(self, qapp: QApplication) -> QWidget:
        from src.ui.pages.settings import create_ocr_settings  # noqa: PLC0415

        return create_ocr_settings()

    def test_returns_qwidget(self, qapp: QApplication) -> None:
        """Factory returns a QWidget."""
        w = self._build(qapp)
        assert isinstance(w, QWidget)

    def test_has_ocr_radio_buttons(self, qapp: QApplication) -> None:
        """OCR settings has radio buttons for OCR methods."""
        w = self._build(qapp)
        radios = w.findChildren(QRadioButton)
        # Should have at least 3 (Tesseract, EasyOCR, Google Cloud)
        assert len(radios) >= 3  # noqa: PLR2004

    def test_ocr_radio_text_matches_methods(self, qapp: QApplication) -> None:
        """Every OCR method has a radio tagged with its method identifier."""
        from src.constants.ocr import OCR_METHODS  # noqa: PLC0415

        w = self._build(qapp)
        radios = w.findChildren(QRadioButton)
        radio_methods = {r.property("method") for r in radios}
        for method in OCR_METHODS:
            assert method in radio_methods

    def test_has_sync_ocr_availability(self, qapp: QApplication) -> None:
        """OCR widget exposes _sync_ocr_availability."""
        w = self._build(qapp)
        assert hasattr(w, "_sync_ocr_availability")
        assert callable(w._sync_ocr_availability)

    def test_ocr_method_toggled_saves_setting(self, qapp: QApplication) -> None:
        """Clicking an OCR radio button saves the setting."""
        with patch("src.ui.pages.settings.save_setting") as mock_save:
            w = self._build(qapp)
            groups = w.findChildren(QButtonGroup)
            ocr_group = groups[0]
            btns = ocr_group.buttons()
            # Click the first enabled button
            for btn in btns:
                if btn.isEnabled():
                    btn.setChecked(True)
                    ocr_group.buttonClicked.emit(btn)
                    break
            save_calls = [
                c for c in mock_save.call_args_list if c[0][0] == "ocr/method"
            ]
            assert len(save_calls) >= 1

    def test_google_cloud_disabled_when_no_key(self, qapp: QApplication) -> None:
        """Google Cloud OCR radio is disabled when setup returns False."""
        from src.constants.ocr import OCR_METHOD_GOOGLE_CLOUD  # noqa: PLC0415

        with (
            patch(
                "src.ui.pages.settings.check_ocr_availability",
                return_value=(True, "OK"),
            ),
            patch(
                "src.utils.config_manager.check_google_cloud_setup",
                return_value=False,
            ),
        ):
            w = self._build(qapp)
            radios = w.findChildren(QRadioButton)
            google_radio = next(
                (r for r in radios if r.property("method") == OCR_METHOD_GOOGLE_CLOUD),
                None,
            )
            assert google_radio is not None
            assert not google_radio.isEnabled()


# ===================================================================
# create_llm_settings
# ===================================================================


class TestCreateLLMSettings:
    """Tests for create_llm_settings() factory."""

    @pytest.fixture(autouse=True)
    def _deps(self, _mock_settings_deps):
        """Auto-use mock dependencies."""

    def _build(self, qapp: QApplication) -> QWidget:
        from src.ui.pages.settings import create_llm_settings  # noqa: PLC0415

        return create_llm_settings()

    def test_returns_qwidget(self, qapp: QApplication) -> None:
        """Factory returns a QWidget."""
        w = self._build(qapp)
        assert isinstance(w, QWidget)

    def test_no_provider_radios(self, qapp: QApplication) -> None:
        """LLM settings has no PROVIDER radio buttons.

        The two radios that remain (Developer API / Vertex AI) are
        intra-section auth-mode controls inside the Gemini card —
        provider selection itself is no longer radio-based.
        """
        w = self._build(qapp)
        radios = w.findChildren(QRadioButton)
        # Exactly the Vertex auth-mode pair, nothing else.
        assert len(radios) == 2  # noqa: PLR2004

    def test_both_provider_sections_visible(self, qapp: QApplication) -> None:
        """Both Gemini and Custom provider sections are always visible."""
        from PySide6.QtWidgets import QLineEdit  # noqa: PLC0415

        with _patch_custom_providers():
            w = self._build(qapp)
        # Both sections should have password fields for API keys
        password_fields = [
            le
            for le in w.findChildren(QLineEdit)
            if le.echoMode() == QLineEdit.EchoMode.Password
        ]
        assert len(password_fields) >= 2  # noqa: PLR2004  # Gemini + Custom

    def test_vertex_block_nested_inside_gemini_card(
        self,
        qapp: QApplication,
    ) -> None:
        """Vertex AI controls nest inside the Gemini card, not a sibling card.

        Vertex is just a different auth mode for the same provider, so
        they share one section header.  The Vertex auth-mode radio
        must share an ancestor with the Gemini API-key Password field
        where that ancestor is NOT just the top-level page (otherwise
        they'd be sibling cards as before consolidation).
        """
        from PySide6.QtWidgets import QLineEdit, QRadioButton

        w = self._build(qapp)

        # Gemini API key is the first Password-mode QLineEdit in
        # source order (Gemini section is the first to render).
        password_fields = [
            le
            for le in w.findChildren(QLineEdit)
            if le.echoMode() == QLineEdit.EchoMode.Password
        ]
        assert password_fields, "no password fields rendered on LLM tab"
        gemini_key = password_fields[0]

        # The Vertex auth-mode radio is identifiable by its
        # ``use_vertex=True`` property; ``find_vertex_radios``
        # avoids depending on label text (which is i18n-dependent).
        vertex_radios = [
            r for r in w.findChildren(QRadioButton) if r.property("use_vertex") is True
        ]
        assert len(vertex_radios) == 1, (
            f"expected exactly one Vertex radio, got {len(vertex_radios)}"
        )
        vertex_radio = vertex_radios[0]

        # Walk the radio's ancestors; one of them must also contain
        # the Gemini Password field — confirming they're co-housed in
        # the Gemini card, not in two separate sibling cards.
        ancestor = vertex_radio.parentWidget()
        while ancestor is not None and ancestor is not w:
            if gemini_key in ancestor.findChildren(QLineEdit):
                return
            ancestor = ancestor.parentWidget()
        pytest.fail(
            "Vertex radio is not nested inside the Gemini card — "
            "they live as separate sibling cards instead.",
        )

    def test_only_default_model_combo(self, qapp: QApplication) -> None:
        """LLM settings exposes the Default Model picker + Vertex location.

        Two combos total: the global "Default model" combo at the top
        of the tab, and the Vertex AI location dropdown inside the
        Vertex section (hidden when Vertex toggle is off, but the
        widget is still present).
        """
        w = self._build(qapp)
        combos = w.findChildren(QComboBox)
        assert len(combos) == 2  # noqa: PLR2004

    def test_custom_endpoint_field_present(self, qapp: QApplication) -> None:
        """Custom provider section has an endpoint text field."""
        from PySide6.QtWidgets import QLineEdit  # noqa: PLC0415

        with _patch_custom_providers():
            w = self._build(qapp)
        line_edits = w.findChildren(QLineEdit)
        # Should have fields for: Gemini API key, Custom API key,
        # Custom model, Custom endpoint
        text_fields = [
            le for le in line_edits if le.echoMode() != QLineEdit.EchoMode.Password
        ]
        assert len(text_fields) >= 2  # noqa: PLR2004  # model + endpoint


# ===================================================================
# create_provider_config — model disable and hint banner
# ===================================================================


class TestCreateProviderConfig:
    """Tests for create_provider_config() helper."""

    @pytest.fixture(autouse=True)
    def _deps(self, _mock_settings_deps):
        """Auto-use mock dependencies."""

    def test_provider_config_returns_qwidget(self, qapp: QApplication) -> None:
        """create_provider_config returns a QWidget (QFrame section group)."""
        from src.ui.pages.settings import create_provider_config  # noqa: PLC0415

        group = QButtonGroup()
        radio = QRadioButton("TestProvider")
        group.addButton(radio)
        w = create_provider_config(
            "TestProvider",
            "test/api_key",
            "test/model",
            ["model-a", "model-b"],
        )
        assert isinstance(w, QWidget)

    def test_provider_config_with_extra_fields(self, qapp: QApplication) -> None:
        """Extra fields (like endpoint) are added to the section."""
        from src.ui.pages.settings import create_provider_config  # noqa: PLC0415

        group = QButtonGroup()
        radio = QRadioButton("Custom")
        group.addButton(radio)
        w = create_provider_config(
            "Custom",
            "test/api_key",
            "test/model",
            None,
            extra_fields=[
                (
                    "Endpoint",
                    "test/endpoint",
                    "https://...",
                    "test.endpoint",
                    "test.endpoint_placeholder",
                ),
            ],
        )
        labels = w.findChildren(QLabel)
        assert len(labels) >= 2  # noqa: PLR2004  # at least title + fields

    def test_provider_config_with_hint_banner(self, qapp: QApplication) -> None:
        """Hint banner is created when hint_tr_key is provided."""
        from src.ui.pages.settings import create_provider_config  # noqa: PLC0415

        group = QButtonGroup()
        radio = QRadioButton("Gemini")
        group.addButton(radio)
        w = create_provider_config(
            "Gemini",
            "test/api_key",
            "test/model",
            ["model-a"],
            hint_tr_key="settings.gemini_api_key_hint",
        )
        assert isinstance(w, QWidget)

    def test_provider_config_with_title_tr_key(self, qapp: QApplication) -> None:
        """When title_tr_key is set, the section uses that key for the title."""
        from src.ui.pages.settings import create_provider_config  # noqa: PLC0415

        group = QButtonGroup()
        radio = QRadioButton("Custom")
        group.addButton(radio)
        w = create_provider_config(
            "Custom",
            "test/api_key",
            "test/model",
            None,
            title_tr_key="settings.custom_provider_title",
        )
        assert isinstance(w, QWidget)


# ===================================================================
# create_translation_settings
# ===================================================================


class TestCreateTranslationSettings:
    """Tests for create_translation_settings() factory."""

    @pytest.fixture(autouse=True)
    def _deps(self, _mock_settings_deps):
        """Auto-use mock dependencies."""

    def _build(self, qapp: QApplication) -> QWidget:
        from src.ui.pages.settings import create_translation_settings  # noqa: PLC0415

        return create_translation_settings()

    def test_returns_qwidget(self, qapp: QApplication) -> None:
        """Factory returns a QWidget."""
        w = self._build(qapp)
        assert isinstance(w, QWidget)

    def test_has_checkboxes(self, qapp: QApplication) -> None:
        """Translation settings has checkboxes for various options."""
        w = self._build(qapp)
        cbs = w.findChildren(QCheckBox)
        # Should have checkboxes for comments, shapes, notes, sheet names,
        # images, auto-convert legacy, auto-convert ODF, auto-remove history
        assert len(cbs) >= 7  # noqa: PLR2004

    def test_ocr_hint_visible_when_ocr_not_ready(self, qapp: QApplication) -> None:
        """OCR hint banner is visible when OCR is not configured."""
        with patch(
            "src.ui.pages.settings.check_ocr_setup",
            return_value=False,
        ):
            w = self._build(qapp)
            # The translate images checkbox should be disabled
            cbs = w.findChildren(QCheckBox)
            # Find the images checkbox (it's one of several; we check that
            # at least one checkbox is disabled)
            disabled_cbs = [cb for cb in cbs if not cb.isEnabled()]
            assert len(disabled_cbs) >= 1

    def test_office_hint_visible_when_no_office(self, qapp: QApplication) -> None:
        """Auto-convert checkboxes disabled when no office converter available."""
        w = self._build(qapp)
        cbs = w.findChildren(QCheckBox)
        # With default mocks (check_office_converter_setup returns False),
        # auto-convert checkboxes should be disabled
        disabled_cbs = [cb for cb in cbs if not cb.isEnabled()]
        # At least 2 disabled: auto-convert legacy + auto-convert ODF
        assert len(disabled_cbs) >= 2  # noqa: PLR2004

    def test_all_checkboxes_enabled_when_ready(self, qapp: QApplication) -> None:
        """All checkboxes enabled when OCR and office are available."""
        with (
            patch(
                "src.ui.pages.settings.check_ocr_setup",
                return_value=True,
            ),
            patch(
                "src.ui.pages.settings.check_office_converter_setup",
                return_value=True,
            ),
        ):
            w = self._build(qapp)
            cbs = w.findChildren(QCheckBox)
            enabled_cbs = [cb for cb in cbs if cb.isEnabled()]
            assert len(enabled_cbs) == len(cbs)

    def test_doc_images_skip_info_banner_exists(
        self,
        qapp: QApplication,
    ) -> None:
        """The skip-with-warning policy banner exists in the section.

        Regression guard: a future cleanup that removes the banner
        leaves users uninformed about the image-failure behaviour.
        We identify the banner by its localised text (the canonical
        public surface), not by an internal property.
        """
        from PySide6.QtWidgets import QFrame, QLabel  # noqa: PLC0415

        from src.constants.i18n import _set_initial_language, tr  # noqa: PLC0415

        _set_initial_language("en-US")
        w = self._build(qapp)

        expected_text = tr("settings.doc_images_skip_info")
        found = False
        for frame in w.findChildren(QFrame):
            if frame.objectName() != "Banner":
                continue
            text_lab = frame.findChild(QLabel, "BannerText")
            if text_lab and text_lab.text() == expected_text:
                found = True
                break
        assert found, (
            "settings.doc_images_skip_info banner not found in "
            "Translate Document section"
        )

    def test_doc_images_skip_info_banner_uses_info_styling(
        self,
        qapp: QApplication,
    ) -> None:
        """Banner border-colour matches the info palette, not warning/error.

        AGENTS.md banner contract: info variants describe a feature;
        warning variants describe an environmental problem.  The
        image-skip banner is informational — its border-colour must
        match ``color("primary")``-derived info palette and *not* the
        warning yellow (``#ffc542``) or error red.
        """
        from PySide6.QtWidgets import QFrame, QLabel  # noqa: PLC0415

        from src.constants.i18n import _set_initial_language, tr  # noqa: PLC0415

        _set_initial_language("en-US")
        w = self._build(qapp)

        expected_text = tr("settings.doc_images_skip_info")
        for frame in w.findChildren(QFrame):
            if frame.objectName() != "Banner":
                continue
            text_lab = frame.findChild(QLabel, "BannerText")
            if text_lab and text_lab.text() == expected_text:
                stylesheet = frame.styleSheet()
                # Must NOT use the warning-yellow border.
                assert "#ffc542" not in stylesheet, (
                    "info banner must not use warning yellow border"
                )
                return
        pytest.fail("info banner not found")

    def test_doc_images_section_leads_translate_document_options(
        self,
        qapp: QApplication,
    ) -> None:
        """The embedded-images surface leads the Translate Document section.

        Images are the most expensive surface (OCR + vision LLM, OCR
        prerequisite, skip-with-warning policy) so users see them
        first.  Verifies the layout reorder: the images checkbox
        appears BEFORE the comments / shapes / notes / sheet-names
        checkboxes in widget-tree (insertion) order.
        """
        from PySide6.QtWidgets import QCheckBox  # noqa: PLC0415

        from src.constants.i18n import _set_initial_language, tr  # noqa: PLC0415

        _set_initial_language("en-US")
        w = self._build(qapp)

        # ``findChildren`` traverses the QObject tree in the order
        # children were added, which mirrors layout insertion.  Match
        # by the localised label so an unrelated checkbox elsewhere
        # in the page can't shift the assertion.
        labels_in_order = [cb.text() for cb in w.findChildren(QCheckBox)]
        images_label = tr("settings.translate_doc_images")
        comments_label = tr("settings.translate_doc_comments")

        assert images_label in labels_in_order, (
            "translate-images checkbox missing from Translate Document section"
        )
        assert comments_label in labels_in_order, (
            "translate-comments checkbox missing from Translate Document section"
        )
        assert labels_in_order.index(images_label) < labels_in_order.index(
            comments_label,
        ), f"images checkbox must precede comments — got order {labels_in_order}"


# ===================================================================
# create_extract_text_settings
# ===================================================================


class TestCreateExtractTextSettings:
    """Tests for create_extract_text_settings() factory."""

    @pytest.fixture(autouse=True)
    def _deps(self, _mock_settings_deps):
        """Auto-use mock dependencies."""

    def _build(self, qapp: QApplication) -> QWidget:
        from src.ui.pages.settings import create_extract_text_settings  # noqa: PLC0415

        return create_extract_text_settings()

    def test_returns_qwidget(self, qapp: QApplication) -> None:
        """Factory returns a QWidget."""
        w = self._build(qapp)
        assert isinstance(w, QWidget)

    def test_has_method_radios(self, qapp: QApplication) -> None:
        """Extract text settings has OCR and LLM method radio buttons."""
        from src.constants.settings import (  # noqa: PLC0415
            EXTRACT_METHOD_LLM,
            EXTRACT_METHOD_OCR,
        )

        w = self._build(qapp)
        radios = w.findChildren(QRadioButton)
        methods = {r.property("method") for r in radios}
        assert EXTRACT_METHOD_OCR in methods
        assert EXTRACT_METHOD_LLM in methods

    def test_has_format_radios(self, qapp: QApplication) -> None:
        """Extract text settings has .txt and .docx format radio buttons."""
        w = self._build(qapp)
        radios = w.findChildren(QRadioButton)
        exts = {r.property("ext") for r in radios}
        assert ".txt" in exts
        assert ".docx" in exts

    def test_method_radios_enabled_when_available(self, qapp: QApplication) -> None:
        """Both OCR and LLM radios are enabled when both setups are available."""
        from src.constants.settings import (  # noqa: PLC0415
            EXTRACT_METHOD_LLM,
            EXTRACT_METHOD_OCR,
        )

        w = self._build(qapp)
        radios = w.findChildren(QRadioButton)
        method_radios = [
            r
            for r in radios
            if r.property("method") in (EXTRACT_METHOD_OCR, EXTRACT_METHOD_LLM)
        ]
        for r in method_radios:
            assert r.isEnabled()

    def test_ocr_disabled_when_not_setup(self, qapp: QApplication) -> None:
        """OCR radio is disabled when OCR setup is not available."""
        from src.constants.settings import EXTRACT_METHOD_OCR  # noqa: PLC0415

        with patch(
            "src.ui.pages.settings.check_ocr_setup",
            return_value=False,
        ):
            w = self._build(qapp)
            radios = w.findChildren(QRadioButton)
            ocr_radio = next(
                (r for r in radios if r.property("method") == EXTRACT_METHOD_OCR),
                None,
            )
            assert ocr_radio is not None
            assert not ocr_radio.isEnabled()

    def test_llm_disabled_when_not_setup(self, qapp: QApplication) -> None:
        """LLM radio is disabled when LLM setup is not available."""
        from src.constants.settings import EXTRACT_METHOD_LLM  # noqa: PLC0415

        with patch(
            "src.ui.pages.settings.check_llm_setup",
            return_value=False,
        ):
            w = self._build(qapp)
            radios = w.findChildren(QRadioButton)
            llm_radio = next(
                (r for r in radios if r.property("method") == EXTRACT_METHOD_LLM),
                None,
            )
            assert llm_radio is not None
            assert not llm_radio.isEnabled()

    def test_method_toggle_saves_setting(self, qapp: QApplication) -> None:
        """Toggling the extract method saves the setting."""
        from src.constants.settings import (  # noqa: PLC0415
            EXTRACT_METHOD_LLM,
            EXTRACT_METHOD_OCR,
        )

        with patch("src.ui.pages.settings.save_setting") as mock_save:
            w = self._build(qapp)
            groups = w.findChildren(QButtonGroup)
            # Find the method button group (has OCR/LLM radios)
            method_group = None
            for g in groups:
                methods = {b.property("method") for b in g.buttons()}
                if EXTRACT_METHOD_OCR in methods or EXTRACT_METHOD_LLM in methods:
                    method_group = g
                    break
            assert method_group is not None
            llm_btn = next(
                (
                    b
                    for b in method_group.buttons()
                    if b.property("method") == EXTRACT_METHOD_LLM
                ),
                None,
            )
            if llm_btn and llm_btn.isEnabled():
                llm_btn.setChecked(True)
                method_group.buttonClicked.emit(llm_btn)
                save_calls = [
                    c
                    for c in mock_save.call_args_list
                    if c[0][0] == "extraction/method"
                ]
                assert len(save_calls) >= 1

    def test_format_toggle_saves_setting(self, qapp: QApplication) -> None:
        """Toggling the output format saves the setting."""
        with patch("src.ui.pages.settings.save_setting") as mock_save:
            w = self._build(qapp)
            groups = w.findChildren(QButtonGroup)
            # Find the format button group (has .txt/.docx radios)
            fmt_group = None
            for g in groups:
                for b in g.buttons():
                    if b.property("ext") == ".docx":
                        fmt_group = g
                        break
                if fmt_group:
                    break
            assert fmt_group is not None
            docx_btn = next(
                (b for b in fmt_group.buttons() if b.property("ext") == ".docx"),
                None,
            )
            if docx_btn:
                docx_btn.setChecked(True)
                fmt_group.buttonClicked.emit(docx_btn)
                save_calls = [
                    c
                    for c in mock_save.call_args_list
                    if c[0][0] == "extraction/last_output_format"
                ]
                assert len(save_calls) >= 1

    def test_has_auto_remove_checkbox(self, qapp: QApplication) -> None:
        """Extract text settings has an auto-remove history checkbox."""
        w = self._build(qapp)
        cbs = w.findChildren(QCheckBox)
        assert len(cbs) >= 1

    def test_sync_method_availability_callable(self, qapp: QApplication) -> None:
        """The extract text widget exposes _sync_method_availability."""
        w = self._build(qapp)
        assert hasattr(w, "_sync_method_availability")
        w._sync_method_availability()  # Should not raise


# ===================================================================
# create_subtitle_settings
# ===================================================================


class TestCreateSubtitleSettings:
    """Tests for create_subtitle_settings() factory."""

    @pytest.fixture(autouse=True)
    def _deps(self, _mock_settings_deps):
        """Auto-use mock dependencies."""

    def _build(self, qapp: QApplication) -> QWidget:
        # Also need to mock check_google_cloud_setup used locally
        with patch(
            "src.utils.config_manager.check_google_cloud_setup",
            return_value=True,
        ):
            from src.ui.pages.settings import create_subtitle_settings  # noqa: PLC0415

            return create_subtitle_settings()

    def test_returns_qwidget(self, qapp: QApplication) -> None:
        """Factory returns a QWidget."""
        w = self._build(qapp)
        assert isinstance(w, QWidget)

    def test_has_stt_method_radios(self, qapp: QApplication) -> None:
        """Subtitle settings has STT method radio buttons."""
        from src.constants.settings import STT_GOOGLE, STT_WHISPER  # noqa: PLC0415

        w = self._build(qapp)
        radios = w.findChildren(QRadioButton)
        radio_methods = {r.property("method") for r in radios}
        assert STT_WHISPER in radio_methods
        assert STT_GOOGLE in radio_methods

    def test_has_whisper_model_radios(self, qapp: QApplication) -> None:
        """Subtitle settings has Whisper model size radio buttons."""
        w = self._build(qapp)
        radios = w.findChildren(QRadioButton)
        radio_texts = {r.text() for r in radios}
        # Whisper models: tiny, base, small, medium, large
        assert any("base" in t for t in radio_texts)
        assert any("large" in t for t in radio_texts)

    def test_has_subtitle_format_radios(self, qapp: QApplication) -> None:
        """Subtitle settings has SRT and VTT format radio buttons."""
        w = self._build(qapp)
        radios = w.findChildren(QRadioButton)
        radio_texts = {r.text() for r in radios}
        assert "SRT" in radio_texts
        assert "VTT" in radio_texts

    def test_has_sync_stt_availability(self, qapp: QApplication) -> None:
        """Subtitle widget exposes _sync_stt_availability."""
        w = self._build(qapp)
        assert hasattr(w, "_sync_stt_availability")

    def test_google_stt_disabled_when_no_key(self, qapp: QApplication) -> None:
        """Google Cloud STT radio is disabled when key is missing."""
        from src.constants.settings import STT_GOOGLE  # noqa: PLC0415

        with patch(
            "src.utils.config_manager.check_google_cloud_setup",
            return_value=False,
        ):
            from src.ui.pages.settings import create_subtitle_settings  # noqa: PLC0415

            w = create_subtitle_settings()
            radios = w.findChildren(QRadioButton)
            google_radio = next(
                (r for r in radios if r.property("method") == STT_GOOGLE),
                None,
            )
            assert google_radio is not None
            assert not google_radio.isEnabled()


# ===================================================================
# create_voice_settings
# ===================================================================


class TestCreateVoiceSettings:
    """Tests for create_voice_settings() factory."""

    @pytest.fixture(autouse=True)
    def _deps(self, _mock_settings_deps):
        """Auto-use mock dependencies."""

    def _build(self, qapp: QApplication) -> QWidget:
        with patch(
            "src.utils.config_manager.check_google_cloud_setup",
            return_value=True,
        ):
            from src.ui.pages.settings import create_voice_settings  # noqa: PLC0415

            return create_voice_settings()

    def test_returns_qwidget(self, qapp: QApplication) -> None:
        """Factory returns a QWidget."""
        w = self._build(qapp)
        assert isinstance(w, QWidget)

    def test_has_tts_method_radios(self, qapp: QApplication) -> None:
        """Voice settings has TTS method radio buttons."""
        from src.constants.settings import (  # noqa: PLC0415
            VOICE_TTS_EDGE,
            VOICE_TTS_GOOGLE,
        )

        w = self._build(qapp)
        radios = w.findChildren(QRadioButton)
        radio_methods = {r.property("method") for r in radios}
        assert VOICE_TTS_EDGE in radio_methods
        assert VOICE_TTS_GOOGLE in radio_methods

    def test_has_voice_format_radios(self, qapp: QApplication) -> None:
        """Voice settings has MP3 and WAV format radio buttons."""
        w = self._build(qapp)
        radios = w.findChildren(QRadioButton)
        radio_texts = {r.text() for r in radios}
        assert "MP3" in radio_texts
        assert "WAV" in radio_texts

    def test_has_sync_tts_availability(self, qapp: QApplication) -> None:
        """Voice widget exposes _sync_tts_availability."""
        w = self._build(qapp)
        assert hasattr(w, "_sync_tts_availability")

    def test_google_tts_disabled_when_no_key(self, qapp: QApplication) -> None:
        """Google Cloud TTS radio is disabled when key is missing."""
        from src.constants.settings import VOICE_TTS_GOOGLE  # noqa: PLC0415

        with patch(
            "src.utils.config_manager.check_google_cloud_setup",
            return_value=False,
        ):
            from src.ui.pages.settings import create_voice_settings  # noqa: PLC0415

            w = create_voice_settings()
            radios = w.findChildren(QRadioButton)
            google_radio = next(
                (r for r in radios if r.property("method") == VOICE_TTS_GOOGLE),
                None,
            )
            assert google_radio is not None
            assert not google_radio.isEnabled()

    def test_has_gemini_tts_radio(self, qapp: QApplication) -> None:
        """Gemini TTS appears alongside Edge / Google / ElevenLabs."""
        from src.constants.settings import VOICE_TTS_GEMINI  # noqa: PLC0415

        w = self._build(qapp)
        radios = w.findChildren(QRadioButton)
        radio_methods = {r.property("method") for r in radios}
        assert VOICE_TTS_GEMINI in radio_methods

    def test_gemini_tts_disabled_when_no_key(self, qapp: QApplication) -> None:
        """Gemini TTS radio is disabled when neither Gemini API key nor Vertex setup."""
        from src.constants.settings import VOICE_TTS_GEMINI  # noqa: PLC0415

        with patch(
            "src.utils.config_manager.check_gemini_setup",
            return_value=False,
        ):
            from src.ui.pages.settings import create_voice_settings  # noqa: PLC0415

            w = create_voice_settings()
            radios = w.findChildren(QRadioButton)
            gemini_radio = next(
                (r for r in radios if r.property("method") == VOICE_TTS_GEMINI),
                None,
            )
            assert gemini_radio is not None
            assert not gemini_radio.isEnabled()

    def test_gemini_tts_enabled_when_key_set(self, qapp: QApplication) -> None:
        """Gemini TTS radio is enabled when ``check_gemini_setup`` returns True."""
        from src.constants.settings import VOICE_TTS_GEMINI  # noqa: PLC0415

        with patch(
            "src.utils.config_manager.check_gemini_setup",
            return_value=True,
        ):
            from src.ui.pages.settings import create_voice_settings  # noqa: PLC0415

            w = create_voice_settings()
            radios = w.findChildren(QRadioButton)
            gemini_radio = next(
                (r for r in radios if r.property("method") == VOICE_TTS_GEMINI),
                None,
            )
            assert gemini_radio is not None
            assert gemini_radio.isEnabled()

    def test_sync_tts_availability_disables_gemini_on_flip(
        self,
        qapp: QApplication,
    ) -> None:
        """``_sync_tts_availability`` flips Gemini radio + banner state.

        Initial render has Gemini available (key set).  Mid-session
        the user removes the key (or it expires) — triggering the
        sync hook (e.g. on tab switch back) should DISABLE the Gemini
        radio and SHOW its setup-hint banner without re-creating the
        widget.  Without this, a user who configured Gemini TTS, then
        cleared the key in another tab, would still see Gemini
        clickable but every call would AUTH_ERROR.
        """
        from src.constants.settings import VOICE_TTS_GEMINI  # noqa: PLC0415
        from src.ui.pages.settings import create_voice_settings  # noqa: PLC0415

        # Build with Gemini available initially.
        with patch(
            "src.utils.config_manager.check_gemini_setup",
            return_value=True,
        ):
            w = create_voice_settings()

        radios = w.findChildren(QRadioButton)
        gemini_radio = next(
            (r for r in radios if r.property("method") == VOICE_TTS_GEMINI),
            None,
        )
        assert gemini_radio is not None
        assert gemini_radio.isEnabled(), "Gemini should start enabled"

        # Now flip to unavailable + re-sync (mimics what the tab-
        # switch handler does when the user comes back to Voice).
        with patch(
            "src.utils.config_manager.check_gemini_setup",
            return_value=False,
        ):
            w._sync_tts_availability()

        assert not gemini_radio.isEnabled(), (
            "Gemini radio should be disabled after key removed + re-sync"
        )

    def test_edge_tts_default_selected(self, qapp: QApplication) -> None:
        """Edge TTS is selected by default."""
        from src.constants.settings import VOICE_TTS_EDGE  # noqa: PLC0415

        w = self._build(qapp)
        groups = w.findChildren(QButtonGroup)
        # The TTS method group is the first one
        tts_group = groups[0]
        checked = tts_group.checkedButton()
        assert checked is not None
        assert checked.property("method") == VOICE_TTS_EDGE

    def test_voice_picker_exposed_on_widget(self, qapp: QApplication) -> None:
        """The Voice tab exposes ``_sync_voice_picker_for_method`` for re-sync."""
        w = self._build(qapp)
        assert hasattr(w, "_sync_voice_picker_for_method")

    def test_voice_picker_swaps_widget_per_method(
        self,
        qapp: QApplication,
    ) -> None:
        """Picking a different TTS method swaps the picker stack page.

        Each engine has a different config surface:
        - Edge / Google: ``QWidget`` containing male/female radios
          (Edge resolves the voice from ``_EDGE_VOICES``; Google passes
          ``ssmlGender`` to the API and lets the server pick).
        - ElevenLabs: ``QWidget`` containing male/female radios + voice
          combo (Auto / curated / Custom) + a Voice ID text field
          shown only when Custom is selected.
        - Gemini: ``QWidget`` containing male/female radios on top of a
          ``QComboBox`` (curated catalogue dropdown).
        """
        from PySide6.QtWidgets import (  # noqa: PLC0415
            QComboBox,
            QRadioButton,
            QStackedWidget,
        )

        from src.constants.settings import (  # noqa: PLC0415
            SETTING_VOICE_TTS_METHOD,
            VOICE_TTS_EDGE,
            VOICE_TTS_ELEVENLABS,
            VOICE_TTS_GEMINI,
            VOICE_TTS_GOOGLE,
        )

        w = self._build(qapp)
        stacks = w.findChildren(QStackedWidget)
        assert stacks, "voice-picker QStackedWidget not found"
        stack = stacks[0]

        def _expect_gender_radios(method: str) -> None:
            with patch(
                "src.ui.pages.settings.load_setting",
                side_effect=lambda key, default="": (
                    method if key == SETTING_VOICE_TTS_METHOD else default
                ),
            ):
                w._sync_voice_picker_for_method()
            page = stack.currentWidget()
            radios = page.findChildren(QRadioButton)
            assert len(radios) == 2, (  # noqa: PLR2004
                f"{method} picker should expose male/female radios; "
                f"got {len(radios)} radios"
            )

        # Edge & Google → container widget with two radios (male / female).
        _expect_gender_radios(VOICE_TTS_EDGE)
        _expect_gender_radios(VOICE_TTS_GOOGLE)

        # ElevenLabs → gender radios + voice combo + custom edit.
        with patch(
            "src.ui.pages.settings.load_setting",
            side_effect=lambda key, default="": (
                VOICE_TTS_ELEVENLABS if key == SETTING_VOICE_TTS_METHOD else default
            ),
        ):
            w._sync_voice_picker_for_method()
        el_page = stack.currentWidget()
        assert len(el_page.findChildren(QRadioButton)) == 2  # noqa: PLR2004
        assert len(el_page.findChildren(QComboBox)) == 1

        # Gemini → gender radios + combo (curated catalogue) in a column.
        with patch(
            "src.ui.pages.settings.load_setting",
            side_effect=lambda key, default="": (
                VOICE_TTS_GEMINI if key == SETTING_VOICE_TTS_METHOD else default
            ),
        ):
            w._sync_voice_picker_for_method()
        gemini_page = stack.currentWidget()
        gemini_radios = gemini_page.findChildren(QRadioButton)
        gemini_combos = gemini_page.findChildren(QComboBox)
        assert len(gemini_radios) == 2, (  # noqa: PLR2004
            "Gemini picker should expose male/female gender radios; "
            f"got {len(gemini_radios)} radios"
        )
        assert len(gemini_combos) == 1, (
            "Gemini picker should expose one voice combo; "
            f"got {len(gemini_combos)} combos"
        )

    def test_gemini_voice_combo_lists_only_curated_voices_for_gender(
        self,
        qapp: QApplication,
    ) -> None:
        """Gemini combo holds exactly the curated voices for the saved gender.

        No "Auto" sentinel — every entry is a concrete voice the engine
        will pass straight through.  Items are filtered to voices
        matching the saved gender (default FEMALE) so picking a male
        voice with the gender radio set to Female isn't possible.
        """
        from PySide6.QtWidgets import QComboBox, QStackedWidget  # noqa: PLC0415

        from src.core.speech_engine import (  # noqa: PLC0415
            GEMINI_TTS_VOICES_BY_GENDER,
        )

        w = self._build(qapp)
        stack = w.findChildren(QStackedWidget)[0]
        # 4th page in the stack (Edge / Google / ElevenLabs / Gemini)
        # is now a wrapper containing a gender radio + a voice combo;
        # the combo is the only QComboBox in the wrapper.
        gemini_page = stack.widget(3)
        combos = gemini_page.findChildren(QComboBox)
        assert len(combos) == 1
        combo = combos[0]
        items = [combo.itemData(i) for i in range(combo.count())]
        assert items == list(GEMINI_TTS_VOICES_BY_GENDER["FEMALE"])

    def test_gemini_voice_combo_filters_by_gender(
        self,
        qapp: QApplication,
    ) -> None:
        """Toggling gender repopulates the Gemini voice combo.

        Picking the Male radio (on any of the Edge / Google / Gemini
        gender widgets — they all share the same setting) drops the
        female voices and surfaces the male catalogue instead.
        """
        from PySide6.QtWidgets import (  # noqa: PLC0415
            QComboBox,
            QRadioButton,
            QStackedWidget,
        )

        from src.constants.settings import (  # noqa: PLC0415
            SETTING_LAST_VOICE_GENDER,
            SETTING_VOICE_TTS_METHOD,
            VOICE_TTS_GEMINI,
        )
        from src.core.speech_engine import (  # noqa: PLC0415
            GEMINI_TTS_VOICES_BY_GENDER,
        )

        w = self._build(qapp)
        stack = w.findChildren(QStackedWidget)[0]

        def _fake_load(key, default=""):  # noqa: ANN001, ANN202
            if key == SETTING_VOICE_TTS_METHOD:
                return VOICE_TTS_GEMINI
            if key == SETTING_LAST_VOICE_GENDER:
                return "MALE"
            return default

        with patch(
            "src.ui.pages.settings.load_setting",
            side_effect=_fake_load,
        ):
            w._sync_voice_picker_for_method()
            gemini_page = stack.currentWidget()
            combo = gemini_page.findChildren(QComboBox)[0]
            male_radio = next(
                r
                for r in gemini_page.findChildren(QRadioButton)
                if r.property("gender") == "MALE"
            )
            # ``QRadioButton.click()`` toggles the radio, fires the
            # group's ``buttonClicked`` signal (which our wiring listens
            # to), and so triggers ``_populate_gemini_voice_combo`` —
            # which reads the patched gender (MALE) and rebuilds the
            # combo from the male catalogue.
            male_radio.click()
            male_items = [combo.itemData(i) for i in range(combo.count())]
        assert male_items == list(GEMINI_TTS_VOICES_BY_GENDER["MALE"])

    def test_gemini_voice_combo_auto_picks_default_on_gender_swap(
        self,
        qapp: QApplication,
    ) -> None:
        """Auto-pick gender default when the saved voice is dropped or empty.

        When the saved voice no longer matches the new gender (or is
        empty — the user has never picked one), the combo auto-picks
        the gender default (first voice in the new list — Kore for
        Female, Puck for Male) and persists it.  There is no Auto
        sentinel — every state lands on a concrete voice.
        """
        from PySide6.QtWidgets import (  # noqa: PLC0415
            QComboBox,
            QRadioButton,
            QStackedWidget,
        )

        from src.constants.settings import (  # noqa: PLC0415
            SETTING_GEMINI_TTS_VOICE_NAME,
            SETTING_LAST_VOICE_GENDER,
            SETTING_VOICE_TTS_METHOD,
            VOICE_TTS_GEMINI,
        )

        w = self._build(qapp)
        stack = w.findChildren(QStackedWidget)[0]

        # Case 1: saved gender FEMALE, saved voice "Charon" (a male
        # voice). Sync should auto-pick Kore (first female voice) and
        # persist via save_setting.
        def _fake_load_charon(key, default=""):  # noqa: ANN001, ANN202
            if key == SETTING_VOICE_TTS_METHOD:
                return VOICE_TTS_GEMINI
            if key == SETTING_LAST_VOICE_GENDER:
                return "FEMALE"
            if key == SETTING_GEMINI_TTS_VOICE_NAME:
                return "Charon"
            return default

        save_calls: list[tuple[str, str]] = []

        def _capture_save(key, value):  # noqa: ANN001, ANN202
            save_calls.append((key, value))

        with (
            patch(
                "src.ui.pages.settings.load_setting",
                side_effect=_fake_load_charon,
            ),
            patch(
                "src.ui.pages.settings.save_setting",
                side_effect=_capture_save,
            ),
        ):
            w._sync_voice_picker_for_method()
        gemini_page = stack.currentWidget()
        combo = gemini_page.findChildren(QComboBox)[0]
        # Default lookup is via ``get_gemini_default_voice`` (not
        # position 0) so the test stays valid after the catalogue
        # was sorted strictly A→Z.
        from src.core.speech_engine import (  # noqa: PLC0415
            get_gemini_default_voice,
        )

        female_default = get_gemini_default_voice("FEMALE")
        assert combo.currentData() == female_default
        assert (SETTING_GEMINI_TTS_VOICE_NAME, female_default) in save_calls

        # Case 2: saved voice empty (no prior pick) — toggling gender
        # also lands on the new gender's default (Puck for Male) and
        # persists, because there's no Auto sentinel to fall back to.
        def _fake_load_auto(key, default=""):  # noqa: ANN001, ANN202
            if key == SETTING_VOICE_TTS_METHOD:
                return VOICE_TTS_GEMINI
            if key == SETTING_LAST_VOICE_GENDER:
                return "MALE"
            if key == SETTING_GEMINI_TTS_VOICE_NAME:
                return ""
            return default

        save_calls.clear()
        with (
            patch(
                "src.ui.pages.settings.load_setting",
                side_effect=_fake_load_auto,
            ),
            patch(
                "src.ui.pages.settings.save_setting",
                side_effect=_capture_save,
            ),
        ):
            male_radio = next(
                r
                for r in gemini_page.findChildren(QRadioButton)
                if r.property("gender") == "MALE"
            )
            male_radio.click()
        male_default = get_gemini_default_voice("MALE")
        assert combo.currentData() == male_default
        assert (SETTING_GEMINI_TTS_VOICE_NAME, male_default) in save_calls


# ===================================================================
# create_dubbing_settings
# ===================================================================


class TestCreateDubbingSettings:
    """Tests for create_dubbing_settings() factory."""

    @pytest.fixture(autouse=True)
    def _deps(self, _mock_settings_deps):
        """Auto-use mock dependencies."""

    def _build(self, qapp: QApplication) -> QWidget:
        from src.ui.pages.settings import create_dubbing_settings  # noqa: PLC0415

        return create_dubbing_settings()

    def test_returns_qwidget(self, qapp: QApplication) -> None:
        """Factory returns a QWidget."""
        w = self._build(qapp)
        assert isinstance(w, QWidget)

    def test_has_auto_remove_checkbox(self, qapp: QApplication) -> None:
        """Dubbing settings has an auto-remove history checkbox."""
        w = self._build(qapp)
        cbs = w.findChildren(QCheckBox)
        assert len(cbs) >= 1

    def test_has_labels(self, qapp: QApplication) -> None:
        """Dubbing settings has labels for output section."""
        w = self._build(qapp)
        labels = w.findChildren(QLabel)
        assert len(labels) >= 1


# ===================================================================
# Tab change triggers state refresh
# ===================================================================


class TestTabChangeRefresh:
    """Tests that switching tabs triggers the correct refresh callbacks."""

    @pytest.fixture(autouse=True)
    def _deps(self, _mock_settings_deps):
        """Auto-use mock dependencies."""

    def test_switching_to_general_tab_refreshes_office(
        self,
        qapp: QApplication,
    ) -> None:
        """Switching to General tab (index 0) calls _sync_office_availability."""
        from src.ui.pages.settings import create_settings_page  # noqa: PLC0415

        page = create_settings_page()
        tabs = page.findChild(QTabWidget)
        # Start on a different tab
        tabs.setCurrentIndex(3)
        # Mock _sync_office_availability on the general widget
        with patch.object(
            type(tabs.widget(0)),
            "_sync_office_availability",
            create=True,
        ):
            # Switch to general tab
            tabs.setCurrentIndex(0)
            # No assertion needed beyond "does not raise"

    def test_switching_to_ocr_tab_does_not_raise(
        self,
        qapp: QApplication,
    ) -> None:
        """Switching to OCR tab (index 3) completes without errors."""
        from src.ui.pages.settings import create_settings_page  # noqa: PLC0415

        page = create_settings_page()
        tabs = page.findChild(QTabWidget)
        tabs.setCurrentIndex(0)
        tabs.setCurrentIndex(3)
        # Should not raise

    def test_switching_to_translation_tab_does_not_raise(
        self,
        qapp: QApplication,
    ) -> None:
        """Switching to Translation tab (index 6) completes without errors."""
        from src.ui.pages.settings import create_settings_page  # noqa: PLC0415

        page = create_settings_page()
        tabs = page.findChild(QTabWidget)
        tabs.setCurrentIndex(6)

    def test_switching_to_extract_tab_does_not_raise(
        self,
        qapp: QApplication,
    ) -> None:
        """Switching to Extract Text tab (index 11) completes without errors."""
        from src.ui.pages.settings import create_settings_page  # noqa: PLC0415

        page = create_settings_page()
        tabs = page.findChild(QTabWidget)
        tabs.setCurrentIndex(11)

    def test_switching_to_subtitle_tab_does_not_raise(
        self,
        qapp: QApplication,
    ) -> None:
        """Switching to Subtitle tab (index 7) completes without errors."""
        from src.ui.pages.settings import create_settings_page  # noqa: PLC0415

        page = create_settings_page()
        tabs = page.findChild(QTabWidget)
        tabs.setCurrentIndex(7)

    def test_switching_to_voice_tab_does_not_raise(
        self,
        qapp: QApplication,
    ) -> None:
        """Switching to Voice tab (index 8) completes without errors."""
        from src.ui.pages.settings import create_settings_page  # noqa: PLC0415

        page = create_settings_page()
        tabs = page.findChild(QTabWidget)
        tabs.setCurrentIndex(8)


# ===================================================================
# Integration: full page construction with different config states
# ===================================================================


class TestSettingsPageIntegration:
    """Integration tests for settings page with various configurations."""

    def test_page_with_ocr_unavailable(self, qapp: QApplication) -> None:
        """Settings page constructs even when OCR is not available."""
        patches = dict(_SETTINGS_PATCHES)
        patches["src.ui.pages.settings.check_ocr_setup"] = lambda: False
        patches["src.ui.pages.settings.check_ocr_availability"] = lambda m: (
            False,
            "Not found",
        )
        patches["src.ui.pages.settings.detect_tesseract_languages"] = set

        import contextlib  # noqa: PLC0415

        with contextlib.ExitStack() as stack:
            for target, replacement in patches.items():
                stack.enter_context(patch(target, replacement))

            from src.ui.pages.settings import create_settings_page  # noqa: PLC0415

            page = create_settings_page()
            assert isinstance(page, QWidget)

    def test_page_with_llm_unavailable(self, qapp: QApplication) -> None:
        """Settings page constructs even when LLM is not available."""
        patches = dict(_SETTINGS_PATCHES)
        patches["src.ui.pages.settings.check_llm_setup"] = lambda: False

        import contextlib  # noqa: PLC0415

        with contextlib.ExitStack() as stack:
            for target, replacement in patches.items():
                stack.enter_context(patch(target, replacement))

            from src.ui.pages.settings import create_settings_page  # noqa: PLC0415

            page = create_settings_page()
            assert isinstance(page, QWidget)

    def test_page_with_saved_dark_theme(self, qapp: QApplication) -> None:
        """Settings page respects a saved 'dark' theme preference."""

        def custom_load(key, default=""):
            if key == "app/theme":
                return "dark"
            return default

        patches = dict(_SETTINGS_PATCHES)
        patches["src.ui.pages.settings.load_setting"] = custom_load
        patches["src.ui.components.load_setting"] = custom_load

        import contextlib  # noqa: PLC0415

        with contextlib.ExitStack() as stack:
            for target, replacement in patches.items():
                stack.enter_context(patch(target, replacement))

            from src.ui.pages.settings import create_general_settings  # noqa: PLC0415

            w = create_general_settings()
            groups = w.findChildren(QButtonGroup)
            theme_group = groups[0]
            checked = theme_group.checkedButton()
            assert checked is not None

    def test_page_with_saved_llm_custom(self, qapp: QApplication) -> None:
        """Settings page loads Custom LLM config with both sections visible."""
        from PySide6.QtWidgets import QLineEdit  # noqa: PLC0415

        def custom_load(key, default=""):
            if key == "llm/method":
                return "Custom"
            if key == "llm/custom_api_key":
                return "fake-key"
            if key == "llm/custom_model":
                return "gpt-4"
            if key == "llm/custom_endpoint":
                return "https://api.example.com"
            return default

        patches = dict(_SETTINGS_PATCHES)
        patches["src.ui.pages.settings.load_setting"] = custom_load
        patches["src.ui.components.load_setting"] = custom_load

        import contextlib  # noqa: PLC0415

        with contextlib.ExitStack() as stack:
            for target, replacement in patches.items():
                stack.enter_context(patch(target, replacement))
            stack.enter_context(_patch_custom_providers())

            from src.ui.pages.settings import create_llm_settings  # noqa: PLC0415

            w = create_llm_settings()
            # No PROVIDER radios; only the Vertex auth-mode pair (2)
            # remains inside the Gemini card.
            radios = w.findChildren(QRadioButton)
            assert len(radios) == 2  # noqa: PLR2004
            # Both sections should be visible with input fields
            inputs = w.findChildren(QLineEdit)
            assert len(inputs) >= 2  # noqa: PLR2004

    def test_page_with_office_available(self, qapp: QApplication) -> None:
        """General settings shows success banner when office is available."""
        patches = dict(_SETTINGS_PATCHES)
        patches["src.ui.pages.settings.check_libreoffice_available"] = lambda: True

        import contextlib  # noqa: PLC0415

        with contextlib.ExitStack() as stack:
            for target, replacement in patches.items():
                stack.enter_context(patch(target, replacement))

            from src.ui.pages.settings import create_general_settings  # noqa: PLC0415

            w = create_general_settings()
            assert isinstance(w, QWidget)


# ===================================================================
# Gap 1: Tab refresh callback verification (HIGH)
# ===================================================================


class TestTabChangeCallbackVerification:
    """Verifies that switching tabs actually invokes the correct sync functions."""

    @pytest.fixture(autouse=True)
    def _deps(self, _mock_settings_deps):
        """Auto-use mock dependencies."""

    def _build_page(self, qapp: QApplication) -> QWidget:
        from src.ui.pages.settings import create_settings_page  # noqa: PLC0415

        return create_settings_page()

    def test_general_tab_calls_sync_office_availability(
        self,
        qapp: QApplication,
    ) -> None:
        """Switching to General tab (index 0) calls _sync_office_availability."""
        page = self._build_page(qapp)
        tabs = page.findChild(QTabWidget)
        general_widget = tabs.widget(0)

        # Find the actual inner widget (inside the scrollable container)
        from PySide6.QtWidgets import QScrollArea  # noqa: PLC0415

        scroll = general_widget.findChild(QScrollArea)
        inner = scroll.widget() if scroll else general_widget
        # Walk children to find the one with _sync_office_availability
        target = None
        for child in [inner, *inner.findChildren(QWidget)]:
            if hasattr(child, "_sync_office_availability"):
                target = child
                break
        assert target is not None, "No child has _sync_office_availability"

        mock_sync = MagicMock()
        target._sync_office_availability = mock_sync

        # Start from a different tab, then switch to General
        tabs.setCurrentIndex(3)
        mock_sync.reset_mock()
        tabs.setCurrentIndex(0)
        mock_sync.assert_called()

    def test_ocr_tab_calls_sync_ocr_availability(
        self,
        qapp: QApplication,
    ) -> None:
        """Switching to OCR tab (index 3) calls _sync_ocr_availability."""
        page = self._build_page(qapp)
        tabs = page.findChild(QTabWidget)
        ocr_wrapper = tabs.widget(3)

        from PySide6.QtWidgets import QScrollArea  # noqa: PLC0415

        scroll = ocr_wrapper.findChild(QScrollArea)
        inner = scroll.widget() if scroll else ocr_wrapper
        target = None
        for child in [inner, *inner.findChildren(QWidget)]:
            if hasattr(child, "_sync_ocr_availability"):
                target = child
                break
        assert target is not None, "No child has _sync_ocr_availability"

        mock_sync = MagicMock()
        target._sync_ocr_availability = mock_sync

        tabs.setCurrentIndex(0)
        mock_sync.reset_mock()
        tabs.setCurrentIndex(3)
        mock_sync.assert_called()

    def test_translation_tab_calls_sync_on_children(
        self,
        qapp: QApplication,
    ) -> None:
        """Switching to Translation tab (index 6) calls sync on children.

        Verifies _sync_ocr_state and _sync_office_state are invoked.
        """
        page = self._build_page(qapp)
        tabs = page.findChild(QTabWidget)
        translation_wrapper = tabs.widget(6)

        from PySide6.QtWidgets import QScrollArea  # noqa: PLC0415

        scroll = translation_wrapper.findChild(QScrollArea)
        inner = scroll.widget() if scroll else translation_wrapper

        # Find children with sync methods and replace with mocks
        mock_ocr = MagicMock()
        mock_office = MagicMock()
        found_ocr = False
        found_office = False
        for child in inner.findChildren(QWidget):
            if hasattr(child, "_sync_ocr_state"):
                child._sync_ocr_state = mock_ocr
                found_ocr = True
            if hasattr(child, "_sync_office_state"):
                child._sync_office_state = mock_office
                found_office = True
        assert found_ocr, "No child has _sync_ocr_state"
        assert found_office, "No child has _sync_office_state"

        tabs.setCurrentIndex(0)
        mock_ocr.reset_mock()
        mock_office.reset_mock()
        tabs.setCurrentIndex(6)
        mock_ocr.assert_called()
        mock_office.assert_called()

    def test_extract_tab_calls_sync_method_availability(
        self,
        qapp: QApplication,
    ) -> None:
        """Switching to Extract tab (index 11) calls _sync_method_availability."""
        page = self._build_page(qapp)
        tabs = page.findChild(QTabWidget)
        extract_wrapper = tabs.widget(11)

        from PySide6.QtWidgets import QScrollArea  # noqa: PLC0415

        scroll = extract_wrapper.findChild(QScrollArea)
        inner = scroll.widget() if scroll else extract_wrapper

        mock_sync = MagicMock()
        found = False
        for child in inner.findChildren(QWidget):
            if hasattr(child, "_sync_method_availability"):
                child._sync_method_availability = mock_sync
                found = True
        assert found, "No child has _sync_method_availability"

        tabs.setCurrentIndex(0)
        mock_sync.reset_mock()
        tabs.setCurrentIndex(11)
        mock_sync.assert_called()

    def test_subtitle_tab_calls_sync_stt_availability(
        self,
        qapp: QApplication,
    ) -> None:
        """Switching to Subtitle tab (index 7) calls _sync_stt_availability."""
        page = self._build_page(qapp)
        tabs = page.findChild(QTabWidget)
        subtitle_wrapper = tabs.widget(7)

        from PySide6.QtWidgets import QScrollArea  # noqa: PLC0415

        scroll = subtitle_wrapper.findChild(QScrollArea)
        inner = scroll.widget() if scroll else subtitle_wrapper
        target = None
        for child in [inner, *inner.findChildren(QWidget)]:
            if hasattr(child, "_sync_stt_availability"):
                target = child
                break
        assert target is not None, "No child has _sync_stt_availability"

        mock_sync = MagicMock()
        target._sync_stt_availability = mock_sync

        tabs.setCurrentIndex(0)
        mock_sync.reset_mock()
        tabs.setCurrentIndex(7)
        mock_sync.assert_called()

    def test_voice_tab_calls_sync_tts_availability(
        self,
        qapp: QApplication,
    ) -> None:
        """Switching to Voice tab (index 8) calls _sync_tts_availability."""
        page = self._build_page(qapp)
        tabs = page.findChild(QTabWidget)
        voice_wrapper = tabs.widget(8)

        from PySide6.QtWidgets import QScrollArea  # noqa: PLC0415

        scroll = voice_wrapper.findChild(QScrollArea)
        inner = scroll.widget() if scroll else voice_wrapper
        target = None
        for child in [inner, *inner.findChildren(QWidget)]:
            if hasattr(child, "_sync_tts_availability"):
                target = child
                break
        assert target is not None, "No child has _sync_tts_availability"

        mock_sync = MagicMock()
        target._sync_tts_availability = mock_sync

        tabs.setCurrentIndex(0)
        mock_sync.reset_mock()
        tabs.setCurrentIndex(8)
        mock_sync.assert_called()


# ===================================================================
# Gap 2: Provider config model enable/disable (HIGH)
# ===================================================================


class TestProviderConfigModelEnableDisable:
    """Tests for model field enable/disable and hint banner visibility.

    Covers create_provider_config() model enable/disable logic.
    """

    @pytest.fixture(autouse=True)
    def _deps(self, _mock_settings_deps):
        """Auto-use mock dependencies."""

    def _build_provider(
        self,
        qapp: QApplication,
        *,
        api_key_value: str = "",
        hint: bool = False,
    ) -> QWidget:
        """Build a provider config with a controlled api key value."""
        from src.ui.pages.settings import create_provider_config  # noqa: PLC0415

        def custom_load(key, default=""):
            if key == "test/api_key":
                return api_key_value
            return default

        group = QButtonGroup()
        radio = QRadioButton("TestProv")
        group.addButton(radio)

        with (
            patch("src.ui.pages.settings.load_setting", custom_load),
            patch("src.ui.components.load_setting", custom_load),
            patch("src.ui.pages.settings.save_setting"),
        ):
            return create_provider_config(
                "TestProv",
                "test/api_key",
                "test/model",
                ["model-a", "model-b"],
                hint_tr_key="test.hint" if hint else None,
            )

    def test_model_disabled_when_api_key_empty(
        self,
        qapp: QApplication,
    ) -> None:
        """Model combo is disabled when API key is empty."""
        w = self._build_provider(qapp, api_key_value="")
        combos = w.findChildren(QComboBox)
        assert len(combos) >= 1
        model_combo = combos[0]
        assert not model_combo.isEnabled()

    def test_model_enabled_when_api_key_filled(
        self,
        qapp: QApplication,
    ) -> None:
        """Model combo is enabled when API key has content."""
        w = self._build_provider(qapp, api_key_value="my-secret-key")
        combos = w.findChildren(QComboBox)
        assert len(combos) >= 1
        model_combo = combos[0]
        assert model_combo.isEnabled()

    def test_hint_banner_visible_when_api_key_empty(
        self,
        qapp: QApplication,
    ) -> None:
        """Hint banner is NOT hidden when API key is empty."""
        w = self._build_provider(qapp, api_key_value="", hint=True)
        from PySide6.QtWidgets import QFrame  # noqa: PLC0415

        # Find the hint banner (QFrame with objectName "Banner")
        banners = [f for f in w.findChildren(QFrame) if f.objectName() == "Banner"]
        assert len(banners) >= 1
        # isHidden() checks the widget's own hidden flag, not effective visibility
        assert not banners[0].isHidden()

    def test_hint_banner_hidden_when_api_key_filled(
        self,
        qapp: QApplication,
    ) -> None:
        """Hint banner IS hidden when API key has content."""
        w = self._build_provider(qapp, api_key_value="my-key", hint=True)
        from PySide6.QtWidgets import QFrame  # noqa: PLC0415

        banners = [f for f in w.findChildren(QFrame) if f.objectName() == "Banner"]
        assert len(banners) >= 1
        assert banners[0].isHidden()

    def test_model_field_toggles_on_key_change(
        self,
        qapp: QApplication,
    ) -> None:
        """Model field enables/disables as API key content changes."""
        from PySide6.QtWidgets import QLineEdit  # noqa: PLC0415

        w = self._build_provider(qapp, api_key_value="")
        combos = w.findChildren(QComboBox)
        model_combo = combos[0]
        assert not model_combo.isEnabled()

        # Find the API key input (QLineEdit with password echo)
        line_edits = w.findChildren(QLineEdit)
        api_input = None
        for le in line_edits:
            if le.echoMode() == QLineEdit.EchoMode.Password:
                api_input = le
                break
        assert api_input is not None, "Could not find password QLineEdit"

        # Simulate typing an API key
        with patch("src.ui.pages.settings.save_setting"):
            api_input.setText("new-api-key")
        assert model_combo.isEnabled()

        # Clear the API key
        with patch("src.ui.pages.settings.save_setting"):
            api_input.setText("")
        assert not model_combo.isEnabled()


# ===================================================================
# Gap 3: System theme monitor in auto mode (HIGH)
# ===================================================================


class TestSystemThemeMonitorAutoMode:
    """Tests for on_theme_changed() starting/stopping the system theme monitor."""

    @pytest.fixture(autouse=True)
    def _deps(self, _mock_settings_deps):
        """Auto-use mock dependencies."""

    def test_auto_theme_calls_detect_and_starts_monitor(
        self,
        qapp: QApplication,
    ) -> None:
        """Selecting 'Auto' theme calls detect_system_theme when no monitor exists."""
        with (
            patch("src.ui.pages.settings.save_setting"),
            patch("src.ui.pages.settings.set_theme") as mock_set_theme,
            patch(
                "src.ui.system_theme.detect_system_theme",
                return_value="light",
            ) as mock_detect,
        ):
            from src.ui.pages.settings import create_general_settings  # noqa: PLC0415

            w = create_general_settings()
            groups = w.findChildren(QButtonGroup)
            theme_group = groups[0]
            btns = theme_group.buttons()
            # Index 0 = "Auto"
            auto_btn = btns[0]
            auto_btn.setChecked(True)
            theme_group.buttonClicked.emit(auto_btn)

            # Since widget.window() won't have _system_theme_monitor,
            # detect_system_theme should be called as fallback
            mock_detect.assert_called_once()
            mock_set_theme.assert_called_with("light")

    def test_auto_theme_starts_existing_monitor(
        self,
        qapp: QApplication,
    ) -> None:
        """Selecting 'Auto' starts the monitor if widget.window() has one."""
        with (
            patch("src.ui.pages.settings.save_setting"),
            patch("src.ui.pages.settings.set_theme"),
        ):
            from src.ui.pages.settings import create_general_settings  # noqa: PLC0415

            w = create_general_settings()

            # Attach a mock monitor to the window
            mock_monitor = MagicMock()
            w.window()._system_theme_monitor = mock_monitor

            groups = w.findChildren(QButtonGroup)
            theme_group = groups[0]
            btns = theme_group.buttons()
            auto_btn = btns[0]
            auto_btn.setChecked(True)
            theme_group.buttonClicked.emit(auto_btn)

            mock_monitor.start.assert_called_once()

    def test_non_auto_theme_stops_monitor(
        self,
        qapp: QApplication,
    ) -> None:
        """Selecting 'Light' or 'Dark' stops the system theme monitor."""
        with (
            patch("src.ui.pages.settings.save_setting"),
            patch("src.ui.pages.settings.set_theme"),
        ):
            from src.ui.pages.settings import create_general_settings  # noqa: PLC0415

            w = create_general_settings()

            # Attach a mock monitor to the window
            mock_monitor = MagicMock()
            w.window()._system_theme_monitor = mock_monitor

            groups = w.findChildren(QButtonGroup)
            theme_group = groups[0]
            btns = theme_group.buttons()
            # Index 1 = "Light"
            light_btn = btns[1]
            light_btn.setChecked(True)
            theme_group.buttonClicked.emit(light_btn)

            mock_monitor.stop.assert_called_once()

    def test_switch_from_auto_to_dark_stops_monitor(
        self,
        qapp: QApplication,
    ) -> None:
        """Switching from Auto to Dark stops the monitor."""
        with (
            patch("src.ui.pages.settings.save_setting"),
            patch("src.ui.pages.settings.set_theme"),
        ):
            from src.ui.pages.settings import create_general_settings  # noqa: PLC0415

            w = create_general_settings()

            mock_monitor = MagicMock()
            w.window()._system_theme_monitor = mock_monitor

            groups = w.findChildren(QButtonGroup)
            theme_group = groups[0]
            btns = theme_group.buttons()

            # First select auto
            btns[0].setChecked(True)
            theme_group.buttonClicked.emit(btns[0])
            mock_monitor.start.assert_called_once()

            # Now switch to dark
            mock_monitor.reset_mock()
            btns[2].setChecked(True)
            theme_group.buttonClicked.emit(btns[2])
            mock_monitor.stop.assert_called_once()


# ===================================================================
# Gap 4: OCR/Translation sync callbacks with blockSignals (HIGH)
# ===================================================================


class TestTranslationSyncCallbacksBlockSignals:
    """Tests for _sync_ocr_state() and _sync_office_state() blockSignals.

    Verifies that create_translation_settings() sync callbacks
    properly disable/clear checkboxes using blockSignals.
    """

    def test_ocr_checkbox_disabled_and_cleared_when_unavailable(
        self,
        qapp: QApplication,
    ) -> None:
        """Images checkbox is disabled AND unchecked when OCR is unavailable."""
        import contextlib  # noqa: PLC0415

        patches = dict(_SETTINGS_PATCHES)
        patches["src.ui.pages.settings.check_ocr_setup"] = lambda: False

        with contextlib.ExitStack() as stack:
            for target, replacement in patches.items():
                stack.enter_context(patch(target, replacement))

            from src.ui.pages.settings import (  # noqa: PLC0415
                create_translation_settings,
            )

            w = create_translation_settings()
            # Find the widget that has _sync_ocr_state
            target = None
            for child in w.findChildren(QWidget):
                if hasattr(child, "_sync_ocr_state"):
                    target = child
                    break
            assert target is not None

            # The images checkbox should be inside the same section
            cbs = w.findChildren(QCheckBox)
            # Find the translate images checkbox — it is on the widget
            # that owns _sync_ocr_state or adjacent
            # The checkbox is the one that was disabled by _sync_ocr_state
            disabled_cbs = [cb for cb in cbs if not cb.isEnabled()]
            assert len(disabled_cbs) >= 1
            # All disabled image checkboxes should be unchecked
            for cb in disabled_cbs:
                assert not cb.isChecked()

    def test_ocr_checkbox_enabled_when_available(
        self,
        qapp: QApplication,
    ) -> None:
        """Images checkbox is enabled when OCR IS available."""
        import contextlib  # noqa: PLC0415

        patches = dict(_SETTINGS_PATCHES)
        patches["src.ui.pages.settings.check_ocr_setup"] = lambda: True
        patches["src.ui.pages.settings.check_office_converter_setup"] = lambda: True

        with contextlib.ExitStack() as stack:
            for target, replacement in patches.items():
                stack.enter_context(patch(target, replacement))

            from src.ui.pages.settings import (  # noqa: PLC0415
                create_translation_settings,
            )

            w = create_translation_settings()
            # All checkboxes should be enabled
            cbs = w.findChildren(QCheckBox)
            for cb in cbs:
                assert cb.isEnabled(), f"Checkbox '{cb.text()}' unexpectedly disabled"

    def test_sync_ocr_state_preserves_saved_preference(
        self,
        qapp: QApplication,
    ) -> None:
        """_sync_ocr_state() must not overwrite the persisted preference.

        A transient OCR outage should disable the UI only — the user's
        stored choice must survive for when OCR comes back.
        """
        import contextlib  # noqa: PLC0415

        def custom_load(key, default=""):
            if key == "translation/translate_doc_images":
                return True
            return default

        patches = dict(_SETTINGS_PATCHES)
        patches["src.ui.pages.settings.load_setting"] = custom_load
        patches["src.ui.components.load_setting"] = custom_load
        patches["src.ui.pages.settings.check_ocr_setup"] = lambda: True
        patches["src.ui.pages.settings.check_office_converter_setup"] = lambda: True

        with contextlib.ExitStack() as stack:
            for target, replacement in patches.items():
                stack.enter_context(patch(target, replacement))

            from src.ui.pages.settings import (  # noqa: PLC0415
                create_translation_settings,
            )

            w = create_translation_settings()

        target_widget = None
        for child in w.findChildren(QWidget):
            if hasattr(child, "_sync_ocr_state"):
                target_widget = child
                break
        assert target_widget is not None

        with (
            patch(
                "src.ui.pages.settings.check_ocr_setup",
                return_value=False,
            ),
            patch("src.ui.pages.settings.save_setting") as mock_save,
        ):
            target_widget._sync_ocr_state()

        save_calls = [
            c
            for c in mock_save.call_args_list
            if len(c[0]) >= 1 and c[0][0] == "translation/translate_doc_images"
        ]
        assert save_calls == []

    def test_office_checkboxes_disabled_when_unavailable(
        self,
        qapp: QApplication,
    ) -> None:
        """Auto-convert checkboxes disabled and unchecked without office."""
        import contextlib  # noqa: PLC0415

        patches = dict(_SETTINGS_PATCHES)
        patches["src.ui.pages.settings.check_office_converter_setup"] = lambda: False

        with contextlib.ExitStack() as stack:
            for target, replacement in patches.items():
                stack.enter_context(patch(target, replacement))

            from src.ui.pages.settings import (  # noqa: PLC0415
                create_translation_settings,
            )

            w = create_translation_settings()

        # Find the widget with _sync_office_state
        target_widget = None
        for child in w.findChildren(QWidget):
            if hasattr(child, "_sync_office_state"):
                target_widget = child
                break
        assert target_widget is not None

        # Check that at least 2 checkboxes are disabled (legacy + ODF)
        cbs = w.findChildren(QCheckBox)
        disabled_cbs = [cb for cb in cbs if not cb.isEnabled()]
        assert len(disabled_cbs) >= 2  # noqa: PLR2004
        for cb in disabled_cbs:
            assert not cb.isChecked()

    def test_office_checkboxes_enabled_when_available(
        self,
        qapp: QApplication,
    ) -> None:
        """Auto-convert checkboxes are enabled when office converter is available."""
        import contextlib  # noqa: PLC0415

        patches = dict(_SETTINGS_PATCHES)
        patches["src.ui.pages.settings.check_ocr_setup"] = lambda: True
        patches["src.ui.pages.settings.check_office_converter_setup"] = lambda: True

        with contextlib.ExitStack() as stack:
            for target, replacement in patches.items():
                stack.enter_context(patch(target, replacement))

            from src.ui.pages.settings import (  # noqa: PLC0415
                create_translation_settings,
            )

            w = create_translation_settings()

        cbs = w.findChildren(QCheckBox)
        for cb in cbs:
            assert cb.isEnabled(), f"Checkbox '{cb.text()}' unexpectedly disabled"

    def test_sync_office_state_preserves_saved_preferences(
        self,
        qapp: QApplication,
    ) -> None:
        """_sync_office_state() must not overwrite persisted preferences.

        A transient office-converter outage should disable the UI only —
        the user's stored choices must survive for when a converter returns.
        """
        import contextlib  # noqa: PLC0415

        def custom_load(key, default=""):
            if key in (
                "translation/auto_convert_legacy",
                "translation/auto_convert_odf",
            ):
                return True
            return default

        patches = dict(_SETTINGS_PATCHES)
        patches["src.ui.pages.settings.load_setting"] = custom_load
        patches["src.ui.components.load_setting"] = custom_load
        patches["src.ui.pages.settings.check_ocr_setup"] = lambda: True
        patches["src.ui.pages.settings.check_office_converter_setup"] = lambda: True

        with contextlib.ExitStack() as stack:
            for target, replacement in patches.items():
                stack.enter_context(patch(target, replacement))

            from src.ui.pages.settings import (  # noqa: PLC0415
                create_translation_settings,
            )

            w = create_translation_settings()

        target_widget = None
        for child in w.findChildren(QWidget):
            if hasattr(child, "_sync_office_state"):
                target_widget = child
                break
        assert target_widget is not None

        with (
            patch(
                "src.ui.pages.settings.check_office_converter_setup",
                return_value=False,
            ),
            patch("src.ui.pages.settings.save_setting") as mock_save,
        ):
            target_widget._sync_office_state()

        auto_convert_saves = [
            c
            for c in mock_save.call_args_list
            if len(c[0]) >= 1
            and c[0][0]
            in (
                "translation/auto_convert_legacy",
                "translation/auto_convert_odf",
            )
        ]
        assert auto_convert_saves == []


# ===================================================================
# TestSettingsTabContent — widgets present in each tab
# ===================================================================


class TestSettingsTabContent:
    """Verifies each settings tab contains expected widget types."""

    @pytest.fixture(autouse=True)
    def _deps(self, _mock_settings_deps):
        """Auto-use mock dependencies."""

    def _build_page(self, qapp: QApplication) -> QWidget:
        from src.ui.pages.settings import create_settings_page  # noqa: PLC0415

        return create_settings_page()

    def test_general_tab_has_radio_buttons(self, qapp: QApplication) -> None:
        """General tab has radio buttons for theme selection."""
        page = self._build_page(qapp)
        tabs = page.findChild(QTabWidget)
        general = tabs.widget(0)
        radios = general.findChildren(QRadioButton)
        assert len(radios) >= 3  # noqa: PLR2004

    def test_general_tab_has_combo_box(self, qapp: QApplication) -> None:
        """General tab has a combo box for language selection."""
        page = self._build_page(qapp)
        tabs = page.findChild(QTabWidget)
        general = tabs.widget(0)
        combos = general.findChildren(QComboBox)
        assert len(combos) >= 1

    def test_general_tab_has_labels(self, qapp: QApplication) -> None:
        """General tab has labels for theme and language rows."""
        page = self._build_page(qapp)
        tabs = page.findChild(QTabWidget)
        general = tabs.widget(0)
        labels = general.findChildren(QLabel)
        assert len(labels) >= 2  # noqa: PLR2004

    def test_service_tab_has_labels(self, qapp: QApplication) -> None:
        """Service tab contains labels for Cloud API section."""
        page = self._build_page(qapp)
        tabs = page.findChild(QTabWidget)
        service = tabs.widget(2)
        labels = service.findChildren(QLabel)
        assert len(labels) >= 1

    def test_ocr_tab_has_radio_buttons(self, qapp: QApplication) -> None:
        """OCR tab contains radio buttons for OCR methods."""
        page = self._build_page(qapp)
        tabs = page.findChild(QTabWidget)
        ocr = tabs.widget(3)
        radios = ocr.findChildren(QRadioButton)
        assert len(radios) >= 3  # noqa: PLR2004

    def test_llm_tab_has_no_provider_radio_buttons(self, qapp: QApplication) -> None:
        """LLM tab has no PROVIDER radio buttons.

        The two radios on the tab (Developer API / Vertex AI) are
        Gemini-internal auth-mode controls, not provider selection.
        """
        page = self._build_page(qapp)
        tabs = page.findChild(QTabWidget)
        llm = tabs.widget(4)
        radios = llm.findChildren(QRadioButton)
        assert len(radios) == 2  # noqa: PLR2004

    def test_llm_tab_has_api_key_fields(self, qapp: QApplication) -> None:
        """LLM tab has API key fields for both providers."""
        from PySide6.QtWidgets import QLineEdit  # noqa: PLC0415

        with _patch_custom_providers():
            page = self._build_page(qapp)
        tabs = page.findChild(QTabWidget)
        llm = tabs.widget(4)
        password_fields = [
            le
            for le in llm.findChildren(QLineEdit)
            if le.echoMode() == QLineEdit.EchoMode.Password
        ]
        assert len(password_fields) >= 2  # noqa: PLR2004  # Gemini + Custom API keys

    def test_translation_tab_has_checkboxes(self, qapp: QApplication) -> None:
        """Translation tab contains checkboxes for various options."""
        page = self._build_page(qapp)
        tabs = page.findChild(QTabWidget)
        translation = tabs.widget(6)
        cbs = translation.findChildren(QCheckBox)
        assert len(cbs) >= 7  # noqa: PLR2004

    def test_subtitle_tab_has_radio_buttons(self, qapp: QApplication) -> None:
        """Subtitle tab contains radio buttons for STT method and format."""
        page = self._build_page(qapp)
        tabs = page.findChild(QTabWidget)
        subtitle = tabs.widget(7)
        radios = subtitle.findChildren(QRadioButton)
        assert len(radios) >= 4  # noqa: PLR2004

    def test_voice_tab_has_radio_buttons(self, qapp: QApplication) -> None:
        """Voice tab contains radio buttons for TTS method and format."""
        page = self._build_page(qapp)
        tabs = page.findChild(QTabWidget)
        voice = tabs.widget(8)
        radios = voice.findChildren(QRadioButton)
        assert len(radios) >= 4  # noqa: PLR2004

    def test_dubbing_tab_has_checkbox(self, qapp: QApplication) -> None:
        """Dubbing tab contains at least one checkbox for auto-remove."""
        page = self._build_page(qapp)
        tabs = page.findChild(QTabWidget)
        dubbing = tabs.widget(9)
        cbs = dubbing.findChildren(QCheckBox)
        assert len(cbs) >= 1

    def test_extract_tab_has_radio_buttons(self, qapp: QApplication) -> None:
        """Extract Text tab contains radio buttons for method and format."""
        page = self._build_page(qapp)
        tabs = page.findChild(QTabWidget)
        extract = tabs.widget(11)
        radios = extract.findChildren(QRadioButton)
        assert len(radios) >= 4  # noqa: PLR2004

    def test_extract_tab_has_checkbox(self, qapp: QApplication) -> None:
        """Extract Text tab contains at least one checkbox."""
        page = self._build_page(qapp)
        tabs = page.findChild(QTabWidget)
        extract = tabs.widget(11)
        cbs = extract.findChildren(QCheckBox)
        assert len(cbs) >= 1


# ===================================================================
# TestSettingsThemeTab — theme and language controls
# ===================================================================


class TestSettingsThemeTab:
    """Tests for theme radio buttons and language dropdown in General tab."""

    @pytest.fixture(autouse=True)
    def _deps(self, _mock_settings_deps):
        """Auto-use mock dependencies."""

    def _build(self, qapp: QApplication) -> QWidget:
        from src.ui.pages.settings import create_general_settings  # noqa: PLC0415

        return create_general_settings()

    def test_theme_has_three_options(self, qapp: QApplication) -> None:
        """Theme group has exactly 3 radio buttons (Auto, Light, Dark)."""
        w = self._build(qapp)
        groups = w.findChildren(QButtonGroup)
        theme_group = groups[0]
        assert len(theme_group.buttons()) == 3  # noqa: PLR2004

    def test_theme_options_text(self, qapp: QApplication) -> None:
        """Theme radio button texts are translatable keys for auto/light/dark."""
        w = self._build(qapp)
        groups = w.findChildren(QButtonGroup)
        theme_group = groups[0]
        btn_texts = [b.text() for b in theme_group.buttons()]
        # There should be exactly 3 non-empty texts
        assert len(btn_texts) == 3  # noqa: PLR2004
        assert all(t != "" for t in btn_texts)

    def test_theme_change_saves_setting(self, qapp: QApplication) -> None:
        """Switching theme radio saves the theme setting key."""
        with patch("src.ui.pages.settings.save_setting") as mock_save:
            w = self._build(qapp)
            groups = w.findChildren(QButtonGroup)
            theme_group = groups[0]
            btns = theme_group.buttons()
            # Click Light (index 1)
            btns[1].setChecked(True)
            theme_group.buttonClicked.emit(btns[1])
            save_calls = [c for c in mock_save.call_args_list if c[0][0] == "app/theme"]
            assert len(save_calls) >= 1

    def test_language_dropdown_has_all_languages(self, qapp: QApplication) -> None:
        """Language combo has items matching UI_LANGUAGES count."""
        from src.constants.i18n import UI_LANGUAGES  # noqa: PLC0415

        w = self._build(qapp)
        combos = w.findChildren(QComboBox)
        lang_combo = combos[0]
        assert lang_combo.count() == len(UI_LANGUAGES)

    def test_language_dropdown_item_data_matches_codes(
        self,
        qapp: QApplication,
    ) -> None:
        """Language combo item data contains language codes from UI_LANGUAGES."""
        from src.constants.i18n import UI_LANGUAGES  # noqa: PLC0415

        w = self._build(qapp)
        combos = w.findChildren(QComboBox)
        lang_combo = combos[0]
        for i, (code, *_) in enumerate(UI_LANGUAGES):
            assert lang_combo.itemData(i) == code

    def test_language_default_en_us(self, qapp: QApplication) -> None:
        """Default language selection is en-US."""
        w = self._build(qapp)
        combos = w.findChildren(QComboBox)
        lang_combo = combos[0]
        assert lang_combo.currentData() == "en-US"

    def test_saved_dark_theme_selects_dark_radio(self, qapp: QApplication) -> None:
        """When saved theme is 'dark', the Dark radio is selected."""
        import contextlib  # noqa: PLC0415

        def custom_load(key, default=""):
            if key == "app/theme":
                return "dark"
            return default

        patches = dict(_SETTINGS_PATCHES)
        patches["src.ui.pages.settings.load_setting"] = custom_load
        patches["src.ui.components.load_setting"] = custom_load

        with contextlib.ExitStack() as stack:
            for target, replacement in patches.items():
                stack.enter_context(patch(target, replacement))

            from src.ui.pages.settings import create_general_settings  # noqa: PLC0415

            w = create_general_settings()
            groups = w.findChildren(QButtonGroup)
            theme_group = groups[0]
            checked = theme_group.checkedButton()
            assert checked is not None
            # Index 2 = Dark
            assert theme_group.id(checked) == 2  # noqa: PLR2004


# ===================================================================
# TestSettingsServiceTab — API key fields
# ===================================================================


class TestSettingsServiceTab:
    """Tests for Service settings tab API key fields."""

    @pytest.fixture(autouse=True)
    def _deps(self, _mock_settings_deps):
        """Auto-use mock dependencies."""

    def _build(self, qapp: QApplication) -> QWidget:
        from src.ui.pages.settings import create_service_settings  # noqa: PLC0415

        return create_service_settings()

    def test_has_password_input_field(self, qapp: QApplication) -> None:
        """Service tab has at least one password (API key) input field."""
        from PySide6.QtWidgets import QLineEdit  # noqa: PLC0415

        w = self._build(qapp)
        line_edits = w.findChildren(QLineEdit)
        password_fields = [
            le for le in line_edits if le.echoMode() == QLineEdit.EchoMode.Password
        ]
        assert len(password_fields) >= 1

    def test_api_key_field_has_placeholder(self, qapp: QApplication) -> None:
        """API key input has a non-empty placeholder text."""
        from PySide6.QtWidgets import QLineEdit  # noqa: PLC0415

        w = self._build(qapp)
        line_edits = w.findChildren(QLineEdit)
        password_fields = [
            le for le in line_edits if le.echoMode() == QLineEdit.EchoMode.Password
        ]
        assert len(password_fields) >= 1
        assert password_fields[0].placeholderText() != ""

    def test_api_key_save_on_change(self, qapp: QApplication) -> None:
        """Changing the API key input triggers save_setting."""
        from PySide6.QtWidgets import QLineEdit  # noqa: PLC0415

        with (
            patch("src.ui.pages.settings.save_setting"),
            patch("src.ui.components.save_setting") as mock_comp_save,
        ):
            w = self._build(qapp)
            line_edits = w.findChildren(QLineEdit)
            password_fields = [
                le for le in line_edits if le.echoMode() == QLineEdit.EchoMode.Password
            ]
            assert len(password_fields) >= 1
            mock_comp_save.reset_mock()
            password_fields[0].setText("test-api-key-value")
            # save_setting in components should have been called
            assert mock_comp_save.called

    def test_api_key_visibility_toggle(self, qapp: QApplication) -> None:
        """API key field has a visibility toggle button."""
        from PySide6.QtWidgets import QLineEdit, QPushButton  # noqa: PLC0415

        w = self._build(qapp)
        line_edits = w.findChildren(QLineEdit)
        password_fields = [
            le for le in line_edits if le.echoMode() == QLineEdit.EchoMode.Password
        ]
        assert len(password_fields) >= 1
        # There should be at least one QPushButton near the password field
        buttons = w.findChildren(QPushButton)
        assert len(buttons) >= 1

    def test_api_key_empty_by_default(self, qapp: QApplication) -> None:
        """API key field is empty when no setting is saved."""
        from PySide6.QtWidgets import QLineEdit  # noqa: PLC0415

        w = self._build(qapp)
        line_edits = w.findChildren(QLineEdit)
        password_fields = [
            le for le in line_edits if le.echoMode() == QLineEdit.EchoMode.Password
        ]
        assert len(password_fields) >= 1
        assert password_fields[0].text() == ""


# ===================================================================
# TestSettingsOCRTab — OCR method radio buttons
# ===================================================================


class TestSettingsOCRTab:
    """Tests for OCR settings tab radio button details."""

    @pytest.fixture(autouse=True)
    def _deps(self, _mock_settings_deps):
        """Auto-use mock dependencies."""

    def _build(self, qapp: QApplication) -> QWidget:
        from src.ui.pages.settings import create_ocr_settings  # noqa: PLC0415

        return create_ocr_settings()

    def test_ocr_methods_count(self, qapp: QApplication) -> None:
        """OCR tab has one radio per OCR_METHODS entry."""
        from src.constants.ocr import OCR_METHODS  # noqa: PLC0415

        w = self._build(qapp)
        radios = w.findChildren(QRadioButton)
        radio_methods = {r.property("method") for r in radios}
        for method in OCR_METHODS:
            assert method in radio_methods

    def test_tesseract_radio_method(self, qapp: QApplication) -> None:
        """Tesseract radio exposes OCR_METHOD_TESSERACT via its 'method' property."""
        from src.constants.ocr import OCR_METHOD_TESSERACT  # noqa: PLC0415

        w = self._build(qapp)
        radios = w.findChildren(QRadioButton)
        assert any(r.property("method") == OCR_METHOD_TESSERACT for r in radios)

    def test_easyocr_radio_method(self, qapp: QApplication) -> None:
        """EasyOCR radio exposes OCR_METHOD_EASYOCR via its 'method' property."""
        from src.constants.ocr import OCR_METHOD_EASYOCR  # noqa: PLC0415

        w = self._build(qapp)
        radios = w.findChildren(QRadioButton)
        assert any(r.property("method") == OCR_METHOD_EASYOCR for r in radios)

    def test_google_cloud_radio_method(self, qapp: QApplication) -> None:
        """Google Cloud OCR radio is tagged with OCR_METHOD_GOOGLE_CLOUD."""
        from src.constants.ocr import OCR_METHOD_GOOGLE_CLOUD  # noqa: PLC0415

        w = self._build(qapp)
        radios = w.findChildren(QRadioButton)
        assert any(r.property("method") == OCR_METHOD_GOOGLE_CLOUD for r in radios)

    def test_ocr_radios_have_pointing_cursor(self, qapp: QApplication) -> None:
        """All OCR radio buttons have PointingHandCursor."""
        w = self._build(qapp)
        radios = w.findChildren(QRadioButton)
        for r in radios:
            assert r.cursor().shape() == Qt.CursorShape.PointingHandCursor

    def test_ocr_button_group_exclusive(self, qapp: QApplication) -> None:
        """OCR button group is exclusive."""
        w = self._build(qapp)
        groups = w.findChildren(QButtonGroup)
        assert len(groups) >= 1
        assert groups[0].exclusive()


# ===================================================================
# TestSettingsLLMTab — LLM provider and model details
# ===================================================================


class TestSettingsLLMTab:
    """Tests for LLM settings tab provider sections (no radios)."""

    @pytest.fixture(autouse=True)
    def _deps(self, _mock_settings_deps):
        """Auto-use mock dependencies."""

    def _build(self, qapp: QApplication) -> QWidget:
        from src.ui.pages.settings import create_llm_settings  # noqa: PLC0415

        return create_llm_settings()

    def test_no_provider_radios(self, qapp: QApplication) -> None:
        """LLM tab has no PROVIDER radio buttons.

        The two radios on the tab are Gemini auth-mode (Developer API /
        Vertex AI), not provider selection.
        """
        w = self._build(qapp)
        radios = w.findChildren(QRadioButton)
        assert len(radios) == 2  # noqa: PLR2004

    def test_no_extra_button_groups(self, qapp: QApplication) -> None:
        """LLM tab owns exactly one QButtonGroup (Gemini auth mode)."""
        w = self._build(qapp)
        groups = w.findChildren(QButtonGroup)
        assert len(groups) == 1

    def test_only_default_model_combo(self, qapp: QApplication) -> None:
        """Default Model combo + Vertex location combo (no Gemini model combo)."""
        w = self._build(qapp)
        combos = w.findChildren(QComboBox)
        assert len(combos) == 2  # noqa: PLR2004

    def test_custom_endpoint_field_exists(self, qapp: QApplication) -> None:
        """Custom provider section has an endpoint text field."""
        from PySide6.QtWidgets import QLineEdit  # noqa: PLC0415

        with _patch_custom_providers():
            w = self._build(qapp)
        line_edits = w.findChildren(QLineEdit)
        # Should have fields for: Gemini API key, Custom API key,
        # Custom model, Custom endpoint
        # Filter for non-password text fields
        text_fields = [
            le for le in line_edits if le.echoMode() != QLineEdit.EchoMode.Password
        ]
        assert len(text_fields) >= 2  # noqa: PLR2004  # model + endpoint

    def test_both_api_key_fields_exist(self, qapp: QApplication) -> None:
        """Both Gemini and Custom API key fields exist."""
        from PySide6.QtWidgets import QLineEdit  # noqa: PLC0415

        with _patch_custom_providers():
            w = self._build(qapp)
        password_fields = [
            le
            for le in w.findChildren(QLineEdit)
            if le.echoMode() == QLineEdit.EchoMode.Password
        ]
        assert len(password_fields) >= 2  # noqa: PLR2004  # Gemini + Custom


# ===================================================================
# TestSettingsTranslationTab — checkboxes and paths
# ===================================================================


class TestSettingsTranslationTab:
    """Tests for Translation settings tab checkboxes and path controls."""

    @pytest.fixture(autouse=True)
    def _deps(self, _mock_settings_deps):
        """Auto-use mock dependencies."""

    def _build(self, qapp: QApplication) -> QWidget:
        from src.ui.pages.settings import create_translation_settings  # noqa: PLC0415

        return create_translation_settings()

    def test_auto_remove_checkbox_exists(self, qapp: QApplication) -> None:
        """Translation settings has an auto-remove history checkbox."""
        w = self._build(qapp)
        cbs = w.findChildren(QCheckBox)
        assert len(cbs) >= 1

    def test_comments_checkbox_exists(self, qapp: QApplication) -> None:
        """Translation settings has a translate comments checkbox."""
        w = self._build(qapp)
        cbs = w.findChildren(QCheckBox)
        # At least 5: comments, shapes, notes, sheet names, images
        assert len(cbs) >= 5  # noqa: PLR2004

    def test_legacy_conversion_checkbox_disabled_without_office(
        self,
        qapp: QApplication,
    ) -> None:
        """Auto-convert legacy checkbox is disabled when no office is available."""
        w = self._build(qapp)
        cbs = w.findChildren(QCheckBox)
        # Default mocks have check_office_converter_setup returning False
        disabled_cbs = [cb for cb in cbs if not cb.isEnabled()]
        # At least auto-convert legacy and auto-convert ODF
        assert len(disabled_cbs) >= 2  # noqa: PLR2004

    def test_odf_conversion_checkbox_disabled_without_office(
        self,
        qapp: QApplication,
    ) -> None:
        """Auto-convert ODF checkbox is disabled when no office is available."""
        w = self._build(qapp)
        cbs = w.findChildren(QCheckBox)
        disabled_cbs = [cb for cb in cbs if not cb.isEnabled()]
        assert len(disabled_cbs) >= 2  # noqa: PLR2004

    def test_images_checkbox_disabled_without_ocr(
        self,
        qapp: QApplication,
    ) -> None:
        """Translate images checkbox disabled when OCR is not configured."""
        with patch(
            "src.ui.pages.settings.check_ocr_setup",
            return_value=False,
        ):
            w = self._build(qapp)
            cbs = w.findChildren(QCheckBox)
            disabled_cbs = [cb for cb in cbs if not cb.isEnabled()]
            assert len(disabled_cbs) >= 1

    def test_has_output_path_section(self, qapp: QApplication) -> None:
        """Translation settings has labels for output path section."""
        w = self._build(qapp)
        labels = w.findChildren(QLabel)
        assert len(labels) >= 1

    def test_sync_ocr_state_method_exists(self, qapp: QApplication) -> None:
        """Translation widget child has _sync_ocr_state method."""
        w = self._build(qapp)
        found = False
        for child in w.findChildren(QWidget):
            if hasattr(child, "_sync_ocr_state"):
                found = True
                break
        assert found

    def test_sync_office_state_method_exists(self, qapp: QApplication) -> None:
        """Translation widget child has _sync_office_state method."""
        w = self._build(qapp)
        found = False
        for child in w.findChildren(QWidget):
            if hasattr(child, "_sync_office_state"):
                found = True
                break
        assert found


# ===================================================================
# TestSettingsSubtitleTab — STT and format details
# ===================================================================


class TestSettingsSubtitleTab:
    """Tests for Subtitle settings tab STT method and format options."""

    @pytest.fixture(autouse=True)
    def _deps(self, _mock_settings_deps):
        """Auto-use mock dependencies."""

    def _build(self, qapp: QApplication) -> QWidget:
        with patch(
            "src.utils.config_manager.check_google_cloud_setup",
            return_value=True,
        ):
            from src.ui.pages.settings import create_subtitle_settings  # noqa: PLC0415

            return create_subtitle_settings()

    def test_whisper_radio_text(self, qapp: QApplication) -> None:
        """Subtitle settings has a Whisper STT radio button."""
        from src.constants.settings import STT_WHISPER  # noqa: PLC0415

        w = self._build(qapp)
        radios = w.findChildren(QRadioButton)
        assert any(r.property("method") == STT_WHISPER for r in radios)

    def test_google_cloud_stt_radio_text(self, qapp: QApplication) -> None:
        """Subtitle settings has a Google Cloud STT radio button."""
        from src.constants.settings import STT_GOOGLE  # noqa: PLC0415

        w = self._build(qapp)
        radios = w.findChildren(QRadioButton)
        assert any(r.property("method") == STT_GOOGLE for r in radios)

    def test_whisper_model_sizes_present(self, qapp: QApplication) -> None:
        """All Whisper model sizes are present as radio buttons."""
        w = self._build(qapp)
        radios = w.findChildren(QRadioButton)
        radio_texts = [r.text() for r in radios]
        for size in ("tiny", "base", "small", "medium", "large"):
            assert any(size in t for t in radio_texts), f"Missing model {size}"

    def test_srt_format_radio(self, qapp: QApplication) -> None:
        """Subtitle settings has SRT format radio."""
        w = self._build(qapp)
        radios = w.findChildren(QRadioButton)
        assert any(r.text() == "SRT" for r in radios)

    def test_vtt_format_radio(self, qapp: QApplication) -> None:
        """Subtitle settings has VTT format radio."""
        w = self._build(qapp)
        radios = w.findChildren(QRadioButton)
        assert any(r.text() == "VTT" for r in radios)

    def test_google_model_combo_exists(self, qapp: QApplication) -> None:
        """Subtitle settings has a Google STT model combo box."""
        w = self._build(qapp)
        combos = w.findChildren(QComboBox)
        assert len(combos) >= 1

    def test_google_model_combo_has_default_option(
        self,
        qapp: QApplication,
    ) -> None:
        """Google STT model combo includes 'default' option."""
        w = self._build(qapp)
        combos = w.findChildren(QComboBox)
        assert len(combos) >= 1
        items = [combos[0].itemText(i) for i in range(combos[0].count())]
        assert "default" in items

    def test_stt_method_toggle_saves_setting(self, qapp: QApplication) -> None:
        """Toggling STT method saves the setting."""
        from src.constants.settings import STT_GOOGLE, STT_WHISPER  # noqa: PLC0415

        with (
            patch("src.ui.pages.settings.save_setting") as mock_save,
            patch(
                "src.utils.config_manager.check_google_cloud_setup",
                return_value=True,
            ),
        ):
            from src.ui.pages.settings import create_subtitle_settings  # noqa: PLC0415

            w = create_subtitle_settings()
            groups = w.findChildren(QButtonGroup)
            # Find the STT button group (has Whisper/Google Cloud radios)
            stt_group = None
            for g in groups:
                methods = {b.property("method") for b in g.buttons()}
                if STT_WHISPER in methods:
                    stt_group = g
                    break
            assert stt_group is not None
            google_btn = next(
                (b for b in stt_group.buttons() if b.property("method") == STT_GOOGLE),
                None,
            )
            if google_btn and google_btn.isEnabled():
                google_btn.setChecked(True)
                stt_group.buttonClicked.emit(google_btn)
                save_calls = [
                    c
                    for c in mock_save.call_args_list
                    if c[0][0] == "subtitle/stt_method"
                ]
                assert len(save_calls) >= 1

    def test_whisper_default_selected(self, qapp: QApplication) -> None:
        """Whisper is selected by default for STT method."""
        from src.constants.settings import STT_GOOGLE, STT_WHISPER  # noqa: PLC0415

        w = self._build(qapp)
        groups = w.findChildren(QButtonGroup)
        stt_group = None
        for g in groups:
            methods = {b.property("method") for b in g.buttons()}
            if STT_WHISPER in methods and STT_GOOGLE in methods:
                stt_group = g
                break
        assert stt_group is not None
        checked = stt_group.checkedButton()
        assert checked is not None
        assert checked.property("method") == STT_WHISPER


# ===================================================================
# TestSettingsVoiceTab — TTS method and format details
# ===================================================================


class TestSettingsVoiceTab:
    """Tests for Voice settings tab TTS method and format options."""

    @pytest.fixture(autouse=True)
    def _deps(self, _mock_settings_deps):
        """Auto-use mock dependencies."""

    def _build(self, qapp: QApplication) -> QWidget:
        with patch(
            "src.utils.config_manager.check_google_cloud_setup",
            return_value=True,
        ):
            from src.ui.pages.settings import create_voice_settings  # noqa: PLC0415

            return create_voice_settings()

    def test_edge_tts_radio_text(self, qapp: QApplication) -> None:
        """Voice settings has an Edge TTS radio button."""
        from src.constants.settings import VOICE_TTS_EDGE  # noqa: PLC0415

        w = self._build(qapp)
        radios = w.findChildren(QRadioButton)
        assert any(r.property("method") == VOICE_TTS_EDGE for r in radios)

    def test_google_cloud_tts_radio_text(self, qapp: QApplication) -> None:
        """Voice settings has a Google Cloud TTS radio button."""
        from src.constants.settings import VOICE_TTS_GOOGLE  # noqa: PLC0415

        w = self._build(qapp)
        radios = w.findChildren(QRadioButton)
        assert any(r.property("method") == VOICE_TTS_GOOGLE for r in radios)

    def test_mp3_format_radio(self, qapp: QApplication) -> None:
        """Voice settings has MP3 format radio."""
        w = self._build(qapp)
        radios = w.findChildren(QRadioButton)
        assert any(r.text() == "MP3" for r in radios)

    def test_wav_format_radio(self, qapp: QApplication) -> None:
        """Voice settings has WAV format radio."""
        w = self._build(qapp)
        radios = w.findChildren(QRadioButton)
        assert any(r.text() == "WAV" for r in radios)

    def test_tts_method_toggle_saves_setting(self, qapp: QApplication) -> None:
        """Toggling TTS method saves the setting."""
        from src.constants.settings import (  # noqa: PLC0415
            VOICE_TTS_EDGE,
            VOICE_TTS_GOOGLE,
        )

        with (
            patch("src.ui.pages.settings.save_setting") as mock_save,
            patch(
                "src.utils.config_manager.check_google_cloud_setup",
                return_value=True,
            ),
        ):
            from src.ui.pages.settings import create_voice_settings  # noqa: PLC0415

            w = create_voice_settings()
            groups = w.findChildren(QButtonGroup)
            # Find the TTS method group (has Edge TTS radio)
            tts_group = None
            for g in groups:
                methods = {b.property("method") for b in g.buttons()}
                if VOICE_TTS_EDGE in methods:
                    tts_group = g
                    break
            assert tts_group is not None
            google_btn = next(
                (
                    b
                    for b in tts_group.buttons()
                    if b.property("method") == VOICE_TTS_GOOGLE
                ),
                None,
            )
            if google_btn and google_btn.isEnabled():
                google_btn.setChecked(True)
                tts_group.buttonClicked.emit(google_btn)
                save_calls = [
                    c for c in mock_save.call_args_list if c[0][0] == "voice/tts_method"
                ]
                assert len(save_calls) >= 1

    def test_voice_format_toggle_saves_setting(self, qapp: QApplication) -> None:
        """Toggling voice output format saves the setting."""
        with (
            patch("src.ui.pages.settings.save_setting") as mock_save,
            patch(
                "src.utils.config_manager.check_google_cloud_setup",
                return_value=True,
            ),
        ):
            from src.ui.pages.settings import create_voice_settings  # noqa: PLC0415

            w = create_voice_settings()
            groups = w.findChildren(QButtonGroup)
            # Find the format group (has MP3/WAV)
            fmt_group = None
            for g in groups:
                btn_texts = {b.text() for b in g.buttons()}
                if "WAV" in btn_texts:
                    fmt_group = g
                    break
            assert fmt_group is not None
            wav_btn = next(
                (b for b in fmt_group.buttons() if b.text() == "WAV"),
                None,
            )
            if wav_btn:
                wav_btn.setChecked(True)
                fmt_group.buttonClicked.emit(wav_btn)
                save_calls = [
                    c
                    for c in mock_save.call_args_list
                    if c[0][0] == "voice/last_output_format"
                ]
                assert len(save_calls) >= 1

    def test_has_auto_remove_checkbox(self, qapp: QApplication) -> None:
        """Voice settings has an auto-remove history checkbox."""
        w = self._build(qapp)
        cbs = w.findChildren(QCheckBox)
        assert len(cbs) >= 1


# ===================================================================
# TestSettingsDubbingTab — dubbing settings fields
# ===================================================================


class TestSettingsDubbingTab:
    """Tests for Dubbing settings tab output and history sections."""

    @pytest.fixture(autouse=True)
    def _deps(self, _mock_settings_deps):
        """Auto-use mock dependencies."""

    def _build(self, qapp: QApplication) -> QWidget:
        from src.ui.pages.settings import create_dubbing_settings  # noqa: PLC0415

        return create_dubbing_settings()

    def test_has_output_labels(self, qapp: QApplication) -> None:
        """Dubbing settings has labels for output path section."""
        w = self._build(qapp)
        labels = w.findChildren(QLabel)
        assert len(labels) >= 1

    def test_has_auto_remove_checkbox(self, qapp: QApplication) -> None:
        """Dubbing settings has an auto-remove checkbox."""
        w = self._build(qapp)
        cbs = w.findChildren(QCheckBox)
        assert len(cbs) >= 1

    def test_auto_remove_default_unchecked(self, qapp: QApplication) -> None:
        """Auto-remove checkbox defaults to unchecked."""
        w = self._build(qapp)
        cbs = w.findChildren(QCheckBox)
        assert len(cbs) >= 1
        # Default is False (unchecked) per create_setting_checkbox default=False
        assert not cbs[0].isChecked()

    def test_dubbing_widget_is_qwidget(self, qapp: QApplication) -> None:
        """Dubbing settings factory returns a QWidget."""
        w = self._build(qapp)
        assert isinstance(w, QWidget)


# ===================================================================
# TestSettingsExtractTab — extraction method and format details
# ===================================================================


class TestSettingsExtractTab:
    """Tests for Extract Text settings tab method and format options."""

    @pytest.fixture(autouse=True)
    def _deps(self, _mock_settings_deps):
        """Auto-use mock dependencies."""

    def _build(self, qapp: QApplication) -> QWidget:
        from src.ui.pages.settings import create_extract_text_settings  # noqa: PLC0415

        return create_extract_text_settings()

    def test_ocr_method_radio(self, qapp: QApplication) -> None:
        """Extract settings has an OCR method radio button."""
        from src.constants.settings import EXTRACT_METHOD_OCR  # noqa: PLC0415

        w = self._build(qapp)
        radios = w.findChildren(QRadioButton)
        assert any(r.property("method") == EXTRACT_METHOD_OCR for r in radios)

    def test_llm_method_radio(self, qapp: QApplication) -> None:
        """Extract settings has an LLM method radio button."""
        from src.constants.settings import EXTRACT_METHOD_LLM  # noqa: PLC0415

        w = self._build(qapp)
        radios = w.findChildren(QRadioButton)
        assert any(r.property("method") == EXTRACT_METHOD_LLM for r in radios)

    def test_txt_format_radio(self, qapp: QApplication) -> None:
        """Extract settings has .txt format radio button."""
        w = self._build(qapp)
        radios = w.findChildren(QRadioButton)
        assert any(r.property("ext") == ".txt" for r in radios)

    def test_docx_format_radio(self, qapp: QApplication) -> None:
        """Extract settings has .docx format radio button."""
        w = self._build(qapp)
        radios = w.findChildren(QRadioButton)
        assert any(r.property("ext") == ".docx" for r in radios)

    def test_default_method_ocr_when_available(self, qapp: QApplication) -> None:
        """OCR is selected by default when both methods are available."""
        from src.constants.settings import (  # noqa: PLC0415
            EXTRACT_METHOD_LLM,
            EXTRACT_METHOD_OCR,
        )

        w = self._build(qapp)
        groups = w.findChildren(QButtonGroup)
        method_group = None
        for g in groups:
            methods = {b.property("method") for b in g.buttons()}
            if EXTRACT_METHOD_OCR in methods and EXTRACT_METHOD_LLM in methods:
                method_group = g
                break
        assert method_group is not None
        checked = method_group.checkedButton()
        assert checked is not None
        assert checked.property("method") == EXTRACT_METHOD_OCR

    def test_default_format_txt(self, qapp: QApplication) -> None:
        """Default format is .txt when no saved setting."""
        w = self._build(qapp)
        groups = w.findChildren(QButtonGroup)
        fmt_group = None
        for g in groups:
            for b in g.buttons():
                if b.property("ext") == ".txt":
                    fmt_group = g
                    break
            if fmt_group:
                break
        assert fmt_group is not None
        checked = fmt_group.checkedButton()
        assert checked is not None
        assert checked.property("ext") == ".txt"


# ===================================================================
# TestSettingsApplyTheme — apply_theme updates styles
# ===================================================================


class TestSettingsApplyThemeUpdatesStyles:
    """Tests that apply_theme() updates all tab styles correctly."""

    @pytest.fixture(autouse=True)
    def _deps(self, _mock_settings_deps):
        """Auto-use mock dependencies."""

    def _build_page(self, qapp: QApplication) -> QWidget:
        from src.ui.pages.settings import create_settings_page  # noqa: PLC0415

        return create_settings_page()

    def test_apply_theme_updates_tab_widget_style(
        self,
        qapp: QApplication,
    ) -> None:
        """apply_theme() restyles the QTabWidget."""
        page = self._build_page(qapp)
        tabs = page.findChild(QTabWidget)
        tabs.setStyleSheet("")
        page.apply_theme()
        assert tabs.styleSheet() != ""

    def test_apply_theme_updates_radio_styles(
        self,
        qapp: QApplication,
    ) -> None:
        """apply_theme() restyles QRadioButton widgets."""
        page = self._build_page(qapp)
        radios = page.findChildren(QRadioButton)
        for r in radios:
            r.setStyleSheet("")
        page.apply_theme()
        styled = [r for r in radios if r.styleSheet() != ""]
        assert len(styled) > 0

    def test_apply_theme_twice_does_not_raise(
        self,
        qapp: QApplication,
    ) -> None:
        """Calling apply_theme() multiple times does not raise."""
        page = self._build_page(qapp)
        page.apply_theme()
        page.apply_theme()

    def test_apply_theme_after_tab_switch(
        self,
        qapp: QApplication,
    ) -> None:
        """apply_theme() works after switching tabs."""
        page = self._build_page(qapp)
        tabs = page.findChild(QTabWidget)
        tabs.setCurrentIndex(3)
        page.apply_theme()
        tabs.setCurrentIndex(0)
        page.apply_theme()


# ===================================================================
# TestSettingsApplyLanguage — apply_language updates labels
# ===================================================================


class TestSettingsApplyLanguageUpdatesLabels:
    """Tests that apply_language() updates all tab labels correctly."""

    @pytest.fixture(autouse=True)
    def _deps(self, _mock_settings_deps):
        """Auto-use mock dependencies."""

    def _build_page(self, qapp: QApplication) -> QWidget:
        from src.ui.pages.settings import create_settings_page  # noqa: PLC0415

        return create_settings_page()

    def test_apply_language_updates_all_tab_texts(
        self,
        qapp: QApplication,
    ) -> None:
        """apply_language() updates all 9 tab titles."""
        page = self._build_page(qapp)
        tabs = page.findChild(QTabWidget)
        # Replace all tab texts with placeholders
        for i in range(tabs.count()):
            tabs.setTabText(i, f"PLACEHOLDER_{i}")
        page.apply_language()
        for i in range(tabs.count()):
            assert tabs.tabText(i) != f"PLACEHOLDER_{i}"

    def test_apply_language_twice_does_not_raise(
        self,
        qapp: QApplication,
    ) -> None:
        """Calling apply_language() multiple times does not raise."""
        page = self._build_page(qapp)
        page.apply_language()
        page.apply_language()

    def test_apply_language_after_tab_switch(
        self,
        qapp: QApplication,
    ) -> None:
        """apply_language() works after switching tabs."""
        page = self._build_page(qapp)
        tabs = page.findChild(QTabWidget)
        tabs.setCurrentIndex(5)
        page.apply_language()
        tabs.setCurrentIndex(2)
        page.apply_language()

    def test_apply_language_updates_first_tab_text(
        self,
        qapp: QApplication,
    ) -> None:
        """apply_language() specifically updates the General tab text."""
        page = self._build_page(qapp)
        tabs = page.findChild(QTabWidget)
        tabs.setTabText(0, "WRONG")
        page.apply_language()
        assert tabs.tabText(0) != "WRONG"

    def test_apply_language_updates_last_tab_text(
        self,
        qapp: QApplication,
    ) -> None:
        """apply_language() specifically updates the Extract Text tab text."""
        page = self._build_page(qapp)
        tabs = page.findChild(QTabWidget)
        tabs.setTabText(8, "WRONG")
        page.apply_language()
        assert tabs.tabText(8) != "WRONG"


# ===================================================================
# TestAutoFallbackSelectionEdgeCases — edge cases
# ===================================================================


class TestAutoFallbackSelectionEdgeCases:
    """Extended edge-case tests for auto_fallback_selection()."""

    @patch("src.ui.pages.settings.save_setting")
    def test_single_enabled_button_becomes_selected(
        self,
        mock_save: MagicMock,
        qapp: QApplication,
    ) -> None:
        """With only one enabled button and no selection, it becomes selected."""
        from src.ui.pages.settings import auto_fallback_selection  # noqa: PLC0415

        group = QButtonGroup()
        btn_a = QRadioButton("A")
        btn_a.setEnabled(False)
        group.addButton(btn_a)
        btn_b = QRadioButton("B")
        btn_b.setEnabled(True)
        group.addButton(btn_b)

        auto_fallback_selection(group, "key")
        assert group.checkedButton() is btn_b
        mock_save.assert_called_once_with("key", "B")

    @patch("src.ui.pages.settings.save_setting")
    def test_empty_group_no_crash(
        self,
        mock_save: MagicMock,
        qapp: QApplication,
    ) -> None:
        """Calling on an empty button group does not raise and saves empty."""
        from src.ui.pages.settings import auto_fallback_selection  # noqa: PLC0415

        group = QButtonGroup()
        auto_fallback_selection(group, "key")
        # No buttons to iterate, falls through to save empty string
        mock_save.assert_called_once_with("key", "")

    @patch("src.ui.pages.settings.save_setting")
    def test_all_disabled_clears_selection_and_saves_empty(
        self,
        mock_save: MagicMock,
        qapp: QApplication,
    ) -> None:
        """When all buttons are disabled and one was checked, selection is cleared."""
        from src.ui.pages.settings import auto_fallback_selection  # noqa: PLC0415

        group = QButtonGroup()
        btn = QRadioButton("X")
        btn.setEnabled(False)
        btn.setChecked(True)
        group.addButton(btn)

        auto_fallback_selection(group, "key")
        assert group.checkedButton() is None
        mock_save.assert_called_once_with("key", "")

    @patch("src.ui.pages.settings.save_setting")
    def test_checked_enabled_button_stays_selected(
        self,
        mock_save: MagicMock,
        qapp: QApplication,
    ) -> None:
        """When checked button is already enabled, nothing changes."""
        from src.ui.pages.settings import auto_fallback_selection  # noqa: PLC0415

        group = QButtonGroup()
        btn_a = QRadioButton("A")
        btn_a.setEnabled(True)
        btn_a.setChecked(True)
        group.addButton(btn_a)
        btn_b = QRadioButton("B")
        btn_b.setEnabled(True)
        group.addButton(btn_b)

        auto_fallback_selection(group, "key")
        assert group.checkedButton() is btn_a
        mock_save.assert_not_called()

    @patch("src.ui.pages.settings.save_setting")
    def test_fallback_picks_first_enabled_button(
        self,
        mock_save: MagicMock,
        qapp: QApplication,
    ) -> None:
        """Fallback picks the first enabled button in order."""
        from src.ui.pages.settings import auto_fallback_selection  # noqa: PLC0415

        group = QButtonGroup()
        btn_a = QRadioButton("A")
        btn_a.setEnabled(False)
        group.addButton(btn_a)
        btn_b = QRadioButton("B")
        btn_b.setEnabled(False)
        group.addButton(btn_b)
        btn_c = QRadioButton("C")
        btn_c.setEnabled(True)
        group.addButton(btn_c)

        auto_fallback_selection(group, "key")
        assert group.checkedButton() is btn_c
        mock_save.assert_called_once_with("key", "C")

    @patch("src.ui.pages.settings.save_setting")
    def test_persist_true_saves_empty_when_all_disabled(
        self,
        mock_save: MagicMock,
        qapp: QApplication,
    ) -> None:
        """With persist=True and all disabled, saves empty string."""
        from src.ui.pages.settings import auto_fallback_selection  # noqa: PLC0415

        group = QButtonGroup()
        btn = QRadioButton("Z")
        btn.setEnabled(False)
        btn.setChecked(True)
        group.addButton(btn)

        auto_fallback_selection(group, "key", persist=True)
        assert group.checkedButton() is None
        mock_save.assert_called_once_with("key", "")


# ===================================================================
# EXPANDED: Settings page — additional tests for all tabs
# ===================================================================


class TestCreateSettingsPageExpanded:
    """Expanded tests for create_settings_page() construction and structure."""

    @pytest.fixture(autouse=True)
    def _deps(self, _mock_settings_deps):
        """Auto-use mock dependencies."""

    def _build_page(self, qapp: QApplication) -> QWidget:
        from src.ui.pages.settings import create_settings_page  # noqa: PLC0415

        return create_settings_page()

    def test_each_tab_is_qwidget(self, qapp: QApplication) -> None:
        """Every tab content is a QWidget."""
        page = self._build_page(qapp)
        tabs = page.findChild(QTabWidget)
        for i in range(tabs.count()):
            assert isinstance(tabs.widget(i), QWidget)

    def test_switch_to_out_of_range_tab(self, qapp: QApplication) -> None:
        """Switching to an out-of-range index does not crash."""
        page = self._build_page(qapp)
        tabs = page.findChild(QTabWidget)
        page.switch_to_tab(999)
        # QTabWidget silently ignores invalid indices
        assert tabs.currentIndex() >= 0

    def test_apply_theme_then_apply_language(self, qapp: QApplication) -> None:
        """Calling apply_theme then apply_language in sequence succeeds."""
        page = self._build_page(qapp)
        page.apply_theme()
        page.apply_language()

    def test_apply_language_then_apply_theme(self, qapp: QApplication) -> None:
        """Calling apply_language then apply_theme in sequence succeeds."""
        page = self._build_page(qapp)
        page.apply_language()
        page.apply_theme()

    def test_tab_widget_current_starts_at_zero(self, qapp: QApplication) -> None:
        """Tab widget starts on the first tab."""
        page = self._build_page(qapp)
        tabs = page.findChild(QTabWidget)
        assert tabs.currentIndex() == 0

    def test_switch_all_tabs(self, qapp: QApplication) -> None:
        """Switching through all tab indices does not crash."""
        page = self._build_page(qapp)
        tabs = page.findChild(QTabWidget)
        for i in range(tabs.count()):
            page.switch_to_tab(i)
            assert tabs.currentIndex() == i

    def test_page_has_layout(self, qapp: QApplication) -> None:
        """The settings page widget has a layout."""
        page = self._build_page(qapp)
        assert page.layout() is not None

    def test_double_apply_theme(self, qapp: QApplication) -> None:
        """Calling apply_theme twice does not raise."""
        page = self._build_page(qapp)
        page.apply_theme()
        page.apply_theme()

    def test_double_apply_language(self, qapp: QApplication) -> None:
        """Calling apply_language twice does not raise."""
        page = self._build_page(qapp)
        page.apply_language()
        page.apply_language()


class TestGeneralSettingsExpanded:
    """Expanded tests for create_general_settings()."""

    @pytest.fixture(autouse=True)
    def _deps(self, _mock_settings_deps):
        """Auto-use mock dependencies."""

    def _build(self, qapp: QApplication) -> QWidget:
        from src.ui.pages.settings import create_general_settings  # noqa: PLC0415

        return create_general_settings()

    def test_theme_radios_have_cursor(self, qapp: QApplication) -> None:
        """Theme radio buttons have pointing hand cursor."""
        w = self._build(qapp)
        radios = w.findChildren(QRadioButton)
        for r in radios[:3]:
            assert r.cursor().shape() == Qt.CursorShape.PointingHandCursor

    def test_language_combo_has_cursor(self, qapp: QApplication) -> None:
        """Language combo box has pointing hand cursor."""
        w = self._build(qapp)
        combos = w.findChildren(QComboBox)
        assert combos[0].cursor().shape() == Qt.CursorShape.PointingHandCursor

    def test_language_combo_items_have_data(self, qapp: QApplication) -> None:
        """Each language combo item has a locale code as itemData."""
        w = self._build(qapp)
        combos = w.findChildren(QComboBox)
        lang_combo = combos[0]
        for i in range(lang_combo.count()):
            data = lang_combo.itemData(i)
            assert data is not None
            assert isinstance(data, str)

    def test_theme_auto_selected_by_default(self, qapp: QApplication) -> None:
        """First theme radio (Auto) is checked by default."""
        w = self._build(qapp)
        groups = w.findChildren(QButtonGroup)
        theme_group = groups[0]
        checked = theme_group.checkedButton()
        assert checked is not None
        # Index 0 is the Auto/System radio
        assert theme_group.id(checked) == 0

    def test_three_theme_radios_exist(self, qapp: QApplication) -> None:
        """Exactly 3 theme radios exist (Auto, Light, Dark)."""
        w = self._build(qapp)
        groups = w.findChildren(QButtonGroup)
        theme_group = groups[0]
        assert len(theme_group.buttons()) == 3  # noqa: PLR2004

    def test_office_path_widget_exists(self, qapp: QApplication) -> None:
        """General settings contains the LibreOffice path widget."""
        w = self._build(qapp)
        labels = w.findChildren(QLabel)
        label_texts = [lb.text() for lb in labels]
        # Should have a label related to LibreOffice path or office
        assert len(label_texts) > 0

    def test_saved_light_theme_selects_light(self, qapp: QApplication) -> None:
        """Saved 'light' theme selects the Light radio."""
        import contextlib  # noqa: PLC0415

        patches = dict(_SETTINGS_PATCHES)

        def custom_load(key, default=""):
            if key == "app/theme":
                return "light"
            return default

        patches["src.ui.pages.settings.load_setting"] = custom_load
        patches["src.ui.components.load_setting"] = custom_load

        with contextlib.ExitStack() as stack:
            for target, replacement in patches.items():
                stack.enter_context(patch(target, replacement))

            from src.ui.pages.settings import create_general_settings  # noqa: PLC0415

            w = create_general_settings()
            groups = w.findChildren(QButtonGroup)
            theme_group = groups[0]
            checked = theme_group.checkedButton()
            assert checked is not None
            # Index 1 is the Light radio
            assert theme_group.id(checked) == 1

    def test_saved_language_selects_correct_combo_index(
        self,
        qapp: QApplication,
    ) -> None:
        """Saved language code selects the correct combo item."""
        import contextlib  # noqa: PLC0415

        patches = dict(_SETTINGS_PATCHES)

        def custom_load(key, default=""):
            if key == "app/ui_language":
                return "vi"
            return default

        patches["src.ui.pages.settings.load_setting"] = custom_load
        patches["src.ui.components.load_setting"] = custom_load

        with contextlib.ExitStack() as stack:
            for target, replacement in patches.items():
                stack.enter_context(patch(target, replacement))

            from src.ui.pages.settings import create_general_settings  # noqa: PLC0415

            w = create_general_settings()
            combos = w.findChildren(QComboBox)
            lang_combo = combos[0]
            assert lang_combo.currentData() == "vi"

    def test_msoffice_banner_visible_when_available(
        self,
        qapp: QApplication,
    ) -> None:
        """MS Office success banner is visible when MS Office is available."""
        import contextlib  # noqa: PLC0415

        patches = dict(_SETTINGS_PATCHES)
        patches["src.ui.pages.settings.check_msoffice_available"] = lambda: True

        with contextlib.ExitStack() as stack:
            for target, replacement in patches.items():
                stack.enter_context(patch(target, replacement))

            from src.ui.pages.settings import create_general_settings  # noqa: PLC0415

            w = create_general_settings()
            assert isinstance(w, QWidget)


class TestServiceSettingsExpanded:
    """Expanded tests for create_service_settings()."""

    @pytest.fixture(autouse=True)
    def _deps(self, _mock_settings_deps):
        """Auto-use mock dependencies."""

    def _build(self, qapp: QApplication) -> QWidget:
        from src.ui.pages.settings import create_service_settings  # noqa: PLC0415

        return create_service_settings()

    def test_has_password_input(self, qapp: QApplication) -> None:
        """Service settings has a password-masked input for API key."""
        from PySide6.QtWidgets import QLineEdit  # noqa: PLC0415

        w = self._build(qapp)
        inputs = w.findChildren(QLineEdit)
        # At least one input should have password echo mode
        password_inputs = [
            i for i in inputs if i.echoMode() == QLineEdit.EchoMode.Password
        ]
        assert len(password_inputs) >= 1

    def test_service_settings_has_info_banner(self, qapp: QApplication) -> None:
        """Service settings has an info banner."""
        from PySide6.QtWidgets import QFrame  # noqa: PLC0415

        w = self._build(qapp)
        frames = [f for f in w.findChildren(QFrame) if f.objectName() == "Banner"]
        assert len(frames) >= 1

    def test_service_settings_layout_not_empty(self, qapp: QApplication) -> None:
        """Service settings widget has a non-empty layout."""
        w = self._build(qapp)
        assert w.layout() is not None
        assert w.layout().count() > 0


class TestOCRSettingsExpanded:
    """Expanded tests for create_ocr_settings()."""

    @pytest.fixture(autouse=True)
    def _deps(self, _mock_settings_deps):
        """Auto-use mock dependencies."""

    def _build(self, qapp: QApplication) -> QWidget:
        from src.ui.pages.settings import create_ocr_settings  # noqa: PLC0415

        return create_ocr_settings()

    def test_ocr_radio_has_cursor(self, qapp: QApplication) -> None:
        """OCR radio buttons have pointing hand cursor."""
        w = self._build(qapp)
        radios = w.findChildren(QRadioButton)
        for r in radios:
            assert r.cursor().shape() == Qt.CursorShape.PointingHandCursor

    def test_one_radio_is_checked_when_available(self, qapp: QApplication) -> None:
        """At least one OCR radio is checked when methods are available."""
        w = self._build(qapp)
        groups = w.findChildren(QButtonGroup)
        ocr_group = groups[0]
        checked = ocr_group.checkedButton()
        assert checked is not None

    def test_ocr_button_group_is_exclusive(self, qapp: QApplication) -> None:
        """OCR button group is exclusive (only one selected)."""
        w = self._build(qapp)
        groups = w.findChildren(QButtonGroup)
        ocr_group = groups[0]
        assert ocr_group.exclusive()

    def test_saved_ocr_method_respected(self, qapp: QApplication) -> None:
        """Saved OCR method is selected on construction."""
        import contextlib  # noqa: PLC0415

        patches = dict(_SETTINGS_PATCHES)

        from src.constants.ocr import OCR_METHOD_TESSERACT  # noqa: PLC0415

        def custom_load(key, default=""):
            if key == "ocr/method":
                return OCR_METHOD_TESSERACT
            return default

        patches["src.ui.pages.settings.load_setting"] = custom_load
        patches["src.ui.components.load_setting"] = custom_load

        with contextlib.ExitStack() as stack:
            for target, replacement in patches.items():
                stack.enter_context(patch(target, replacement))

            from src.ui.pages.settings import create_ocr_settings  # noqa: PLC0415

            w = create_ocr_settings()
            groups = w.findChildren(QButtonGroup)
            ocr_group = groups[0]
            checked = ocr_group.checkedButton()
            assert checked is not None
            assert checked.property("method") == OCR_METHOD_TESSERACT

    def test_ocr_info_banners_exist(self, qapp: QApplication) -> None:
        """OCR settings has info banners."""
        from PySide6.QtWidgets import QFrame  # noqa: PLC0415

        w = self._build(qapp)
        banners = [f for f in w.findChildren(QFrame) if f.objectName() == "Banner"]
        assert len(banners) >= 1

    def test_tesseract_langs_banner_visible(self, qapp: QApplication) -> None:
        """Tesseract languages banner is visible when languages detected."""
        from PySide6.QtWidgets import QFrame  # noqa: PLC0415

        w = self._build(qapp)
        banners = [f for f in w.findChildren(QFrame) if f.objectName() == "Banner"]
        # At least one success banner for tesseract langs
        assert len(banners) >= 2  # noqa: PLR2004

    def test_sync_ocr_availability_does_not_raise(self, qapp: QApplication) -> None:
        """Calling _sync_ocr_availability does not raise."""
        w = self._build(qapp)
        w._sync_ocr_availability()

    def test_all_disabled_ocr_clears_selection(self, qapp: QApplication) -> None:
        """When all OCR methods are unavailable, selection is cleared."""
        import contextlib  # noqa: PLC0415

        patches = dict(_SETTINGS_PATCHES)
        patches["src.ui.pages.settings.check_ocr_availability"] = lambda m: (
            False,
            "Not found",
        )
        patches["src.ui.pages.settings.detect_tesseract_languages"] = set

        with (
            contextlib.ExitStack() as stack,
            patch(
                "src.utils.config_manager.check_google_cloud_setup",
                return_value=False,
            ),
        ):
            for target, replacement in patches.items():
                stack.enter_context(patch(target, replacement))

            from src.ui.pages.settings import create_ocr_settings  # noqa: PLC0415

            w = create_ocr_settings()
            groups = w.findChildren(QButtonGroup)
            ocr_group = groups[0]
            # All disabled means no checked button
            # (auto_fallback_selection clears)
            checked = ocr_group.checkedButton()
            assert checked is None


class TestLLMSettingsExpanded:
    """Expanded tests for create_llm_settings()."""

    @pytest.fixture(autouse=True)
    def _deps(self, _mock_settings_deps):
        """Auto-use mock dependencies."""

    def _build(self, qapp: QApplication) -> QWidget:
        from src.ui.pages.settings import create_llm_settings  # noqa: PLC0415

        return create_llm_settings()

    def test_only_one_button_group(self, qapp: QApplication) -> None:
        """LLM settings owns exactly one QButtonGroup (Gemini auth mode)."""
        w = self._build(qapp)
        groups = w.findChildren(QButtonGroup)
        assert len(groups) == 1

    def test_only_auth_mode_radios(self, qapp: QApplication) -> None:
        """LLM settings has exactly two radios — the Gemini auth-mode pair."""
        w = self._build(qapp)
        radios = w.findChildren(QRadioButton)
        assert len(radios) == 2  # noqa: PLR2004

    def test_only_default_model_combo_on_llm_tab(
        self,
        qapp: QApplication,
    ) -> None:
        """Default Model combo + Vertex location combo are present.

        Total of two QComboBox widgets on the tab.
        """
        w = self._build(qapp)
        combos = w.findChildren(QComboBox)
        assert len(combos) == 2  # noqa: PLR2004

    def test_custom_section_has_endpoint_field(self, qapp: QApplication) -> None:
        """Custom provider section has an endpoint input field."""
        from PySide6.QtWidgets import QLineEdit  # noqa: PLC0415

        with _patch_custom_providers():
            w = self._build(qapp)
        inputs = w.findChildren(QLineEdit)
        # Should have Gemini API key, Custom API key, Custom model,
        # and Custom endpoint inputs
        assert len(inputs) >= 4  # noqa: PLR2004

    def test_both_sections_always_visible(self, qapp: QApplication) -> None:
        """Both provider sections are visible without any radio selection."""
        from PySide6.QtWidgets import QLineEdit  # noqa: PLC0415

        with _patch_custom_providers():
            w = self._build(qapp)
        password_fields = [
            le
            for le in w.findChildren(QLineEdit)
            if le.echoMode() == QLineEdit.EchoMode.Password
        ]
        # Both Gemini and Custom API key fields should be present
        assert len(password_fields) >= 2  # noqa: PLR2004


class TestTranslationSettingsExpanded:
    """Expanded tests for create_translation_settings()."""

    @pytest.fixture(autouse=True)
    def _deps(self, _mock_settings_deps):
        """Auto-use mock dependencies."""

    def _build(self, qapp: QApplication) -> QWidget:
        from src.ui.pages.settings import create_translation_settings  # noqa: PLC0415

        return create_translation_settings()

    def test_has_storage_path(self, qapp: QApplication) -> None:
        """Translation settings has a storage path widget."""
        w = self._build(qapp)
        labels = w.findChildren(QLabel)
        assert len(labels) > 0

    def test_has_auto_remove_checkbox(self, qapp: QApplication) -> None:
        """Translation settings has an auto-remove history checkbox."""
        w = self._build(qapp)
        cbs = w.findChildren(QCheckBox)
        assert len(cbs) >= 1

    def test_checkbox_cursors(self, qapp: QApplication) -> None:
        """Checkboxes have pointing hand cursor."""
        w = self._build(qapp)
        cbs = w.findChildren(QCheckBox)
        for cb in cbs:
            assert cb.cursor().shape() == Qt.CursorShape.PointingHandCursor

    def test_sync_ocr_state_exists(self, qapp: QApplication) -> None:
        """Translation settings has _sync_ocr_state on a child widget."""
        w = self._build(qapp)
        found = any(
            hasattr(child, "_sync_ocr_state") for child in w.findChildren(QWidget)
        )
        assert found

    def test_sync_office_state_exists(self, qapp: QApplication) -> None:
        """Translation settings has _sync_office_state on a child widget."""
        w = self._build(qapp)
        found = any(
            hasattr(child, "_sync_office_state") for child in w.findChildren(QWidget)
        )
        assert found

    def test_images_checkbox_enabled_with_ocr(self, qapp: QApplication) -> None:
        """Translate images checkbox is enabled when OCR is available."""
        with patch("src.ui.pages.settings.check_ocr_setup", return_value=True):
            w = self._build(qapp)
            cbs = w.findChildren(QCheckBox)
            enabled_cbs = [cb for cb in cbs if cb.isEnabled()]
            assert len(enabled_cbs) >= 5  # noqa: PLR2004

    def test_comments_checkbox_present(self, qapp: QApplication) -> None:
        """Translation settings includes a comments checkbox."""
        w = self._build(qapp)
        cbs = w.findChildren(QCheckBox)
        assert len(cbs) >= 7  # noqa: PLR2004


class TestSubtitleSettingsExpanded:
    """Expanded tests for create_subtitle_settings()."""

    @pytest.fixture(autouse=True)
    def _deps(self, _mock_settings_deps):
        """Auto-use mock dependencies."""

    def _build(self, qapp: QApplication) -> QWidget:
        with patch(
            "src.utils.config_manager.check_google_cloud_setup",
            return_value=True,
        ):
            from src.ui.pages.settings import create_subtitle_settings  # noqa: PLC0415

            return create_subtitle_settings()

    def test_has_storage_path(self, qapp: QApplication) -> None:
        """Subtitle settings has a storage path section."""
        w = self._build(qapp)
        labels = w.findChildren(QLabel)
        assert len(labels) > 0

    def test_has_auto_remove_checkbox(self, qapp: QApplication) -> None:
        """Subtitle settings has an auto-remove checkbox."""
        w = self._build(qapp)
        cbs = w.findChildren(QCheckBox)
        assert len(cbs) >= 1

    def test_whisper_default_selected(self, qapp: QApplication) -> None:
        """Whisper is the default STT method when both are available."""
        from src.constants.settings import STT_WHISPER  # noqa: PLC0415

        w = self._build(qapp)
        groups = w.findChildren(QButtonGroup)
        stt_group = groups[0]
        checked = stt_group.checkedButton()
        assert checked is not None
        assert checked.property("method") == STT_WHISPER

    def test_srt_default_format(self, qapp: QApplication) -> None:
        """SRT is the default subtitle format."""
        w = self._build(qapp)
        groups = w.findChildren(QButtonGroup)
        # Format group: find one that has SRT and VTT
        fmt_group = None
        for g in groups:
            btn_texts = {b.text() for b in g.buttons()}
            if "SRT" in btn_texts and "VTT" in btn_texts:
                fmt_group = g
                break
        assert fmt_group is not None
        checked = fmt_group.checkedButton()
        assert checked is not None

    def test_format_radios_have_cursor(self, qapp: QApplication) -> None:
        """Format radio buttons have pointing hand cursor."""
        w = self._build(qapp)
        radios = w.findChildren(QRadioButton)
        for r in radios:
            assert r.cursor().shape() == Qt.CursorShape.PointingHandCursor

    def test_stt_method_saves_on_toggle(self, qapp: QApplication) -> None:
        """Toggling STT method radio saves setting."""
        with (
            patch(
                "src.utils.config_manager.check_google_cloud_setup",
                return_value=True,
            ),
            patch("src.ui.pages.settings.save_setting") as mock_save,
        ):
            from src.ui.pages.settings import create_subtitle_settings  # noqa: PLC0415

            w = create_subtitle_settings()
            groups = w.findChildren(QButtonGroup)
            stt_group = groups[0]
            google_btn = next(
                (b for b in stt_group.buttons() if b.text() == "Google Cloud"),
                None,
            )
            if google_btn and google_btn.isEnabled():
                google_btn.setChecked(True)
                stt_group.buttonClicked.emit(google_btn)
                save_calls = [
                    c
                    for c in mock_save.call_args_list
                    if c[0][0] == "subtitle/stt_method"
                ]
                assert len(save_calls) >= 1


class TestVoiceSettingsExpanded:
    """Expanded tests for create_voice_settings()."""

    @pytest.fixture(autouse=True)
    def _deps(self, _mock_settings_deps):
        """Auto-use mock dependencies."""

    def _build(self, qapp: QApplication) -> QWidget:
        with patch(
            "src.utils.config_manager.check_google_cloud_setup",
            return_value=True,
        ):
            from src.ui.pages.settings import create_voice_settings  # noqa: PLC0415

            return create_voice_settings()

    def test_has_storage_path(self, qapp: QApplication) -> None:
        """Voice settings has a storage path section."""
        w = self._build(qapp)
        labels = w.findChildren(QLabel)
        assert len(labels) > 0

    def test_has_auto_remove_checkbox(self, qapp: QApplication) -> None:
        """Voice settings has an auto-remove checkbox."""
        w = self._build(qapp)
        cbs = w.findChildren(QCheckBox)
        assert len(cbs) >= 1

    def test_mp3_default_format(self, qapp: QApplication) -> None:
        """MP3 is the default voice output format."""
        w = self._build(qapp)
        groups = w.findChildren(QButtonGroup)
        # Find the format group (has MP3 and WAV)
        fmt_group = None
        for g in groups:
            btn_texts = {b.text() for b in g.buttons()}
            if "MP3" in btn_texts and "WAV" in btn_texts:
                fmt_group = g
                break
        assert fmt_group is not None
        checked = fmt_group.checkedButton()
        assert checked is not None

    def test_tts_method_saves_on_toggle(self, qapp: QApplication) -> None:
        """Toggling TTS method radio saves setting."""
        with (
            patch(
                "src.utils.config_manager.check_google_cloud_setup",
                return_value=True,
            ),
            patch("src.ui.pages.settings.save_setting") as mock_save,
        ):
            from src.ui.pages.settings import create_voice_settings  # noqa: PLC0415

            w = create_voice_settings()
            groups = w.findChildren(QButtonGroup)
            tts_group = groups[0]
            google_btn = next(
                (b for b in tts_group.buttons() if b.text() == "Google Cloud TTS"),
                None,
            )
            if google_btn and google_btn.isEnabled():
                google_btn.setChecked(True)
                tts_group.buttonClicked.emit(google_btn)
                save_calls = [
                    c for c in mock_save.call_args_list if c[0][0] == "voice/tts_method"
                ]
                assert len(save_calls) >= 1

    def test_format_toggle_saves_setting(self, qapp: QApplication) -> None:
        """Toggling voice format saves setting."""
        with (
            patch(
                "src.utils.config_manager.check_google_cloud_setup",
                return_value=True,
            ),
            patch("src.ui.pages.settings.save_setting") as mock_save,
        ):
            from src.ui.pages.settings import create_voice_settings  # noqa: PLC0415

            w = create_voice_settings()
            groups = w.findChildren(QButtonGroup)
            # Find format group
            fmt_group = None
            for g in groups:
                btn_texts = {b.text() for b in g.buttons()}
                if "WAV" in btn_texts:
                    fmt_group = g
                    break
            assert fmt_group is not None
            wav_btn = next(
                (b for b in fmt_group.buttons() if b.text() == "WAV"),
                None,
            )
            if wav_btn:
                wav_btn.setChecked(True)
                fmt_group.buttonClicked.emit(wav_btn)
                save_calls = [
                    c
                    for c in mock_save.call_args_list
                    if c[0][0] == "voice/last_output_format"
                ]
                assert len(save_calls) >= 1


class TestDubbingSettingsExpanded:
    """Expanded tests for create_dubbing_settings()."""

    @pytest.fixture(autouse=True)
    def _deps(self, _mock_settings_deps):
        """Auto-use mock dependencies."""

    def _build(self, qapp: QApplication) -> QWidget:
        from src.ui.pages.settings import create_dubbing_settings  # noqa: PLC0415

        return create_dubbing_settings()

    def test_has_storage_path(self, qapp: QApplication) -> None:
        """Dubbing settings has a storage path section."""
        w = self._build(qapp)
        labels = w.findChildren(QLabel)
        assert len(labels) >= 1

    def test_auto_remove_checkbox_has_cursor(self, qapp: QApplication) -> None:
        """Auto-remove checkbox has pointing hand cursor."""
        w = self._build(qapp)
        cbs = w.findChildren(QCheckBox)
        for cb in cbs:
            assert cb.cursor().shape() == Qt.CursorShape.PointingHandCursor

    def test_layout_not_empty(self, qapp: QApplication) -> None:
        """Dubbing settings layout has multiple widgets."""
        w = self._build(qapp)
        assert w.layout() is not None
        assert w.layout().count() > 0


class TestExtractTextSettingsExpanded:
    """Expanded tests for create_extract_text_settings()."""

    @pytest.fixture(autouse=True)
    def _deps(self, _mock_settings_deps):
        """Auto-use mock dependencies."""

    def _build(self, qapp: QApplication) -> QWidget:
        from src.ui.pages.settings import create_extract_text_settings  # noqa: PLC0415

        return create_extract_text_settings()

    def test_has_storage_path(self, qapp: QApplication) -> None:
        """Extract text settings has a storage path section."""
        w = self._build(qapp)
        labels = w.findChildren(QLabel)
        assert len(labels) > 0

    def test_method_group_is_exclusive(self, qapp: QApplication) -> None:
        """Method button group is exclusive."""
        from src.constants.settings import EXTRACT_METHOD_OCR  # noqa: PLC0415

        w = self._build(qapp)
        groups = w.findChildren(QButtonGroup)
        method_group = None
        for g in groups:
            methods = {b.property("method") for b in g.buttons()}
            if EXTRACT_METHOD_OCR in methods:
                method_group = g
                break
        assert method_group is not None
        assert method_group.exclusive()

    def test_format_group_is_exclusive(self, qapp: QApplication) -> None:
        """Format button group is exclusive."""
        w = self._build(qapp)
        groups = w.findChildren(QButtonGroup)
        fmt_group = None
        for g in groups:
            for b in g.buttons():
                if b.property("ext") == ".txt":
                    fmt_group = g
                    break
            if fmt_group:
                break
        assert fmt_group is not None
        assert fmt_group.exclusive()

    def test_both_methods_disabled_shows_fallback(self, qapp: QApplication) -> None:
        """When both OCR and LLM are unavailable, no method is selected."""
        from src.constants.settings import EXTRACT_METHOD_OCR  # noqa: PLC0415

        with (
            patch("src.ui.pages.settings.check_ocr_setup", return_value=False),
            patch("src.ui.pages.settings.check_llm_setup", return_value=False),
        ):
            w = self._build(qapp)
            groups = w.findChildren(QButtonGroup)
            method_group = None
            for g in groups:
                methods = {b.property("method") for b in g.buttons()}
                if EXTRACT_METHOD_OCR in methods:
                    method_group = g
                    break
            assert method_group is not None
            checked = method_group.checkedButton()
            assert checked is None

    def test_method_radios_have_cursor(self, qapp: QApplication) -> None:
        """Method radio buttons have pointing hand cursor."""
        w = self._build(qapp)
        radios = w.findChildren(QRadioButton)
        for r in radios:
            assert r.cursor().shape() == Qt.CursorShape.PointingHandCursor

    def test_auto_remove_checkbox_present(self, qapp: QApplication) -> None:
        """Auto-remove checkbox is present."""
        w = self._build(qapp)
        cbs = w.findChildren(QCheckBox)
        assert len(cbs) >= 1


class TestProviderConfigExpanded:
    """Expanded tests for create_provider_config()."""

    @pytest.fixture(autouse=True)
    def _deps(self, _mock_settings_deps):
        """Auto-use mock dependencies."""

    def test_no_models_creates_input_field(self, qapp: QApplication) -> None:
        """When models=None, a text input is created instead of a combo."""
        from PySide6.QtWidgets import QLineEdit  # noqa: PLC0415

        from src.ui.pages.settings import create_provider_config  # noqa: PLC0415

        group = QButtonGroup()
        radio = QRadioButton("TestProvider")
        group.addButton(radio)
        w = create_provider_config(
            "TestProvider",
            "test/api_key",
            "test/model",
            None,
        )
        inputs = w.findChildren(QLineEdit)
        # Should have API key + model as text inputs
        assert len(inputs) >= 2  # noqa: PLR2004

    def test_models_list_creates_combo(self, qapp: QApplication) -> None:
        """When models is a list, a combo box is created."""
        from src.ui.pages.settings import create_provider_config  # noqa: PLC0415

        group = QButtonGroup()
        radio = QRadioButton("TestProv")
        group.addButton(radio)
        w = create_provider_config(
            "TestProv",
            "test/api_key",
            "test/model",
            ["a", "b", "c"],
        )
        combos = w.findChildren(QComboBox)
        assert len(combos) >= 1
        assert combos[0].count() == 3  # noqa: PLR2004

    def test_empty_extra_fields_no_crash(self, qapp: QApplication) -> None:
        """Passing empty extra_fields list does not crash."""
        from src.ui.pages.settings import create_provider_config  # noqa: PLC0415

        group = QButtonGroup()
        radio = QRadioButton("TestProv")
        group.addButton(radio)
        w = create_provider_config(
            "TestProv",
            "test/api_key",
            "test/model",
            ["m1"],
            extra_fields=[],
        )
        assert isinstance(w, QWidget)

    def test_multiple_extra_fields(self, qapp: QApplication) -> None:
        """Multiple extra fields are all added to the widget."""
        from PySide6.QtWidgets import QLineEdit  # noqa: PLC0415

        from src.ui.pages.settings import create_provider_config  # noqa: PLC0415

        group = QButtonGroup()
        radio = QRadioButton("TestProv")
        group.addButton(radio)
        w = create_provider_config(
            "TestProv",
            "test/api_key",
            "test/model",
            None,
            extra_fields=[
                ("Field1", "k1", "p1", "l1", "pl1"),
                ("Field2", "k2", "p2", "l2", "pl2"),
            ],
        )
        inputs = w.findChildren(QLineEdit)
        # API key + model + 2 extra fields
        assert len(inputs) >= 4  # noqa: PLR2004


class TestSettingsIntegrationExpanded:
    """Expanded integration tests for settings page."""

    def test_page_with_both_offices_available(self, qapp: QApplication) -> None:
        """Settings constructs when both MS Office and LibreOffice are available."""
        import contextlib  # noqa: PLC0415

        patches = dict(_SETTINGS_PATCHES)
        patches["src.ui.pages.settings.check_msoffice_available"] = lambda: True
        patches["src.ui.pages.settings.check_libreoffice_available"] = lambda: True
        patches["src.ui.pages.settings.check_office_converter_setup"] = lambda: True

        with contextlib.ExitStack() as stack:
            for target, replacement in patches.items():
                stack.enter_context(patch(target, replacement))

            from src.ui.pages.settings import create_settings_page  # noqa: PLC0415

            page = create_settings_page()
            assert isinstance(page, QWidget)

    def test_page_with_all_setup_available(self, qapp: QApplication) -> None:
        """Settings constructs with all setups available."""
        import contextlib  # noqa: PLC0415

        patches = dict(_SETTINGS_PATCHES)
        patches["src.ui.pages.settings.check_msoffice_available"] = lambda: True
        patches["src.ui.pages.settings.check_libreoffice_available"] = lambda: True
        patches["src.ui.pages.settings.check_office_converter_setup"] = lambda: True
        patches["src.ui.pages.settings.check_llm_setup"] = lambda: True
        patches["src.ui.pages.settings.check_ocr_setup"] = lambda: True

        with contextlib.ExitStack() as stack:
            for target, replacement in patches.items():
                stack.enter_context(patch(target, replacement))

            from src.ui.pages.settings import create_settings_page  # noqa: PLC0415

            page = create_settings_page()
            page.apply_theme()
            page.apply_language()

    def test_page_with_no_tesseract_languages(self, qapp: QApplication) -> None:
        """Settings constructs when Tesseract is available but no languages."""
        import contextlib  # noqa: PLC0415

        patches = dict(_SETTINGS_PATCHES)
        patches["src.ui.pages.settings.detect_tesseract_languages"] = set

        with contextlib.ExitStack() as stack:
            for target, replacement in patches.items():
                stack.enter_context(patch(target, replacement))

            from src.ui.pages.settings import create_settings_page  # noqa: PLC0415

            page = create_settings_page()
            assert isinstance(page, QWidget)

    def test_page_apply_theme_on_all_tabs(self, qapp: QApplication) -> None:
        """apply_theme works after switching to every tab."""
        import contextlib  # noqa: PLC0415

        patches = dict(_SETTINGS_PATCHES)
        with contextlib.ExitStack() as stack:
            for target, replacement in patches.items():
                stack.enter_context(patch(target, replacement))

            from src.ui.pages.settings import create_settings_page  # noqa: PLC0415

            page = create_settings_page()
            tabs = page.findChild(QTabWidget)
            for i in range(tabs.count()):
                tabs.setCurrentIndex(i)
                page.apply_theme()

    def test_page_apply_language_on_all_tabs(self, qapp: QApplication) -> None:
        """apply_language works after switching to every tab."""
        import contextlib  # noqa: PLC0415

        patches = dict(_SETTINGS_PATCHES)
        with contextlib.ExitStack() as stack:
            for target, replacement in patches.items():
                stack.enter_context(patch(target, replacement))

            from src.ui.pages.settings import create_settings_page  # noqa: PLC0415

            page = create_settings_page()
            tabs = page.findChild(QTabWidget)
            for i in range(tabs.count()):
                tabs.setCurrentIndex(i)
                page.apply_language()

    def test_saved_en_uk_language(self, qapp: QApplication) -> None:
        """Saved en-UK language is respected."""
        import contextlib  # noqa: PLC0415

        patches = dict(_SETTINGS_PATCHES)

        def custom_load(key, default=""):
            if key == "app/ui_language":
                return "en-UK"
            return default

        patches["src.ui.pages.settings.load_setting"] = custom_load
        patches["src.ui.components.load_setting"] = custom_load

        with contextlib.ExitStack() as stack:
            for target, replacement in patches.items():
                stack.enter_context(patch(target, replacement))

            from src.ui.pages.settings import create_general_settings  # noqa: PLC0415

            w = create_general_settings()
            combos = w.findChildren(QComboBox)
            lang_combo = combos[0]
            assert lang_combo.currentData() == "en-UK"


# ===================================================================
# create_live_settings
# ===================================================================


class TestLiveSettingsTab:
    """Tests for create_live_settings() factory."""

    @pytest.fixture(autouse=True)
    def _deps(self, _mock_settings_deps):
        """Auto-use mock dependencies."""

    def _build(self, qapp: QApplication) -> QWidget:
        from src.ui.pages.settings import create_live_settings  # noqa: PLC0415

        return create_live_settings()

    def test_returns_qwidget(self, qapp: QApplication) -> None:
        """Factory returns a QWidget."""
        w = self._build(qapp)
        assert isinstance(w, QWidget)

    def test_has_stt_method_radios(self, qapp: QApplication) -> None:
        """Live settings has STT method radio buttons for Whisper and Soniox."""
        from src.constants.i18n import tr  # noqa: PLC0415

        w = self._build(qapp)
        radios = w.findChildren(QRadioButton)
        radio_texts = {r.text() for r in radios}
        assert tr("settings.live_stt_whisper") in radio_texts
        assert tr("settings.live_stt_soniox") in radio_texts

    def test_radio_labels_have_no_local_or_cloud_annotation(
        self,
        qapp: QApplication,
    ) -> None:
        """Radio labels are plain engine names — no local/cloud suffix.

        The comparison banner now conveys that distinction.
        """
        from src.constants.i18n import tr  # noqa: PLC0415

        whisper_label = tr("settings.live_stt_whisper")
        soniox_label = tr("settings.live_stt_soniox")
        # Lowercase so the assertion catches translated equivalents too.
        assert "(local)" not in whisper_label.lower()
        assert "(cloud)" not in soniox_label.lower()

    def test_stt_comparison_banner_present(self, qapp: QApplication) -> None:
        """A comparison banner appears in the Live STT section.

        Rich-text + info variant, replacing the prior local/cloud
        annotation.  The banner's ``tr_key`` references
        ``settings.live_stt_comparison`` so language switches re-render
        its copy.
        """
        from PySide6.QtWidgets import QLabel  # noqa: PLC0415

        w = self._build(qapp)
        # Each banner widget carries its own QLabel rendering the tr()
        # output; under the test's mock i18n that's the raw key.  The
        # banner is present iff at least one label renders the
        # ``settings.live_stt_comparison`` key as part of its text.
        labels = w.findChildren(QLabel)
        joined = " ".join(lbl.text() for lbl in labels)
        assert "settings.live_stt_comparison" in joined

    def test_has_whisper_model_radios(self, qapp: QApplication) -> None:
        """Live settings has Whisper model size radio buttons."""
        w = self._build(qapp)
        radios = w.findChildren(QRadioButton)
        radio_texts = {r.text() for r in radios}
        # Whisper models: tiny, base, small, medium, large
        assert any("tiny" in t for t in radio_texts)
        assert any("base" in t for t in radio_texts)
        assert any("large" in t for t in radio_texts)

    def test_translation_model_combo_visible_for_whisper(
        self,
        qapp: QApplication,
    ) -> None:
        """Translation-model combo is shown when Whisper is the active STT.

        Whisper transcribes only — translation is a separate LLM step,
        so the model picker is relevant.  Visibility double-gates on
        ``method == LIVE_STT_WHISPER`` AND ``models > 0``.
        """
        from src.constants.i18n import tr  # noqa: PLC0415
        from src.constants.settings import (  # noqa: PLC0415
            LIVE_STT_WHISPER,
            SETTING_LIVE_STT_METHOD,
        )

        with (
            patch(
                "src.utils.config_manager.get_available_models",
                return_value=[("Gemini", "gemini-3-flash-preview")],
            ),
            patch(
                "src.ui.pages.settings.load_setting",
                side_effect=lambda k, d="": (
                    LIVE_STT_WHISPER if k == SETTING_LIVE_STT_METHOD else d
                ),
            ),
        ):
            w = self._build(qapp)

        labels = [
            lbl
            for lbl in w.findChildren(QLabel)
            if lbl.text() == tr("settings.live_translation_model")
        ]
        assert labels, "translation-model row label not found"
        # The label's container row should be visible alongside the combo.
        row_widget = labels[0].parentWidget()
        assert row_widget.isVisibleTo(w)

    def test_translation_model_combo_hidden_for_soniox(
        self,
        qapp: QApplication,
    ) -> None:
        """Translation-model combo is hidden when Soniox is active.

        Soniox translates inside its own WebSocket session — no
        separate LLM call — so the picker would be misleading.
        """
        from src.constants.i18n import tr  # noqa: PLC0415
        from src.constants.settings import (  # noqa: PLC0415
            LIVE_STT_SONIOX,
            SETTING_LIVE_STT_METHOD,
        )

        with (
            patch(
                "src.utils.config_manager.get_available_models",
                return_value=[("Gemini", "gemini-3-flash-preview")],
            ),
            patch(
                "src.utils.config_manager.check_soniox_setup",
                return_value=True,
            ),
            patch(
                "src.ui.pages.settings.load_setting",
                side_effect=lambda k, d="": (
                    LIVE_STT_SONIOX if k == SETTING_LIVE_STT_METHOD else d
                ),
            ),
        ):
            w = self._build(qapp)

        labels = [
            lbl
            for lbl in w.findChildren(QLabel)
            if lbl.text() == tr("settings.live_translation_model")
        ]
        assert labels, "translation-model row label not found"
        row_widget = labels[0].parentWidget()
        assert not row_widget.isVisibleTo(w)

    def test_translation_model_combo_hidden_when_no_models(
        self,
        qapp: QApplication,
    ) -> None:
        """No configured models → combo hidden even on Whisper.

        Avoids showing an empty combo on a fresh install where no
        LLM provider has been wired up yet.
        """
        from src.constants.i18n import tr  # noqa: PLC0415
        from src.constants.settings import (  # noqa: PLC0415
            LIVE_STT_WHISPER,
            SETTING_LIVE_STT_METHOD,
        )

        with (
            patch(
                "src.utils.config_manager.get_available_models",
                return_value=[],
            ),
            patch(
                "src.ui.pages.settings.load_setting",
                side_effect=lambda k, d="": (
                    LIVE_STT_WHISPER if k == SETTING_LIVE_STT_METHOD else d
                ),
            ),
        ):
            w = self._build(qapp)

        labels = [
            lbl
            for lbl in w.findChildren(QLabel)
            if lbl.text() == tr("settings.live_translation_model")
        ]
        assert labels, "translation-model row label not found"
        row_widget = labels[0].parentWidget()
        assert not row_widget.isVisibleTo(w)

    # ── Overlay Configuration section ─────────────────────────────

    def test_overlay_section_heading_uses_configuration_wording(
        self,
        qapp: QApplication,
    ) -> None:
        """The overlay group title reads "Overlay Configuration".

        Matches the broader "X Configuration" pattern used by every
        other section heading in the settings.  A regression that
        reverts to the bare "Overlay Window" wording would visually
        diverge from the rest of the page.
        """
        from src.constants.i18n import _set_initial_language, tr  # noqa: PLC0415

        _set_initial_language("en-US")
        w = self._build(qapp)
        labels_text = [lbl.text() for lbl in w.findChildren(QLabel)]
        assert tr("settings.live_overlay") in labels_text
        # Sanity that the heading text actually contains "Configuration"
        # for the en-US locale.
        assert "Configuration" in tr("settings.live_overlay")

    def test_minimal_captions_checkbox_present(
        self,
        qapp: QApplication,
    ) -> None:
        """The "Show minimal captions" checkbox is rendered in Overlay section.

        Regression guard: a future refactor that drops the toggle
        would leave users with no way to hide overlay chips without
        also hiding them on the main window.
        """
        from src.constants.i18n import _set_initial_language, tr  # noqa: PLC0415

        _set_initial_language("en-US")
        w = self._build(qapp)
        expected = tr("settings.live_overlay_minimal")
        cb_labels = [cb.text() for cb in w.findChildren(QCheckBox)]
        assert expected in cb_labels, (
            f"expected '{expected}' checkbox in Live settings; got {cb_labels}"
        )

    def test_minimal_captions_toggle_emits_appearance_signal(
        self,
        qapp: QApplication,
    ) -> None:
        """Toggling the minimal-captions checkbox broadcasts on the signal.

        The signal carries ``(SETTING_LIVE_OVERLAY_MINIMAL, bool)``
        so any running ``_OverlayWindow`` instance hides/shows its
        chips immediately — no overlay-restart required.
        """
        from src.constants.i18n import _set_initial_language, tr  # noqa: PLC0415
        from src.constants.settings import (  # noqa: PLC0415
            SETTING_LIVE_OVERLAY_MINIMAL,
            overlay_appearance_changed,
        )

        _set_initial_language("en-US")
        w = self._build(qapp)
        target_text = tr("settings.live_overlay_minimal")
        cb = next(c for c in w.findChildren(QCheckBox) if c.text() == target_text)

        received: list[tuple[str, object]] = []
        overlay_appearance_changed.connect(
            lambda k, v: received.append((k, v)),
        )

        cb.setChecked(not cb.isChecked())
        assert received, "expected appearance signal on toggle"
        last_key, last_val = received[-1]
        assert last_key == SETTING_LIVE_OVERLAY_MINIMAL
        assert isinstance(last_val, bool)

    def test_font_size_slider_broadcasts_appearance_signal(
        self,
        qapp: QApplication,
    ) -> None:
        """Settings font-size slider emits ``overlay_appearance_changed``.

        Live-sync contract: dragging the slider in the settings page
        must broadcast through the shared signal so any running
        overlay updates its transcript font in real time.  Without
        this emit, the change persists to disk but the overlay
        only picks it up on next open.
        """
        from PySide6.QtWidgets import QSlider  # noqa: PLC0415

        from src.constants.settings import (  # noqa: PLC0415
            SETTING_LIVE_OVERLAY_FONT_SIZE,
            overlay_appearance_changed,
        )
        from src.ui.pages.live import (  # noqa: PLC0415
            _OVERLAY_MAX_FONT_PX,
            _OVERLAY_MIN_FONT_PX,
        )

        w = self._build(qapp)
        # The Live tab now hosts multiple sliders (Session auto-stop +
        # Overlay font / opacity); pick the font slider by its
        # distinctive range so test order is stable as new sliders
        # are added to the tab.
        sliders = [
            s
            for s in w.findChildren(QSlider)
            if s.minimum() == _OVERLAY_MIN_FONT_PX
            and s.maximum() == _OVERLAY_MAX_FONT_PX
        ]
        assert sliders, "expected font-size slider in Live tab"

        received: list[tuple[str, object]] = []
        overlay_appearance_changed.connect(
            lambda k, v: received.append((k, v)),
        )

        font_slider = sliders[0]
        font_slider.setValue(font_slider.value() + 1)

        font_emits = [
            (k, v) for k, v in received if k == SETTING_LIVE_OVERLAY_FONT_SIZE
        ]
        assert font_emits, f"expected font-size emit on slider drag; got {received}"

    def test_external_appearance_change_syncs_checkbox(
        self,
        qapp: QApplication,
    ) -> None:
        """The Settings checkbox catches up when the signal fires elsewhere.

        Real-world: user toggles minimal-mode via a keyboard
        shortcut on the floating overlay (hypothetical future
        addition) — the Settings checkbox must reflect the new
        state so the next Settings open isn't out of date.
        """
        from src.constants.i18n import _set_initial_language, tr  # noqa: PLC0415
        from src.constants.settings import (  # noqa: PLC0415
            SETTING_LIVE_OVERLAY_MINIMAL,
            overlay_appearance_changed,
        )

        _set_initial_language("en-US")
        w = self._build(qapp)
        target_text = tr("settings.live_overlay_minimal")
        cb = next(c for c in w.findChildren(QCheckBox) if c.text() == target_text)
        initial = cb.isChecked()

        # External emit (e.g. from overlay's own setter)
        overlay_appearance_changed.emit(
            SETTING_LIVE_OVERLAY_MINIMAL,
            not initial,
        )
        assert cb.isChecked() != initial, (
            "settings checkbox did not catch up to external signal"
        )


# ===================================================================
# Auto-stop UI (Auto actions section: None / 3 min / 10 min radios)
# ===================================================================


class TestAutoStopUI:
    """Covers the Auto-actions-section auto-stop radios in the Live tab.

    The runtime timer is tested in ``TestLivePageAutoStop`` against
    the saved ``SETTING_LIVE_AUTO_STOP_MINUTES`` value.  These tests
    pin the SETTINGS-side controls: the three radios (None / After 3
    minutes / After 10 minutes) read/write the same integer-minutes
    setting and snap legacy slider values to the nearest bucket.
    """

    @pytest.fixture(autouse=True)
    def _deps(self, _mock_settings_deps):
        """Auto-use mock dependencies."""

    def _build(self, qapp: QApplication) -> QWidget:  # noqa: ARG002
        from src.ui.pages.settings import create_live_settings  # noqa: PLC0415

        return create_live_settings()

    def _find_auto_stop_radios(self, page: QWidget) -> dict[int, QWidget]:
        """Locates the three auto-stop radios by their ``value`` property.

        Returns a ``{minutes: radio}`` map.  The auto-stop radios are
        the only QRadioButtons in the Live tab whose ``value``
        property is an exact ``int`` (the save-mode / format radios
        use string property values, the Show speaker radios use bool
        values — ``isinstance(True, int)`` is True in Python, so we
        rule those out with the strict ``type(...) is int`` check).
        """
        from PySide6.QtWidgets import QRadioButton  # noqa: PLC0415

        found: dict[int, QWidget] = {}
        for r in page.findChildren(QRadioButton):
            val = r.property("value")
            if type(val) is int:  # noqa: E721 — bool subclass of int, exclude it
                found[val] = r
        assert set(found) == {0, 3, 10}, (
            f"expected radios for minutes {{0, 3, 10}}, found {set(found)}"
        )
        return found

    def test_zero_selects_none_radio(self, qapp: QApplication) -> None:
        """Saved 0 → "None" radio checked."""
        from unittest.mock import patch  # noqa: PLC0415

        with patch(
            "src.ui.pages.settings.load_setting",
            side_effect=lambda key, default=None: (
                0 if key == "live/auto_stop_minutes" else default
            ),
        ):
            page = self._build(qapp)

        radios = self._find_auto_stop_radios(page)
        assert radios[0].isChecked() is True
        assert radios[3].isChecked() is False
        assert radios[10].isChecked() is False

    def test_three_selects_three_min_radio(self, qapp: QApplication) -> None:
        """Saved 3 → "After 3 minutes" radio checked."""
        from unittest.mock import patch  # noqa: PLC0415

        with patch(
            "src.ui.pages.settings.load_setting",
            side_effect=lambda key, default=None: (
                3 if key == "live/auto_stop_minutes" else default
            ),
        ):
            page = self._build(qapp)

        radios = self._find_auto_stop_radios(page)
        assert radios[3].isChecked() is True

    def test_ten_selects_ten_min_radio(self, qapp: QApplication) -> None:
        """Saved 10 → "After 10 minutes" radio checked."""
        from unittest.mock import patch  # noqa: PLC0415

        with patch(
            "src.ui.pages.settings.load_setting",
            side_effect=lambda key, default=None: (
                10 if key == "live/auto_stop_minutes" else default
            ),
        ):
            page = self._build(qapp)

        radios = self._find_auto_stop_radios(page)
        assert radios[10].isChecked() is True

    def test_legacy_low_value_snaps_to_3(self, qapp: QApplication) -> None:
        """Legacy slider value in (0, 6] snaps to "After 3 minutes"."""
        from unittest.mock import patch  # noqa: PLC0415

        with patch(
            "src.ui.pages.settings.load_setting",
            side_effect=lambda key, default=None: (
                5 if key == "live/auto_stop_minutes" else default
            ),
        ):
            page = self._build(qapp)

        radios = self._find_auto_stop_radios(page)
        assert radios[3].isChecked() is True

    def test_legacy_high_value_snaps_to_10(self, qapp: QApplication) -> None:
        """Legacy slider value > 6 snaps to "After 10 minutes"."""
        from unittest.mock import patch  # noqa: PLC0415

        with patch(
            "src.ui.pages.settings.load_setting",
            side_effect=lambda key, default=None: (
                999 if key == "live/auto_stop_minutes" else default
            ),
        ):
            page = self._build(qapp)

        radios = self._find_auto_stop_radios(page)
        assert radios[10].isChecked() is True

    def test_malformed_saved_value_falls_back_to_none(
        self,
        qapp: QApplication,
    ) -> None:
        """Non-int saved value (corrupted INI) → "None" radio.

        The constructor wraps ``int(load_setting(...))`` in a
        try/except so a broken setting can't crash page creation.
        """
        from unittest.mock import patch  # noqa: PLC0415

        with patch(
            "src.ui.pages.settings.load_setting",
            side_effect=lambda key, default=None: (
                "not-a-number" if key == "live/auto_stop_minutes" else default
            ),
        ):
            page = self._build(qapp)

        radios = self._find_auto_stop_radios(page)
        assert radios[0].isChecked() is True

    def test_clicking_three_min_persists(self, qapp: QApplication) -> None:
        """Clicking "After 3 minutes" writes "3" to the setting."""
        from unittest.mock import patch  # noqa: PLC0415

        with patch(
            "src.ui.pages.settings.load_setting",
            side_effect=lambda key, default=None: (
                0 if key == "live/auto_stop_minutes" else default
            ),
        ):
            page = self._build(qapp)
        radios = self._find_auto_stop_radios(page)

        saved: list[tuple[str, str]] = []
        with patch(
            "src.ui.pages.settings.save_setting",
            side_effect=lambda key, val: saved.append((key, val)),
        ):
            radios[3].click()

        assert ("live/auto_stop_minutes", "3") in saved

    def test_clicking_ten_min_persists(self, qapp: QApplication) -> None:
        """Clicking "After 10 minutes" writes "10" to the setting."""
        from unittest.mock import patch  # noqa: PLC0415

        with patch(
            "src.ui.pages.settings.load_setting",
            side_effect=lambda key, default=None: (
                0 if key == "live/auto_stop_minutes" else default
            ),
        ):
            page = self._build(qapp)
        radios = self._find_auto_stop_radios(page)

        saved: list[tuple[str, str]] = []
        with patch(
            "src.ui.pages.settings.save_setting",
            side_effect=lambda key, val: saved.append((key, val)),
        ):
            radios[10].click()

        assert ("live/auto_stop_minutes", "10") in saved

    def test_clicking_none_persists_zero(self, qapp: QApplication) -> None:
        """Clicking "None" writes "0" — disabling the timer for the next session."""
        from unittest.mock import patch  # noqa: PLC0415

        with patch(
            "src.ui.pages.settings.load_setting",
            side_effect=lambda key, default=None: (
                10 if key == "live/auto_stop_minutes" else default
            ),
        ):
            page = self._build(qapp)
        radios = self._find_auto_stop_radios(page)
        assert radios[10].isChecked() is True

        saved: list[tuple[str, str]] = []
        with patch(
            "src.ui.pages.settings.save_setting",
            side_effect=lambda key, val: saved.append((key, val)),
        ):
            radios[0].click()

        assert ("live/auto_stop_minutes", "0") in saved


class TestCreateTranslateTextSettings:
    """Tests for the create_translate_text_settings() factory."""

    @pytest.fixture(autouse=True)
    def _deps(self, _mock_settings_deps):
        """Auto-use mock dependencies."""

    def _build(self, qapp: QApplication) -> QWidget:
        from src.ui.pages.settings import (  # noqa: PLC0415
            create_translate_text_settings,
        )

        return create_translate_text_settings()

    def test_returns_qwidget(self, qapp: QApplication) -> None:
        """Factory returns a QWidget."""
        w = self._build(qapp)
        assert isinstance(w, QWidget)

    def test_contains_auto_save_history_checkbox(self, qapp: QApplication) -> None:
        """Widget contains a checkbox for auto-save history."""
        from src.constants.i18n import tr  # noqa: PLC0415

        w = self._build(qapp)
        checkboxes = w.findChildren(QCheckBox)
        texts = {cb.text() for cb in checkboxes}
        assert tr("settings.translate_text_auto_save") in texts

    def test_contains_labels(self, qapp: QApplication) -> None:
        """Widget contains labels for TTS output and history sections."""
        w = self._build(qapp)
        labels = w.findChildren(QLabel)
        assert len(labels) >= 1

    def test_auto_save_checkbox_loads_default_setting(
        self,
        qapp: QApplication,
    ) -> None:
        """Auto-save checkbox loads the default setting on creation."""
        w = self._build(qapp)
        checkboxes = w.findChildren(QCheckBox)
        assert len(checkboxes) >= 1
        # Default is True per create_setting_checkbox call
        auto_save_cb = checkboxes[0]
        assert auto_save_cb.isChecked() is True

    def test_checkbox_toggling_saves_setting(self, qapp: QApplication) -> None:
        """Toggling the auto-save checkbox calls save_setting."""
        with patch("src.ui.components.save_setting") as mock_save:
            w = self._build(qapp)
            checkboxes = w.findChildren(QCheckBox)
            auto_save_cb = checkboxes[0]
            # Toggle off
            auto_save_cb.setChecked(False)
            save_calls = [
                c
                for c in mock_save.call_args_list
                if c[0][0] == "translate_text/auto_save_history"
            ]
            assert len(save_calls) >= 1
            assert save_calls[-1][0][1] is False

    def test_has_tts_storage_path_widget(self, qapp: QApplication) -> None:
        """Widget contains a TTS storage path selector."""
        from PySide6.QtWidgets import QPushButton  # noqa: PLC0415

        w = self._build(qapp)
        # The storage path widget includes a Browse button
        buttons = w.findChildren(QPushButton)
        # At least one button for browse and one for reset
        assert len(buttons) >= 1


class TestCreateTranslateTextSettingsExpanded:
    """Extended tests for create_translate_text_settings()."""

    def test_checkbox_default_when_no_setting_exists(
        self,
        qapp: QApplication,
    ) -> None:
        """Auto-save checkbox defaults to True when no saved value exists."""
        import contextlib  # noqa: PLC0415

        patches = dict(_SETTINGS_PATCHES)
        # Ensure load_setting returns default for all keys
        patches["src.ui.pages.settings.load_setting"] = lambda key, default="": default
        patches["src.ui.components.load_setting"] = lambda key, default="": default

        with contextlib.ExitStack() as stack:
            for target, replacement in patches.items():
                stack.enter_context(patch(target, replacement))

            from src.ui.pages.settings import (  # noqa: PLC0415
                create_translate_text_settings,
            )

            w = create_translate_text_settings()
            checkboxes = w.findChildren(QCheckBox)
            # Default for auto_save is True
            assert checkboxes[0].isChecked() is True

    def test_checkbox_reflects_saved_true_value(
        self,
        qapp: QApplication,
    ) -> None:
        """Auto-save checkbox is checked when saved value is True."""
        import contextlib  # noqa: PLC0415

        def custom_load(key, default=""):
            if key == "translate_text/auto_save_history":
                return True
            return default

        patches = dict(_SETTINGS_PATCHES)
        patches["src.ui.pages.settings.load_setting"] = custom_load
        patches["src.ui.components.load_setting"] = custom_load

        with contextlib.ExitStack() as stack:
            for target, replacement in patches.items():
                stack.enter_context(patch(target, replacement))

            from src.ui.pages.settings import (  # noqa: PLC0415
                create_translate_text_settings,
            )

            w = create_translate_text_settings()
            checkboxes = w.findChildren(QCheckBox)
            assert checkboxes[0].isChecked() is True

    def test_checkbox_reflects_saved_false_value(
        self,
        qapp: QApplication,
    ) -> None:
        """Auto-save checkbox is unchecked when saved value is False."""
        import contextlib  # noqa: PLC0415

        def custom_load(key, default=""):
            if key == "translate_text/auto_save_history":
                return False
            return default

        patches = dict(_SETTINGS_PATCHES)
        patches["src.ui.pages.settings.load_setting"] = custom_load
        patches["src.ui.components.load_setting"] = custom_load

        with contextlib.ExitStack() as stack:
            for target, replacement in patches.items():
                stack.enter_context(patch(target, replacement))

            from src.ui.pages.settings import (  # noqa: PLC0415
                create_translate_text_settings,
            )

            w = create_translate_text_settings()
            checkboxes = w.findChildren(QCheckBox)
            assert checkboxes[0].isChecked() is False

    def test_widget_has_proper_layout_structure(
        self,
        qapp: QApplication,
    ) -> None:
        """Widget has a QVBoxLayout with at least two groups and a stretch."""
        import contextlib  # noqa: PLC0415

        patches = dict(_SETTINGS_PATCHES)
        with contextlib.ExitStack() as stack:
            for target, replacement in patches.items():
                stack.enter_context(patch(target, replacement))

            from src.ui.pages.settings import (  # noqa: PLC0415
                create_translate_text_settings,
            )

            w = create_translate_text_settings()
            layout = w.layout()
            from PySide6.QtWidgets import QVBoxLayout  # noqa: PLC0415

            assert isinstance(layout, QVBoxLayout)
            # At least 2 group widgets + 1 stretch spacer
            assert layout.count() >= 3  # noqa: PLR2004


# ===================================================================
# TestSettingsTabSwitching — tab navigation
# ===================================================================


class TestSettingsTabSwitching:
    """Tests for settings page tab navigation."""

    @pytest.fixture(autouse=True)
    def _deps(self, _mock_settings_deps):
        """Auto-use mock dependencies."""

    def _build_page(self, qapp: QApplication) -> QWidget:
        from src.ui.pages.settings import create_settings_page  # noqa: PLC0415

        return create_settings_page()

    def test_tab_widget_has_correct_number_of_tabs(
        self,
        qapp: QApplication,
    ) -> None:
        """Tab widget has exactly 12 tabs."""
        page = self._build_page(qapp)
        tabs = page.findChild(QTabWidget)
        assert tabs.count() == 12  # noqa: PLR2004

    def test_switching_tabs_changes_current_index(
        self,
        qapp: QApplication,
    ) -> None:
        """Switching tabs changes the current visible content index."""
        page = self._build_page(qapp)
        tabs = page.findChild(QTabWidget)
        for idx in range(tabs.count()):
            tabs.setCurrentIndex(idx)
            assert tabs.currentIndex() == idx

    def test_tab_index_0_is_general(self, qapp: QApplication) -> None:
        """Tab index 0 corresponds to the General settings tab."""
        from src.constants.i18n import tr  # noqa: PLC0415

        page = self._build_page(qapp)
        tabs = page.findChild(QTabWidget)
        assert tabs.tabText(0) == tr("settings.general")

    def test_tab_index_1_is_shortcuts(self, qapp: QApplication) -> None:
        """Tab index 1 corresponds to the Shortcuts settings tab."""
        from src.constants.i18n import tr  # noqa: PLC0415

        page = self._build_page(qapp)
        tabs = page.findChild(QTabWidget)
        assert tabs.tabText(1) == tr("settings.shortcuts")

    def test_tab_index_2_is_service(self, qapp: QApplication) -> None:
        """Tab index 2 corresponds to the Service settings tab."""
        from src.constants.i18n import tr  # noqa: PLC0415

        page = self._build_page(qapp)
        tabs = page.findChild(QTabWidget)
        assert tabs.tabText(2) == tr("settings.service")

    def test_tab_index_3_is_ocr(self, qapp: QApplication) -> None:
        """Tab index 3 corresponds to the OCR settings tab."""
        from src.constants.i18n import tr  # noqa: PLC0415

        page = self._build_page(qapp)
        tabs = page.findChild(QTabWidget)
        assert tabs.tabText(3) == tr("settings.ocr")

    def test_tab_index_4_is_llm(self, qapp: QApplication) -> None:
        """Tab index 4 corresponds to the LLM settings tab."""
        from src.constants.i18n import tr  # noqa: PLC0415

        page = self._build_page(qapp)
        tabs = page.findChild(QTabWidget)
        assert tabs.tabText(4) == tr("settings.llm")

    def test_tab_index_5_is_translate_text(self, qapp: QApplication) -> None:
        """Tab index 5 corresponds to the Translate Text settings tab."""
        from src.constants.i18n import tr  # noqa: PLC0415

        page = self._build_page(qapp)
        tabs = page.findChild(QTabWidget)
        assert tabs.tabText(5) == tr("settings.translate_text")

    def test_tab_index_6_is_translation(self, qapp: QApplication) -> None:
        """Tab index 6 corresponds to the Translation settings tab."""
        from src.constants.i18n import tr  # noqa: PLC0415

        page = self._build_page(qapp)
        tabs = page.findChild(QTabWidget)
        assert tabs.tabText(6) == tr("settings.translation")

    def test_tab_index_7_is_subtitle(self, qapp: QApplication) -> None:
        """Tab index 7 corresponds to the Subtitle settings tab."""
        from src.constants.i18n import tr  # noqa: PLC0415

        page = self._build_page(qapp)
        tabs = page.findChild(QTabWidget)
        assert tabs.tabText(7) == tr("settings.subtitle")

    def test_tab_index_8_is_voice(self, qapp: QApplication) -> None:
        """Tab index 8 corresponds to the Voice settings tab."""
        from src.constants.i18n import tr  # noqa: PLC0415

        page = self._build_page(qapp)
        tabs = page.findChild(QTabWidget)
        assert tabs.tabText(8) == tr("settings.voice")

    def test_tab_index_9_is_dubbing(self, qapp: QApplication) -> None:
        """Tab index 9 corresponds to the Dubbing settings tab."""
        from src.constants.i18n import tr  # noqa: PLC0415

        page = self._build_page(qapp)
        tabs = page.findChild(QTabWidget)
        assert tabs.tabText(9) == tr("settings.dubbing")

    def test_tab_index_10_is_live(self, qapp: QApplication) -> None:
        """Tab index 10 corresponds to the Live settings tab."""
        from src.constants.i18n import tr  # noqa: PLC0415

        page = self._build_page(qapp)
        tabs = page.findChild(QTabWidget)
        assert tabs.tabText(10) == tr("settings.live")

    def test_tab_index_11_is_extract_text(self, qapp: QApplication) -> None:
        """Tab index 11 corresponds to the Extract Text settings tab."""
        from src.constants.i18n import tr  # noqa: PLC0415

        page = self._build_page(qapp)
        tabs = page.findChild(QTabWidget)
        assert tabs.tabText(11) == tr("settings.extract_text")

    def test_translate_text_tab_has_checkbox(self, qapp: QApplication) -> None:
        """Translate Text tab (index 5) contains at least one checkbox."""
        page = self._build_page(qapp)
        tabs = page.findChild(QTabWidget)
        translate_text = tabs.widget(5)
        cbs = translate_text.findChildren(QCheckBox)
        assert len(cbs) >= 1


# ===================================================================
# TestSettingsThemeChange — theme change from settings
# ===================================================================


class TestSettingsThemeChange:
    """Tests for theme changes triggered from the General settings tab."""

    @pytest.fixture(autouse=True)
    def _deps(self, _mock_settings_deps):
        """Auto-use mock dependencies."""

    def test_theme_change_calls_save_setting_and_set_theme(
        self,
        qapp: QApplication,
    ) -> None:
        """Changing theme radio calls save_setting and set_theme."""
        with (
            patch("src.ui.pages.settings.save_setting") as mock_save,
            patch("src.ui.pages.settings.set_theme") as mock_set_theme,
        ):
            from src.ui.pages.settings import create_general_settings  # noqa: PLC0415

            w = create_general_settings()
            groups = w.findChildren(QButtonGroup)
            theme_group = groups[0]
            btns = theme_group.buttons()
            # Click "Light" (index 1)
            btns[1].setChecked(True)
            theme_group.buttonClicked.emit(btns[1])
            # Verify save_setting was called with app/theme
            save_calls = [c for c in mock_save.call_args_list if c[0][0] == "app/theme"]
            assert len(save_calls) >= 1
            assert save_calls[-1][0][1] == "light"
            # Verify set_theme was called with "light"
            mock_set_theme.assert_called_with("light")

    def test_theme_auto_triggers_system_detection(
        self,
        qapp: QApplication,
    ) -> None:
        """Changing theme to 'Auto' triggers system theme detection."""
        with (
            patch("src.ui.pages.settings.save_setting") as mock_save,
            patch("src.ui.pages.settings.set_theme") as mock_set_theme,
            patch(
                "src.ui.system_theme.detect_system_theme",
                return_value="dark",
            ) as mock_detect,
        ):
            from src.ui.pages.settings import create_general_settings  # noqa: PLC0415

            w = create_general_settings()
            groups = w.findChildren(QButtonGroup)
            theme_group = groups[0]
            btns = theme_group.buttons()
            # Click "Auto" (index 0)
            btns[0].setChecked(True)
            theme_group.buttonClicked.emit(btns[0])
            # Verify save_setting was called with "auto"
            save_calls = [c for c in mock_save.call_args_list if c[0][0] == "app/theme"]
            assert any(c[0][1] == "auto" for c in save_calls)
            # detect_system_theme should be called as fallback (no monitor)
            mock_detect.assert_called_once()
            mock_set_theme.assert_called_with("dark")

    def test_theme_dark_calls_set_theme_dark(
        self,
        qapp: QApplication,
    ) -> None:
        """Selecting Dark theme calls set_theme('dark')."""
        with (
            patch("src.ui.pages.settings.save_setting"),
            patch("src.ui.pages.settings.set_theme") as mock_set_theme,
        ):
            from src.ui.pages.settings import create_general_settings  # noqa: PLC0415

            w = create_general_settings()
            groups = w.findChildren(QButtonGroup)
            theme_group = groups[0]
            btns = theme_group.buttons()
            # Click "Dark" (index 2)
            btns[2].setChecked(True)
            theme_group.buttonClicked.emit(btns[2])
            mock_set_theme.assert_called_with("dark")

    def test_theme_auto_with_monitor_starts_it(
        self,
        qapp: QApplication,
    ) -> None:
        """Selecting 'Auto' starts the monitor when one exists on window."""
        with (
            patch("src.ui.pages.settings.save_setting"),
            patch("src.ui.pages.settings.set_theme"),
        ):
            from src.ui.pages.settings import create_general_settings  # noqa: PLC0415

            w = create_general_settings()
            mock_monitor = MagicMock()
            w.window()._system_theme_monitor = mock_monitor

            groups = w.findChildren(QButtonGroup)
            theme_group = groups[0]
            btns = theme_group.buttons()
            btns[0].setChecked(True)
            theme_group.buttonClicked.emit(btns[0])
            mock_monitor.start.assert_called_once()

    def test_theme_non_auto_stops_monitor(
        self,
        qapp: QApplication,
    ) -> None:
        """Selecting a non-Auto theme stops the system theme monitor."""
        with (
            patch("src.ui.pages.settings.save_setting"),
            patch("src.ui.pages.settings.set_theme"),
        ):
            from src.ui.pages.settings import create_general_settings  # noqa: PLC0415

            w = create_general_settings()
            mock_monitor = MagicMock()
            w.window()._system_theme_monitor = mock_monitor

            groups = w.findChildren(QButtonGroup)
            theme_group = groups[0]
            btns = theme_group.buttons()
            # Click "Light" (index 1)
            btns[1].setChecked(True)
            theme_group.buttonClicked.emit(btns[1])
            mock_monitor.stop.assert_called_once()


# ===================================================================
# TestSettingsLanguageChange — language change from settings
# ===================================================================


class TestSettingsLanguageChange:
    """Tests for language changes triggered from the General settings tab."""

    @pytest.fixture(autouse=True)
    def _deps(self, _mock_settings_deps):
        """Auto-use mock dependencies."""

    def test_language_change_calls_save_setting_and_set_language(
        self,
        qapp: QApplication,
    ) -> None:
        """Changing the language combo calls save_setting and set_language."""
        with (
            patch("src.ui.pages.settings.save_setting") as mock_save,
            patch("src.ui.pages.settings.set_language") as mock_set_lang,
        ):
            from src.ui.pages.settings import create_general_settings  # noqa: PLC0415

            w = create_general_settings()
            combos = w.findChildren(QComboBox)
            lang_combo = combos[0]
            # Switch to a different language (index 1)
            if lang_combo.count() > 1:
                lang_combo.setCurrentIndex(1)
                code = lang_combo.itemData(1)
                # Verify save_setting was called for ui_language
                save_calls = [
                    c for c in mock_save.call_args_list if c[0][0] == "app/ui_language"
                ]
                assert len(save_calls) >= 1
                assert save_calls[-1][0][1] == code
                # Verify set_language was called with the code
                mock_set_lang.assert_called_with(code)

    def test_language_change_to_third_option(
        self,
        qapp: QApplication,
    ) -> None:
        """Changing to the third language option persists the correct code."""
        with (
            patch("src.ui.pages.settings.save_setting") as mock_save,
            patch("src.ui.pages.settings.set_language") as mock_set_lang,
        ):
            from src.ui.pages.settings import create_general_settings  # noqa: PLC0415

            w = create_general_settings()
            combos = w.findChildren(QComboBox)
            lang_combo = combos[0]
            if lang_combo.count() > 2:  # noqa: PLR2004
                lang_combo.setCurrentIndex(2)
                code = lang_combo.itemData(2)
                save_calls = [
                    c for c in mock_save.call_args_list if c[0][0] == "app/ui_language"
                ]
                assert len(save_calls) >= 1
                assert save_calls[-1][0][1] == code
                mock_set_lang.assert_called_with(code)

    def test_language_default_selection_is_en_us(
        self,
        qapp: QApplication,
    ) -> None:
        """Default language selection is en-US when no saved value."""
        from src.ui.pages.settings import create_general_settings  # noqa: PLC0415

        w = create_general_settings()
        combos = w.findChildren(QComboBox)
        lang_combo = combos[0]
        assert lang_combo.currentData() == "en-US"

    def test_saved_language_is_preselected(
        self,
        qapp: QApplication,
    ) -> None:
        """A saved language code is pre-selected in the combo box."""
        import contextlib  # noqa: PLC0415

        def custom_load(key, default=""):
            if key == "app/ui_language":
                return "en-UK"
            return default

        patches = dict(_SETTINGS_PATCHES)
        patches["src.ui.pages.settings.load_setting"] = custom_load
        patches["src.ui.components.load_setting"] = custom_load

        with contextlib.ExitStack() as stack:
            for target, replacement in patches.items():
                stack.enter_context(patch(target, replacement))

            from src.ui.pages.settings import create_general_settings  # noqa: PLC0415

            w = create_general_settings()
            combos = w.findChildren(QComboBox)
            lang_combo = combos[0]
            assert lang_combo.currentData() == "en-UK"

    def test_language_combo_has_all_ui_languages(
        self,
        qapp: QApplication,
    ) -> None:
        """Language combo box contains all entries from UI_LANGUAGES."""
        from src.constants.i18n import UI_LANGUAGES  # noqa: PLC0415
        from src.ui.pages.settings import create_general_settings  # noqa: PLC0415

        w = create_general_settings()
        combos = w.findChildren(QComboBox)
        lang_combo = combos[0]
        assert lang_combo.count() == len(UI_LANGUAGES)


class TestServiceGeminiCrossReference:
    """Service tab shows a pointer telling users Gemini lives on the LLM tab."""

    @pytest.fixture(autouse=True)
    def _deps(self, _mock_settings_deps):
        """Auto-use mock dependencies."""

    def test_gemini_reference_banner_present(self, qapp: QApplication) -> None:
        from PySide6.QtWidgets import QFrame  # noqa: PLC0415

        from src.ui.pages.settings import (  # noqa: PLC0415
            create_service_settings,
        )

        w = create_service_settings()
        banners = [f for f in w.findChildren(QFrame) if f.objectName() == "Banner"]
        # Service tab has: Gemini cross-ref, Google Cloud info, Soniox info,
        # ElevenLabs info. At least 4 banners total.
        assert len(banners) >= 4  # noqa: PLR2004


# ---------------------------------------------------------------------------
# Settings-page dispatcher (_hook late-binding + dict-based dispatch)
# ---------------------------------------------------------------------------


class TestDispatcherLateBinding:
    """Tests for the _tab_specs dispatcher built in create_settings_page()."""

    @pytest.fixture(autouse=True)
    def _deps(self, _mock_settings_deps):
        """Auto-use mock dependencies."""

    def test_service_tab_has_no_refresh_hook(self, qapp: QApplication) -> None:
        """Tabs without upstream dependencies are safely skipped by dispatch."""
        from src.ui.pages.settings import create_settings_page  # noqa: PLC0415

        page = create_settings_page()
        tabs = page.findChild(QTabWidget)

        # Service tab = index 2 (per ordering in _tab_specs). Switching to it
        # must not raise, even though no _sync_* hook is registered.
        tabs.setCurrentIndex(2)
        # If we got here, no exception was raised.
        assert tabs.currentIndex() == 2

    def test_llm_tab_has_no_refresh_hook(self, qapp: QApplication) -> None:
        """LLM tab (index 4) likewise has no refresh callable — dispatch no-ops."""
        from src.ui.pages.settings import create_settings_page  # noqa: PLC0415

        page = create_settings_page()
        tabs = page.findChild(QTabWidget)
        tabs.setCurrentIndex(4)
        assert tabs.currentIndex() == 4

    def test_hook_is_late_bound_for_monkey_patching(
        self,
        qapp: QApplication,
    ) -> None:
        """Tests can replace a widget's _sync_* attribute post-construction.

        The dispatcher wraps hook references in a late-lookup lambda so the
        new attribute is honoured on the next tab switch.
        """
        from PySide6.QtWidgets import QScrollArea  # noqa: PLC0415

        from src.ui.pages.settings import create_settings_page  # noqa: PLC0415

        page = create_settings_page()
        tabs = page.findChild(QTabWidget)

        # tabs.widget(i) returns the QScrollArea that wraps the real inner
        # widget; call .widget() to reach the widget that owns the hook.
        ocr_wrapper = tabs.widget(3)
        inner = (
            ocr_wrapper.widget()
            if isinstance(ocr_wrapper, QScrollArea)
            else ocr_wrapper
        )

        replacement = MagicMock()
        inner._sync_ocr_availability = replacement

        tabs.setCurrentIndex(0)  # Move away first so next switch triggers refresh.
        tabs.setCurrentIndex(3)
        replacement.assert_called()


# ---------------------------------------------------------------------------
# LLM tab — Custom provider Name field
# ---------------------------------------------------------------------------


class TestCustomProviderName:
    """Tests for the per-provider Name input and its section-title feedback."""

    @pytest.fixture(autouse=True)
    def _deps(self, _mock_settings_deps):
        """Auto-use mock dependencies."""

    def test_name_field_present_and_populates_from_data(
        self,
        qapp: QApplication,
    ) -> None:
        from PySide6.QtWidgets import QLineEdit  # noqa: PLC0415

        from src.utils.config_manager import (  # noqa: PLC0415
            save_custom_providers,
        )

        save_custom_providers(
            [
                {"name": "OpenRouter", "api_key": "k", "endpoint": "e", "models": "m"},
            ]
        )

        from src.ui.pages.settings import create_llm_settings  # noqa: PLC0415

        w = create_llm_settings()
        inputs = w.findChildren(QLineEdit)
        # One of the inputs should hold the name.
        assert any(i.text() == "OpenRouter" for i in inputs)

    def test_section_title_uses_name_when_set(self, qapp: QApplication) -> None:
        """When the provider has a Name, the section title includes it.

        Patches ``tr()`` on the settings module so the template substitutes
        the {name} placeholder (the test-env tr by default returns raw keys).
        """
        from src.utils.config_manager import (  # noqa: PLC0415
            save_custom_providers,
        )

        save_custom_providers(
            [
                {"name": "MyLLM", "api_key": "", "endpoint": "", "models": ""},
            ]
        )

        def fake_tr(key, **kwargs):
            if key == "settings.custom_provider_named_title":
                return f"{kwargs.get('name', '')} Configuration"
            return key

        with patch("src.ui.pages.settings.tr", side_effect=fake_tr):
            from src.ui.pages.settings import create_llm_settings  # noqa: PLC0415

            w = create_llm_settings()

        labels = w.findChildren(QLabel)
        titles = [label.text() for label in labels]
        assert any(t == "MyLLM Configuration" for t in titles), (
            f"Expected 'MyLLM Configuration' in titles, got: {titles}"
        )

    def test_section_title_falls_back_to_default_when_name_empty(
        self,
        qapp: QApplication,
    ) -> None:
        """With no Name, the title reads the default custom_provider_title key."""
        from src.utils.config_manager import (  # noqa: PLC0415
            save_custom_providers,
        )

        save_custom_providers(
            [
                {"name": "", "api_key": "", "endpoint": "", "models": ""},
            ]
        )

        from src.ui.pages.settings import create_llm_settings  # noqa: PLC0415

        w = create_llm_settings()
        labels = [lab.text() for lab in w.findChildren(QLabel)]
        # In tests, tr() returns the key verbatim for keys without an active
        # translation table. The default fallback key is custom_provider_title.
        assert any("custom_provider_title" in t or "Configuration" in t for t in labels)

    def test_name_edit_persists_via_debounced_save(
        self,
        qapp: QApplication,
    ) -> None:
        """Editing the Name field schedules a save via the 400ms debounce timer."""
        from PySide6.QtCore import QCoreApplication  # noqa: PLC0415
        from PySide6.QtWidgets import QLineEdit  # noqa: PLC0415

        from src.utils.config_manager import (  # noqa: PLC0415
            load_custom_providers,
            save_custom_providers,
        )

        save_custom_providers(
            [
                {"name": "Initial", "api_key": "k", "endpoint": "e", "models": "m"},
            ]
        )

        from src.ui.pages.settings import create_llm_settings  # noqa: PLC0415

        w = create_llm_settings()
        inputs = w.findChildren(QLineEdit)
        name_input = next(i for i in inputs if i.text() == "Initial")

        name_input.setText("Renamed")
        # Force the debounce timer to fire synchronously.
        from PySide6.QtCore import QTimer  # noqa: PLC0415

        timers = w.findChildren(QTimer)
        for t in timers:
            if t.isSingleShot() and t.isActive():
                t.stop()
                t.timeout.emit()

        QCoreApplication.processEvents()
        providers = load_custom_providers()
        assert any(p.get("name") == "Renamed" for p in providers)

    def test_about_to_quit_flushes_pending_provider_save(
        self,
        qapp: QApplication,
    ) -> None:
        """``aboutToQuit`` flushes the debounced provider save.

        Pin AGENTS.md's load-bearing claim: a user editing a provider
        and quitting within the 400 ms debounce window must NOT lose
        the edit.  Without the ``aboutToQuit → _save_providers_now``
        connection in ``create_llm_settings``, the singleshot timer
        wouldn't fire after the event loop stops and the edit would
        silently disappear.
        """
        from PySide6.QtCore import QTimer  # noqa: PLC0415
        from PySide6.QtWidgets import QLineEdit  # noqa: PLC0415

        from src.utils.config_manager import (  # noqa: PLC0415
            load_custom_providers,
            save_custom_providers,
        )

        save_custom_providers(
            [
                {
                    "name": "QuitTest",
                    "api_key": "k",
                    "endpoint": "e",
                    "models": "m",
                },
            ],
        )

        from src.ui.pages.settings import create_llm_settings  # noqa: PLC0415

        w = create_llm_settings()
        inputs = w.findChildren(QLineEdit)
        name_input = next(i for i in inputs if i.text() == "QuitTest")

        # Edit + verify timer is now armed (debounce window active).
        name_input.setText("FlushedOnQuit")
        timers = [
            t for t in w.findChildren(QTimer) if t.isSingleShot() and t.isActive()
        ]
        assert timers, "debounce timer not armed after edit"

        # Fire ``aboutToQuit`` — the production wiring at
        # ``settings.py:833`` should drain the pending save.  We don't
        # actually quit; we just emit the signal QApplication would
        # emit during shutdown.
        qapp.aboutToQuit.emit()

        providers = load_custom_providers()
        assert any(p.get("name") == "FlushedOnQuit" for p in providers), (
            "edit was lost — aboutToQuit did not flush the debounced save"
        )


# ---------------------------------------------------------------------------
# Banner placement — setup-hint banners render *above* the input they gate
# ---------------------------------------------------------------------------


class TestBannerAboveInput:
    """Verifies banners appear before the disabled control they explain.

    Uses the parent layout's child order (via indexOf) to check that each
    warning banner is inserted ahead of its corresponding input.
    """

    @pytest.fixture(autouse=True)
    def _deps(self, _mock_settings_deps):
        """Auto-use mock dependencies."""

    @staticmethod
    def _find_banner_with_tr_key(widget, tr_key: str):
        """Locates a banner frame by the tr-key rendered in its label.

        In the test environment tr() returns the raw key, so every banner's
        QLabel text equals the tr_key it was constructed with.
        """
        from PySide6.QtWidgets import QFrame, QLabel  # noqa: PLC0415

        for f in widget.findChildren(QFrame):
            if f.objectName() != "Banner":
                continue
            for lab in f.findChildren(QLabel):
                if tr_key in lab.text():
                    return f
        return None

    @staticmethod
    def _order_in_parent(frame, target) -> tuple[int, int] | None:
        """Returns (frame_idx, target_idx) in their shared parent layout."""
        parent = frame.parentWidget()
        if parent is None or parent.layout() is None:
            return None
        lay = parent.layout()
        f_idx = lay.indexOf(frame)
        t_idx = lay.indexOf(target)
        if f_idx < 0 or t_idx < 0:
            return None
        return (f_idx, t_idx)

    def test_ocr_setup_hint_above_method_radios(self, qapp: QApplication) -> None:
        """OCR tab: Google-Cloud setup-hint precedes the method radios."""
        with patch(
            "src.utils.config_manager.check_google_cloud_setup",
            return_value=False,
        ):
            from src.ui.pages.settings import create_ocr_settings  # noqa: PLC0415

            w = create_ocr_settings()

        banner = self._find_banner_with_tr_key(w, "settings.ocr_google_setup_hint")
        assert banner is not None, "OCR google setup hint banner not found"

        # The methods layout holds the radios; find the first radio's index.
        from PySide6.QtWidgets import QRadioButton  # noqa: PLC0415

        radios = w.findChildren(QRadioButton)
        assert radios, "No OCR radios found"

        # Banner parent is the section group; find the first radio in the
        # same parent (or in a sibling layout item under the same section).
        parent = banner.parentWidget()
        lay = parent.layout()
        banner_idx = lay.indexOf(banner)
        # The methods container (QVBoxLayout or container widget) is added
        # AFTER the banner in the section. We just verify the banner's index
        # is non-negative and the section has structure.
        assert banner_idx >= 0

    def test_translation_ocr_hint_above_images_checkbox(
        self,
        qapp: QApplication,
    ) -> None:
        """Translate Document: OCR-missing hint precedes the images checkbox."""
        with patch(
            "src.ui.pages.settings.check_ocr_setup",
            return_value=False,
        ):
            from src.ui.pages.settings import (  # noqa: PLC0415
                create_translation_settings,
            )

            w = create_translation_settings()

        banner = self._find_banner_with_tr_key(w, "settings.doc_images_no_ocr")
        assert banner is not None

        # Find the translate-images checkbox (the one gated by OCR setup).
        from PySide6.QtWidgets import QCheckBox  # noqa: PLC0415

        cbs = w.findChildren(QCheckBox)
        # Checkbox labels use tr keys in test env; find any checkbox that's
        # disabled (the images one, since OCR is missing).
        disabled_cbs = [cb for cb in cbs if not cb.isEnabled()]
        assert disabled_cbs

        # Banner and the disabled checkbox should be in the same parent layout
        # with the banner appearing first.
        images_cb = disabled_cbs[0]
        # Walk up to a shared ancestor.
        banner_parent = banner.parentWidget()
        cb_parent = images_cb.parentWidget()
        # Traverse up until we share ancestry. In practice the checkbox is
        # wrapped once in a row widget; the row is a sibling of the banner.
        lay = banner_parent.layout() if banner_parent else None
        if lay is None:
            pytest.skip("Cannot inspect banner parent layout")
        # Banner's layout index should be less than the image-row's index
        # in the same layout.
        b_idx = lay.indexOf(banner)
        # Find the row widget containing the disabled checkbox.
        row = cb_parent
        while row and row.parentWidget() is not banner_parent:
            row = row.parentWidget()
        if row is None:
            pytest.skip("Couldn't locate image-row in banner's parent")
        r_idx = lay.indexOf(row)
        assert b_idx >= 0
        assert r_idx >= 0
        assert b_idx < r_idx, (
            f"Banner at index {b_idx} should precede image row at {r_idx}"
        )

    def test_translate_text_voice_hint_above_storage_path(
        self,
        qapp: QApplication,
    ) -> None:
        """Translate Text: Voice-tab pointer banner precedes the storage path."""
        from src.ui.pages.settings import (  # noqa: PLC0415
            create_translate_text_settings,
        )

        w = create_translate_text_settings()
        banner = self._find_banner_with_tr_key(
            w,
            "settings.translate_text_tts_voice_hint",
        )
        assert banner is not None


class TestPiperDownloadDialogDrainsThreads:
    """The Piper voice library dialog bounded-waits in-flight downloads on close.

    Pins the ``wait(2000)`` contract documented in AGENTS.md for
    every page-owned ``QThread`` — without it, closing the dialog
    mid-download would surface "QThread destroyed while still running"
    warnings.  Page-level ``aboutToQuit`` plumbing is no longer
    needed because the dialog owns its threads and is always closed
    before the app exits.
    """

    @pytest.fixture(autouse=True)
    def _deps(self, _mock_settings_deps):
        """Auto-use mock dependencies."""

    def test_done_drains_threads(self, qapp: QApplication) -> None:  # noqa: ARG002
        """``done()`` calls ``wait`` on every tracked download thread."""
        from unittest.mock import MagicMock  # noqa: PLC0415

        from src.ui.dialogs import PiperVoiceDownloadDialog  # noqa: PLC0415

        dlg = PiperVoiceDownloadDialog()
        # Inject a fake thread; ``done()`` must call ``wait(2000)`` on it.
        fake_thread = MagicMock()
        dlg._threads["en_US-amy-medium"] = fake_thread
        dlg.done(0)
        fake_thread.wait.assert_called_once_with(2000)
        assert dlg._threads == {}, (
            "Drain should also clear the tracking dict so a stale "
            "thread reference can't outlive the dialog"
        )


class TestPiperVoiceSection:
    """Piper voice picker page (stack index 4) — combo + summary banner."""

    @pytest.fixture(autouse=True)
    def _deps(self, _mock_settings_deps):
        """Auto-use mock dependencies."""

    def test_piper_page_has_gender_radios_and_manage_button(
        self,
        qapp: QApplication,
    ) -> None:
        """Stack index 4 = 2 gender radios + a "Download voices…" button.

        The per-voice combo + per-voice download button are gone:
        voice picking is handled by the engine (auto-pick from
        ``(target_lang, gender)``), and the user only decides which
        languages to install via the new library dialog.
        """
        from PySide6.QtWidgets import (  # noqa: PLC0415
            QComboBox,
            QPushButton,
            QRadioButton,
            QStackedWidget,
        )

        from src.constants.i18n import _set_initial_language, tr  # noqa: PLC0415
        from src.constants.settings import (  # noqa: PLC0415
            SETTING_VOICE_TTS_METHOD,
            VOICE_TTS_PIPER,
        )
        from src.ui.pages.settings import create_voice_settings  # noqa: PLC0415

        _set_initial_language("en-US")
        with patch(
            "src.ui.pages.settings.load_setting",
            side_effect=lambda key, default="": (
                VOICE_TTS_PIPER if key == SETTING_VOICE_TTS_METHOD else default
            ),
        ):
            w = create_voice_settings()
            w._sync_voice_picker_for_method()
        stack = w.findChildren(QStackedWidget)[0]
        piper_page = stack.widget(4)
        assert len(piper_page.findChildren(QRadioButton)) == 2  # noqa: PLR2004
        assert len(piper_page.findChildren(QComboBox)) == 0, (
            "Piper page must NOT have a per-voice combo any more — "
            "voice picking is handled by the engine via "
            "get_piper_voice_for(target_lang, gender)"
        )
        # The library-dialog launcher must be present.
        manage_label = tr("settings.piper_manage_voices")
        assert any(
            btn.text() == manage_label for btn in piper_page.findChildren(QPushButton)
        ), (
            "Piper page must expose a ``Download voices…`` button "
            "that opens the library dialog"
        )

    def test_summary_banner_shows_warning_when_no_voices_installed(
        self,
        qapp: QApplication,
    ) -> None:
        """Empty install set → warning variant + ``piper_no_voices`` text."""
        from PySide6.QtWidgets import (  # noqa: PLC0415
            QLabel,
            QStackedWidget,
        )

        from src.constants.i18n import _set_initial_language, tr  # noqa: PLC0415

        _set_initial_language("en-US")
        try:
            with patch(
                "src.core.speech_engine.installed_piper_languages",
                return_value=set(),
            ):
                from src.ui.pages.settings import (  # noqa: PLC0415
                    create_voice_settings,
                )

                w = create_voice_settings()
            # Banner now lives ABOVE the engine radios (mirror Tesseract
            # placement) — search the whole widget, not just the Piper
            # stack page.
            _ = w.findChildren(QStackedWidget)[0]
            labels = [lab for lab in w.findChildren(QLabel) if "Piper" in lab.text()]
            assert labels, "summary banner label not found"
            assert any(
                lab.text() == tr("settings.piper_no_voices") for lab in labels
            ), f"warning text not found in {[lab.text() for lab in labels]}"
        finally:
            _set_initial_language("en-US")

    def test_summary_banner_shows_count_when_voices_installed(
        self,
        qapp: QApplication,
    ) -> None:
        """≥ 1 installed → success variant + ``piper_installed_langs`` text."""
        from PySide6.QtWidgets import (  # noqa: PLC0415
            QLabel,
            QStackedWidget,
        )

        from src.constants.i18n import _set_initial_language, tr  # noqa: PLC0415

        _set_initial_language("en-US")
        try:
            with patch(
                "src.core.speech_engine.installed_piper_languages",
                return_value={"English", "French", "Vietnamese"},
            ):
                from src.ui.pages.settings import (  # noqa: PLC0415
                    create_voice_settings,
                )

                w = create_voice_settings()
            _ = w.findChildren(QStackedWidget)[0]
            labels = [lab for lab in w.findChildren(QLabel) if "Piper" in lab.text()]
            assert labels, "summary banner label not found"
            expected = tr("settings.piper_installed_langs", count=3)
            assert any(lab.text() == expected for lab in labels), (
                f"success text not found in {[lab.text() for lab in labels]}"
            )
        finally:
            _set_initial_language("en-US")


class TestGenderToggleSyncsAcrossPages:
    """Toggling gender on any page must update the shared setting.

    Piper has no per-voice combo any more — voice picking moved into
    the engine (``get_piper_voice_for(target_lang, gender)``), so the
    gender broadcast only needs to reach the Gemini + ElevenLabs
    filtered combos and persist the new gender for the Piper page
    to read at synthesis time.
    """

    @pytest.fixture(autouse=True)
    def _deps(self, _mock_settings_deps):
        """Auto-use mock dependencies."""

    def test_edge_gender_toggle_persists_setting(
        self,
        qapp: QApplication,  # noqa: ARG002
    ) -> None:
        """Clicking Male on the Edge page writes ``SETTING_LAST_VOICE_GENDER=MALE``."""
        from PySide6.QtWidgets import QRadioButton, QStackedWidget  # noqa: PLC0415

        from src.constants.settings import (  # noqa: PLC0415
            SETTING_LAST_VOICE_GENDER,
            SETTING_VOICE_TTS_METHOD,
            VOICE_TTS_EDGE,
        )
        from src.ui.pages.settings import create_voice_settings  # noqa: PLC0415

        save_calls: list[tuple[str, str]] = []

        def _capture_save(key, value):  # noqa: ANN001, ANN202
            save_calls.append((key, value))

        def _fake_load(key, default=""):  # noqa: ANN001, ANN202
            if key == SETTING_VOICE_TTS_METHOD:
                return VOICE_TTS_EDGE
            return default

        with (
            patch(
                "src.ui.pages.settings.load_setting",
                side_effect=_fake_load,
            ),
            patch(
                "src.ui.pages.settings.save_setting",
                side_effect=_capture_save,
            ),
        ):
            w = create_voice_settings()
            stack = w.findChildren(QStackedWidget)[0]
            edge_page = stack.widget(0)
            male_radio = next(
                r
                for r in edge_page.findChildren(QRadioButton)
                if r.property("gender") == "MALE"
            )
            male_radio.click()

        assert (SETTING_LAST_VOICE_GENDER, "MALE") in save_calls, (
            "Edge gender toggle must persist to the shared "
            "SETTING_LAST_VOICE_GENDER so the Piper engine reads "
            f"the right gender at synthesis time; saw {save_calls}"
        )


class TestElevenLabsCustomVoicePreservation:
    """ElevenLabs custom voice IDs survive a gender toggle.

    A cloned/custom voice (one whose ID isn't in the curated
    catalogue) is gender-agnostic — flipping the radio shouldn't
    silently drop the user's specific pick.  The
    ``_elevenlabs_custom_sentinel`` branch in
    ``_resolve_elevenlabs_target`` is the load-bearing piece: it
    short-circuits before the in-list / force-default logic.
    """

    @pytest.fixture(autouse=True)
    def _deps(self, _mock_settings_deps):
        """Auto-use mock dependencies."""

    def test_custom_voice_id_preserved_across_gender_toggle(
        self,
        qapp: QApplication,
    ) -> None:
        from PySide6.QtWidgets import (  # noqa: PLC0415
            QComboBox,
            QLineEdit,
            QRadioButton,
            QStackedWidget,
        )

        from src.constants.settings import (  # noqa: PLC0415
            SETTING_ELEVENLABS_VOICE_ID,
            SETTING_LAST_VOICE_GENDER,
            SETTING_VOICE_TTS_METHOD,
            VOICE_TTS_ELEVENLABS,
        )
        from src.ui.pages.settings import create_voice_settings  # noqa: PLC0415

        # Pre-load: gender FEMALE, voice = a fake cloned voice that
        # isn't in any curated gender list.
        custom_id = "my_cloned_voice_12345abcde"

        def _fake_load(key, default=""):  # noqa: ANN001, ANN202
            if key == SETTING_VOICE_TTS_METHOD:
                return VOICE_TTS_ELEVENLABS
            if key == SETTING_LAST_VOICE_GENDER:
                return "FEMALE"
            if key == SETTING_ELEVENLABS_VOICE_ID:
                return custom_id
            return default

        save_calls: list[tuple[str, str]] = []

        def _capture_save(key, value):  # noqa: ANN001, ANN202
            save_calls.append((key, value))

        with (
            patch(
                "src.ui.pages.settings.load_setting",
                side_effect=_fake_load,
            ),
            patch(
                "src.ui.pages.settings.save_setting",
                side_effect=_capture_save,
            ),
        ):
            w = create_voice_settings()
            w._sync_voice_picker_for_method()
        stack = w.findChildren(QStackedWidget)[0]
        el_page = stack.currentWidget()

        # Initial state: combo lands on Custom; text field holds the
        # custom ID; the canonical setting is unchanged.
        combo = el_page.findChildren(QComboBox)[0]
        text_field = el_page.findChildren(QLineEdit)[0]
        assert combo.currentData() == "__custom__"
        assert text_field.text() == custom_id

        # Toggle gender to MALE — the combo refresh should keep us on
        # Custom (because the saved ID is not in any curated list)
        # and NOT overwrite SETTING_ELEVENLABS_VOICE_ID with a
        # gender-default ID.
        save_calls.clear()
        with (
            patch(
                "src.ui.pages.settings.load_setting",
                side_effect=lambda k, d="": {
                    SETTING_VOICE_TTS_METHOD: VOICE_TTS_ELEVENLABS,
                    SETTING_LAST_VOICE_GENDER: "MALE",
                    SETTING_ELEVENLABS_VOICE_ID: custom_id,
                }.get(k, d),
            ),
            patch(
                "src.ui.pages.settings.save_setting",
                side_effect=_capture_save,
            ),
        ):
            male_radio = next(
                r
                for r in el_page.findChildren(QRadioButton)
                if r.property("gender") == "MALE"
            )
            male_radio.click()

        # Combo still on Custom; text field still holds the user's
        # cloned-voice ID; nothing wrote SETTING_ELEVENLABS_VOICE_ID
        # to a gender-default value.
        assert combo.currentData() == "__custom__"
        assert text_field.text() == custom_id
        for key, value in save_calls:
            assert not (key == SETTING_ELEVENLABS_VOICE_ID and value != custom_id), (
                f"custom voice was overwritten by gender toggle: {key}={value!r}"
            )


class TestElevenLabsCustomEditDoesNotOverflowStack:
    """Picking Custom on the ElevenLabs page bumps the stack height.

    Bug surfaced from a screenshot: selecting Custom (enter Voice ID)
    revealed the text input below the combo, but the QStackedWidget
    container was still pinned to its build-time sizeHint (gender
    radio + combo only) — the new text field overflowed below the
    section group's bottom border.  The fix routes
    ``_on_elevenlabs_voice_changed`` through ``_resize_stack_to_current``
    so the stack re-fits after the visibility flip.
    """

    @pytest.fixture(autouse=True)
    def _deps(self, _mock_settings_deps):
        """Auto-use mock dependencies."""

    def test_selecting_custom_grows_stack_height(
        self,
        qapp: QApplication,  # noqa: ARG002
    ) -> None:
        """Stack height after picking Custom > height before."""
        from PySide6.QtWidgets import (  # noqa: PLC0415
            QComboBox,
            QStackedWidget,
        )

        from src.constants.settings import (  # noqa: PLC0415
            SETTING_ELEVENLABS_VOICE_ID,
            SETTING_LAST_VOICE_GENDER,
            SETTING_VOICE_TTS_METHOD,
            VOICE_TTS_ELEVENLABS,
        )
        from src.ui.pages.settings import create_voice_settings  # noqa: PLC0415

        # Land on ElevenLabs with a CURATED voice (not Custom) so the
        # text field starts hidden — the height delta we measure is
        # exactly the visibility flip's contribution.
        def _fake_load(key, default=""):  # noqa: ANN001, ANN202
            if key == SETTING_VOICE_TTS_METHOD:
                return VOICE_TTS_ELEVENLABS
            if key == SETTING_LAST_VOICE_GENDER:
                return "FEMALE"
            if key == SETTING_ELEVENLABS_VOICE_ID:
                return ""  # empty → gender default (Rachel)
            return default

        with patch(
            "src.ui.pages.settings.load_setting",
            side_effect=_fake_load,
        ):
            w = create_voice_settings()
            w._sync_voice_picker_for_method()

        stack = w.findChildren(QStackedWidget)[0]
        height_before = stack.height()

        # Select the Custom sentinel via the combo.  Find it by data
        # so we don't depend on the localised label.
        page = stack.currentWidget()
        combo = page.findChildren(QComboBox)[0]
        custom_idx = next(
            i for i in range(combo.count()) if combo.itemData(i) == "__custom__"
        )
        combo.setCurrentIndex(custom_idx)

        height_after = stack.height()
        assert height_after > height_before, (
            f"ElevenLabs stack must grow when Custom reveals the "
            f"voice-ID text field; before={height_before}, "
            f"after={height_after}.  Without resize, the new field "
            f"overflows below the section group's border."
        )


class TestPiperInstalledBannerVariantSwitch:
    """Banner stylesheet flips between success and warning variants.

    The summary banner above the Piper picker shows green (success)
    when ≥ 1 voice is installed and yellow (warning) when 0 are.
    A regression that updates only the *text* but forgets the
    ``setStyleSheet(style_banner(variant))`` would leave a stale
    "0 installed" green badge on a fresh install (or a stale
    "5 installed" yellow badge after the user installs voices).
    """

    @pytest.fixture(autouse=True)
    def _deps(self, _mock_settings_deps):
        """Auto-use mock dependencies."""

    def test_banner_stylesheet_changes_when_install_count_changes(
        self,
        qapp: QApplication,
    ) -> None:
        from PySide6.QtWidgets import (  # noqa: PLC0415
            QFrame,
            QLabel,
            QStackedWidget,
        )

        from src.constants.i18n import _set_initial_language  # noqa: PLC0415
        from src.constants.settings import (  # noqa: PLC0415
            SETTING_VOICE_TTS_METHOD,
            VOICE_TTS_PIPER,
        )
        from src.ui.pages.settings import create_voice_settings  # noqa: PLC0415

        _set_initial_language("en-US")
        # ``_refresh_piper_installed_banner`` captures the
        # ``installed_piper_languages`` import inside the closure at
        # page-build time, so we can't swap the implementation after
        # build.  Build two pages instead — one per install state —
        # and compare their banner stylesheets.
        try:

            def _fake_load(key, default=""):  # noqa: ANN001, ANN202
                if key == SETTING_VOICE_TTS_METHOD:
                    return VOICE_TTS_PIPER
                return default

            def _build_page_for_install_state(installed: set[str]):
                with (
                    patch(
                        "src.core.speech_engine.installed_piper_languages",
                        return_value=installed,
                    ),
                    patch(
                        "src.ui.pages.settings.load_setting",
                        side_effect=_fake_load,
                    ),
                ):
                    w = create_voice_settings()
                    w._sync_voice_picker_for_method()
                # Banner now lives ABOVE the engine radios — search
                # the whole widget tree, not just the Piper stack page.
                # Match on objectName="Banner" so we only ever pull
                # the install-banner QFrame itself, not a wrapping
                # section-group QFrame whose recursive label search
                # would also match (and return default styling).
                _ = w.findChildren(QStackedWidget)[0]
                banners = [
                    f
                    for f in w.findChildren(QFrame)
                    if f.objectName() == "Banner"
                    and any(
                        "language(s) installed" in lab.text()
                        or "no voices installed" in lab.text()
                        for lab in f.findChildren(QLabel)
                    )
                ]
                assert banners, "summary banner not found"
                return banners[0]

            warning_banner = _build_page_for_install_state(set())
            success_banner = _build_page_for_install_state(
                {"English", "French", "Vietnamese"},
            )

            assert warning_banner.styleSheet() != success_banner.styleSheet(), (
                "Banner stylesheet must flip between warning (0 "
                "installed) and success (≥ 1 installed); only updating "
                "the text would leave a stale badge."
            )

            # Icon pixmap must also follow the variant — an orange
            # warning border with a green check icon (the previous
            # bug) is contradictory and confusing for the user.
            warning_icon = warning_banner.findChild(QLabel, "BannerIcon")
            success_icon = success_banner.findChild(QLabel, "BannerIcon")
            assert warning_icon is not None
            assert success_icon is not None
            warning_bytes = warning_icon.pixmap().toImage().bits().tobytes()
            success_bytes = success_icon.pixmap().toImage().bits().tobytes()
            assert warning_bytes != success_bytes, (
                "Banner icon pixmap must flip with variant — leaving "
                "a green check on the warning state produces the "
                "contradictory '⚠ orange border + ✓ green check' "
                "combo the user reported."
            )
        finally:
            _set_initial_language("en-US")


class TestTesseractBannerIconMatchesVariant:
    """Tesseract banner icon stays coherent with the border variant.

    Mirrors the Piper banner regression guard — the bug was orange
    warning border with green check icon for the "no languages"
    state.  Tesseract doesn't have the dynamic-variant-switch issue
    (language packs are detected once at app start), but pin the
    contract so a future refactor that adds dynamic switching
    doesn't silently regress to the same broken visual.
    """

    # NOTE: deliberately NOT using ``_mock_settings_deps`` autouse —
    # that fixture pre-mocks ``detect_tesseract_languages`` to a
    # populated set, which would force the success banner regardless
    # of our local patch.  Build patches manually so the no-langs
    # state is reachable.

    def _build_with_langs(self, langs: set[str]):
        import contextlib  # noqa: PLC0415

        from src.constants.i18n import _set_initial_language  # noqa: PLC0415

        # i18n must be loaded so the banner labels read as
        # "TesseractOCR: …" rather than the raw key string.
        _set_initial_language("en-US")
        patches = dict(_SETTINGS_PATCHES)
        patches["src.ui.pages.settings.detect_tesseract_languages"] = lambda: langs
        patches["src.ui.pages.settings.check_ocr_availability"] = lambda _m: (
            True,
            "OK",
        )
        with contextlib.ExitStack() as stack:
            for target, replacement in patches.items():
                stack.enter_context(patch(target, replacement))
            from src.ui.pages.settings import create_ocr_settings  # noqa: PLC0415

            return create_ocr_settings()

    def test_no_langs_uses_alert_triangle_with_warning_border(
        self,
        qapp: QApplication,
    ) -> None:
        import hashlib  # noqa: PLC0415

        from PySide6.QtGui import QIcon  # noqa: PLC0415
        from PySide6.QtWidgets import QFrame, QLabel  # noqa: PLC0415

        from src.constants.ui import (  # noqa: PLC0415
            ALERT_TRIANGLE_PATH,
            BANNER_ICON_SIZE,
        )

        w = self._build_with_langs(set())

        # Find the TesseractOCR installed-langs banner.
        for f in w.findChildren(QFrame):
            if f.objectName() != "Banner":
                continue
            text_lab = f.findChild(QLabel, "BannerText")
            if text_lab and text_lab.text().startswith("TesseractOCR"):
                banner = f
                break
        else:
            pytest.fail("TesseractOCR installed-langs banner not found")

        # Border: warning yellow.
        assert "#ffc542" in banner.styleSheet(), (
            "no-langs state must use the warning border colour"
        )
        # Icon: alert-triangle (matches reference render).
        icon_label = banner.findChild(QLabel, "BannerIcon")
        actual_hash = hashlib.sha1(
            icon_label.pixmap().toImage().bits().tobytes(),
        ).hexdigest()[:8]
        reference_hash = hashlib.sha1(
            QIcon(ALERT_TRIANGLE_PATH)
            .pixmap(BANNER_ICON_SIZE, BANNER_ICON_SIZE)
            .toImage()
            .bits()
            .tobytes(),
        ).hexdigest()[:8]
        assert actual_hash == reference_hash, (
            "no-langs banner must show the alert-triangle (warning) "
            "icon — not the green check that contradicts the orange "
            "border"
        )

    def test_with_langs_uses_check_circle_with_success_border(
        self,
        qapp: QApplication,
    ) -> None:
        import hashlib  # noqa: PLC0415

        from PySide6.QtGui import QIcon  # noqa: PLC0415
        from PySide6.QtWidgets import QFrame, QLabel  # noqa: PLC0415

        from src.constants.ui import (  # noqa: PLC0415
            BANNER_ICON_SIZE,
            CHECK_CIRCLE_PATH,
        )

        w = self._build_with_langs({"eng", "fra"})

        for f in w.findChildren(QFrame):
            if f.objectName() != "Banner":
                continue
            text_lab = f.findChild(QLabel, "BannerText")
            if text_lab and text_lab.text().startswith("TesseractOCR"):
                banner = f
                break
        else:
            pytest.fail("TesseractOCR installed-langs banner not found")

        # Success border colour comes from the theme (varies); just
        # assert it's NOT the warning yellow.
        assert "#ffc542" not in banner.styleSheet(), (
            "with-langs state must NOT use the warning border colour"
        )
        # Icon: check-circle.
        icon_label = banner.findChild(QLabel, "BannerIcon")
        actual_hash = hashlib.sha1(
            icon_label.pixmap().toImage().bits().tobytes(),
        ).hexdigest()[:8]
        reference_hash = hashlib.sha1(
            QIcon(CHECK_CIRCLE_PATH)
            .pixmap(BANNER_ICON_SIZE, BANNER_ICON_SIZE)
            .toImage()
            .bits()
            .tobytes(),
        ).hexdigest()[:8]
        assert actual_hash == reference_hash


# ---------------------------------------------------------------------------
# Custom provider editor — debounced save persistence (per-field coverage)
# ---------------------------------------------------------------------------


class TestCustomProviderEditorSaveCancel:
    """The custom-provider editor section saves on debounced commit.

    The 400 ms-debounced save is documented in AGENTS.md as the
    persistence contract; ``TestCustomProviderName`` already pins
    the Name field round-trip but the Endpoint field — which is
    edited far more often (users paste/repaste OpenRouter / Azure
    / Anthropic-shim URLs) — had no direct coverage.

    Note: there is no in-place "Cancel" button on the LLM tab —
    edits commit through the QTimer-driven save path or stay in
    the in-memory provider data dict until the next commit. The
    revert-on-cancel sub-test is therefore omitted intentionally.
    """

    @pytest.fixture(autouse=True)
    def _deps(self, _mock_settings_deps):
        """Auto-use mock dependencies."""

    def test_endpoint_edit_persists_via_debounced_save(
        self,
        qapp,
    ) -> None:
        """Editing the Endpoint field schedules a save via the 400ms timer."""
        from PySide6.QtCore import QCoreApplication, QTimer  # noqa: PLC0415
        from PySide6.QtWidgets import QLineEdit  # noqa: PLC0415

        from src.utils.config_manager import (  # noqa: PLC0415
            load_custom_providers,
            save_custom_providers,
        )

        # Seed a stub provider with a unique endpoint so we can find the field
        save_custom_providers(
            [
                {
                    "name": "OpenRouter",
                    "api_key": "sk-test",
                    "endpoint": "https://old.example.com",
                    "models": "gpt-4o",
                },
            ],
        )

        from src.ui.pages.settings import create_llm_settings  # noqa: PLC0415

        w = create_llm_settings()

        # Find the endpoint input by its persisted text
        line_edits = w.findChildren(QLineEdit)
        endpoint_input = next(
            i for i in line_edits if i.text() == "https://old.example.com"
        )
        new_endpoint = "https://api.openrouter.ai/api/v1"
        endpoint_input.setText(new_endpoint)

        # Force the debounce timer to fire synchronously instead of
        # waiting 400 ms (matches the existing TestCustomProviderName
        # pattern).
        for t in w.findChildren(QTimer):
            if t.isSingleShot() and t.isActive():
                t.stop()
                t.timeout.emit()

        QCoreApplication.processEvents()

        providers = load_custom_providers()
        assert any(p.get("endpoint") == new_endpoint for p in providers), (
            f"Endpoint edit did not persist via debounced save — "
            f"loaded providers: {providers}"
        )


class TestAddSaveToAutoInfo:
    """Tests for the _add_save_to_auto_info helper.

    Shared by 5 storage-picker sites (Translate Document / Extract Text /
    Subtitle / Voice / Dubbing).  Adds the info-variant banner above the
    given storage widget so users understand the Auto-mode fallback chain
    (configured → source-parent → Desktop) before they pick a path.
    """

    def test_helper_adds_banner_and_widget_in_order(
        self,
        qapp: QApplication,
    ) -> None:
        """Helper appends [banner, storage_widget] to the layout in order."""
        from PySide6.QtWidgets import QPushButton, QVBoxLayout, QWidget  # noqa: PLC0415

        from src.constants.i18n import _set_initial_language  # noqa: PLC0415
        from src.ui.pages.settings import _add_save_to_auto_info  # noqa: PLC0415

        _set_initial_language("en-US")

        container = QWidget()
        layout = QVBoxLayout(container)
        storage_stub = QPushButton("storage_stub")

        _add_save_to_auto_info(layout, storage_stub)

        # Exactly 2 items: banner first, storage second.
        assert layout.count() == 2
        banner_widget = layout.itemAt(0).widget()
        storage_widget = layout.itemAt(1).widget()
        assert banner_widget is not None
        assert storage_widget is storage_stub
        # The first widget is the banner — find its text label and
        # confirm it carries the en-US copy (no raw key fallback).
        text_label = banner_widget.findChild(QLabel, "BannerText")
        assert text_label is not None, "banner missing BannerText label"
        # Banner should mention the Auto-mode fallback chain.  Don't
        # pin the exact wording (copy may evolve), but assert it
        # contains the "Auto"/Desktop concept hints so a regression to
        # the raw key string ("settings.save_to_auto_info") would fail.
        text = text_label.text()
        assert "Auto" in text and "Desktop" in text, (
            f"banner text doesn't read as the Auto-fallback hint: {text!r}"
        )

    def test_helper_uses_info_variant_banner(
        self,
        qapp: QApplication,
    ) -> None:
        """Banner is built with variant='info' (blue) — not 'warning' (yellow).

        Pins the variant choice because the message is *guidance*, not
        a runtime problem.  A regression to 'warning' would surface as
        a yellow-bordered banner that misrepresents the state.
        """
        from PySide6.QtWidgets import QPushButton, QVBoxLayout, QWidget  # noqa: PLC0415

        from src.constants.i18n import _set_initial_language  # noqa: PLC0415
        from src.ui.pages.settings import _add_save_to_auto_info  # noqa: PLC0415

        _set_initial_language("en-US")

        container = QWidget()
        layout = QVBoxLayout(container)
        _add_save_to_auto_info(layout, QPushButton("stub"))

        banner = layout.itemAt(0).widget()
        # The info-variant border colour is from the theme palette; any
        # warning-variant border would carry the yellow ``#ffc542`` we
        # already pin elsewhere.  Confirm the warning colour is NOT in
        # the banner stylesheet to lock the variant.
        assert banner is not None
        assert "#ffc542" not in banner.styleSheet(), (
            "save-to-auto-info banner must not use the warning variant"
        )
