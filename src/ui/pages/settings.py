"""Settings page UI for the AI Translate application."""

import platform
from collections.abc import Callable

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QHideEvent, QIcon, QKeyEvent
from PySide6.QtWidgets import (
    QApplication,
    QBoxLayout,
    QButtonGroup,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QSizePolicy,
    QSlider,
    QStackedWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from src.constants import (
    FLAG_ICON_HEIGHT,
    FLAG_ICON_WIDTH,
    FLAGS_DIR,
    HEIGHT_CONTROL,
    LABEL_WIDTH,
    LLM_METHOD_GEMINI,
    MARGIN_SECTION,
    MARGIN_SUBSECTION,
    OCR_METHOD_EASYOCR,
    OCR_METHOD_GOOGLE_CLOUD,
    OCR_METHOD_TESSERACT,
    OCR_METHODS,
    SETTING_AUTO_CONVERT_LEGACY,
    SETTING_AUTO_CONVERT_ODF,
    SETTING_AUTO_REMOVE_HISTORY,
    SETTING_GOOGLE_CLOUD_API_KEY,
    SETTING_LIBREOFFICE_PATH,
    SETTING_LLM_GEMINI_API_KEY,
    SETTING_LLM_GEMINI_MODEL,
    SETTING_OCR_METHOD,
    SETTING_STORAGE_PATH,
    SETTING_THEME,
    SETTING_TRANSLATE_DOC_COMMENTS,
    SETTING_TRANSLATE_DOC_IMAGES,
    SETTING_TRANSLATE_DOC_NOTES,
    SETTING_TRANSLATE_DOC_SHAPES,
    SETTING_TRANSLATE_SHEET_NAMES,
    SETTING_UI_LANGUAGE,
    SPACING_SECTION,
    SPACING_SUBSECTION,
    UI_LANGUAGES,
    color,
    language_changed,
    set_language,
    set_theme,
    style_delete_button,
    style_input_field,
    style_input_label,
    style_outlined_primary_button,
    style_radio_button,
    style_secondary_button,
    style_setting_combo,
    style_setting_container,
    style_tab_widget,
    style_table_delete_button,
    theme_changed,
    tr,
)
from src.ui.components import (
    create_banner,
    create_page_container,
    create_scrollable_container,
    create_section_group,
    create_setting_checkbox,
    create_setting_combo,
    create_setting_input,
    create_setting_path,
    remask_secrets,
)
from src.utils.config_manager import (
    check_libreoffice_available,
    check_llm_setup,
    check_msoffice_available,
    check_ocr_setup,
    check_office_converter_setup,
    load_setting,
    save_setting,
)
from src.utils.ocr_checker import check_ocr_availability, detect_tesseract_languages


def _bind_text(widget: QWidget, tr_key: str, **kwargs: object) -> None:
    """Wires a widget's text to a translation key for live re-translation.

    Sets the widget's current text from ``tr(tr_key, **kwargs)`` and
    attaches an ``apply_language`` attribute that re-runs the lookup.
    The window's language-changed broadcast iterates every QWidget via
    ``findChildren`` and invokes any ``apply_language`` it finds, so
    this attribute is enough for the locale to propagate without any
    page-level bookkeeping.

    Used for inline ``QLabel`` / ``QPushButton`` / ``QRadioButton``
    instances that don't go through ``create_setting_*`` helpers
    (which already wire ``apply_language`` themselves via
    ``label_tr_key=``).
    """
    text = tr(tr_key, **kwargs)
    widget.setText(text)

    def _apply() -> None:
        widget.setText(tr(tr_key, **kwargs))

    widget.apply_language = _apply  # type: ignore[attr-defined]


def _add_save_to_auto_info(
    out_layout: QBoxLayout,
    storage_widget: QWidget,
) -> None:
    """Adds the Auto-fallback info banner above the storage-path widget.

    Five tabs (Translate Document, Extract Text, Subtitle, Voice, Dubbing)
    show the same banner explaining the Auto-mode fallback chain
    (configured → source-parent → Desktop), so a deleted / read-only /
    unmounted source folder silently redirects output to the Desktop
    instead of crashing the pipeline.  Extracted to keep the per-tab
    builders DRY — the banner is identical at every site.
    """
    banner_frame, _ = create_banner(
        tr("settings.save_to_auto_info"),
        variant="info",
        tr_key="settings.save_to_auto_info",
    )
    out_layout.addWidget(banner_frame)
    out_layout.addWidget(storage_widget)


def auto_fallback_selection(
    button_group: QButtonGroup,
    setting_key: str,
    *,
    persist: bool = True,
) -> None:
    """Ensures a valid selection exists in the group, falling back if necessary.

    Args:
        button_group: The group of radio buttons.
        setting_key: The persistent setting key to update.
        persist: Whether to save the fallback to settings. Set to False
            during initialization to avoid overwriting user preferences
            when a method is temporarily unavailable.
    """
    current = button_group.checkedButton()

    # If something is selected and it's still enabled, we are good.
    if current and current.isEnabled():
        return

    # If something was selected but now it's disabled (or nothing was selected),
    # try to find an alternative.
    for btn in button_group.buttons():
        if btn.isEnabled():
            btn.setChecked(True)
            if persist:
                # Prefer an internal "method" property so localized labels
                # don't leak into the persisted value.
                value = btn.property("method") or btn.text()
                save_setting(setting_key, value)
            return

    # No enabled options found, clear selection and setting.
    if current:
        button_group.setExclusive(False)
        current.setChecked(False)
        button_group.setExclusive(True)
    if persist:
        save_setting(setting_key, "")


def create_service_settings() -> QWidget:
    """Creates the Service settings tab for external API keys.

    Holds credentials for Google Cloud (shared across Vision OCR, STT, TTS),
    Soniox (real-time STT), and ElevenLabs (neural TTS).
    """
    from src.constants.settings import (  # noqa: PLC0415
        SETTING_ELEVENLABS_API_KEY,
        SETTING_SONIOX_API_KEY,
    )

    widget = QWidget()
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(0, MARGIN_SECTION, 0, 0)
    layout.setSpacing(SPACING_SECTION)

    # Cross-reference: Gemini credentials live on the LLM tab, not here.
    gemini_ref_frame, _ = create_banner(
        tr("settings.service_gemini_reference"),
        variant="info",
        tr_key="settings.service_gemini_reference",
    )
    layout.addWidget(gemini_ref_frame)

    # Google Cloud section
    cloud_group, cloud_layout, _ = create_section_group(
        tr("settings.google_cloud"),
        tr_key="settings.google_cloud",
    )

    # Info banner
    cloud_info_frame, _ = create_banner(
        tr("settings.google_cloud_info"),
        variant="info",
        tr_key="settings.google_cloud_info",
    )
    cloud_layout.addWidget(cloud_info_frame)

    # API Key input
    api_key_widget, api_key_input = create_setting_input(
        tr("settings.cloud_api_key"),
        SETTING_GOOGLE_CLOUD_API_KEY,
        tr("settings.cloud_api_key_placeholder"),
        is_password=True,
        label_tr_key="settings.cloud_api_key",
        placeholder_tr_key="settings.cloud_api_key_placeholder",
    )
    cloud_layout.addWidget(api_key_widget)
    layout.addWidget(cloud_group)

    # Soniox section
    soniox_group, soniox_layout, _ = create_section_group(
        tr("settings.soniox"),
        tr_key="settings.soniox",
    )
    soniox_info_frame, _ = create_banner(
        tr("settings.soniox_info"),
        variant="info",
        tr_key="settings.soniox_info",
    )
    soniox_layout.addWidget(soniox_info_frame)

    soniox_key_widget, _ = create_setting_input(
        tr("settings.soniox_api_key"),
        SETTING_SONIOX_API_KEY,
        tr("settings.soniox_api_key_placeholder"),
        is_password=True,
        label_tr_key="settings.soniox_api_key",
        placeholder_tr_key="settings.soniox_api_key_placeholder",
    )
    soniox_layout.addWidget(soniox_key_widget)
    layout.addWidget(soniox_group)

    # ElevenLabs section
    el_group, el_layout, _ = create_section_group(
        tr("settings.elevenlabs"),
        tr_key="settings.elevenlabs",
    )
    el_info_frame, _ = create_banner(
        tr("settings.elevenlabs_info"),
        variant="info",
        tr_key="settings.elevenlabs_info",
    )
    el_layout.addWidget(el_info_frame)

    el_key_widget, _ = create_setting_input(
        tr("settings.elevenlabs_api_key"),
        SETTING_ELEVENLABS_API_KEY,
        tr("settings.elevenlabs_api_key_placeholder"),
        is_password=True,
        label_tr_key="settings.elevenlabs_api_key",
        placeholder_tr_key="settings.elevenlabs_api_key_placeholder",
    )
    el_layout.addWidget(el_key_widget)
    # Voice ID lives on the Generate Voice (TTS) tab next to the
    # engine selector — the Service tab is reserved for credentials
    # (API keys), so per-engine behaviour config (voice picks, model
    # selection) goes with the engine choice itself.
    layout.addWidget(el_group)

    layout.addStretch()
    return widget


def create_ocr_settings() -> QWidget:  # noqa: PLR0915
    """Creates the OCR settings tab content.

    Exposes the OCR backend selection (Tesseract / EasyOCR / Google Cloud OCR),
    a Tesseract installed-language summary, and gates the Google Cloud OCR
    radio on the Service-tab API key.
    """
    from src.utils.config_manager import check_google_cloud_setup  # noqa: PLC0415

    method_tr_keys = {
        OCR_METHOD_TESSERACT: "settings.ocr_tesseract",
        OCR_METHOD_EASYOCR: "settings.ocr_easyocr",
        OCR_METHOD_GOOGLE_CLOUD: "settings.ocr_google",
    }

    widget = QWidget()
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(0, MARGIN_SECTION, 0, 0)
    layout.setSpacing(SPACING_SECTION)

    ocr_group, ocr_layout, _ = create_section_group(
        tr("settings.ocr_config"),
        tr_key="settings.ocr_config",
    )

    # Info banner explaining what OCR is used for
    ocr_info_frame, _ = create_banner(
        tr("settings.ocr_info"),
        variant="info",
        tr_key="settings.ocr_info",
    )
    ocr_layout.addWidget(ocr_info_frame)

    # Comparison banner describing each OCR method's characteristics
    ocr_comparison_frame, _ = create_banner(
        tr("settings.ocr_comparison"),
        variant="info",
        tr_key="settings.ocr_comparison",
        rich_text=True,
    )
    ocr_layout.addWidget(ocr_comparison_frame)

    # Tesseract status banner (shown above radio buttons).  Three states:
    #   1. Binary missing       → warning with OS-aware install instructions
    #   2. Binary + no langs    → warning telling the user to add packs
    #   3. Binary + N langs     → success with the live count
    # The banner is rich-text from construction so the install variant
    # can render the ``<a href>`` link + ``<code>`` block; plain-text
    # variants pass through unchanged.  Refreshed on tab show so a user
    # who installs Tesseract in another terminal sees the update without
    # restarting.
    tess_banner, tess_label = create_banner(
        "",
        variant="warning",
        rich_text=True,
    )
    ocr_layout.addWidget(tess_banner)

    def _refresh_tesseract_banner() -> None:  # noqa: PLR0912 — per-OS + state dispatch
        """Re-detects Tesseract state and re-skins the banner accordingly."""
        from PySide6.QtGui import QIcon  # noqa: PLC0415
        from PySide6.QtWidgets import QLabel  # noqa: PLC0415

        from src.constants import style_banner  # noqa: PLC0415
        from src.constants.ui import (  # noqa: PLC0415
            ALERT_TRIANGLE_PATH,
            BANNER_ICON_SIZE,
            CHECK_CIRCLE_PATH,
        )
        from src.utils.install_hints import format_install_clause  # noqa: PLC0415
        from src.utils.ocr_checker import (  # noqa: PLC0415
            get_tesseract_install_hint,
            get_tesseract_langpack_install_hint,
        )

        is_installed, _ = check_ocr_availability(OCR_METHOD_TESSERACT)
        if not is_installed:
            # Per-OS dispatch follows the same convention as
            # ``LivePage._sync_system_audio_warning`` — pick exactly
            # one platform's instructions and inline the auto-detected
            # package-manager command for Linux.  ``format_install_clause``
            # gracefully empties when no package manager is recognised so
            # the base banner reads cleanly on exotic distros.
            system = platform.system()
            if system == "Linux":
                key = "settings.ocr_tesseract_install_linux"
                text = tr(
                    key,
                    linux_install=format_install_clause(get_tesseract_install_hint()),
                )
            elif system == "Darwin":
                key = "settings.ocr_tesseract_install_macos"
                text = tr(key)
            elif system == "Windows":
                key = "settings.ocr_tesseract_install_windows"
                text = tr(key)
            else:
                key = "settings.ocr_tesseract_install_unsupported"
                text = tr(key)
            variant = "warning"
        else:
            langs = detect_tesseract_languages()
            if langs:
                text = tr("settings.ocr_tesseract_langs", count=len(langs))
                variant = "success"
            else:
                # Same per-OS dispatcher as the missing-binary case —
                # the install command differs (language pack vs binary)
                # but the user-facing pattern is identical.
                system = platform.system()
                if system == "Linux":
                    text = tr(
                        "settings.ocr_tesseract_no_langs_linux",
                        linux_install=format_install_clause(
                            get_tesseract_langpack_install_hint(),
                        ),
                    )
                elif system == "Darwin":
                    text = tr("settings.ocr_tesseract_no_langs_macos")
                elif system == "Windows":
                    text = tr("settings.ocr_tesseract_no_langs_windows")
                else:
                    text = tr("settings.ocr_tesseract_no_langs_unsupported")
                variant = "warning"

        tess_label.setText(text)
        tess_banner.setStyleSheet(style_banner(variant))
        icon_label = tess_banner.findChild(QLabel, "BannerIcon")
        if icon_label is not None:
            icon_path = (
                CHECK_CIRCLE_PATH if variant == "success" else ALERT_TRIANGLE_PATH
            )
            icon_label.setPixmap(
                QIcon(icon_path).pixmap(BANNER_ICON_SIZE, BANNER_ICON_SIZE),
            )

    tess_banner.apply_language = _refresh_tesseract_banner
    _refresh_tesseract_banner()

    # EasyOCR install banner — visible only when the optional package
    # isn't installed.  Unlike Tesseract there's no per-OS dispatch
    # (the install command is ``pip install easyocr`` everywhere) and
    # no "no language packs" intermediate state, so this is just a
    # binary show/hide.
    easyocr_install_banner, _ = create_banner(
        tr("settings.ocr_easyocr_install"),
        variant="warning",
        tr_key="settings.ocr_easyocr_install",
        rich_text=True,
    )
    easyocr_install_banner.setVisible(
        not check_ocr_availability(OCR_METHOD_EASYOCR)[0],
    )
    ocr_layout.addWidget(easyocr_install_banner)

    # Radio buttons for OCR methods
    button_group = QButtonGroup(widget)
    button_group.setExclusive(True)

    methods_layout = QVBoxLayout()
    methods_layout.setContentsMargins(
        MARGIN_SUBSECTION, MARGIN_SUBSECTION, MARGIN_SUBSECTION, MARGIN_SUBSECTION
    )
    methods_layout.setSpacing(SPACING_SUBSECTION)

    saved_ocr = load_setting(SETTING_OCR_METHOD, "")

    for i, method in enumerate(OCR_METHODS):
        radio = QRadioButton(tr(method_tr_keys[method]))
        radio.setCursor(Qt.CursorShape.PointingHandCursor)
        radio.setStyleSheet(style_radio_button())
        radio.setProperty("method", method)
        button_group.addButton(radio, i)
        methods_layout.addWidget(radio)

        # Disable if method is not ready
        if method == OCR_METHOD_GOOGLE_CLOUD:
            # Google Cloud availability depends on the Service tab API key
            radio.setEnabled(check_google_cloud_setup())
        else:
            is_ready, _ = check_ocr_availability(method)
            radio.setEnabled(is_ready)

        if method == saved_ocr and radio.isEnabled():
            radio.setChecked(True)

    def on_ocr_method_toggled(btn: QRadioButton) -> None:
        """Persists the selected OCR method to settings."""
        if btn.isChecked():
            save_setting(SETTING_OCR_METHOD, btn.property("method"))

    button_group.buttonClicked.connect(on_ocr_method_toggled)

    # Hint shown when Google Cloud OCR is disabled (missing API key).
    # Rendered above the method radios so it precedes the control it explains.
    google_setup_hint_frame, _ = create_banner(
        tr("settings.ocr_google_setup_hint"),
        variant="warning",
        tr_key="settings.ocr_google_setup_hint",
    )
    google_setup_hint_frame.setVisible(not check_google_cloud_setup())
    ocr_layout.addWidget(google_setup_hint_frame)

    ocr_layout.addLayout(methods_layout)

    layout.addWidget(ocr_group)

    # Ensure valid initial selection and persist it so check_ocr_setup()
    # returns True immediately without requiring the user to manually
    # open Settings.
    auto_fallback_selection(button_group, SETTING_OCR_METHOD)

    def _sync_ocr_availability() -> None:
        """Re-checks OCR method availability (Tesseract/EasyOCR/Google Cloud)."""
        google_ok = check_google_cloud_setup()
        for btn in button_group.buttons():
            method = btn.property("method")
            if method == OCR_METHOD_GOOGLE_CLOUD:
                btn.setEnabled(google_ok)
            else:
                is_ready, _ = check_ocr_availability(method)
                btn.setEnabled(is_ready)
        google_setup_hint_frame.setVisible(not google_ok)
        # Re-detect Tesseract state so a user who installed the binary
        # (or added language packs) in another terminal sees the banner
        # update without restarting the app.
        _refresh_tesseract_banner()
        easyocr_install_banner.setVisible(
            not check_ocr_availability(OCR_METHOD_EASYOCR)[0],
        )
        auto_fallback_selection(button_group, SETTING_OCR_METHOD)

    widget._sync_ocr_availability = _sync_ocr_availability

    layout.addStretch()
    return widget


def _create_vertex_ai_section(parent: QWidget) -> QWidget:  # noqa: PLR0915
    """Builds the Vertex AI sub-block intended to nest INSIDE the Gemini section.

    A "Use Vertex AI" checkbox toggles a sub-panel with GCP project,
    location dropdown, and an optional service-account JSON file
    picker.  When the checkbox is off the sub-panel is hidden so users
    on the Developer API path see no clutter.  The returned widget
    has NO outer section header — it lives within the Gemini card so
    the user sees a single "Gemini" configuration block.

    All fields persist immediately via the standard ``create_setting_*``
    helpers; no submit button needed.
    """
    from src.constants import (  # noqa: PLC0415
        SETTING_LLM_GEMINI_USE_VERTEX,
        SETTING_LLM_VERTEX_CREDENTIALS,
        SETTING_LLM_VERTEX_LOCATION,
        SETTING_LLM_VERTEX_PROJECT,
        VERTEX_DEFAULT_LOCATION,
        VERTEX_LOCATIONS,
    )
    from src.ui.components import (  # noqa: PLC0415
        create_setting_combo,
        create_setting_input,
        create_setting_path,
    )

    # Header-less container: just a vertical layout that the caller
    # embeds inside the Gemini card.
    container = QWidget(parent)
    container_layout = QVBoxLayout(container)
    container_layout.setContentsMargins(0, 0, 0, 0)
    container_layout.setSpacing(SPACING_SUBSECTION)

    # ── Authentication mode: radio pair (Developer API vs Vertex AI) ──
    # Two mutually-exclusive auth modes for the same provider, so a
    # radio group communicates the relationship more honestly than a
    # checkbox.  Persistence still uses the boolean
    # ``SETTING_LLM_GEMINI_USE_VERTEX`` (False = Developer, True =
    # Vertex), so no settings migration needed.  Layout follows the
    # app-standard "label-left, controls-right" row pattern (same as
    # the Theme picker row in the General tab).
    auth_row_widget = QWidget()
    auth_row_widget.setStyleSheet(style_setting_container())
    auth_row = QHBoxLayout(auth_row_widget)
    auth_row.setContentsMargins(0, 0, 0, 0)
    auth_row.setSpacing(SPACING_SUBSECTION)

    auth_label = QLabel(tr("settings.gemini_auth_label"))
    _bind_text(auth_label, "settings.gemini_auth_label")
    auth_label.setStyleSheet(style_input_label())
    auth_label.setFixedWidth(LABEL_WIDTH)
    auth_label.setFixedHeight(HEIGHT_CONTROL)
    auth_label.setAlignment(
        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
    )
    auth_row.addWidget(auth_label)

    auth_group = QButtonGroup(container)
    auth_group.setExclusive(True)
    # ``load_setting`` returns a real bool when the default is False
    # (it parses common truthy strings); no defensive cast needed.
    use_vertex_initial = load_setting(SETTING_LLM_GEMINI_USE_VERTEX, False)

    dev_radio = QRadioButton(tr("settings.gemini_auth_dev_api"))
    dev_radio.setCursor(Qt.CursorShape.PointingHandCursor)
    dev_radio.setStyleSheet(style_radio_button())
    dev_radio.setProperty("use_vertex", False)
    auth_group.addButton(dev_radio, 0)
    auth_row.addWidget(dev_radio)

    vertex_radio = QRadioButton(tr("settings.gemini_auth_vertex"))
    vertex_radio.setCursor(Qt.CursorShape.PointingHandCursor)
    vertex_radio.setStyleSheet(style_radio_button())
    vertex_radio.setProperty("use_vertex", True)
    auth_group.addButton(vertex_radio, 1)
    auth_row.addWidget(vertex_radio)

    auth_row.addStretch()
    container_layout.addWidget(auth_row_widget)

    if use_vertex_initial:
        vertex_radio.setChecked(True)
    else:
        dev_radio.setChecked(True)

    def _on_auth_toggled(btn: QRadioButton) -> None:
        """Persists the bool-encoded auth choice."""
        if btn.isChecked():
            save_setting(SETTING_LLM_GEMINI_USE_VERTEX, str(btn.property("use_vertex")))

    auth_group.buttonClicked.connect(_on_auth_toggled)

    # Sub-panel: only visible when Vertex mode is on.
    sub_panel = QWidget(container)
    sub_layout = QVBoxLayout(sub_panel)
    sub_layout.setContentsMargins(0, 0, 0, 0)
    sub_layout.setSpacing(SPACING_SUBSECTION)

    project_widget, _ = create_setting_input(
        tr("settings.vertex_project"),
        SETTING_LLM_VERTEX_PROJECT,
        tr("settings.vertex_project_placeholder"),
        label_tr_key="settings.vertex_project",
        placeholder_tr_key="settings.vertex_project_placeholder",
    )
    sub_layout.addWidget(project_widget)

    location_widget, location_combo = create_setting_combo(
        tr("settings.vertex_location"),
        SETTING_LLM_VERTEX_LOCATION,
        list(VERTEX_LOCATIONS),
        label_tr_key="settings.vertex_location",
    )
    # Default to us-central1 when no value has been picked yet.
    if not location_combo.currentText():
        location_combo.setCurrentText(VERTEX_DEFAULT_LOCATION)
    sub_layout.addWidget(location_widget)

    creds_widget, _ = create_setting_path(
        tr("settings.vertex_credentials"),
        SETTING_LLM_VERTEX_CREDENTIALS,
        label_tr_key="settings.vertex_credentials",
        browse_mode="file",
        dialog_title_tr_key="settings.vertex_credentials_dialog_title",
        placeholder_tr_key="settings.vertex_credentials_placeholder",
    )
    sub_layout.addWidget(creds_widget)

    container_layout.addWidget(sub_panel)
    sub_panel.setVisible(vertex_radio.isChecked())
    vertex_radio.toggled.connect(sub_panel.setVisible)

    # Keep references on the parent so language / theme refreshes can
    # find them (the standard apply_language/apply_theme walkers
    # iterate findChildren — these widgets carry their own hooks).
    container.setParent(parent)
    return container


def create_provider_config(  # noqa: PLR0913
    name: str,
    api_key_setting: str,
    model_setting: str,
    models: list[str] | None,
    extra_fields: list[tuple[str, str, str, str, str]] | None = None,
    title_tr_key: str | None = None,
    hint_tr_key: str | None = None,
    show_model: bool = True,
) -> QWidget:
    """Helper to create a standardized LLM provider configuration section.

    Args:
        name: Provider display name (e.g. "Gemini", "Custom").
        api_key_setting: Persistent setting key for the API key.
        model_setting: Persistent setting key for the model.
        models: Pre-defined model list, or None for free-text input.
        extra_fields: List of (label, setting_key, placeholder,
            label_tr_key, placeholder_tr_key) tuples.
        title_tr_key: Override tr key for the section title. When set,
            the title uses ``tr(title_tr_key)`` instead of
            ``tr("settings.config_title", name=...)``.
        hint_tr_key: Optional tr key for a hint banner shown when the
            API key is empty. Supports rich text (clickable links).
        show_model: Whether to show the model combo/input widget.
            Defaults to True. Set to False to hide the model selector.
    """
    if title_tr_key:
        group, layout, _ = create_section_group(
            tr(title_tr_key),
            tr_key=title_tr_key,
        )
    else:
        group, layout, _ = create_section_group(
            tr("settings.config_title", name=name),
            tr_key="settings.config_title",
            tr_kwargs={"name": name},
        )
    # Hint banner shown when API key is empty
    hint_banner = None
    if hint_tr_key:
        hint_banner, _ = create_banner(
            tr(hint_tr_key),
            variant="info",
            tr_key=hint_tr_key,
            rich_text=True,
        )
        layout.addWidget(hint_banner)

    inputs = []

    # API Key
    api_widget, api_input = create_setting_input(
        tr("settings.api_key"),
        api_key_setting,
        tr("settings.api_key_placeholder_provider", name=name),
        is_password=True,
        label_tr_key="settings.api_key",
        placeholder_tr_key="settings.api_key_placeholder_provider",
        placeholder_tr_kwargs={"name": name},
    )
    layout.addWidget(api_widget)
    inputs.append(api_input)

    # Set initial hint banner visibility
    if hint_banner is not None:
        hint_banner.setVisible(not bool(api_input.text().strip()))

    # Extra fields (e.g., Endpoint) — placed before model for Custom provider
    for label, key, placeholder, l_key, p_key in extra_fields or []:
        widget, field_input = create_setting_input(
            label,
            key,
            placeholder,
            label_tr_key=l_key,
            placeholder_tr_key=p_key,
        )
        layout.addWidget(widget)
        inputs.append(field_input)

    # Model (Combo, TagInput, or plain Input) — only shown when show_model is True
    model_input = None
    if show_model:
        if models:
            model_widget, model_input = create_setting_combo(
                tr("settings.model"),
                model_setting,
                models,
                label_tr_key="settings.model",
            )
            layout.addWidget(model_widget)
            inputs.append(model_input)
        else:
            from src.ui.components import create_setting_tag_input  # noqa: PLC0415

            model_widget, model_input = create_setting_tag_input(
                tr("settings.model"),
                model_setting,
                tr("settings.model_placeholder"),
                label_tr_key="settings.model",
                placeholder_tr_key="settings.model_placeholder",
            )
            layout.addWidget(model_widget)
            inputs.append(model_input)

    def update_status() -> None:
        """Updates the model-input enable state and hint-banner visibility."""

        def get_val(w: QWidget) -> str:
            """Extract the text value from a QLineEdit or QComboBox."""
            if hasattr(w, "text"):
                return w.text()
            if hasattr(w, "currentText"):
                return w.currentText()
            return ""

        # Check readiness from all inputs except the model field itself,
        # so the model input stays editable when only it is empty.
        prerequisite_inputs = [
            i for i in inputs if isinstance(i, QWidget) and i is not model_input
        ]
        prereqs_filled = all(bool(get_val(i).strip()) for i in prerequisite_inputs)
        if model_input and hasattr(model_input, "setEnabled"):
            model_input.setEnabled(prereqs_filled)

        # Toggle hint banner based on API key presence
        if hint_banner is not None:
            hint_banner.setVisible(not bool(api_input.text().strip()))

    for i in inputs:
        if hasattr(i, "textChanged"):
            i.textChanged.connect(lambda _: update_status())
        elif hasattr(i, "currentTextChanged"):
            i.currentTextChanged.connect(lambda _: update_status())
        elif hasattr(i, "tags_changed"):
            i.tags_changed.connect(lambda _: update_status())

    update_status()  # Initial state
    return group


def create_llm_settings() -> QWidget:  # noqa: PLR0915
    """Creates the LLM settings tab content.

    Exposes the Gemini provider (API key + hint banner) and a dynamic list of
    custom OpenAI-compatible providers — each with Name / API key / Endpoint /
    Models fields and a remove-with-confirmation action. Custom providers
    persist as a JSON blob under ``SETTING_LLM_CUSTOM_PROVIDERS``.
    """
    widget = QWidget()
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(0, MARGIN_SECTION, 0, 0)
    layout.setSpacing(SPACING_SECTION)

    # ── Default model section ──
    # The canonical cross-feature fallback — leads the tab so users see the
    # app-wide setting first. Hidden on fresh installs (no models available
    # yet) and reveals the moment a provider is configured below.
    from src.constants.settings import SETTING_LLM_LAST_MODEL  # noqa: PLC0415
    from src.utils.config_manager import (  # noqa: PLC0415
        format_model_id,
        get_available_models,
    )

    default_group, default_layout, _ = create_section_group(
        tr("settings.default_model_title"),
        tr_key="settings.default_model_title",
    )

    default_row = QWidget()
    default_row.setStyleSheet(style_setting_container())
    default_row_layout = QHBoxLayout(default_row)
    default_row_layout.setContentsMargins(0, 0, 0, 0)

    default_label = QLabel("")
    _bind_text(default_label, "settings.default_model")
    default_label.setStyleSheet(style_input_label())
    default_label.setFixedWidth(LABEL_WIDTH)
    default_label.setFixedHeight(HEIGHT_CONTROL)
    default_label.setAlignment(
        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
    )
    default_row_layout.addWidget(default_label)

    default_combo = QComboBox()
    default_combo.setFixedHeight(HEIGHT_CONTROL)
    default_combo.setCursor(Qt.CursorShape.PointingHandCursor)
    default_combo.view().setCursor(Qt.CursorShape.PointingHandCursor)
    default_combo.view().setUniformItemSizes(True)
    default_combo.view().setSpacing(0)
    default_combo.setStyleSheet(style_setting_combo())

    def _refresh_default_combo() -> None:
        """Re-populates the combo and hides the section entirely when empty.

        Hiding (rather than disabling with a placeholder) keeps the tab
        clean on fresh installs — the Default Model section appears the
        moment the user wires up their first provider.
        """
        default_combo.blockSignals(True)
        default_combo.clear()
        models = get_available_models()
        default_group.setVisible(bool(models))
        if models:
            for provider, model_name in models:
                default_combo.addItem(
                    model_name,
                    format_model_id(provider, model_name),
                )
            default_combo.setEnabled(True)
            last = load_setting(SETTING_LLM_LAST_MODEL, "")
            if last:
                for i in range(default_combo.count()):
                    if default_combo.itemData(i) == last:
                        default_combo.setCurrentIndex(i)
                        break
        default_combo.blockSignals(False)

    def _on_default_changed(_idx: int) -> None:
        value = default_combo.currentData() or ""
        if value:
            save_setting(SETTING_LLM_LAST_MODEL, value)

    default_combo.currentIndexChanged.connect(_on_default_changed)
    default_row_layout.addWidget(default_combo, 1)
    default_layout.addWidget(default_row)

    layout.addWidget(default_group)

    # Refresh when the tab is shown (new providers may have been added
    # since the tab was built).
    widget._refresh_default_model_combo = _refresh_default_combo
    _refresh_default_combo()

    # Gemini provider section.  API-key auth is the default; the Vertex
    # AI sub-block (project + location + service-account credentials)
    # nests INSIDE the same card so the user sees one "Gemini"
    # configuration block — Vertex is just a different auth mode for
    # the same provider, not a separate one.
    gemini_card = create_provider_config(
        LLM_METHOD_GEMINI,
        SETTING_LLM_GEMINI_API_KEY,
        SETTING_LLM_GEMINI_MODEL,
        None,
        hint_tr_key="settings.gemini_api_key_hint",
        show_model=False,
    )
    gemini_card.layout().addWidget(_create_vertex_ai_section(gemini_card))
    layout.addWidget(gemini_card)

    # ── Dynamic custom provider sections ──
    from src.ui.components import create_setting_tag_input  # noqa: PLC0415
    from src.utils.config_manager import (  # noqa: PLC0415
        is_valid_endpoint,
        load_custom_providers,
        save_custom_providers,
    )

    providers_container = QVBoxLayout()
    providers_container.setSpacing(SPACING_SECTION)
    provider_widgets: list[QWidget] = []

    def _save_all_providers() -> None:
        """Collects data from all provider widgets and saves to settings."""
        providers: list[dict[str, str]] = []
        for pw in provider_widgets:
            data = pw.property("provider_data")
            if data:
                providers.append(data)
        save_custom_providers(providers)

    # Debounce disk writes while the user is typing — long endpoints and API
    # keys otherwise trigger one save per keystroke.
    _save_timer = QTimer(widget)
    _save_timer.setSingleShot(True)
    _save_timer.setInterval(400)
    _save_timer.timeout.connect(_save_all_providers)

    def _schedule_save() -> None:
        """Starts or restarts the debounce window for a provider save."""
        _save_timer.start()

    def _save_providers_now() -> None:
        """Cancels any pending debounce and writes to disk immediately.

        Guarded with ``shiboken6.isValid`` because the closure stays
        connected to ``qapp.aboutToQuit`` for the app's lifetime, but
        the captured ``_save_timer`` belongs to the page widget — if
        the page was destroyed (theme reload, test teardown), the
        underlying QTimer C++ object is gone and ``stop()`` would
        raise ``RuntimeError: Internal C++ object already deleted``.
        Falling through silently is safe: a destroyed page has no
        pending edits to flush.
        """
        from shiboken6 import isValid  # noqa: PLC0415

        if not isValid(_save_timer):
            return
        _save_timer.stop()
        _save_all_providers()

    # Flush any pending debounced save on app shutdown. QTimer single-shots
    # don't fire after the event loop stops, so a user editing + quitting
    # within the debounce window would otherwise lose those edits.
    app = QApplication.instance()
    if app is not None:
        app.aboutToQuit.connect(_save_providers_now)

    def _build_provider_section(  # noqa: PLR0915
        data: dict[str, str],
    ) -> QWidget:
        """Builds a single custom provider section with remove button."""
        group, group_layout, title_label = create_section_group(
            tr("settings.custom_provider_title"),
            tr_key="settings.custom_provider_title",
        )

        # Store mutable data on the widget
        group.setProperty("provider_data", data)

        def _refresh_section_title() -> None:
            """Shows "{name} Configuration" as the section title, or a default."""
            current = group.property("provider_data") or {}
            name_val = (current.get("name") or "").strip()
            if name_val:
                title_label.setText(
                    tr("settings.custom_provider_named_title", name=name_val),
                )
            else:
                title_label.setText(tr("settings.custom_provider_title"))

        # Re-translate the default on language switch while honouring the name.
        group.apply_language = _refresh_section_title

        # Name field
        name_widget, name_input = create_setting_input(
            tr("settings.custom_provider_name"),
            "",
            tr("settings.custom_provider_name_placeholder"),
            label_tr_key="settings.custom_provider_name",
            placeholder_tr_key="settings.custom_provider_name_placeholder",
        )
        name_input.blockSignals(True)
        name_input.setText(data.get("name", ""))
        name_input.blockSignals(False)

        def _on_name_changed(value: str) -> None:
            _on_field_changed(group, "name", value)
            _refresh_section_title()

        name_input.textChanged.connect(_on_name_changed)
        group_layout.addWidget(name_widget)
        _refresh_section_title()

        # API Key field
        api_widget, api_input = create_setting_input(
            tr("settings.api_key"),
            "",
            tr("settings.api_key_placeholder_provider", name="Custom"),
            is_password=True,
            label_tr_key="settings.api_key",
            placeholder_tr_key="settings.api_key_placeholder_provider",
            placeholder_tr_kwargs={"name": "Custom"},
        )
        api_input.blockSignals(True)
        api_input.setText(data.get("api_key", ""))
        api_input.blockSignals(False)
        api_input.textChanged.connect(
            lambda t: _on_field_changed(group, "api_key", t),
        )
        group_layout.addWidget(api_widget)

        # Endpoint field
        ep_widget, ep_input = create_setting_input(
            tr("settings.endpoint"),
            "",
            tr("settings.endpoint_placeholder"),
            label_tr_key="settings.endpoint",
            placeholder_tr_key="settings.endpoint_placeholder",
        )
        ep_input.blockSignals(True)
        ep_input.setText(data.get("endpoint", ""))
        ep_input.blockSignals(False)

        # Visual feedback: red border + hint when the text isn't a valid
        # http(s) URL.  The model picker filters out invalid endpoints
        # anyway, but users deserve to see *why* their model disappeared.
        from src.constants import color as _color  # noqa: PLC0415

        _valid_ep_style = ep_input.styleSheet()
        _invalid_ep_style = (
            _valid_ep_style + f" QLineEdit {{ border: 1px solid {_color('error')}; }}"
        )

        def _on_endpoint_changed(t: str) -> None:
            _on_field_changed(group, "endpoint", t)
            # Treat empty as neutral (not yet filled in); only flag garbage.
            is_invalid = bool(t.strip()) and not is_valid_endpoint(t)
            ep_input.setStyleSheet(
                _invalid_ep_style if is_invalid else _valid_ep_style,
            )

        ep_input.textChanged.connect(_on_endpoint_changed)
        # Apply initial highlight for persisted garbage.
        _on_endpoint_changed(ep_input.text())

        group_layout.addWidget(ep_widget)

        # Models field (tag input)
        model_container, model_tag = create_setting_tag_input(
            tr("settings.model"),
            "",
            tr("settings.model_placeholder"),
            label_tr_key="settings.model",
            placeholder_tr_key="settings.model_placeholder",
        )
        models_str = data.get("models", "")
        if models_str:
            model_tag.set_tags(
                [m.strip() for m in models_str.split(",") if m.strip()],
            )
        model_tag.tags_changed.connect(
            lambda _: _on_field_changed(group, "models", model_tag.text()),
        )
        group_layout.addWidget(model_container)

        # Remove button
        remove_btn = QPushButton("")
        _bind_text(remove_btn, "settings.remove_provider")
        remove_btn.setFixedHeight(HEIGHT_CONTROL)
        remove_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        remove_btn.setStyleSheet(style_delete_button())
        remove_btn.clicked.connect(lambda: _remove_provider(group))
        group_layout.addWidget(remove_btn)

        return group

    def _on_field_changed(
        group: QWidget,
        field: str,
        value: str,
    ) -> None:
        """Updates the provider data dict and schedules a debounced save."""
        data = group.property("provider_data")
        if data:
            data[field] = value.strip()
            group.setProperty("provider_data", data)
            _schedule_save()

    def _add_provider(data: dict[str, str] | None = None) -> None:
        """Adds a new custom provider section."""
        if data is None:
            data = {"name": "", "api_key": "", "endpoint": "", "models": ""}
        section = _build_provider_section(data)
        provider_widgets.append(section)
        providers_container.addWidget(section)

    def _remove_provider(group: QWidget) -> None:
        """Removes a custom provider section after user confirms."""
        from src.ui.dialogs import CustomConfirmDialog  # noqa: PLC0415

        confirmed = CustomConfirmDialog.confirm(
            widget.window(),
            tr("settings.remove_provider_title"),
            tr("settings.remove_provider_msg"),
            is_danger=True,
        )
        if not confirmed:
            return
        if group in provider_widgets:
            provider_widgets.remove(group)
            providers_container.removeWidget(group)
            group.deleteLater()
            # Removal is an explicit, user-initiated destructive change —
            # persist immediately and drop any pending edit debounce.
            _save_providers_now()

    # Load existing providers
    for prov_data in load_custom_providers():
        _add_provider(prov_data)

    layout.addLayout(providers_container)

    # "Add Provider" button
    add_btn = QPushButton("")
    _bind_text(add_btn, "settings.add_provider")
    add_btn.setFixedHeight(HEIGHT_CONTROL)
    add_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    add_btn.setStyleSheet(style_secondary_button())
    # Lambda discards the QPushButton.clicked bool arg so it doesn't become `data`.
    add_btn.clicked.connect(lambda: _add_provider())  # noqa: PLW0108
    layout.addWidget(add_btn)

    layout.addStretch()
    return widget


def create_general_settings() -> QWidget:  # noqa: PLR0915
    """Creates the General settings tab content.

    Returns:
        QWidget: The general settings widget.
    """
    widget = QWidget()
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(0, MARGIN_SECTION, 0, 0)
    layout.setSpacing(SPACING_SECTION)

    # 0. Appearance Section (Theme + Language)
    theme_group, theme_layout, _ = create_section_group(
        tr("settings.appearance"),
        tr_key="settings.appearance",
    )

    # --- Theme row ---
    theme_container = QWidget()
    theme_container.setStyleSheet(style_setting_container())
    theme_row = QHBoxLayout(theme_container)
    theme_row.setContentsMargins(0, 0, 0, 0)
    theme_row.setSpacing(SPACING_SUBSECTION)

    theme_label = QLabel(tr("settings.theme"))
    _bind_text(theme_label, "settings.theme")
    theme_label.setStyleSheet(style_input_label())
    theme_label.setFixedWidth(LABEL_WIDTH)
    theme_label.setFixedHeight(HEIGHT_CONTROL)
    theme_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    theme_row.addWidget(theme_label)

    theme_button_group = QButtonGroup(widget)
    theme_button_group.setExclusive(True)

    saved_theme = load_setting(SETTING_THEME, "auto")
    theme_options = [
        (tr("settings.auto_system"), "auto"),
        (tr("settings.light"), "light"),
        (tr("settings.dark"), "dark"),
    ]

    theme_radios = []
    for i, (label_text, _value) in enumerate(theme_options):
        radio = QRadioButton(label_text)
        radio.setCursor(Qt.CursorShape.PointingHandCursor)
        radio.setStyleSheet(style_radio_button())
        theme_button_group.addButton(radio, i)
        theme_row.addWidget(radio)
        theme_radios.append(radio)
        if _value == str(saved_theme).lower():
            radio.setChecked(True)

    theme_row.addStretch()

    def on_theme_changed(btn: QRadioButton) -> None:
        """Persists the selected theme and applies it (with auto-detect support)."""
        if not btn.isChecked():
            return
        idx = theme_button_group.id(btn)
        _label, value = theme_options[idx]
        save_setting(SETTING_THEME, value)
        monitor = getattr(widget.window(), "_system_theme_monitor", None)
        if value == "auto":
            if monitor:
                monitor.start()
            else:
                from src.ui.system_theme import detect_system_theme  # noqa: PLC0415

                set_theme(detect_system_theme())
        else:
            if monitor:
                monitor.stop()
            set_theme(value)

    theme_button_group.buttonClicked.connect(on_theme_changed)

    def _sync_theme_selection(_resolved: str | None = None) -> None:
        """Syncs radios to the saved preference after any theme change.

        Connected to `theme_changed`, which fires with the resolved theme
        ("light" / "dark") — but the radios reflect the user's *preference*
        (including "auto"), so we re-read SETTING_THEME rather than trusting
        the signal argument.
        """
        pref = str(load_setting(SETTING_THEME, "auto")).lower()
        for i, (_label, value) in enumerate(theme_options):
            if value == pref and not theme_radios[i].isChecked():
                theme_button_group.blockSignals(True)
                theme_radios[i].setChecked(True)
                theme_button_group.blockSignals(False)
                break

    theme_changed.connect(_sync_theme_selection)

    def _apply_theme_row() -> None:
        theme_container.setStyleSheet(style_setting_container())
        theme_label.setStyleSheet(style_input_label())

    theme_container.apply_theme = _apply_theme_row

    # Theme radio text keys for language updates
    _theme_radio_tr_keys = ["settings.auto_system", "settings.light", "settings.dark"]

    def _apply_language_theme_row() -> None:
        theme_label.setText(tr("settings.theme"))
        for i, key in enumerate(_theme_radio_tr_keys):
            theme_radios[i].setText(tr(key))

    theme_container.apply_language = _apply_language_theme_row

    theme_layout.addWidget(theme_container)

    # --- Language row ---
    lang_container = QWidget()
    lang_container.setStyleSheet(style_setting_container())
    lang_row = QHBoxLayout(lang_container)
    lang_row.setContentsMargins(0, 0, 0, 0)

    lang_label = QLabel(tr("settings.language"))
    _bind_text(lang_label, "settings.language")
    lang_label.setStyleSheet(style_input_label())
    lang_label.setFixedWidth(LABEL_WIDTH)
    lang_label.setFixedHeight(HEIGHT_CONTROL)
    lang_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    lang_row.addWidget(lang_label)

    lang_combo = QComboBox()
    lang_combo.setCursor(Qt.CursorShape.PointingHandCursor)
    lang_combo.view().setCursor(Qt.CursorShape.PointingHandCursor)
    lang_combo.view().setUniformItemSizes(True)
    lang_combo.view().setSpacing(0)
    lang_combo.setStyleSheet(style_setting_combo())
    lang_combo.setFixedHeight(HEIGHT_CONTROL)
    lang_combo.setIconSize(QSize(FLAG_ICON_WIDTH, FLAG_ICON_HEIGHT))

    saved_lang = load_setting(SETTING_UI_LANGUAGE, "en-US")
    for code, display_name, icon in UI_LANGUAGES:
        flag = QIcon(f"{FLAGS_DIR}/{icon}.png")
        lang_combo.addItem(flag, display_name, code)

    # Select saved language; fall back to en-US if the stored code is unknown
    matched_index = next(
        (i for i, (code, *_) in enumerate(UI_LANGUAGES) if code == saved_lang),
        None,
    )
    if matched_index is None:
        fallback_index = next(
            (i for i, (code, *_) in enumerate(UI_LANGUAGES) if code == "en-US"),
            0,
        )
        lang_combo.setCurrentIndex(fallback_index)
        fallback_code = lang_combo.itemData(fallback_index)
        save_setting(SETTING_UI_LANGUAGE, fallback_code)
        set_language(fallback_code)
    else:
        lang_combo.setCurrentIndex(matched_index)

    def on_lang_changed(index: int) -> None:
        """Persists the selected UI language and triggers a language switch."""
        code = lang_combo.itemData(index)
        if code:
            save_setting(SETTING_UI_LANGUAGE, code)
            set_language(code)

    lang_combo.currentIndexChanged.connect(on_lang_changed)

    def _sync_lang_selection(_code: str | None = None) -> None:
        """Syncs the combo to the saved UI language after any language switch."""
        current_code = str(load_setting(SETTING_UI_LANGUAGE, "en-US"))
        idx = next(
            (i for i, (code, *_) in enumerate(UI_LANGUAGES) if code == current_code),
            None,
        )
        if idx is not None and lang_combo.currentIndex() != idx:
            lang_combo.blockSignals(True)
            lang_combo.setCurrentIndex(idx)
            lang_combo.blockSignals(False)

    language_changed.connect(_sync_lang_selection)

    lang_row.addWidget(lang_combo, 1)

    def _apply_theme_lang_row() -> None:
        lang_container.setStyleSheet(style_setting_container())
        lang_label.setStyleSheet(style_input_label())
        lang_combo.setStyleSheet(style_setting_combo())

    lang_container.apply_theme = _apply_theme_lang_row

    def _apply_language_lang_row() -> None:
        lang_label.setText(tr("settings.language"))

    lang_container.apply_language = _apply_language_lang_row

    theme_layout.addWidget(lang_container)
    layout.addWidget(theme_group)

    # 1. Office Configuration Section
    office_group, office_layout, _ = create_section_group(
        tr("settings.office"),
        tr_key="settings.office",
    )

    # Info banner explaining what an office backend unlocks
    import sys  # noqa: PLC0415

    _office_info_key = (
        "settings.office_info_win"
        if sys.platform == "win32"
        else "settings.office_info"
    )
    office_info_frame, _ = create_banner(
        tr(_office_info_key),
        variant="info",
        tr_key=_office_info_key,
    )
    office_layout.addWidget(office_info_frame)

    # Success banners for detected office backends (always created, visibility toggled)
    msoffice_banner, _ = create_banner(
        tr("settings.office_msoffice_ready"),
        variant="success",
        tr_key="settings.office_msoffice_ready",
    )
    office_layout.addWidget(msoffice_banner)

    libreoffice_banner, _ = create_banner(
        tr("settings.office_libreoffice_ready"),
        variant="success",
        tr_key="settings.office_libreoffice_ready",
    )
    office_layout.addWidget(libreoffice_banner)

    # LibreOffice path input (always created, visibility toggled)
    office_path_widget, _ = create_setting_path(
        tr("settings.libreoffice_path"),
        SETTING_LIBREOFFICE_PATH,
        widget,
        custom_label_width=240,
        label_tr_key="settings.libreoffice_path",
        browse_mode="file",
        dialog_title_tr_key="settings.select_libreoffice",
        default_path="",
        placeholder_tr_key="settings.libreoffice_path_placeholder",
    )
    office_layout.addWidget(office_path_widget)

    def _sync_office_availability() -> None:
        """Re-checks MS Office / LibreOffice availability and toggles widgets."""
        has_ms = check_msoffice_available()
        has_lo = check_libreoffice_available()
        msoffice_banner.setVisible(has_ms)
        libreoffice_banner.setVisible(has_lo)
        office_path_widget.setVisible(not has_ms and not has_lo)

    _sync_office_availability()  # initial state
    widget._sync_office_availability = _sync_office_availability

    layout.addWidget(office_group)

    # Updates section — non-blocking startup check against GitHub Releases.
    from src.constants.settings import (  # noqa: PLC0415
        SETTING_AUTO_UPDATE_CHECK,
    )

    updates_group, updates_layout, _ = create_section_group(
        tr("settings.updates"),
        tr_key="settings.updates",
    )
    update_check_widget, _ = create_setting_checkbox(
        tr("settings.auto_update_check"),
        SETTING_AUTO_UPDATE_CHECK,
        default=True,
        label_tr_key="settings.auto_update_check",
    )
    updates_layout.addWidget(update_check_widget)
    layout.addWidget(updates_group)

    layout.addStretch()
    return widget


def create_translation_settings() -> QWidget:  # noqa: PLR0915
    """Creates the Translate Document settings tab content.

    Exposes the translated-file output directory, the document-translation
    scope toggles (comments / shapes / speaker notes / sheet names / embedded
    images), legacy-and-ODF auto-convert toggles, and the auto-remove-from-
    history toggle. The images toggle is gated on OCR; auto-convert toggles
    are gated on the presence of an office converter — both are disabled
    (not cleared) when their backend is unavailable.
    """
    widget = QWidget()
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(0, MARGIN_SECTION, 0, 0)
    layout.setSpacing(SPACING_SECTION)

    # 1. Output Section
    out_group, out_layout, _ = create_section_group(
        tr("settings.output"),
        tr_key="settings.output",
    )
    storage_widget, _ = create_setting_path(
        tr("settings.save_to"),
        SETTING_STORAGE_PATH,
        widget,
        custom_label_width=240,
        label_tr_key="settings.save_to",
        placeholder_tr_key="settings.save_to_auto",
    )
    _add_save_to_auto_info(out_layout, storage_widget)
    layout.addWidget(out_group)

    # 2. Document Translation Section
    doc_group, doc_layout, _ = create_section_group(
        tr("settings.doc_options"),
        tr_key="settings.doc_options",
    )

    # ── Embedded images (top of section) ─────────────────────────
    # Images are the most expensive / most-discussed translation
    # surface (OCR + vision LLM, skip-with-warning policy, OCR setup
    # required), so they lead the Translate Document section.
    # Cheaper text-only toggles below build on the simpler default.

    # Both banners render *above* the checkbox they relate to, per the
    # AGENTS.md banner convention ("placed near the gating control",
    # consistently above).  Stacking order top→bottom:
    #   1. OCR-not-configured warning (when OCR is missing)
    #   2. Skip-with-warning info     (when image translation is on)
    #   3. Translate embedded images checkbox
    ocr_hint_frame, _ = create_banner(
        tr("settings.doc_images_no_ocr"),
        variant="warning",
        tr_key="settings.doc_images_no_ocr",
    )
    doc_layout.addWidget(ocr_hint_frame)

    # Info banner explaining the skip-with-warning policy for embedded
    # images.  Always visible: this is policy clarification (what the
    # feature does), not an environmental warning, so users benefit
    # from seeing it *before* they decide whether to enable image
    # translation rather than as a surprise after toggling on.
    doc_images_info_frame, _ = create_banner(
        tr("settings.doc_images_skip_info"),
        variant="info",
        tr_key="settings.doc_images_skip_info",
    )
    doc_layout.addWidget(doc_images_info_frame)

    # Translate embedded images checkbox
    translate_images_widget, translate_images_cb = create_setting_checkbox(
        tr("settings.translate_doc_images"),
        SETTING_TRANSLATE_DOC_IMAGES,
        default=False,
        label_tr_key="settings.translate_doc_images",
    )
    doc_layout.addWidget(translate_images_widget)

    # ── Other surfaces ───────────────────────────────────────────

    # Translate comments checkbox
    translate_comments_widget, _ = create_setting_checkbox(
        tr("settings.translate_doc_comments"),
        SETTING_TRANSLATE_DOC_COMMENTS,
        default=False,
        label_tr_key="settings.translate_doc_comments",
    )
    doc_layout.addWidget(translate_comments_widget)

    # Translate shapes / text boxes checkbox
    translate_shapes_widget, _ = create_setting_checkbox(
        tr("settings.translate_doc_shapes"),
        SETTING_TRANSLATE_DOC_SHAPES,
        default=False,
        label_tr_key="settings.translate_doc_shapes",
    )
    doc_layout.addWidget(translate_shapes_widget)

    # Translate speaker notes checkbox
    translate_notes_widget, _ = create_setting_checkbox(
        tr("settings.translate_doc_notes"),
        SETTING_TRANSLATE_DOC_NOTES,
        default=False,
        label_tr_key="settings.translate_doc_notes",
    )
    doc_layout.addWidget(translate_notes_widget)

    # Translate sheet names checkbox
    translate_sheet_names_widget, _ = create_setting_checkbox(
        tr("settings.translate_doc_sheet_names"),
        SETTING_TRANSLATE_SHEET_NAMES,
        default=False,
        label_tr_key="settings.translate_doc_sheet_names",
    )
    doc_layout.addWidget(translate_sheet_names_widget)

    def _sync_ocr_state() -> None:
        """Disables the checkbox and shows a hint when OCR is not set up.

        Does not overwrite the stored preference — when OCR returns, the
        user's original choice is still honored.
        """
        ocr_ready = check_ocr_setup()
        translate_images_cb.setEnabled(ocr_ready)
        ocr_hint_frame.setVisible(not ocr_ready)

    _sync_ocr_state()

    # Hint banner shown when no office converter is available (rendered
    # above the auto-convert checkboxes it gates).
    import sys  # noqa: PLC0415

    _office_hint_key = (
        "settings.auto_convert_no_office_win"
        if sys.platform == "win32"
        else "settings.auto_convert_no_office"
    )
    office_hint_frame, _ = create_banner(
        tr(_office_hint_key),
        variant="warning",
        tr_key=_office_hint_key,
    )
    doc_layout.addWidget(office_hint_frame)

    # Auto-convert legacy to modern format checkbox
    auto_convert_legacy_widget, auto_convert_legacy_cb = create_setting_checkbox(
        tr("settings.auto_convert_legacy"),
        SETTING_AUTO_CONVERT_LEGACY,
        default=False,
        label_tr_key="settings.auto_convert_legacy",
    )
    doc_layout.addWidget(auto_convert_legacy_widget)

    # Auto-convert ODF to modern format checkbox
    auto_convert_odf_widget, auto_convert_odf_cb = create_setting_checkbox(
        tr("settings.auto_convert_odf"),
        SETTING_AUTO_CONVERT_ODF,
        default=False,
        label_tr_key="settings.auto_convert_odf",
    )
    doc_layout.addWidget(auto_convert_odf_widget)

    def _sync_office_state() -> None:
        """Disables auto-convert checkboxes when no office converter is available.

        Does not overwrite the stored preference — when a converter returns,
        the user's original choice is still honored.
        """
        office_ready = check_office_converter_setup()
        auto_convert_legacy_cb.setEnabled(office_ready)
        auto_convert_odf_cb.setEnabled(office_ready)
        office_hint_frame.setVisible(not office_ready)

    _sync_office_state()

    # Banner apply_theme/apply_language hooks are invoked directly by
    # window.py's findChildren(QWidget) walk — no manual chaining needed.
    translate_images_widget._sync_ocr_state = _sync_ocr_state
    auto_convert_legacy_widget._sync_office_state = _sync_office_state
    layout.addWidget(doc_group)

    # 3. History Section
    hist_group, hist_layout, _ = create_section_group(
        tr("settings.history_mgmt"),
        tr_key="settings.history_mgmt",
    )
    auto_remove_widget, _ = create_setting_checkbox(
        tr("settings.auto_remove"),
        SETTING_AUTO_REMOVE_HISTORY,
        default=False,
        label_tr_key="settings.auto_remove",
    )
    hist_layout.addWidget(auto_remove_widget)
    layout.addWidget(hist_group)

    layout.addStretch()
    return widget


def create_extract_text_settings() -> QWidget:  # noqa: PLR0915
    """Creates the Extract Text settings tab content.

    Exposes the storage path, extraction method (OCR vs LLM vision), output
    format (.txt / .docx), and the auto-remove-from-history toggle.
    """
    from src.constants.settings import (  # noqa: PLC0415
        EXTRACT_METHOD_LLM,
        EXTRACT_METHOD_OCR,
        SETTING_EXTRACT_AUTO_REMOVE,
        SETTING_EXTRACT_METHOD,
        SETTING_EXTRACT_STORAGE_PATH,
        SETTING_LAST_EXTRACT_FORMAT,
    )

    widget = QWidget()
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(0, MARGIN_SECTION, 0, 0)
    layout.setSpacing(SPACING_SECTION)

    # Output Configuration section
    out_group, out_layout, _ = create_section_group(
        tr("settings.extract_text_output"),
        tr_key="settings.extract_text_output",
    )

    storage_widget, _ = create_setting_path(
        tr("settings.extract_text_save_to"),
        SETTING_EXTRACT_STORAGE_PATH,
        widget,
        custom_label_width=240,
        label_tr_key="settings.extract_text_save_to",
        placeholder_tr_key="settings.save_to_auto",
    )
    _add_save_to_auto_info(out_layout, storage_widget)
    layout.addWidget(out_group)

    # Extraction Options section (method + output format)
    fmt_group, fmt_group_layout, _ = create_section_group(
        tr("settings.extract_text_options"),
        tr_key="settings.extract_text_options",
    )

    # "Method:" label + horizontal radio buttons (OCR / LLM)
    ocr_available = check_ocr_setup()
    llm_available = check_llm_setup()

    method_options = [
        (tr("settings.extract_method_ocr"), EXTRACT_METHOD_OCR, ocr_available),
        (tr("settings.extract_method_llm"), EXTRACT_METHOD_LLM, llm_available),
    ]

    method_container = QWidget()
    method_container.setStyleSheet(style_setting_container())
    method_row = QHBoxLayout(method_container)
    method_row.setContentsMargins(0, 0, 0, 0)

    method_label = QLabel(tr("settings.extract_text_method"))
    _bind_text(method_label, "settings.extract_text_method")
    method_label.setStyleSheet(style_input_label())
    method_label.setFixedWidth(LABEL_WIDTH)
    method_label.setFixedHeight(HEIGHT_CONTROL)
    method_label.setAlignment(
        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
    )
    method_row.addWidget(method_label)

    method_radio_layout = QHBoxLayout()
    method_radio_layout.setSpacing(SPACING_SUBSECTION)

    method_button_group = QButtonGroup(widget)
    method_button_group.setExclusive(True)
    saved_method = load_setting(SETTING_EXTRACT_METHOD, EXTRACT_METHOD_OCR)

    for i, (label, method_val, available) in enumerate(method_options):
        radio = QRadioButton(label)
        radio.setCursor(Qt.CursorShape.PointingHandCursor)
        radio.setStyleSheet(style_radio_button())
        radio.setProperty("method", method_val)
        radio.setEnabled(available)
        method_button_group.addButton(radio, i)
        method_radio_layout.addWidget(radio)
        if method_val == saved_method and available:
            radio.setChecked(True)

    def _on_method_toggled(btn: QRadioButton) -> None:
        """Persists the selected text extraction method (OCR or LLM)."""
        if btn.isChecked():
            save_setting(SETTING_EXTRACT_METHOD, btn.property("method"))

    method_button_group.buttonClicked.connect(_on_method_toggled)
    method_radio_layout.addStretch()

    auto_fallback_selection(method_button_group, SETTING_EXTRACT_METHOD)

    method_row.addLayout(method_radio_layout, 1)

    # Setup hints shown when the backing engine isn't configured. Rendered
    # above the method radios so they precede the control they explain.
    ocr_setup_hint_frame, _ = create_banner(
        tr("settings.extract_ocr_setup_hint"),
        variant="warning",
        tr_key="settings.extract_ocr_setup_hint",
    )
    ocr_setup_hint_frame.setVisible(not ocr_available)
    fmt_group_layout.addWidget(ocr_setup_hint_frame)

    llm_setup_hint_frame, _ = create_banner(
        tr("settings.extract_llm_setup_hint"),
        variant="warning",
        tr_key="settings.extract_llm_setup_hint",
    )
    llm_setup_hint_frame.setVisible(not llm_available)
    fmt_group_layout.addWidget(llm_setup_hint_frame)

    fmt_group_layout.addWidget(method_container)

    def _sync_method_availability() -> None:
        """Re-checks OCR/LLM availability and updates radio enabled state."""
        ocr_ok = check_ocr_setup()
        llm_ok = check_llm_setup()
        for btn in method_button_group.buttons():
            method_val = btn.property("method")
            if method_val == EXTRACT_METHOD_OCR:
                btn.setEnabled(ocr_ok)
            elif method_val == EXTRACT_METHOD_LLM:
                btn.setEnabled(llm_ok)
        ocr_setup_hint_frame.setVisible(not ocr_ok)
        llm_setup_hint_frame.setVisible(not llm_ok)
        auto_fallback_selection(
            method_button_group,
            SETTING_EXTRACT_METHOD,
        )

    widget._sync_method_availability = _sync_method_availability

    # "Output format:" label + horizontal radio buttons.  The radio
    # labels themselves carry tr keys via the loop below so they
    # re-translate on language switch alongside the headline label.
    _fmt_radio_keys = [
        ("settings.extract_format_txt", ".txt"),
        ("settings.extract_format_docx", ".docx"),
    ]
    format_options = [(tr(key), value) for key, value in _fmt_radio_keys]

    fmt_container = QWidget()
    fmt_container.setStyleSheet(style_setting_container())
    fmt_row = QHBoxLayout(fmt_container)
    fmt_row.setContentsMargins(0, 0, 0, 0)

    fmt_label = QLabel("")
    _bind_text(fmt_label, "settings.extract_text_format")
    fmt_label.setStyleSheet(style_input_label())
    fmt_label.setFixedWidth(LABEL_WIDTH)
    fmt_label.setFixedHeight(HEIGHT_CONTROL)
    fmt_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    fmt_row.addWidget(fmt_label)

    fmt_radio_layout = QHBoxLayout()
    fmt_radio_layout.setSpacing(SPACING_SUBSECTION)

    fmt_button_group = QButtonGroup(widget)
    fmt_button_group.setExclusive(True)
    saved_fmt = load_setting(SETTING_LAST_EXTRACT_FORMAT, ".txt")

    for i, ((tr_key, ext), (label, _)) in enumerate(
        zip(_fmt_radio_keys, format_options, strict=True),
    ):
        radio = QRadioButton(label)
        _bind_text(radio, tr_key)
        radio.setCursor(Qt.CursorShape.PointingHandCursor)
        radio.setStyleSheet(style_radio_button())
        radio.setProperty("ext", ext)
        fmt_button_group.addButton(radio, i)
        fmt_radio_layout.addWidget(radio)
        if ext == saved_fmt:
            radio.setChecked(True)

    def _on_format_toggled(btn: QRadioButton) -> None:
        """Persists the selected extraction output format (.txt or .docx)."""
        if btn.isChecked():
            save_setting(SETTING_LAST_EXTRACT_FORMAT, btn.property("ext"))

    fmt_button_group.buttonClicked.connect(_on_format_toggled)
    fmt_radio_layout.addStretch()

    # Default to first option if nothing matched
    if not fmt_button_group.checkedButton():
        first = fmt_button_group.button(0)
        if first:
            first.setChecked(True)

    fmt_row.addLayout(fmt_radio_layout, 1)
    fmt_group_layout.addWidget(fmt_container)
    layout.addWidget(fmt_group)

    # History Management section
    hist_group, hist_layout, _ = create_section_group(
        tr("settings.history_mgmt"),
        tr_key="settings.history_mgmt",
    )
    auto_remove_widget, _ = create_setting_checkbox(
        tr("settings.extract_auto_remove"),
        SETTING_EXTRACT_AUTO_REMOVE,
        default=False,
        label_tr_key="settings.extract_auto_remove",
    )
    hist_layout.addWidget(auto_remove_widget)
    layout.addWidget(hist_group)

    layout.addStretch()
    return widget


def create_subtitle_settings() -> QWidget:  # noqa: PLR0915
    """Creates the Generate Subtitle settings tab content.

    Exposes the subtitle-file output directory, the STT engine selection
    (Whisper or Google Cloud STT — with engine-specific model panels that
    swap on selection), the output format (.srt / .vtt), and the auto-
    remove-from-history toggle. The Google Cloud radio is gated on the
    Service-tab API key, with a setup-hint banner when it's unconfigured.
    """
    from src.constants.settings import (  # noqa: PLC0415
        SETTING_GOOGLE_STT_MODEL,
        SETTING_LAST_SUBTITLE_FORMAT,
        SETTING_SUBTITLE_AUTO_REMOVE,
        SETTING_SUBTITLE_STORAGE_PATH,
        SETTING_SUBTITLE_STT_METHOD,
        SETTING_WHISPER_MODEL,
        STT_GOOGLE,
        STT_WHISPER,
    )
    from src.utils.config_manager import check_google_cloud_setup  # noqa: PLC0415

    widget = QWidget()
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(0, MARGIN_SECTION, 0, 0)
    layout.setSpacing(SPACING_SECTION)

    # 1. Output section
    out_group, out_layout, _ = create_section_group(
        tr("settings.output"),
        tr_key="settings.output",
    )
    storage_widget, _ = create_setting_path(
        tr("settings.subtitle_save_to"),
        SETTING_SUBTITLE_STORAGE_PATH,
        widget,
        custom_label_width=240,
        label_tr_key="settings.subtitle_save_to",
        placeholder_tr_key="settings.save_to_auto",
    )
    _add_save_to_auto_info(out_layout, storage_widget)
    layout.addWidget(out_group)

    # 2. STT Engine section
    stt_group, stt_group_layout, _ = create_section_group(
        tr("settings.stt_engine"),
        tr_key="settings.stt_engine",
    )

    # Comparison banner
    stt_comparison_frame, _ = create_banner(
        tr("settings.stt_comparison"),
        variant="info",
        tr_key="settings.stt_comparison",
        rich_text=True,
    )
    stt_group_layout.addWidget(stt_comparison_frame)

    stt_options = [
        (tr("settings.stt_whisper"), STT_WHISPER),
        (tr("settings.stt_google"), STT_GOOGLE),
    ]

    stt_container = QWidget()
    stt_container.setStyleSheet(style_setting_container())
    stt_row = QHBoxLayout(stt_container)
    stt_row.setContentsMargins(0, 0, 0, 0)

    stt_label = QLabel(tr("settings.subtitle_stt_method"))
    _bind_text(stt_label, "settings.subtitle_stt_method")
    stt_label.setStyleSheet(style_input_label())
    stt_label.setFixedWidth(LABEL_WIDTH)
    stt_label.setFixedHeight(HEIGHT_CONTROL)
    stt_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    stt_row.addWidget(stt_label)

    stt_radio_layout = QHBoxLayout()
    stt_radio_layout.setSpacing(SPACING_SUBSECTION)
    stt_button_group = QButtonGroup(widget)
    stt_button_group.setExclusive(True)
    saved_stt = load_setting(SETTING_SUBTITLE_STT_METHOD, STT_WHISPER)

    google_available = check_google_cloud_setup()

    for i, (label, method_val) in enumerate(stt_options):
        radio = QRadioButton(label)
        radio.setCursor(Qt.CursorShape.PointingHandCursor)
        radio.setStyleSheet(style_radio_button())
        radio.setProperty("method", method_val)
        stt_button_group.addButton(radio, i)
        stt_radio_layout.addWidget(radio)
        if method_val == STT_GOOGLE and not google_available:
            radio.setEnabled(False)
        elif method_val == saved_stt:
            radio.setChecked(True)

    stt_radio_layout.addStretch()
    auto_fallback_selection(stt_button_group, SETTING_SUBTITLE_STT_METHOD)

    stt_row.addLayout(stt_radio_layout, 1)

    # Hint shown when Google Cloud STT is disabled (missing API key).
    # Rendered above the method radios so it precedes the control it explains.
    google_setup_hint_frame, _ = create_banner(
        tr("settings.stt_google_setup_hint"),
        variant="warning",
        tr_key="settings.stt_google_setup_hint",
    )
    google_setup_hint_frame.setVisible(not google_available)
    stt_group_layout.addWidget(google_setup_hint_frame)

    stt_group_layout.addWidget(stt_container)

    # Whisper model size (separate labeled row with radio buttons)
    model_container = QWidget()
    model_container.setStyleSheet(style_setting_container())
    model_row = QHBoxLayout(model_container)
    model_row.setContentsMargins(0, 0, 0, 0)

    model_label = QLabel("")
    _bind_text(model_label, "settings.whisper_model")
    model_label.setStyleSheet(style_input_label())
    model_label.setFixedWidth(LABEL_WIDTH)
    model_label.setFixedHeight(HEIGHT_CONTROL)
    model_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    model_row.addWidget(model_label)

    model_radio_layout = QHBoxLayout()
    model_radio_layout.setSpacing(SPACING_SUBSECTION)
    model_button_group = QButtonGroup(widget)
    model_button_group.setExclusive(True)
    saved_model = load_setting(SETTING_WHISPER_MODEL, "base")

    _whisper_models = [
        ("tiny", "75 MB"),
        ("base", "140 MB"),
        ("small", "460 MB"),
        ("medium", "1.5 GB"),
        ("large", "3.0 GB"),
    ]
    for i, (size, disk) in enumerate(_whisper_models):
        radio = QRadioButton(f"{size} ({disk})")
        radio.setCursor(Qt.CursorShape.PointingHandCursor)
        radio.setStyleSheet(style_radio_button())
        radio.setProperty("model", size)
        model_button_group.addButton(radio, i)
        model_radio_layout.addWidget(radio)
        if size == saved_model:
            radio.setChecked(True)

    def _on_model_toggled(btn: QRadioButton) -> None:
        """Persists the selected Whisper model size for subtitle STT."""
        if btn.isChecked():
            save_setting(SETTING_WHISPER_MODEL, btn.property("model"))

    model_button_group.buttonClicked.connect(_on_model_toggled)
    model_radio_layout.addStretch()

    if not model_button_group.checkedButton():
        base_btn = model_button_group.button(1)
        if base_btn:
            base_btn.setChecked(True)

    model_row.addLayout(model_radio_layout, 1)
    # Info banner for Whisper auto-download
    whisper_info_frame, _ = create_banner(
        tr("settings.whisper_auto_download"),
        variant="info",
        tr_key="settings.whisper_auto_download",
    )
    stt_group_layout.addWidget(whisper_info_frame)
    stt_group_layout.addWidget(model_container)

    # Google Cloud STT model selector
    google_model_widget, _gm_combo = create_setting_combo(
        tr("settings.google_stt_model"),
        SETTING_GOOGLE_STT_MODEL,
        [
            "default",
            "latest_long",
            "latest_short",
            "phone_call",
            "video",
            "medical_dictation",
            "medical_conversation",
        ],
        label_tr_key="settings.google_stt_model",
    )
    stt_group_layout.addWidget(google_model_widget)

    def _apply_method_panels(method: str) -> None:
        """Shows the Whisper or Google panel based on the active STT method."""
        is_whisper = method == STT_WHISPER
        whisper_info_frame.setVisible(is_whisper)
        model_container.setVisible(is_whisper)
        google_model_widget.setVisible(not is_whisper)

    def _on_stt_method_toggled(btn: QRadioButton) -> None:
        """Persists the STT method and toggles Whisper/Google model panels."""
        if btn.isChecked():
            method = btn.property("method")
            save_setting(SETTING_SUBTITLE_STT_METHOD, method)
            _apply_method_panels(method)

    stt_button_group.buttonClicked.connect(_on_stt_method_toggled)

    # Seed panel visibility from the actually-selected radio (not `saved_stt`,
    # which may be stale after auto_fallback_selection flipped the selection).
    active = stt_button_group.checkedButton()
    _apply_method_panels(active.property("method") if active else STT_WHISPER)

    layout.addWidget(stt_group)

    def _sync_stt_availability() -> None:
        """Re-checks Google Cloud availability for STT method."""
        available = check_google_cloud_setup()
        for btn in stt_button_group.buttons():
            if btn.property("method") == STT_GOOGLE:
                btn.setEnabled(available)
        google_setup_hint_frame.setVisible(not available)
        auto_fallback_selection(stt_button_group, SETTING_SUBTITLE_STT_METHOD)
        # auto_fallback_selection uses setChecked(), which doesn't fire
        # buttonClicked — re-apply panel visibility manually so a post-
        # fallback selection doesn't leave stale model panels showing.
        active_btn = stt_button_group.checkedButton()
        _apply_method_panels(
            active_btn.property("method") if active_btn else STT_WHISPER,
        )

    widget._sync_stt_availability = _sync_stt_availability

    # 3. Subtitle Generation section
    gen_group, gen_layout, _ = create_section_group(
        tr("settings.subtitle_generation"),
        tr_key="settings.subtitle_generation",
    )

    # Output format radio buttons
    # Engine supports SRT/VTT/ASS/SSA/CSV via ``_convert_subtitle_format``
    # in subtitle.py.  TXT was previously here but removed — Subtitle
    # page is for subtitles (media playback alignment); plain-text
    # transcripts are served by the Extract Text page or by opening
    # SRT in any text editor.  CSV stays for spreadsheet workflows.
    fmt_options = [
        ("SRT", ".srt"),
        ("VTT", ".vtt"),
        ("ASS", ".ass"),
        ("SSA", ".ssa"),
        ("CSV", ".csv"),
    ]

    fmt_container = QWidget()
    fmt_container.setStyleSheet(style_setting_container())
    fmt_row = QHBoxLayout(fmt_container)
    fmt_row.setContentsMargins(0, 0, 0, 0)

    fmt_label = QLabel("")
    _bind_text(fmt_label, "settings.subtitle_format")
    fmt_label.setStyleSheet(style_input_label())
    fmt_label.setFixedWidth(LABEL_WIDTH)
    fmt_label.setFixedHeight(HEIGHT_CONTROL)
    fmt_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    fmt_row.addWidget(fmt_label)

    fmt_radio_layout = QHBoxLayout()
    fmt_radio_layout.setSpacing(SPACING_SUBSECTION)
    fmt_button_group = QButtonGroup(widget)
    fmt_button_group.setExclusive(True)
    saved_fmt = load_setting(SETTING_LAST_SUBTITLE_FORMAT, ".srt")

    for i, (label, ext) in enumerate(fmt_options):
        radio = QRadioButton(label)
        radio.setCursor(Qt.CursorShape.PointingHandCursor)
        radio.setStyleSheet(style_radio_button())
        radio.setProperty("ext", ext)
        fmt_button_group.addButton(radio, i)
        fmt_radio_layout.addWidget(radio)
        if ext == saved_fmt:
            radio.setChecked(True)

    def _on_subtitle_format_toggled(btn: QRadioButton) -> None:
        """Persists the selected subtitle output format (.srt, .vtt, etc.)."""
        if btn.isChecked():
            save_setting(SETTING_LAST_SUBTITLE_FORMAT, btn.property("ext"))

    fmt_button_group.buttonClicked.connect(_on_subtitle_format_toggled)
    fmt_radio_layout.addStretch()

    if not fmt_button_group.checkedButton():
        first = fmt_button_group.button(0)
        if first:
            first.setChecked(True)

    fmt_row.addLayout(fmt_radio_layout, 1)
    gen_layout.addWidget(fmt_container)
    layout.addWidget(gen_group)

    # 4. History Management section
    hist_group, hist_layout, _ = create_section_group(
        tr("settings.history_mgmt"),
        tr_key="settings.history_mgmt",
    )
    auto_remove_widget, _ = create_setting_checkbox(
        tr("settings.subtitle_auto_remove"),
        SETTING_SUBTITLE_AUTO_REMOVE,
        default=False,
        label_tr_key="settings.subtitle_auto_remove",
    )
    hist_layout.addWidget(auto_remove_widget)
    layout.addWidget(hist_group)

    layout.addStretch()
    return widget


def create_translate_text_settings() -> QWidget:  # noqa: PLR0915
    """Creates the Translate Text settings tab content.

    Exposes the TTS-copy output directory for the Listen button and the
    auto-save-to-history toggle. TTS engine/voice selection lives on the
    Voice tab (shared setting).
    """
    from src.constants.settings import (  # noqa: PLC0415
        SETTING_TRANSLATE_TEXT_AUTO_SAVE,
        SETTING_TRANSLATE_TEXT_TTS_STORAGE,
    )

    widget = QWidget()
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(0, MARGIN_SECTION, 0, 0)
    layout.setSpacing(SPACING_SECTION)

    # 1. TTS Output section
    tts_group, tts_layout, _ = create_section_group(
        tr("settings.translate_text_tts_output"),
        tr_key="settings.translate_text_tts_output",
    )

    # Hint pointing to the Voice tab for engine/voice configuration
    tts_hint_frame, _ = create_banner(
        tr("settings.translate_text_tts_voice_hint"),
        variant="info",
        tr_key="settings.translate_text_tts_voice_hint",
    )
    tts_layout.addWidget(tts_hint_frame)

    storage_widget, _ = create_setting_path(
        tr("settings.translate_text_tts_save_to"),
        SETTING_TRANSLATE_TEXT_TTS_STORAGE,
        widget,
        custom_label_width=240,
        label_tr_key="settings.translate_text_tts_save_to",
        placeholder_tr_key="settings.translate_text_tts_no_save",
    )
    tts_layout.addWidget(storage_widget)
    layout.addWidget(tts_group)

    # 2. History section — auto-save toggle. TTS cache is wiped on app start.
    hist_group, hist_layout, _ = create_section_group(
        tr("settings.history_mgmt"),
        tr_key="settings.history_mgmt",
    )
    auto_save_widget, _ = create_setting_checkbox(
        tr("settings.translate_text_auto_save"),
        SETTING_TRANSLATE_TEXT_AUTO_SAVE,
        default=True,
        label_tr_key="settings.translate_text_auto_save",
    )
    hist_layout.addWidget(auto_save_widget)
    layout.addWidget(hist_group)

    layout.addStretch()
    return widget


def create_voice_settings() -> QWidget:  # noqa: PLR0915
    """Creates the Generate Voice settings tab content.

    Exposes the voice-audio output directory, the TTS engine selection
    (Edge TTS / Google Cloud TTS / ElevenLabs — cloud options gated on
    Service-tab API keys with setup-hint banners), the output audio format
    (.mp3 / .wav), and the auto-remove-from-history toggle.
    """
    from src.constants.settings import (  # noqa: PLC0415
        SETTING_LAST_VOICE_FORMAT,
        SETTING_VOICE_AUTO_REMOVE,
        SETTING_VOICE_STORAGE_PATH,
        SETTING_VOICE_TTS_METHOD,
        VOICE_TTS_EDGE,
        VOICE_TTS_ELEVENLABS,
        VOICE_TTS_GEMINI,
        VOICE_TTS_GOOGLE,
        VOICE_TTS_PIPER,
    )
    from src.utils.config_manager import (  # noqa: PLC0415
        check_elevenlabs_setup,
        check_gemini_setup,
        check_google_cloud_setup,
    )

    widget = QWidget()
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(0, MARGIN_SECTION, 0, 0)
    layout.setSpacing(SPACING_SECTION)

    # NOTE: no FFmpeg setup-hint banner here.  The Generate Voice PAGE
    # already shows the install banner at the top via
    # ``create_ffmpeg_install_banner`` — duplicating it on this settings
    # tab adds visual noise without surfacing new information.

    # 1. Output section
    out_group, out_layout, _ = create_section_group(
        tr("settings.output"),
        tr_key="settings.output",
    )
    storage_widget, _ = create_setting_path(
        tr("settings.voice_save_to"),
        SETTING_VOICE_STORAGE_PATH,
        widget,
        custom_label_width=240,
        label_tr_key="settings.voice_save_to",
        placeholder_tr_key="settings.save_to_auto",
    )
    _add_save_to_auto_info(out_layout, storage_widget)
    layout.addWidget(out_group)

    # 2. TTS Engine section
    tts_group, tts_group_layout, _ = create_section_group(
        tr("settings.tts_engine"),
        tr_key="settings.tts_engine",
    )

    # Comparison banner
    tts_comparison_frame, _ = create_banner(
        tr("settings.tts_comparison"),
        variant="info",
        tr_key="settings.tts_comparison",
        rich_text=True,
    )
    tts_group_layout.addWidget(tts_comparison_frame)

    # Piper installed-languages banner (Tesseract-style).  Two states:
    # success "Piper TTS: N language(s) installed" vs warning
    # "no voices installed yet — pick a language and Download".
    # Lives ABOVE the engine radios so the user sees their offline
    # readiness regardless of which engine is currently selected.
    # Refreshed by ``_refresh_piper_installed_banner`` after every
    # successful download.
    from src.core.speech_engine import (  # noqa: PLC0415
        installed_piper_languages,
    )

    piper_installed_banner, piper_installed_label = create_banner(
        "",
        variant="success",
    )
    tts_group_layout.addWidget(piper_installed_banner)

    def _refresh_piper_installed_banner() -> None:
        """Updates the banner with the current installed-language count.

        Swaps to the warning variant when zero voices are installed so
        a fresh user sees a clear "next step" message instead of a
        green "0 installed" badge.  Updates BOTH the border-colour
        stylesheet AND the leading icon — leaving the icon stale
        produces the contradictory "orange warning border + green
        check" combo that AGENTS.md banner contract forbids.
        """
        from PySide6.QtGui import QIcon  # noqa: PLC0415
        from PySide6.QtWidgets import QLabel  # noqa: PLC0415

        from src.constants import style_banner  # noqa: PLC0415
        from src.constants.ui import (  # noqa: PLC0415
            ALERT_TRIANGLE_PATH,
            BANNER_ICON_SIZE,
            CHECK_CIRCLE_PATH,
        )

        count = len(installed_piper_languages())
        variant = "success" if count > 0 else "warning"
        if count > 0:
            piper_installed_label.setText(
                tr("settings.piper_installed_langs", count=count),
            )
        else:
            piper_installed_label.setText(tr("settings.piper_no_voices"))
        piper_installed_banner.setStyleSheet(style_banner(variant))
        # Find the inner icon QLabel by objectName and swap its
        # pixmap so success/warning visuals stay coherent.
        icon_label = piper_installed_banner.findChild(QLabel, "BannerIcon")
        if icon_label is not None:
            icon_path = (
                CHECK_CIRCLE_PATH if variant == "success" else ALERT_TRIANGLE_PATH
            )
            icon_label.setPixmap(
                QIcon(icon_path).pixmap(BANNER_ICON_SIZE, BANNER_ICON_SIZE),
            )

    # Re-translate on language switch — language_changed broadcast
    # iterates QWidgets and calls ``apply_language`` on whatever
    # defines it.  Using the dynamic builder so the {count} placeholder
    # gets re-substituted with the live install count.
    piper_installed_banner.apply_language = _refresh_piper_installed_banner
    _refresh_piper_installed_banner()

    # ElevenLabs is paid-only and the most niche of the cloud options;
    # surfacing it last keeps the free engines (Edge / Gemini / Piper)
    # and the "first paid option you'd reach for" (Google Cloud) above
    # the fold.
    method_options = [
        (tr("settings.tts_edge"), VOICE_TTS_EDGE),
        (tr("settings.tts_google"), VOICE_TTS_GOOGLE),
        (tr("settings.tts_gemini"), VOICE_TTS_GEMINI),
        (tr("settings.tts_piper"), VOICE_TTS_PIPER),
        (tr("settings.tts_elevenlabs"), VOICE_TTS_ELEVENLABS),
    ]

    method_container = QWidget()
    method_container.setStyleSheet(style_setting_container())
    method_row = QHBoxLayout(method_container)
    method_row.setContentsMargins(0, 0, 0, 0)

    method_label = QLabel(tr("settings.voice_tts_method"))
    _bind_text(method_label, "settings.voice_tts_method")
    method_label.setStyleSheet(style_input_label())
    method_label.setFixedWidth(LABEL_WIDTH)
    method_label.setFixedHeight(HEIGHT_CONTROL)
    method_label.setAlignment(
        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
    )
    method_row.addWidget(method_label)

    method_radio_layout = QHBoxLayout()
    method_radio_layout.setSpacing(SPACING_SUBSECTION)
    method_button_group = QButtonGroup(widget)
    method_button_group.setExclusive(True)
    saved_method = load_setting(SETTING_VOICE_TTS_METHOD, VOICE_TTS_EDGE)

    google_available = check_google_cloud_setup()
    elevenlabs_available = check_elevenlabs_setup()
    gemini_available = check_gemini_setup()

    for i, (label, method_val) in enumerate(method_options):
        radio = QRadioButton(label)
        radio.setCursor(Qt.CursorShape.PointingHandCursor)
        radio.setStyleSheet(style_radio_button())
        radio.setProperty("method", method_val)
        method_button_group.addButton(radio, i)
        method_radio_layout.addWidget(radio)
        if (
            (method_val == VOICE_TTS_GOOGLE and not google_available)
            or (method_val == VOICE_TTS_ELEVENLABS and not elevenlabs_available)
            or (method_val == VOICE_TTS_GEMINI and not gemini_available)
        ):
            radio.setEnabled(False)
        elif method_val == saved_method:
            radio.setChecked(True)

    def _on_tts_method_toggled(btn: QRadioButton) -> None:
        """Persists the selected TTS method for voice generation."""
        if btn.isChecked():
            save_setting(SETTING_VOICE_TTS_METHOD, btn.property("method"))

    method_button_group.buttonClicked.connect(_on_tts_method_toggled)
    method_radio_layout.addStretch()

    auto_fallback_selection(method_button_group, SETTING_VOICE_TTS_METHOD)

    method_row.addLayout(method_radio_layout, 1)

    # Hints shown when a cloud TTS backend is disabled (missing API key).
    # Rendered above the method radios so they precede the control they
    # explain — and defined before _sync_tts_availability so the closure
    # captures real widgets, not forward references.
    google_setup_hint_frame, _ = create_banner(
        tr("settings.tts_google_setup_hint"),
        variant="warning",
        tr_key="settings.tts_google_setup_hint",
    )
    google_setup_hint_frame.setVisible(not google_available)
    tts_group_layout.addWidget(google_setup_hint_frame)

    elevenlabs_setup_hint_frame, _ = create_banner(
        tr("settings.tts_elevenlabs_setup_hint"),
        variant="warning",
        tr_key="settings.tts_elevenlabs_setup_hint",
    )
    elevenlabs_setup_hint_frame.setVisible(not elevenlabs_available)
    tts_group_layout.addWidget(elevenlabs_setup_hint_frame)

    gemini_setup_hint_frame, _ = create_banner(
        tr("settings.tts_gemini_setup_hint"),
        variant="warning",
        tr_key="settings.tts_gemini_setup_hint",
    )
    gemini_setup_hint_frame.setVisible(not gemini_available)
    tts_group_layout.addWidget(gemini_setup_hint_frame)

    tts_group_layout.addWidget(method_container)

    def _sync_tts_availability() -> None:
        """Re-checks Google Cloud, ElevenLabs, and Gemini availability.

        Looks each ``check_*_setup`` up via the module attribute on
        every call (instead of relying on the closure-captured local
        import) so that runtime changes to the API-key settings — or
        test-time monkey-patches — actually take effect.  Without
        this dynamic lookup, a user who removed their API key in
        another tab would still see the radio enabled until app
        restart, because the closure would hold the original
        function reference from widget-creation time.
        """
        from src.utils import config_manager  # noqa: PLC0415

        google_ok = config_manager.check_google_cloud_setup()
        elevenlabs_ok = config_manager.check_elevenlabs_setup()
        gemini_ok = config_manager.check_gemini_setup()
        for btn in method_button_group.buttons():
            method = btn.property("method")
            if method == VOICE_TTS_GOOGLE:
                btn.setEnabled(google_ok)
            elif method == VOICE_TTS_ELEVENLABS:
                btn.setEnabled(elevenlabs_ok)
            elif method == VOICE_TTS_GEMINI:
                btn.setEnabled(gemini_ok)
        google_setup_hint_frame.setVisible(not google_ok)
        elevenlabs_setup_hint_frame.setVisible(not elevenlabs_ok)
        gemini_setup_hint_frame.setVisible(not gemini_ok)
        auto_fallback_selection(
            method_button_group,
            SETTING_VOICE_TTS_METHOD,
        )

    widget._sync_tts_availability = _sync_tts_availability

    # ── Per-method Voice picker ────────────────────────────────────
    # One row labelled "Voice" inside a ``QStackedWidget`` that
    # swaps the input depending on which TTS method is currently
    # selected.  Each method writes to its own setting key so
    # switching back returns the user's last per-method choice
    # (instead of one shared "voice" string that leaks across
    # backends with incompatible voice catalogues).
    #   - Edge / Google Cloud / ElevenLabs: ``QLineEdit`` (catalogues
    #     are huge; users paste a voice name from provider docs).
    #   - Gemini: ``QComboBox`` populated from
    #     ``GEMINI_TTS_VOICE_CATALOGUE`` (curated short list with
    #     "Auto (by gender)" first), since the prebuilt set is small
    #     enough to enumerate.
    # ``Fixed`` vertical sizePolicy: with no expanding sibling between
    # the engine row and this voice row, the section vbox would
    # otherwise hand all leftover vertical space to this container
    # (the last expanding child) and render it at ~83 px instead of
    # the 42 px we want.  Pinning to Fixed keeps it at its sizeHint
    # so the radios sit centred in the same 42 px slot every other
    # settings row uses.
    from PySide6.QtWidgets import QSizePolicy  # noqa: PLC0415

    from src.constants.settings import (  # noqa: PLC0415
        SETTING_ELEVENLABS_VOICE_ID,
        SETTING_GEMINI_TTS_VOICE_NAME,
    )

    voice_picker_container = QWidget()
    voice_picker_container.setStyleSheet(style_setting_container())
    voice_picker_container.setSizePolicy(
        QSizePolicy.Policy.Preferred,
        QSizePolicy.Policy.Fixed,
    )
    voice_picker_row = QHBoxLayout(voice_picker_container)
    voice_picker_row.setContentsMargins(0, 0, 0, 0)

    voice_picker_label = QLabel("")
    _bind_text(voice_picker_label, "settings.voice_picker_label")
    voice_picker_label.setStyleSheet(style_input_label())
    voice_picker_label.setFixedWidth(LABEL_WIDTH)
    voice_picker_label.setFixedHeight(HEIGHT_CONTROL)
    voice_picker_label.setAlignment(
        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
    )
    voice_picker_row.addWidget(voice_picker_label)

    voice_picker_stack = QStackedWidget()
    # Stack height adapts to the current page (see ``_resize_stack_to_current``
    # below).  Single-row pages (Edge / Google / ElevenLabs) sit at
    # ``HEIGHT_CONTROL``; the Gemini page is taller because it stacks a
    # gender radio over a voice combo.  Without this, the stack would
    # take ``max(sizeHint)`` across all pages and leave dead space on
    # the single-row pages.
    voice_picker_stack.setSizePolicy(
        QSizePolicy.Policy.Preferred,
        QSizePolicy.Policy.Fixed,
    )
    voice_picker_row.addWidget(voice_picker_stack, 1)
    # The label is fixed at HEIGHT_CONTROL — anchor it to the top of the
    # row so it lines up with the first row of a multi-row page (e.g.
    # Gemini's gender radio) rather than centring against the whole page.
    voice_picker_row.setAlignment(
        voice_picker_label,
        Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft,
    )

    def _resize_stack_to_current() -> None:
        """Sizes the stack to fit only the active page.

        Hoisted above the per-engine picker builders so any engine
        callback (e.g. ElevenLabs toggling its Custom-voice text
        field) can call this directly to bubble its sizeHint change
        up to the stack.  Without that, the stack height stays
        pinned to whatever the page measured at construction time
        and the new field overflows below the section group's border
        — the bug a Vietnamese user reported when picking Custom on
        the ElevenLabs page.

        QStackedWidget's default ``sizeHint`` is the max across all
        pages — for the multi-row Gemini / ElevenLabs-Custom pages
        that would leave ~50 px of dead space below the single-row
        Edge / Google pickers.  Pinning ``setFixedHeight`` per
        change collapses the container back down whenever a smaller
        page becomes current.
        """
        cur = voice_picker_stack.currentWidget()
        if cur is None:
            return
        # Force the page to recalc its sizeHint based on current child
        # visibility — without this, the cached hint from build-time
        # wins and Qt won't notice that, e.g., the ElevenLabs Custom
        # text field just became visible.
        cur.adjustSize()
        h = max(HEIGHT_CONTROL, cur.sizeHint().height())
        voice_picker_stack.setFixedHeight(h)
        # ``adjustSize()`` above resized the page to its *content's*
        # preferred width — for Gemini that's only as wide as the
        # combo's natural sizeHint (~200 px) since no child explicitly
        # asks to stretch.  After a Piper → Gemini switch the page
        # would persist at that narrow width and the combo would no
        # longer fill the row.  Snapping the page back to the stack's
        # full width makes the stretch-to-fill behaviour idempotent
        # across switch cycles.
        cur.resize(voice_picker_stack.width(), h)

    def _build_voice_text_input(setting_key: str, placeholder_key: str) -> QLineEdit:
        """Builds a free-text voice-name input bound to *setting_key*."""
        edit = QLineEdit()
        # Match the bordered look of every other QLineEdit in Settings —
        # without an explicit stylesheet the field renders as bare text
        # on the dark page background, making the placeholder look
        # like a dead label rather than an input the user can click.
        edit.setStyleSheet(style_input_field())
        edit.setFixedHeight(HEIGHT_CONTROL)
        edit.setText(str(load_setting(setting_key, "")))
        edit.setPlaceholderText(tr(placeholder_key))
        edit.editingFinished.connect(
            lambda: save_setting(setting_key, edit.text().strip()),
        )
        return edit

    # Edge & Google TTS both expose a male/female radio bound to the
    # shared ``SETTING_LAST_VOICE_GENDER``.  Edge resolves a curated
    # voice from ``_EDGE_VOICES[(language, gender)]``; Google passes
    # the gender to the API as ``ssmlGender`` with no ``name``, so the
    # server picks an appropriate voice for the language automatically.
    # Free-text voice names were confusing — most users don't know
    # Microsoft / Google Cloud voice catalogues.
    from src.constants.settings import (  # noqa: PLC0415
        SETTING_LAST_VOICE_GENDER,
    )

    def _build_voice_gender_widget() -> QWidget:
        """Builds a Female/Male radio row bound to the shared gender setting.

        QStackedWidget needs distinct widget instances per page, so this
        helper is called once per engine page (Edge / Google /
        ElevenLabs / Gemini / Piper).  All five widgets stay in sync
        because they read/write the same setting key — flipping
        gender on one engine sticks when the user switches to any
        other; ``_on_any_gender_toggled`` also rebroadcasts the new
        gender to the dependent combos and download panel.
        """
        gender_widget = QWidget()
        gender_widget.setStyleSheet("background: transparent;")
        # Match the height of the QLineEdit pages in the same stack so
        # the row doesn't visually grow when the user switches engines.
        gender_widget.setFixedHeight(HEIGHT_CONTROL)
        row = QHBoxLayout(gender_widget)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(SPACING_SUBSECTION)
        row.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        group = QButtonGroup(widget)
        group.setExclusive(True)
        saved = (
            str(load_setting(SETTING_LAST_VOICE_GENDER, "FEMALE")).upper() or "FEMALE"
        )
        for i, (label_key, value) in enumerate(
            [
                ("settings.voice_gender_female", "FEMALE"),
                ("settings.voice_gender_male", "MALE"),
            ]
        ):
            radio = QRadioButton("")
            _bind_text(radio, label_key)
            radio.setCursor(Qt.CursorShape.PointingHandCursor)
            radio.setStyleSheet(style_radio_button())
            radio.setProperty("gender", value)
            group.addButton(radio, i)
            row.addWidget(radio)
            if value == saved:
                radio.setChecked(True)
        row.addStretch()

        def _on_toggled(btn: QRadioButton) -> None:
            """Persists the chosen gender."""
            if btn.isChecked():
                save_setting(SETTING_LAST_VOICE_GENDER, btn.property("gender"))

        group.buttonClicked.connect(_on_toggled)
        # Hold the group on the widget so it isn't garbage-collected
        # before the buttons it owns.
        gender_widget._button_group = group  # type: ignore[attr-defined]
        return gender_widget

    edge_voice_widget = _build_voice_gender_widget()
    google_voice_widget = _build_voice_gender_widget()

    # ElevenLabs: gender radio (top) + voice combo (middle) + custom
    # Voice ID input (bottom, only visible when "Custom" is selected).
    # Single setting (``SETTING_ELEVENLABS_VOICE_ID``) holds the
    # resolved voice ID — empty for "Auto" (engine falls back to
    # gender-default), a curated catalogue ID for picked voices, or any
    # arbitrary string for a custom (e.g. cloned) voice.  We can tell
    # which path the saved value belongs to at load time by looking it
    # up in the curated catalogue.
    from src.core.speech_engine import (  # noqa: PLC0415
        get_elevenlabs_voices_for_gender,
    )

    _elevenlabs_custom_sentinel = "__custom__"

    def _all_curated_elevenlabs_ids() -> set[str]:
        """Returns IDs of every curated voice (across all genders).

        Used at load time to decide whether the saved ID came from the
        catalogue (→ select that entry) or is a custom value (→ show
        the Custom text field with the saved ID populated).
        """
        from src.core.speech_engine import (  # noqa: PLC0415
            ELEVENLABS_VOICES_BY_GENDER,
        )

        return {
            vid
            for entries in ELEVENLABS_VOICES_BY_GENDER.values()
            for _name, vid in entries
        }

    elevenlabs_voice_widget = QWidget()
    elevenlabs_voice_widget.setStyleSheet("background: transparent;")
    elevenlabs_voice_col = QVBoxLayout(elevenlabs_voice_widget)
    elevenlabs_voice_col.setContentsMargins(0, 0, 0, 0)
    # Inherit the QVBoxLayout default spacing (~6 px on Fusion) so the
    # gap between the gender row, voice combo, and Custom-voice text
    # field matches the spacing every other settings row uses inside
    # its parent section group.  An explicit ``SPACING_SUBSECTION``
    # (16 px) here would make the per-engine picker visibly looser
    # than the rest of the Settings page.

    elevenlabs_gender_widget = _build_voice_gender_widget()
    elevenlabs_voice_combo = QComboBox()
    elevenlabs_voice_combo.setFixedHeight(HEIGHT_CONTROL)
    elevenlabs_voice_combo.setCursor(Qt.CursorShape.PointingHandCursor)
    elevenlabs_voice_combo.view().setCursor(Qt.CursorShape.PointingHandCursor)
    elevenlabs_voice_combo.view().setUniformItemSizes(True)
    elevenlabs_voice_combo.view().setSpacing(0)
    elevenlabs_voice_combo.setStyleSheet(style_setting_combo())
    elevenlabs_custom_edit = QLineEdit()
    elevenlabs_custom_edit.setStyleSheet(style_input_field())
    elevenlabs_custom_edit.setFixedHeight(HEIGHT_CONTROL)
    elevenlabs_custom_edit.setPlaceholderText(
        tr("settings.voice_elevenlabs_placeholder"),
    )

    elevenlabs_voice_col.addWidget(elevenlabs_gender_widget)
    elevenlabs_voice_col.addWidget(elevenlabs_voice_combo)
    elevenlabs_voice_col.addWidget(elevenlabs_custom_edit)

    def _resolve_elevenlabs_target(
        saved_id: str,
        voices: tuple[tuple[str, str], ...],
        gender: str,
    ) -> str:
        """Decides which combo entry the saved voice ID should land on.

        Returns the custom sentinel for IDs not in any curated gender
        list (preserves cloned/custom voices across gender toggles),
        the saved ID itself when it's in the current gender's curated
        list, or the gender default otherwise (Rachel for FEMALE,
        George for MALE — looked up by ID rather than by catalogue
        position since the catalogue is sorted strictly A→Z).  Empty
        saved value falls into the "default" branch — there is no
        Auto sentinel.
        """
        from src.core.speech_engine import (  # noqa: PLC0415
            get_elevenlabs_default_voice_id,
        )

        all_ids = _all_curated_elevenlabs_ids()
        if saved_id and saved_id not in all_ids:
            return _elevenlabs_custom_sentinel
        if saved_id in {vid for _n, vid in voices}:
            return saved_id
        return get_elevenlabs_default_voice_id(gender)

    def _populate_elevenlabs_voice_combo() -> None:
        """Repopulates the combo with curated voices for the saved gender.

        Layout: curated voices for current gender → ``Custom (enter
        Voice ID)``.  The custom-edit text field is shown only when
        ``Custom`` is selected; in every other state the saved setting
        equals the dropdown's current data.  No Auto sentinel — empty
        saved value auto-picks the gender default and persists.
        """
        saved_gender = (
            str(load_setting(SETTING_LAST_VOICE_GENDER, "FEMALE")).upper() or "FEMALE"
        )
        saved_id = str(load_setting(SETTING_ELEVENLABS_VOICE_ID, ""))
        voices = get_elevenlabs_voices_for_gender(saved_gender)

        elevenlabs_voice_combo.blockSignals(True)
        elevenlabs_voice_combo.clear()
        for name, vid in voices:
            elevenlabs_voice_combo.addItem(name, vid)
        elevenlabs_voice_combo.addItem(
            tr("settings.voice_elevenlabs_custom"),
            _elevenlabs_custom_sentinel,
        )

        target = _resolve_elevenlabs_target(saved_id, voices, saved_gender)

        for i in range(elevenlabs_voice_combo.count()):
            if elevenlabs_voice_combo.itemData(i) == target:
                elevenlabs_voice_combo.setCurrentIndex(i)
                break
        elevenlabs_voice_combo.blockSignals(False)

        # Sync custom-edit visibility + content.
        is_custom = target == _elevenlabs_custom_sentinel
        elevenlabs_custom_edit.setVisible(is_custom)
        if is_custom and elevenlabs_custom_edit.text() != saved_id:
            elevenlabs_custom_edit.blockSignals(True)
            elevenlabs_custom_edit.setText(saved_id)
            elevenlabs_custom_edit.blockSignals(False)

        # Persist whenever the target differs from saved.  Custom keeps
        # the saved ID as-is (text field already holds it).
        if not is_custom and target != saved_id:
            save_setting(SETTING_ELEVENLABS_VOICE_ID, target)

        # Toggling the custom-edit visibility changes the page's
        # sizeHint by HEIGHT_CONTROL + spacing — bubble it up to the
        # stack so the row doesn't overflow the section group's
        # bottom border (the bug screenshot reported by a user
        # picking Custom on the ElevenLabs page).
        _resize_stack_to_current()

    _populate_elevenlabs_voice_combo()

    def _refresh_elevenlabs_combo_labels() -> None:
        """Re-translates the Custom sentinel on language switch."""
        elevenlabs_voice_combo.blockSignals(True)
        elevenlabs_voice_combo.setItemText(
            elevenlabs_voice_combo.count() - 1,
            tr("settings.voice_elevenlabs_custom"),
        )
        elevenlabs_voice_combo.blockSignals(False)
        elevenlabs_custom_edit.setPlaceholderText(
            tr("settings.voice_elevenlabs_placeholder"),
        )

    elevenlabs_voice_combo.apply_language = _refresh_elevenlabs_combo_labels

    def _on_elevenlabs_voice_changed(idx: int) -> None:
        """Persists the chosen ElevenLabs voice + toggles custom edit."""
        data = elevenlabs_voice_combo.itemData(idx)
        if data == _elevenlabs_custom_sentinel:
            elevenlabs_custom_edit.setVisible(True)
            # Keep whatever was previously saved as the custom seed
            # text — empty if the user just opened Custom for the
            # first time.  Don't overwrite SETTING_ELEVENLABS_VOICE_ID
            # yet; the user will type and editingFinished will save.
            elevenlabs_custom_edit.setFocus(Qt.FocusReason.OtherFocusReason)
        else:
            elevenlabs_custom_edit.setVisible(False)
            save_setting(SETTING_ELEVENLABS_VOICE_ID, data or "")
        # Bubble the custom-edit visibility flip up to the stack
        # height — without it the stack stays at its build-time hint
        # and the new field overflows below the section border.
        _resize_stack_to_current()

    elevenlabs_voice_combo.currentIndexChanged.connect(
        _on_elevenlabs_voice_changed,
    )

    def _on_elevenlabs_custom_committed() -> None:
        """Persists the custom-typed Voice ID when the user finishes editing."""
        save_setting(
            SETTING_ELEVENLABS_VOICE_ID,
            elevenlabs_custom_edit.text().strip(),
        )

    elevenlabs_custom_edit.editingFinished.connect(
        _on_elevenlabs_custom_committed,
    )

    # Gemini: dropdown filtered by the currently-selected gender.  The
    # first item ("Auto") writes empty string to the setting so the
    # engine falls back to gender-default mapping; the remaining items
    # are voices from ``GEMINI_TTS_VOICES_BY_GENDER[<gender>]``.
    # Showing voices that don't match the gender would silently override
    # the gender setting on the engine (explicit voice wins over gender),
    # which is confusing — so we filter the list instead.
    from src.core.speech_engine import (  # noqa: PLC0415
        get_gemini_voices_for_gender,
    )

    gemini_voice_combo = QComboBox()
    gemini_voice_combo.setFixedHeight(HEIGHT_CONTROL)
    gemini_voice_combo.setCursor(Qt.CursorShape.PointingHandCursor)
    gemini_voice_combo.view().setCursor(Qt.CursorShape.PointingHandCursor)
    gemini_voice_combo.view().setUniformItemSizes(True)
    gemini_voice_combo.view().setSpacing(0)
    gemini_voice_combo.setStyleSheet(style_setting_combo())

    def _populate_gemini_voice_combo() -> None:
        """Repopulates the combo with voices matching the saved gender.

        Called on initial build, when any gender radio toggles, and when
        the user switches to the Gemini page.  Always lands on a
        concrete voice — there is no "Auto" sentinel.  If the saved
        value is empty or doesn't match the new gender's list, picks
        the gender default (Kore for Female, Puck for Male — looked
        up by name via :func:`get_gemini_default_voice` rather than
        by catalogue position since the catalogue is sorted strictly
        A→Z) and persists it so the engine sees the same state.
        """
        from src.core.speech_engine import (  # noqa: PLC0415
            get_gemini_default_voice,
        )

        saved_gender = (
            str(load_setting(SETTING_LAST_VOICE_GENDER, "FEMALE")).upper() or "FEMALE"
        )
        saved_voice = str(load_setting(SETTING_GEMINI_TTS_VOICE_NAME, ""))
        voices = get_gemini_voices_for_gender(saved_gender)

        gemini_voice_combo.blockSignals(True)
        gemini_voice_combo.clear()
        for voice in voices:
            gemini_voice_combo.addItem(voice, voice)

        target = (
            saved_voice
            if saved_voice in voices
            else get_gemini_default_voice(saved_gender)
        )
        for i in range(gemini_voice_combo.count()):
            if gemini_voice_combo.itemData(i) == target:
                gemini_voice_combo.setCurrentIndex(i)
                break
        gemini_voice_combo.blockSignals(False)

        # Persist whenever we changed the value so the engine sees the
        # same state we now show — covers empty-saved and out-of-list.
        if target != saved_voice:
            save_setting(SETTING_GEMINI_TTS_VOICE_NAME, target)

    _populate_gemini_voice_combo()

    def _on_gemini_voice_changed(idx: int) -> None:
        """Persists the chosen Gemini voice."""
        save_setting(
            SETTING_GEMINI_TTS_VOICE_NAME,
            gemini_voice_combo.itemData(idx) or "",
        )

    gemini_voice_combo.currentIndexChanged.connect(_on_gemini_voice_changed)

    # Gemini page = gender radio (top) + voice combo (bottom).  The
    # gender radio sets the engine fallback when the combo's "Auto"
    # entry is selected; explicit voice choice overrides gender.
    gemini_voice_widget = QWidget()
    gemini_voice_widget.setStyleSheet("background: transparent;")
    gemini_voice_col = QVBoxLayout(gemini_voice_widget)
    gemini_voice_col.setContentsMargins(0, 0, 0, 0)
    # Inherit default QVBoxLayout spacing — see the matching note on
    # ``elevenlabs_voice_col`` above for the rationale.
    gemini_gender_widget = _build_voice_gender_widget()
    gemini_voice_col.addWidget(gemini_gender_widget)
    gemini_voice_col.addWidget(gemini_voice_combo)

    # Piper page = gender radio (top) + "Download voices…" button
    # that opens the Piper voice library dialog.  The library dialog
    # owns the per-voice install/download state; the engine
    # auto-picks a voice for ``(target_lang, gender)`` from the
    # curated catalogue at synthesis time, so the user only ever
    # decides WHICH languages to install — not which specific voice
    # ID per language.
    piper_voice_widget = QWidget()
    piper_voice_widget.setStyleSheet("background: transparent;")
    piper_voice_col = QVBoxLayout(piper_voice_widget)
    piper_voice_col.setContentsMargins(0, 0, 0, 0)
    # Inherit default QVBoxLayout spacing — see the matching note on
    # ``elevenlabs_voice_col`` above for the rationale.

    piper_gender_widget = _build_voice_gender_widget()
    piper_voice_col.addWidget(piper_gender_widget)

    piper_manage_btn = QPushButton(tr("settings.piper_manage_voices"))
    piper_manage_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    piper_manage_btn.setFixedHeight(HEIGHT_CONTROL)
    piper_manage_btn.setStyleSheet(style_outlined_primary_button())
    # Wrap in a horizontal row with a trailing stretch so the button
    # sizes to its label rather than expanding to the column width
    # (the QVBoxLayout's default Preferred horizontal policy would
    # otherwise stretch a single QPushButton edge-to-edge — visually
    # heavy for a secondary action like "Download voices now").
    piper_manage_row = QHBoxLayout()
    piper_manage_row.setContentsMargins(0, 0, 0, 0)
    piper_manage_row.addWidget(piper_manage_btn)
    piper_manage_row.addStretch(1)
    piper_voice_col.addLayout(piper_manage_row)

    def _open_piper_voice_dialog() -> None:
        """Opens the Piper voice library dialog and refreshes the banner.

        ``voices_changed`` fires whenever a voice install state
        flips; we hook it back to ``_refresh_piper_installed_banner``
        so the summary banner above the engine radios bumps its
        "N language(s) installed" count without polling.
        """
        from src.ui.dialogs import (  # noqa: PLC0415
            PiperVoiceDownloadDialog,
        )

        dlg = PiperVoiceDownloadDialog(widget)
        dlg.voices_changed.connect(_refresh_piper_installed_banner)
        try:
            dlg.exec()
        finally:
            # Final refresh on close — covers downloads that finished
            # after the user clicked Close (rare, but the bounded
            # 2 s wait inside the dialog can let one land last).
            _refresh_piper_installed_banner()

    piper_manage_btn.clicked.connect(_open_piper_voice_dialog)

    # Re-translate the manage button on language switch.
    def _apply_piper_manage_language() -> None:
        piper_manage_btn.setText(tr("settings.piper_manage_voices"))

    piper_manage_btn.apply_language = _apply_piper_manage_language

    # Any of the five gender widgets (Edge / Google / ElevenLabs /
    # Gemini / Piper) writes the same shared setting; repopulate the
    # filtered combos (Gemini + ElevenLabs) from any toggle so they
    # stay in sync regardless of which page the user picked the gender
    # on.  Piper has no per-voice combo any more — the engine
    # auto-picks ``(target_lang, gender)`` from the curated catalogue
    # at synthesis time, so a gender toggle needs no UI sync there.
    def _on_any_gender_toggled() -> None:
        _populate_gemini_voice_combo()
        _populate_elevenlabs_voice_combo()

    for _gw in (
        edge_voice_widget,
        google_voice_widget,
        elevenlabs_gender_widget,
        gemini_gender_widget,
        piper_gender_widget,
    ):
        _gw._button_group.buttonClicked.connect(  # type: ignore[attr-defined]
            lambda _btn: _on_any_gender_toggled(),
        )

    voice_picker_stack.addWidget(edge_voice_widget)  # 0 = Edge
    voice_picker_stack.addWidget(google_voice_widget)  # 1 = Google
    voice_picker_stack.addWidget(elevenlabs_voice_widget)  # 2 = ElevenLabs
    voice_picker_stack.addWidget(gemini_voice_widget)  # 3 = Gemini
    voice_picker_stack.addWidget(piper_voice_widget)  # 4 = Piper

    _voice_method_to_index = {
        VOICE_TTS_EDGE: 0,
        VOICE_TTS_GOOGLE: 1,
        VOICE_TTS_ELEVENLABS: 2,
        VOICE_TTS_GEMINI: 3,
        VOICE_TTS_PIPER: 4,
    }

    voice_picker_stack.currentChanged.connect(
        lambda _idx: _resize_stack_to_current(),
    )

    def _sync_voice_picker_for_method() -> None:
        """Swaps the picker widget to match the currently-selected method."""
        current_method = load_setting(
            SETTING_VOICE_TTS_METHOD,
            VOICE_TTS_EDGE,
        )
        idx = _voice_method_to_index.get(str(current_method), 0)
        voice_picker_stack.setCurrentIndex(idx)
        # ``currentChanged`` only fires when the index actually changes.
        # Call directly so the initial sync (before any toggle) and any
        # noop re-sync still pin the right height.
        _resize_stack_to_current()
        # Re-derive the filtered combos (Gemini + ElevenLabs) from
        # the saved gender every time we land on (or stay on) the
        # respective page — covers cross-tab gender changes and the
        # auto-pick-on-mismatch behaviour.  Refresh the Piper summary
        # banner too: a download finished in the library dialog (or
        # on a future background path) wouldn't otherwise bump the
        # count until the user navigates away and back.
        if str(current_method) == VOICE_TTS_GEMINI:
            _populate_gemini_voice_combo()
        elif str(current_method) == VOICE_TTS_ELEVENLABS:
            _populate_elevenlabs_voice_combo()
        elif str(current_method) == VOICE_TTS_PIPER:
            _refresh_piper_installed_banner()

    _sync_voice_picker_for_method()

    # Hook into the method radio toggle so the picker swaps
    # immediately when the user changes TTS backend.  Re-run via
    # ``buttonClicked`` (after the existing ``_on_tts_method_toggled``
    # already persisted the new value, which our sync reads back).
    method_button_group.buttonClicked.connect(
        lambda _btn: _sync_voice_picker_for_method(),
    )

    tts_group_layout.addWidget(voice_picker_container)

    # Re-sync on tab show too — covers the case where the user
    # changes the TTS method via API (or another tab) and comes back.
    widget._sync_voice_picker_for_method = _sync_voice_picker_for_method

    layout.addWidget(tts_group)

    # 3. Voice Generation section
    gen_group, gen_layout, _ = create_section_group(
        tr("settings.voice_generation"),
        tr_key="settings.voice_generation",
    )

    # Output format radio buttons
    # Voice picker mirrors Live audio's 4-format set.  MP3/WAV are
    # written natively by the synth engine; FLAC/OGG are post-encoded
    # from a WAV intermediate in ``_VoiceWorker`` via the shared
    # ``post_encode_audio`` helper.  All four require ffmpeg (which
    # Voice already requires for chunk concatenation).
    fmt_options = [
        ("MP3", ".mp3"),
        ("WAV", ".wav"),
        ("FLAC", ".flac"),
        ("OGG", ".ogg"),
    ]

    fmt_container = QWidget()
    fmt_container.setStyleSheet(style_setting_container())
    fmt_row = QHBoxLayout(fmt_container)
    fmt_row.setContentsMargins(0, 0, 0, 0)

    fmt_label = QLabel("")
    _bind_text(fmt_label, "settings.voice_format")
    fmt_label.setStyleSheet(style_input_label())
    fmt_label.setFixedWidth(LABEL_WIDTH)
    fmt_label.setFixedHeight(HEIGHT_CONTROL)
    fmt_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    fmt_row.addWidget(fmt_label)

    fmt_radio_layout = QHBoxLayout()
    fmt_radio_layout.setSpacing(SPACING_SUBSECTION)
    fmt_button_group = QButtonGroup(widget)
    fmt_button_group.setExclusive(True)
    saved_fmt = load_setting(SETTING_LAST_VOICE_FORMAT, ".mp3")

    for i, (label, ext) in enumerate(fmt_options):
        radio = QRadioButton(label)
        radio.setCursor(Qt.CursorShape.PointingHandCursor)
        radio.setStyleSheet(style_radio_button())
        radio.setProperty("ext", ext)
        fmt_button_group.addButton(radio, i)
        fmt_radio_layout.addWidget(radio)
        if ext == saved_fmt:
            radio.setChecked(True)

    def _on_voice_format_toggled(btn: QRadioButton) -> None:
        """Persists the selected voice output format (.mp3 / .wav / .flac / .ogg)."""
        if btn.isChecked():
            save_setting(SETTING_LAST_VOICE_FORMAT, btn.property("ext"))

    fmt_button_group.buttonClicked.connect(_on_voice_format_toggled)
    fmt_radio_layout.addStretch()

    if not fmt_button_group.checkedButton():
        first = fmt_button_group.button(0)
        if first:
            first.setChecked(True)

    fmt_row.addLayout(fmt_radio_layout, 1)
    gen_layout.addWidget(fmt_container)
    layout.addWidget(gen_group)

    # NOTE: no per-format ffmpeg gating here.  Whether a format
    # actually needs ffmpeg is backend-dependent (Edge+WAV needs
    # ffmpeg for MP3→WAV transcode; Piper+MP3 needs WAV→MP3; FLAC/OGG
    # always need post-encoding).  No format is truly "safe" without
    # ffmpeg.  The top-of-page ffmpeg install banner on the Voice
    # PAGE (not this settings tab) plus the runtime modal cover this
    # surface — the radios stay enabled here so users can pick any
    # format and rely on the banner / modal to surface the
    # prerequisite if missing.

    # 4. History Management section
    hist_group, hist_layout, _ = create_section_group(
        tr("settings.history_mgmt"),
        tr_key="settings.history_mgmt",
    )
    auto_remove_widget, _ = create_setting_checkbox(
        tr("settings.voice_auto_remove"),
        SETTING_VOICE_AUTO_REMOVE,
        default=False,
        label_tr_key="settings.voice_auto_remove",
    )
    hist_layout.addWidget(auto_remove_widget)
    layout.addWidget(hist_group)

    layout.addStretch()
    return widget


def create_dubbing_settings() -> QWidget:
    """Creates the Dubbing settings tab content.

    Exposes the dubbed-video output directory and the auto-remove-from-history
    toggle. Dubbing is a pipeline that consumes STT, LLM, and TTS engines
    configured on their respective tabs (Subtitle / LLM / Voice). Also
    surfaces a warning when FFmpeg — required by the final mix step — is
    missing from PATH.
    """
    from src.constants.settings import (  # noqa: PLC0415
        SETTING_DUBBING_AUTO_REMOVE,
        SETTING_DUBBING_STORAGE_PATH,
    )

    widget = QWidget()
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(0, MARGIN_SECTION, 0, 0)
    layout.setSpacing(SPACING_SECTION)

    # Pipeline-dependency hint: STT/LLM/TTS engines come from other tabs.
    deps_hint_frame, _ = create_banner(
        tr("settings.dubbing_pipeline_hint"),
        variant="info",
        tr_key="settings.dubbing_pipeline_hint",
    )
    layout.addWidget(deps_hint_frame)

    # NOTE: no FFmpeg setup-hint banner here.  The Dubbing PAGE already
    # shows the install banner at the top via
    # ``create_ffmpeg_install_banner`` — duplicating it on this settings
    # tab adds visual noise without surfacing new information.

    # 1. Output section
    out_group, out_layout, _ = create_section_group(
        tr("settings.output"),
        tr_key="settings.output",
    )
    storage_widget, _ = create_setting_path(
        tr("settings.dubbing_save_to"),
        SETTING_DUBBING_STORAGE_PATH,
        widget,
        custom_label_width=240,
        label_tr_key="settings.dubbing_save_to",
        placeholder_tr_key="settings.save_to_auto",
    )
    _add_save_to_auto_info(out_layout, storage_widget)
    layout.addWidget(out_group)

    # 2. History Management section
    hist_group, hist_layout, _ = create_section_group(
        tr("settings.history_mgmt"),
        tr_key="settings.history_mgmt",
    )
    auto_remove_widget, _ = create_setting_checkbox(
        tr("settings.dubbing_auto_remove"),
        SETTING_DUBBING_AUTO_REMOVE,
        default=False,
        label_tr_key="settings.dubbing_auto_remove",
    )
    hist_layout.addWidget(auto_remove_widget)
    layout.addWidget(hist_group)

    layout.addStretch()
    return widget


def create_live_settings() -> QWidget:  # noqa: PLR0915, PLR0912
    """Creates the Live Translation settings tab content.

    Exposes the live STT engine selection (Whisper / Gemini Live / Soniox —
    cloud options gated on the Gemini API key from the LLM tab and the
    Soniox key from the Service tab), the Whisper model size (visible only
    when Whisper is the active engine), engine-specific info panels that
    swap on selection, and the display preference for showing the original
    text alongside translations.
    """
    from src.constants.settings import (  # noqa: PLC0415
        LIVE_STT_SONIOX,
        LIVE_STT_WHISPER,
        SETTING_LIVE_SHOW_SPEAKER,
        SETTING_LIVE_STT_METHOD,
        SETTING_LIVE_WHISPER_MODEL,
        SETTING_LLM_MODEL_LIVE,
    )
    from src.utils.config_manager import (  # noqa: PLC0415
        check_soniox_setup,
        format_model_id,
        get_available_models,
        load_model_for_feature,
        save_model_for_feature,
    )

    widget = QWidget()
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(0, MARGIN_SECTION, 0, 0)
    layout.setSpacing(SPACING_SECTION)

    def _style_live_settings_slider() -> str:
        """Theme-aware QSS for sliders inside the Live settings tab.

        Used by the Session-section auto-stop slider and the
        Overlay-section font / opacity sliders.  Distinct from
        ``_style_overlay_slider`` in ``live.py`` — that one renders
        white-on-dark for the overlay chrome itself.  Here we want
        the slider to inherit the app's primary colour and look at
        home next to the radio rows in the rest of the tab.
        """
        return (
            "QSlider::groove:horizontal {"
            "  height: 4px;"
            f" background: {color('border_light')};"
            "  border-radius: 2px;"
            "}"
            "QSlider::handle:horizontal {"
            "  width: 16px; height: 16px;"
            "  margin: -6px 0;"
            f" background: {color('primary')};"
            "  border-radius: 8px;"
            "  border: none;"
            "}"
            "QSlider::handle:horizontal:hover {"
            f" background: {color('primary_hover')};"
            "}"
            "QSlider::sub-page:horizontal {"
            f" background: {color('primary')};"
            "  border-radius: 2px;"
            "}"
        )

    # 1. STT Engine section
    stt_group, stt_layout, _ = create_section_group(
        tr("settings.live_stt"),
        tr_key="settings.live_stt",
    )

    # Comparison banner — describes each backend's tradeoffs (offline /
    # online, cost, languages) the same way the OCR / TTS / STT
    # sections do.  Replaces the prior ``(local)`` / ``(cloud)``
    # annotations on the radio labels themselves, which clutter the
    # control row and don't have room for cost / language details.
    stt_comparison_frame, _ = create_banner(
        tr("settings.live_stt_comparison"),
        variant="info",
        tr_key="settings.live_stt_comparison",
        rich_text=True,
    )
    stt_layout.addWidget(stt_comparison_frame)

    # STT method radio buttons
    method_container = QWidget()
    method_container.setStyleSheet(style_setting_container())
    method_row = QHBoxLayout(method_container)
    method_row.setContentsMargins(0, 0, 0, 0)

    method_label = QLabel(tr("settings.live_stt_method"))
    _bind_text(method_label, "settings.live_stt_method")
    method_label.setStyleSheet(style_input_label())
    method_label.setFixedWidth(LABEL_WIDTH)
    method_label.setFixedHeight(HEIGHT_CONTROL)
    method_label.setAlignment(
        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
    )
    method_row.addWidget(method_label)

    method_radio_layout = QHBoxLayout()
    method_radio_layout.setSpacing(SPACING_SUBSECTION)
    method_button_group = QButtonGroup(widget)
    method_button_group.setExclusive(True)
    saved_method = load_setting(SETTING_LIVE_STT_METHOD, LIVE_STT_WHISPER)

    soniox_available = check_soniox_setup()

    _stt_methods = [
        (LIVE_STT_WHISPER, "settings.live_stt_whisper"),
        (LIVE_STT_SONIOX, "settings.live_stt_soniox"),
    ]
    for i, (method_val, tr_key) in enumerate(_stt_methods):
        radio = QRadioButton("")
        _bind_text(radio, tr_key)
        radio.setCursor(Qt.CursorShape.PointingHandCursor)
        radio.setStyleSheet(style_radio_button())
        radio.setProperty("method", method_val)
        method_button_group.addButton(radio, i)
        method_radio_layout.addWidget(radio)
        if method_val == LIVE_STT_SONIOX and not soniox_available:
            radio.setEnabled(False)
        elif method_val == saved_method:
            radio.setChecked(True)

    method_radio_layout.addStretch()
    auto_fallback_selection(method_button_group, SETTING_LIVE_STT_METHOD)

    method_row.addLayout(method_radio_layout, 1)

    # Setup hint shown when the backing API key is missing. Rendered above
    # the method radios so it precedes the control it explains.
    soniox_setup_hint_frame, _ = create_banner(
        tr("settings.live_soniox_setup_hint"),
        variant="warning",
        tr_key="settings.live_soniox_setup_hint",
    )
    soniox_setup_hint_frame.setVisible(not soniox_available)
    stt_layout.addWidget(soniox_setup_hint_frame)

    stt_layout.addWidget(method_container)

    # Whisper model radio buttons (visible only when Whisper is selected)
    model_container = QWidget()
    model_container.setStyleSheet(style_setting_container())
    model_row = QHBoxLayout(model_container)
    model_row.setContentsMargins(0, 0, 0, 0)

    model_label = QLabel("")
    _bind_text(model_label, "settings.whisper_model")
    model_label.setStyleSheet(style_input_label())
    model_label.setFixedWidth(LABEL_WIDTH)
    model_label.setFixedHeight(HEIGHT_CONTROL)
    model_label.setAlignment(
        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
    )
    model_row.addWidget(model_label)

    model_radio_layout = QHBoxLayout()
    model_radio_layout.setSpacing(SPACING_SUBSECTION)
    model_button_group = QButtonGroup(widget)
    model_button_group.setExclusive(True)
    saved_model = load_setting(SETTING_LIVE_WHISPER_MODEL, "tiny")

    _whisper_models = [
        ("tiny", "75 MB"),
        ("base", "140 MB"),
        ("small", "460 MB"),
        ("medium", "1.5 GB"),
        ("large", "3.0 GB"),
    ]
    for i, (size, disk) in enumerate(_whisper_models):
        radio = QRadioButton(f"{size} ({disk})")
        radio.setCursor(Qt.CursorShape.PointingHandCursor)
        radio.setStyleSheet(style_radio_button())
        radio.setProperty("model", size)
        model_button_group.addButton(radio, i)
        model_radio_layout.addWidget(radio)
        if size == saved_model:
            radio.setChecked(True)

    def _on_model_toggled(btn: QRadioButton) -> None:
        """Persists the selected Whisper model size for live STT."""
        if btn.isChecked():
            save_setting(SETTING_LIVE_WHISPER_MODEL, btn.property("model"))

    model_button_group.buttonClicked.connect(_on_model_toggled)
    model_radio_layout.addStretch()

    if not model_button_group.checkedButton():
        tiny_btn = model_button_group.button(0)
        if tiny_btn:
            tiny_btn.setChecked(True)

    model_row.addLayout(model_radio_layout, 1)

    # Translation-model picker for Whisper STT.  Whisper only
    # transcribes (source-language text); translation is a separate
    # LLM step.  Soniox + Gemini Live translate end-to-end inside
    # their own session, so the picker is gated to Whisper only via
    # ``_apply_method_panels`` below.  Hidden entirely when no
    # models are configured (fresh install) — appears the moment
    # the user wires up a provider in the LLM tab.
    translation_model_container = QWidget()
    translation_model_container.setStyleSheet(style_setting_container())
    translation_model_row = QHBoxLayout(translation_model_container)
    translation_model_row.setContentsMargins(0, 0, 0, 0)

    translation_model_label = QLabel("")
    _bind_text(translation_model_label, "settings.live_translation_model")
    translation_model_label.setStyleSheet(style_input_label())
    translation_model_label.setFixedWidth(LABEL_WIDTH)
    translation_model_label.setFixedHeight(HEIGHT_CONTROL)
    translation_model_label.setAlignment(
        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
    )
    translation_model_row.addWidget(translation_model_label)

    translation_model_combo = QComboBox()
    translation_model_combo.setFixedHeight(HEIGHT_CONTROL)
    translation_model_combo.setCursor(Qt.CursorShape.PointingHandCursor)
    translation_model_combo.view().setCursor(Qt.CursorShape.PointingHandCursor)
    translation_model_combo.view().setUniformItemSizes(True)
    translation_model_combo.view().setSpacing(0)
    translation_model_combo.setStyleSheet(style_setting_combo())

    def _refresh_translation_model_combo() -> None:
        """Re-populates the combo and hides the row when no models exist.

        Visibility is double-gated: this function decides "is there a
        choice to make" (≥1 model configured); ``_apply_method_panels``
        decides "is the choice relevant" (Whisper only).  Both must
        return True for the row to be visible.
        """
        translation_model_combo.blockSignals(True)
        translation_model_combo.clear()
        models = get_available_models()
        for provider, model_name in models:
            translation_model_combo.addItem(
                model_name,
                format_model_id(provider, model_name),
            )
        saved = load_model_for_feature(SETTING_LLM_MODEL_LIVE)
        if saved:
            for i in range(translation_model_combo.count()):
                if translation_model_combo.itemData(i) == saved:
                    translation_model_combo.setCurrentIndex(i)
                    break
        translation_model_combo.blockSignals(False)

    def _on_translation_model_changed(_idx: int) -> None:
        value = translation_model_combo.currentData() or ""
        if value:
            save_model_for_feature(SETTING_LLM_MODEL_LIVE, value)

    translation_model_combo.currentIndexChanged.connect(
        _on_translation_model_changed,
    )
    translation_model_row.addWidget(translation_model_combo, 1)

    _refresh_translation_model_combo()

    # Whisper auto-download info
    whisper_info, _ = create_banner(
        tr("settings.whisper_auto_download"),
        variant="info",
        tr_key="settings.whisper_auto_download",
    )

    # Soniox info (visible only when Soniox is selected)
    soniox_info, _ = create_banner(
        tr("settings.live_soniox_info"),
        variant="info",
        tr_key="settings.live_soniox_info",
    )

    # Speaker-labels toggle — gated on Soniox because Whisper doesn't
    # do diarization.  Rendered as an ``[label] [On] [Off]`` radio
    # row to match the STT-engine radios directly above it; pairing
    # the two binary-ish controls in the same visual language keeps
    # the section scannable.
    show_speaker_widget = QWidget()
    show_speaker_widget.setStyleSheet(style_setting_container())
    show_speaker_row = QHBoxLayout(show_speaker_widget)
    show_speaker_row.setContentsMargins(0, 0, 0, 0)

    show_speaker_label = QLabel(tr("settings.live_show_speaker"))
    show_speaker_label.setStyleSheet(style_input_label())
    show_speaker_label.setFixedWidth(LABEL_WIDTH)
    show_speaker_label.setFixedHeight(HEIGHT_CONTROL)
    show_speaker_label.setAlignment(
        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
    )
    _bind_text(show_speaker_label, "settings.live_show_speaker")
    show_speaker_row.addWidget(show_speaker_label)

    show_speaker_radio_layout = QHBoxLayout()
    show_speaker_radio_layout.setSpacing(SPACING_SUBSECTION)
    show_speaker_group = QButtonGroup(widget)
    show_speaker_group.setExclusive(True)
    saved_show_speaker = bool(load_setting(SETTING_LIVE_SHOW_SPEAKER, True))

    # ``setProperty("value", bool)`` is the source of truth for which
    # radio represents which persisted value — the visible text comes
    # from i18n and can change per locale, so we never key off the
    # label.  ``QButtonGroup`` id mirrors the list index for the
    # ``apply_language`` refresh loop below.
    show_speaker_items = [
        (True, "settings.option_on"),
        (False, "settings.option_off"),
    ]
    for i, (value, tr_key) in enumerate(show_speaker_items):
        radio = QRadioButton(tr(tr_key))
        radio.setCursor(Qt.CursorShape.PointingHandCursor)
        radio.setStyleSheet(style_radio_button())
        radio.setProperty("value", value)
        show_speaker_group.addButton(radio, i)
        show_speaker_radio_layout.addWidget(radio)
        if value == saved_show_speaker:
            radio.setChecked(True)
    show_speaker_radio_layout.addStretch()

    def _on_show_speaker_toggled(btn: QRadioButton) -> None:
        if btn.isChecked():
            save_setting(
                SETTING_LIVE_SHOW_SPEAKER,
                bool(btn.property("value")),
            )

    show_speaker_group.buttonClicked.connect(_on_show_speaker_toggled)
    show_speaker_row.addLayout(show_speaker_radio_layout, 1)

    def _refresh_show_speaker_options() -> None:
        # ``QButtonGroup.button(id)`` mirrors the index we passed in
        # ``addButton`` above, so this lookup is O(1) per radio and
        # doesn't rely on positional layout iteration.
        for i, (_, tr_key) in enumerate(show_speaker_items):
            btn = show_speaker_group.button(i)
            if btn is not None:
                btn.setText(tr(tr_key))

    show_speaker_widget.apply_language = _refresh_show_speaker_options

    def _apply_method_panels(method: str) -> None:
        """Shows engine-specific panels based on the active STT method."""
        model_container.setVisible(method == LIVE_STT_WHISPER)
        whisper_info.setVisible(method == LIVE_STT_WHISPER)
        soniox_info.setVisible(method == LIVE_STT_SONIOX)
        # Speaker-label toggle is meaningful only when Soniox is the
        # active backend — Whisper has no diarization so the checkbox
        # would be a no-op.  Visibility tracks the engine choice.
        show_speaker_widget.setVisible(method == LIVE_STT_SONIOX)
        # Translation-model picker: only Whisper needs a separate LLM
        # step (Soniox translates inside its own session).  Also hide
        # when no models are configured at all — no point showing an
        # empty combo on a fresh install.
        translation_model_container.setVisible(
            method == LIVE_STT_WHISPER and translation_model_combo.count() > 0,
        )

    def _on_stt_method_toggled(btn: QRadioButton) -> None:
        """Persists the live STT method and toggles engine-specific panels."""
        if btn.isChecked():
            method = btn.property("method")
            save_setting(SETTING_LIVE_STT_METHOD, method)
            _apply_method_panels(method)

    method_button_group.buttonClicked.connect(_on_stt_method_toggled)

    # Whisper info (auto-download hint) precedes the model radios it explains.
    stt_layout.addWidget(whisper_info)
    stt_layout.addWidget(model_container)
    stt_layout.addWidget(translation_model_container)
    stt_layout.addWidget(soniox_info)
    stt_layout.addWidget(show_speaker_widget)
    layout.addWidget(stt_group)

    # 2. Session section — engine-agnostic session-level controls.
    # Auto-stop is the first occupant; future cost / duration
    # safeguards live here rather than getting buried in the STT
    # engine section where they don't belong.
    from src.constants.settings import (  # noqa: PLC0415
        SETTING_LIVE_AUTO_STOP_MINUTES,
    )

    session_group, session_layout, _ = create_section_group(
        tr("settings.live_auto_actions"),
        tr_key="settings.live_auto_actions",
    )

    # ── Auto-stop after silence ────────────────────────────────────
    # Three-option radio (None / 3 min / 10 min) instead of the prior
    # checkbox-plus-slider so the safeguard reads as a single discrete
    # choice rather than a fine-grained tuning surface.  Engine-
    # agnostic: the Live page restarts a single-shot QTimer on every
    # finalised sentence, so the timer represents "minutes since the
    # last spoken sentence" regardless of which STT backend is active.
    # Applies on the next ``Start`` (the value is read at session
    # start, not live-applied to a running session).
    #
    # Storage stays as an integer in ``SETTING_LIVE_AUTO_STOP_MINUTES``
    # (0 / 3 / 10) so the runtime in ``live.py`` doesn't change.  A
    # legacy saved value from the old slider (1-60) is snapped to the
    # nearest allowed bucket: 0 → None, 1-6 → 3, 7+ → 10.  Picks "3"
    # as the implicit default for the common middle range so the user
    # sees their old "moderate" setting roughly preserved.
    auto_stop_options: tuple[tuple[int, str], ...] = (
        (0, "settings.live_auto_stop_none"),
        (3, "settings.live_auto_stop_3min"),
        (10, "settings.live_auto_stop_10min"),
    )

    try:
        saved_auto_stop = int(load_setting(SETTING_LIVE_AUTO_STOP_MINUTES, 0))
    except (TypeError, ValueError):
        saved_auto_stop = 0
    if saved_auto_stop <= 0:
        snapped_auto_stop = 0
    elif saved_auto_stop <= 6:  # noqa: PLR2004 — midpoint between 3 and 10
        snapped_auto_stop = 3
    else:
        snapped_auto_stop = 10

    auto_stop_widget = QWidget()
    auto_stop_widget.setStyleSheet(style_setting_container())
    auto_stop_row = QHBoxLayout(auto_stop_widget)
    auto_stop_row.setContentsMargins(0, 0, 0, 0)

    auto_stop_label = QLabel(tr("settings.live_auto_stop_label"))
    auto_stop_label.setStyleSheet(style_input_label())
    auto_stop_label.setFixedWidth(LABEL_WIDTH)
    auto_stop_label.setFixedHeight(HEIGHT_CONTROL)
    auto_stop_label.setAlignment(
        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
    )
    _bind_text(auto_stop_label, "settings.live_auto_stop_label")
    auto_stop_row.addWidget(auto_stop_label)

    auto_stop_radio_layout = QHBoxLayout()
    auto_stop_radio_layout.setSpacing(SPACING_SUBSECTION)
    auto_stop_group = QButtonGroup(widget)
    auto_stop_group.setExclusive(True)

    # ``setProperty("value", int)`` is the canonical persisted value
    # (the radio label is i18n-driven and changes per locale, so we
    # never key off the visible text).  ``QButtonGroup`` id mirrors
    # the list index so the language-refresh loop looks each button
    # up in O(1).
    for i, (value, tr_key) in enumerate(auto_stop_options):
        radio = QRadioButton(tr(tr_key))
        radio.setCursor(Qt.CursorShape.PointingHandCursor)
        radio.setStyleSheet(style_radio_button())
        radio.setProperty("value", value)
        auto_stop_group.addButton(radio, i)
        auto_stop_radio_layout.addWidget(radio)
        if value == snapped_auto_stop:
            radio.setChecked(True)
    # Safety net: if snapping didn't land on any option (shouldn't
    # happen given the three buckets cover all ints), check the
    # first radio so the row never renders with zero selection.
    if auto_stop_group.checkedButton() is None:
        first = auto_stop_group.button(0)
        if first is not None:
            first.setChecked(True)
    auto_stop_radio_layout.addStretch()
    auto_stop_row.addLayout(auto_stop_radio_layout, 1)

    def _on_auto_stop_toggled(btn: QRadioButton) -> None:
        if not btn.isChecked():
            return
        minutes = int(btn.property("value") or 0)
        save_setting(SETTING_LIVE_AUTO_STOP_MINUTES, str(minutes))

    def _refresh_auto_stop_options() -> None:
        """Re-renders the radio labels in the current locale."""
        for i, (_value, key) in enumerate(auto_stop_options):
            b = auto_stop_group.button(i)
            if b is not None:
                b.setText(tr(key))

    auto_stop_group.buttonClicked.connect(_on_auto_stop_toggled)
    auto_stop_widget.apply_language = _refresh_auto_stop_options

    # Info banner clarifying the auto-stop trigger.  Users could
    # reasonably assume any of: idle clock time, no audio energy on
    # the mic, no recognised words.  The real trigger is the third
    # (the QTimer restarts on every finalised STT sentence, so
    # background noise / music that never produces a transcript still
    # counts as "silence" for this timer).  Banner sits above the
    # radios — matches the AGENTS convention of "explanation above
    # the gating control".
    auto_stop_info_frame, _ = create_banner(
        tr("settings.live_auto_stop_info"),
        variant="info",
        tr_key="settings.live_auto_stop_info",
    )
    session_layout.addWidget(auto_stop_info_frame)
    session_layout.addWidget(auto_stop_widget)
    layout.addWidget(session_group)

    # Seed panel visibility from the actually-checked radio (may differ from
    # `saved_method` after auto_fallback_selection disabled an unavailable one).
    active = method_button_group.checkedButton()
    _apply_method_panels(active.property("method") if active else LIVE_STT_WHISPER)

    def _sync_live_availability() -> None:
        """Re-checks Soniox availability for Live STT."""
        s_ok = check_soniox_setup()
        for btn in method_button_group.buttons():
            method = btn.property("method")
            if method == LIVE_STT_SONIOX:
                btn.setEnabled(s_ok)
        soniox_setup_hint_frame.setVisible(not s_ok)
        auto_fallback_selection(method_button_group, SETTING_LIVE_STT_METHOD)
        # Pick up newly-added LLM providers so the translation-model
        # combo doesn't stay empty after the user wires up a provider
        # in another tab and returns to this one.
        _refresh_translation_model_combo()
        active_btn = method_button_group.checkedButton()
        _apply_method_panels(
            active_btn.property("method") if active_btn else LIVE_STT_WHISPER,
        )

    widget._sync_live_availability = _sync_live_availability

    # Display section removed — transcript layout + source/translation
    # visibility are now a single picker on the Live page toolbar.

    # Audio Recording section — opt-in save of the live session as
    # transcript text, audio WAV, or both.  ``LIVE_SAVE_NONE`` is the
    # privacy default; the other modes write into the folder at
    # ``SETTING_LIVE_OUTPUT_PATH`` (or app-data ``live_audio/`` when
    # empty) on session stop.
    from src.constants.settings import (  # noqa: PLC0415
        LIVE_SAVE_AUDIO,
        LIVE_SAVE_NONE,
        LIVE_SAVE_TEXT,
        LIVE_SAVE_TEXT_AUDIO,
        SETTING_LIVE_OUTPUT_PATH,
        SETTING_LIVE_SAVE_OUTPUT,
    )

    recording_group, recording_layout, _ = create_section_group(
        tr("settings.live_saving_config"),
        tr_key="settings.live_saving_config",
    )

    # Save-mode radios: None / Text / Audio / Text + Audio.  Rendered
    # as radio buttons (rather than a combo) for visual consistency
    # with the STT-engine and speaker-labels rows above; the four
    # values still fit horizontally on a typical settings-tab width
    # because each label is short.
    save_row = QWidget()
    save_row.setStyleSheet(style_setting_container())
    save_row_layout = QHBoxLayout(save_row)
    save_row_layout.setContentsMargins(0, 0, 0, 0)

    save_mode_label = QLabel(tr("settings.live_save_output"))
    save_mode_label.setStyleSheet(style_input_label())
    save_mode_label.setFixedWidth(LABEL_WIDTH)
    save_mode_label.setFixedHeight(HEIGHT_CONTROL)
    save_mode_label.setAlignment(
        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
    )
    _bind_text(save_mode_label, "settings.live_save_output")
    save_row_layout.addWidget(save_mode_label)

    save_mode_items = [
        (LIVE_SAVE_NONE, "settings.live_save_option_none"),
        (LIVE_SAVE_TEXT, "settings.live_save_option_text"),
        (LIVE_SAVE_AUDIO, "settings.live_save_option_audio"),
        (LIVE_SAVE_TEXT_AUDIO, "settings.live_save_option_text_audio"),
    ]
    save_mode_radio_layout = QHBoxLayout()
    save_mode_radio_layout.setSpacing(SPACING_SUBSECTION)
    save_mode_group = QButtonGroup(widget)
    save_mode_group.setExclusive(True)
    saved_mode = str(load_setting(SETTING_LIVE_SAVE_OUTPUT, LIVE_SAVE_NONE))

    # ``setProperty("value", str)`` is the canonical persisted value;
    # the visible text is i18n-driven and may change per locale, so we
    # never key off the label.  ``QButtonGroup`` id mirrors the list
    # index so the language-refresh loop can look each button up in
    # O(1) without iterating the layout.
    for i, (value, tr_key) in enumerate(save_mode_items):
        radio = QRadioButton(tr(tr_key))
        radio.setCursor(Qt.CursorShape.PointingHandCursor)
        radio.setStyleSheet(style_radio_button())
        radio.setProperty("value", value)
        save_mode_group.addButton(radio, i)
        save_mode_radio_layout.addWidget(radio)
        if value == saved_mode:
            radio.setChecked(True)
    save_mode_radio_layout.addStretch()

    def _on_save_mode_toggled(btn: QRadioButton) -> None:
        if not btn.isChecked():
            return
        mode = str(btn.property("value")) or LIVE_SAVE_NONE
        save_setting(SETTING_LIVE_SAVE_OUTPUT, mode)
        # Auto-fill the path when the user opts into save for the first
        # time.  Without this, the "Save to:" row would render with an
        # empty field and the user has no idea where their files would
        # land — they land in the silent fallback (``~/Documents/AI
        # Translate Live``) but visibility-wise the picker looks like a
        # required-but-blank field.  Stamp the same default into the
        # picker so the user sees where files will go and can override
        # before Start.
        if mode != LIVE_SAVE_NONE and not load_setting(
            SETTING_LIVE_OUTPUT_PATH,
            "",
        ):
            from src.utils.path_manager import (  # noqa: PLC0415
                get_default_live_output_dir,
            )

            output_path_widget.set_path(str(get_default_live_output_dir()))

    save_mode_group.buttonClicked.connect(_on_save_mode_toggled)
    save_row_layout.addLayout(save_mode_radio_layout, 1)

    def _refresh_save_mode_options() -> None:
        for i, (_, tr_key) in enumerate(save_mode_items):
            btn = save_mode_group.button(i)
            if btn is not None:
                btn.setText(tr(tr_key))

    save_row.apply_language = _refresh_save_mode_options

    # Auto-save belongs alongside Auto-stop under "Auto actions" — both
    # are session-lifecycle toggles ("what happens automatically when the
    # session runs / ends").  Inserted at index 3 (after title at 0,
    # auto-stop info banner at 1, auto-stop radios at 2) so the runtime
    # ordering reads top-to-bottom: Auto-stop fires first, then Auto-
    # save persists the session in the stop path.  Format / path / etc.
    # stay in the "Saving configuration" section below — those answer
    # *how* and *where* to save, not *whether*.  QButtonGroup is a
    # logical group, so the radios sitting in a different physical
    # layout doesn't affect the gating below.
    session_layout.insertWidget(3, save_row)

    # ── Transcript + audio format pickers ────────────────────────
    # Both rows are gated on the save-mode selection: transcript
    # format only matters when ``save_mode`` includes Text; audio
    # format only matters when it includes Audio.  Visibility
    # toggles when the user changes the save mode below.
    from src.constants.settings import (  # noqa: PLC0415
        LIVE_AUDIO_FORMAT_FLAC,
        LIVE_AUDIO_FORMAT_MP3,
        LIVE_AUDIO_FORMAT_OGG,
        LIVE_AUDIO_FORMAT_WAV,
        LIVE_TRANSCRIPT_FORMAT_ASS,
        LIVE_TRANSCRIPT_FORMAT_CSV,
        LIVE_TRANSCRIPT_FORMAT_SRT,
        LIVE_TRANSCRIPT_FORMAT_SSA,
        LIVE_TRANSCRIPT_FORMAT_VTT,
        SETTING_LIVE_AUDIO_FORMAT,
        SETTING_LIVE_TRANSCRIPT_FORMAT,
    )

    def _make_format_radio_row(
        label_key: str,
        items: list[tuple[str, str]],
        setting_key: str,
        default_value: str,
    ) -> tuple[QWidget, QButtonGroup, Callable[[], None]]:
        """Builds a ``[label] [radio, radio, ...]`` row.

        Returns ``(widget, group, refresh_callable)``.
        """
        row = QWidget()
        row.setStyleSheet(style_setting_container())
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)

        lbl = QLabel(tr(label_key))
        lbl.setStyleSheet(style_input_label())
        lbl.setFixedWidth(LABEL_WIDTH)
        lbl.setFixedHeight(HEIGHT_CONTROL)
        lbl.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        )
        _bind_text(lbl, label_key)
        row_layout.addWidget(lbl)

        radio_layout = QHBoxLayout()
        radio_layout.setSpacing(SPACING_SUBSECTION)
        group = QButtonGroup(widget)
        group.setExclusive(True)
        saved = str(load_setting(setting_key, default_value)).strip().lower()
        for i, (value, tr_key) in enumerate(items):
            radio = QRadioButton(tr(tr_key))
            radio.setCursor(Qt.CursorShape.PointingHandCursor)
            radio.setStyleSheet(style_radio_button())
            radio.setProperty("value", value)
            group.addButton(radio, i)
            radio_layout.addWidget(radio)
            if value == saved:
                radio.setChecked(True)
        # Fallback: nothing matched the saved value (corrupt setting)
        # — check the first option so the row isn't visually empty.
        if group.checkedButton() is None and items:
            first = group.button(0)
            if first is not None:
                first.setChecked(True)
        radio_layout.addStretch()
        row_layout.addLayout(radio_layout, 1)

        def _on_toggled(btn: QRadioButton) -> None:
            if not btn.isChecked():
                return
            save_setting(setting_key, str(btn.property("value")))

        group.buttonClicked.connect(_on_toggled)

        def _refresh() -> None:
            for i, (_value, key) in enumerate(items):
                b = group.button(i)
                if b is not None:
                    b.setText(tr(key))

        row.apply_language = _refresh
        return row, group, _refresh

    transcript_fmt_row, _transcript_fmt_group, _ = _make_format_radio_row(
        "settings.live_transcript_format",
        [
            (LIVE_TRANSCRIPT_FORMAT_SRT, "settings.live_transcript_fmt_srt"),
            (LIVE_TRANSCRIPT_FORMAT_VTT, "settings.live_transcript_fmt_vtt"),
            (LIVE_TRANSCRIPT_FORMAT_ASS, "settings.live_transcript_fmt_ass"),
            (LIVE_TRANSCRIPT_FORMAT_SSA, "settings.live_transcript_fmt_ssa"),
            (LIVE_TRANSCRIPT_FORMAT_CSV, "settings.live_transcript_fmt_csv"),
        ],
        SETTING_LIVE_TRANSCRIPT_FORMAT,
        LIVE_TRANSCRIPT_FORMAT_SRT,
    )
    audio_fmt_row, audio_fmt_group, _ = _make_format_radio_row(
        "settings.live_audio_format",
        [
            # Order matches Generate Voice settings (MP3 / WAV / FLAC /
            # OGG) — both pages default to MP3, so the default sits at
            # position 0 and the picker reads identically across the
            # two tabs.
            (LIVE_AUDIO_FORMAT_MP3, "settings.live_audio_fmt_mp3"),
            (LIVE_AUDIO_FORMAT_WAV, "settings.live_audio_fmt_wav"),
            (LIVE_AUDIO_FORMAT_FLAC, "settings.live_audio_fmt_flac"),
            (LIVE_AUDIO_FORMAT_OGG, "settings.live_audio_fmt_ogg"),
        ],
        SETTING_LIVE_AUDIO_FORMAT,
        # MP3 default mirrors Generate Voice's MP3 default — both
        # produce audio for end-user consumption (sharing, playback)
        # where small file size matters more than lossless quality.
        # Sessions without ffmpeg gracefully fall back to WAV on Stop
        # via ``post_encode_audio`` so users without ffmpeg still get
        # a working file.
        LIVE_AUDIO_FORMAT_MP3,
    )

    # NOTE: no ffmpeg-gating banner or radio-disable logic here.  The
    # Live PAGE shows a conditional banner ("Saving Live audio as
    # MP3/FLAC/OGG needs FFmpeg…") and the Start handler shows a
    # blocking dialog when the user actually tries to record without
    # ffmpeg.  Disabling the radios here would contradict the page's
    # "pick anything, install dialog blocks Start" UX.
    # Format + path rows stay visible regardless of the Auto-save mode
    # — these settings configure the *output* (where + what shape) and
    # apply to BOTH auto-save (current) and manual save (planned).
    # Hiding them when Auto-save is None would hide configuration that
    # a future Save Transcript button will read.  The Auto-save toggle
    # under "Auto actions" controls *whether* the session is written
    # automatically; this section answers *how*.
    recording_layout.addWidget(transcript_fmt_row)
    recording_layout.addWidget(audio_fmt_row)

    # Default path doubles as the Reset target — when the user clicks
    # "Reset", the field reverts to ``~/Documents/AI Translate Live``
    # instead of going blank, so the visible-folder UX stays intact.
    from src.utils.path_manager import (  # noqa: PLC0415
        get_default_live_output_dir,
    )

    output_path_widget, _ = create_setting_path(
        tr("settings.live_output_path"),
        SETTING_LIVE_OUTPUT_PATH,
        widget,
        label_tr_key="settings.live_output_path",
        default_path=str(get_default_live_output_dir()),
    )
    # Always visible — the path is read by both auto-save and the
    # planned manual Save Transcript button, so hiding it when Auto-
    # save is None would orphan configuration that still matters.
    recording_layout.addWidget(output_path_widget)
    layout.addWidget(recording_group)

    # ── Overlay window appearance ────────────────────────────────────
    # Two sliders: font size (px) and opacity (%).  Width / height are
    # handled by the runtime drag-to-resize handle on the overlay
    # itself — exposing them as numeric inputs encouraged the
    # symmetric-but-pointless ``Save to:`` row for window dimensions,
    # which most users never touch.  Sliders read better than
    # spinboxes for "pick a comfortable visual size" — direct, no
    # arrow-button hit targets, and the live value label provides the
    # numeric readout for users who want a specific value.
    from src.constants.settings import (  # noqa: PLC0415
        SETTING_LIVE_OVERLAY_FONT_SIZE,
        SETTING_LIVE_OVERLAY_MINIMAL,
        SETTING_LIVE_OVERLAY_OPACITY,
        overlay_appearance_changed,
    )
    from src.ui.pages.live import (  # noqa: PLC0415
        _OVERLAY_DEFAULT_FONT_PX,
        _OVERLAY_DEFAULT_OPACITY,
        _OVERLAY_MAX_FONT_PX,
        _OVERLAY_MIN_FONT_PX,
        _OVERLAY_MIN_OPACITY,
    )

    overlay_group, overlay_layout, _ = create_section_group(
        tr("settings.live_overlay"),
        tr_key="settings.live_overlay",
    )

    def _make_overlay_slider_row(
        label_key: str,
        slider: QSlider,
        value_label: QLabel,
    ) -> QWidget:
        """Builds a ``[label] [slider] [value]`` row.

        The value label is a plain QLabel (not a spinbox) — read-only
        feedback for the slider, kept narrow and right-aligned so the
        column lines up across rows.  Slider stretches to fill the
        remaining width.
        """
        row = QWidget()
        row.setStyleSheet(style_setting_container())
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(SPACING_SUBSECTION)

        lbl = QLabel(tr(label_key))
        lbl.setStyleSheet(style_input_label())
        lbl.setFixedWidth(LABEL_WIDTH)
        lbl.setFixedHeight(HEIGHT_CONTROL)
        lbl.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        )
        _bind_text(lbl, label_key)
        row_layout.addWidget(lbl)

        slider.setOrientation(Qt.Orientation.Horizontal)
        slider.setFixedHeight(HEIGHT_CONTROL)
        slider.setCursor(Qt.CursorShape.PointingHandCursor)
        slider.setStyleSheet(_style_live_settings_slider())
        row_layout.addWidget(slider, 1)

        value_label.setFixedWidth(60)
        value_label.setFixedHeight(HEIGHT_CONTROL)
        value_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
        )
        value_label.setStyleSheet(f"color: {color('text_secondary')}; font-size: 13px;")
        row_layout.addWidget(value_label)
        return row

    # Minimal-captions checkbox — leads the section because it's a
    # binary feature toggle; the sliders below tune appearance once
    # the user has decided whether to keep the chips visible.
    minimal_widget, minimal_cb = create_setting_checkbox(
        tr("settings.live_overlay_minimal"),
        SETTING_LIVE_OVERLAY_MINIMAL,
        default=False,
        label_tr_key="settings.live_overlay_minimal",
    )
    overlay_layout.addWidget(minimal_widget)

    def _on_minimal_changed(checked: bool) -> None:
        # ``create_setting_checkbox`` already persists via the
        # checkbox's ``toggled`` connection.  We additionally
        # broadcast through the appearance signal so an open overlay
        # updates its chip visibility in real time without waiting
        # for the next page→overlay refresh.
        overlay_appearance_changed.emit(
            SETTING_LIVE_OVERLAY_MINIMAL,
            bool(checked),
        )

    minimal_cb.toggled.connect(_on_minimal_changed)

    # Font size — same int range as the overlay's runtime clamp.
    font_slider = QSlider()
    font_slider.setMinimum(_OVERLAY_MIN_FONT_PX)
    font_slider.setMaximum(_OVERLAY_MAX_FONT_PX)
    saved_font = load_setting(SETTING_LIVE_OVERLAY_FONT_SIZE, "")
    try:
        saved_font_int = (
            int(saved_font) if str(saved_font).strip() else _OVERLAY_DEFAULT_FONT_PX
        )
    except (ValueError, TypeError):
        saved_font_int = _OVERLAY_DEFAULT_FONT_PX
    font_slider.setValue(saved_font_int)
    font_value_label = QLabel(f"{saved_font_int} px")

    def _on_font_size_changed(v: int) -> None:
        save_setting(SETTING_LIVE_OVERLAY_FONT_SIZE, str(v))
        font_value_label.setText(f"{v} px")
        # Broadcast so a live overlay window updates in real time.
        overlay_appearance_changed.emit(SETTING_LIVE_OVERLAY_FONT_SIZE, v)

    font_slider.valueChanged.connect(_on_font_size_changed)

    # Opacity — shown as a percentage (20–100) for the user; persisted
    # as the float 0.2–1.0 the overlay reads back via
    # ``_load_float_setting``.
    opacity_slider = QSlider()
    opacity_slider.setMinimum(int(_OVERLAY_MIN_OPACITY * 100))
    opacity_slider.setMaximum(100)
    saved_opacity_raw = load_setting(SETTING_LIVE_OVERLAY_OPACITY, "")
    try:
        opacity_float = (
            float(saved_opacity_raw)
            if str(saved_opacity_raw).strip()
            else _OVERLAY_DEFAULT_OPACITY
        )
    except (ValueError, TypeError):
        opacity_float = _OVERLAY_DEFAULT_OPACITY
    saved_opacity_pct = round(opacity_float * 100)
    opacity_slider.setValue(saved_opacity_pct)
    opacity_value_label = QLabel(f"{saved_opacity_pct} %")

    def _on_opacity_changed(v: int) -> None:
        save_setting(SETTING_LIVE_OVERLAY_OPACITY, f"{v / 100:.2f}")
        opacity_value_label.setText(f"{v} %")
        # Broadcast as the float (0.2–1.0) the overlay uses internally.
        overlay_appearance_changed.emit(
            SETTING_LIVE_OVERLAY_OPACITY,
            v / 100,
        )

    opacity_slider.valueChanged.connect(_on_opacity_changed)

    # ── External-change listener (Settings catches up to overlay) ──────────────
    # When the user nudges font size, opacity, or minimal-captions
    # from INSIDE the overlay (keyboard shortcuts / dedicated
    # toggles), the matching control here catches up so the next
    # interaction starts from the true current value.
    # ``blockSignals`` prevents the slider's ``valueChanged`` /
    # checkbox's ``toggled`` from bouncing the same value back
    # through the signal and creating a feedback loop.
    def _on_external_appearance_change(key: str, value: float) -> None:
        if key == SETTING_LIVE_OVERLAY_FONT_SIZE:
            new_v = int(value)
            if new_v != font_slider.value():
                font_slider.blockSignals(True)
                font_slider.setValue(new_v)
                font_slider.blockSignals(False)
                font_value_label.setText(f"{new_v} px")
        elif key == SETTING_LIVE_OVERLAY_OPACITY:
            new_pct = round(float(value) * 100)
            if new_pct != opacity_slider.value():
                opacity_slider.blockSignals(True)
                opacity_slider.setValue(new_pct)
                opacity_slider.blockSignals(False)
                opacity_value_label.setText(f"{new_pct} %")
        elif key == SETTING_LIVE_OVERLAY_MINIMAL:
            new_checked = bool(value)
            if new_checked != minimal_cb.isChecked():
                minimal_cb.blockSignals(True)
                minimal_cb.setChecked(new_checked)
                minimal_cb.blockSignals(False)

    overlay_appearance_changed.connect(_on_external_appearance_change)

    # Disconnect on widget destruction to avoid stale references when
    # the settings page is recreated (tab navigation, language change).
    widget.destroyed.connect(
        lambda: overlay_appearance_changed.disconnect(
            _on_external_appearance_change,
        ),
    )

    overlay_layout.addWidget(
        _make_overlay_slider_row(
            "settings.live_overlay_font_size",
            font_slider,
            font_value_label,
        ),
    )
    overlay_layout.addWidget(
        _make_overlay_slider_row(
            "settings.live_overlay_opacity",
            opacity_slider,
            opacity_value_label,
        ),
    )
    layout.addWidget(overlay_group)

    layout.addStretch()
    return widget


def create_shortcuts_settings() -> QWidget:  # noqa: PLR0915
    """Creates the Shortcuts settings tab as a fixed-order two-column table.

    Each row shows a binding plus an inline Reset button.  Selecting a
    row puts the table in capture mode — a hint label above the table
    appears and the next valid key combination becomes the new binding.
    Captured input must include at least one of Ctrl / Alt / Meta — bare
    letter / digit / punctuation keys are rejected so a shortcut can't
    swallow ordinary typing (function keys F1–F35 are exempt).  ``Esc``
    exits capture mode without writing, ``Delete`` / ``Backspace``
    unbinds the shortcut entirely.  After every change the registry is
    re-scanned for collisions and any conflicts are listed in a warning
    banner above the table.
    """
    from PySide6.QtCore import QEvent, QObject  # noqa: PLC0415
    from PySide6.QtGui import QKeySequence  # noqa: PLC0415
    from PySide6.QtWidgets import (  # noqa: PLC0415
        QLabel,
        QTableWidget,
        QTableWidgetItem,
    )

    from src.constants.shortcuts import (  # noqa: PLC0415
        Shortcut,
        find_conflicts,
        get_default,
        get_shortcut,
        iter_display_shortcuts,
        reset_shortcut,
        set_shortcut,
        shortcuts_changed,
        unbind_shortcut,
    )
    from src.ui.components import create_table  # noqa: PLC0415

    _SHORTCUT_COL_WIDTH = 200  # noqa: N806 — local constant
    _RESET_COL_WIDTH = 90  # noqa: N806 — local constant
    # Custom data roles stored on each shortcut item.
    _ROLE_SHORTCUT_ID = int(Qt.ItemDataRole.UserRole)  # noqa: N806 — local constant
    _ROLE_ORIG_SEQUENCE = int(Qt.ItemDataRole.UserRole) + 1  # noqa: N806 — local constant

    widget = QWidget()
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(0, MARGIN_SECTION, 0, 0)
    layout.setSpacing(SPACING_SECTION)

    # ── Conflict warning (top — persistent global state) ──────────────
    # Sits above the table so an existing-config problem is the first
    # thing the user sees on opening the tab.  Hidden when there are
    # no conflicts.
    conflict_banner, conflict_label = create_banner(
        "",
        variant="warning",
        rich_text=False,
    )
    conflict_banner.setVisible(False)
    layout.addWidget(conflict_banner)

    # ── Table (Glossary-style) ────────────────────────────────────────
    table = create_table(
        headers=[
            tr("settings.shortcuts.col_shortcut"),
            tr("settings.shortcuts.col_action"),
            "",
        ],
        stretch_columns=[1],
        column_widths={0: _SHORTCUT_COL_WIDTH, 2: _RESET_COL_WIDTH},
    )
    table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
    layout.addWidget(table)

    # ── Footer: capture-mode hint + "Reset all" button on one line ─────
    # Hint sits left (stretched, word-wraps on narrow windows so it
    # never collides with the button); Reset all sits right with a
    # fixed width.  The hint appears/disappears in place when row
    # selection changes — the row itself stays present so the table
    # never jumps.  Reset all surfaces ``reset_all_shortcuts()`` from
    # the registry behind a confirmation dialog.
    footer = QHBoxLayout()
    hint_label = QLabel(tr("settings.shortcuts.capture_hint"))
    _bind_text(hint_label, "settings.shortcuts.capture_hint")
    hint_label.setStyleSheet(
        f"color: {color('text_secondary')}; font-size: 12px; padding: 4px 0;",
    )
    hint_label.setWordWrap(True)
    hint_label.setVisible(False)
    footer.addWidget(hint_label, stretch=1)

    reset_all_btn = QPushButton(tr("settings.shortcuts.reset_all"))
    # Outlined-danger style: signals "destructive of customisation"
    # without the visual loudness of a filled-red button — appropriate
    # for an action that wipes every per-action override but is still
    # reversible by re-binding individual shortcuts.
    reset_all_btn.setStyleSheet(style_delete_button())
    reset_all_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    reset_all_btn.setFixedHeight(HEIGHT_CONTROL)
    # Lock horizontal size so the button stays at its natural width
    # whether the hint label is visible or not — without this, hiding
    # the hint leaves nothing to claim the row's stretch and Qt's
    # default size policy lets the button balloon full-width.
    reset_all_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    footer.addWidget(reset_all_btn, alignment=Qt.AlignmentFlag.AlignTop)
    # Always-on stretch on the LEFT keeps the button right-aligned even
    # when the hint label is hidden (insertWidget(0, …) puts the hint
    # before this stretch when it appears).
    footer.insertStretch(1)
    layout.addLayout(footer)

    reset_btns: dict[str, QPushButton] = {}

    def _group_label(shortcut: Shortcut) -> str:
        """Formats the Action cell as ``Group · Action``."""
        return f"{tr(shortcut.group_key)}  ·  {tr(shortcut.label_key)}"

    def _display_sequence(seq: str) -> str:
        """Renders a stored sequence in the OS's native glyph convention.

        Storage stays in Qt's portable form (``Ctrl+Return``) so
        ``settings.ini`` is cross-platform.  For display we ask Qt for
        the native text, which emits ⌘, ⌥, ⌃, ⇧ on macOS and plain
        ``"Ctrl+…"`` on Windows/Linux.  Two readability substitutions
        are applied so the rendered label matches what the user sees
        on their keyboard:
          * ``Return`` → ``Enter``
          * ``Del`` → ``Delete``
        Empty sequence (explicitly unbound shortcut) renders as a
        translatable placeholder.
        """
        if not seq:
            return tr("settings.shortcuts.unbound")
        native = QKeySequence(seq).toString(QKeySequence.SequenceFormat.NativeText)
        text = native or seq
        return text.replace("Return", "Enter").replace("Del", "Delete")

    def _sync_reset_state(shortcut_id: str) -> None:
        """Dims the row's Reset button when the binding matches the default."""
        btn = reset_btns.get(shortcut_id)
        if btn is None:
            return
        btn.setEnabled(get_shortcut(shortcut_id) != get_default(shortcut_id))

    def _populate() -> None:
        """Fills the table from the registry in source-declaration order.

        Source order keeps related actions adjacent (e.g. font-bigger
        right next to font-smaller, opacity-up right next to
        opacity-down) — alphabetic sort by action label would scatter
        them based on translated wording.  Followers of a shared
        group are hidden; the group's own row represents them.
        """
        table.setSortingEnabled(False)
        table.blockSignals(True)
        table.setRowCount(0)
        reset_btns.clear()
        ordered = list(iter_display_shortcuts())
        table.setRowCount(len(ordered))

        for row_idx, shortcut in enumerate(ordered):
            current_seq = get_shortcut(shortcut.id)

            # Col 0 — key-sequence text (read-only; captured via key-press).
            seq_item = QTableWidgetItem(_display_sequence(current_seq))
            seq_item.setFlags(
                Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable,
            )
            seq_item.setData(_ROLE_SHORTCUT_ID, shortcut.id)
            seq_item.setData(_ROLE_ORIG_SEQUENCE, current_seq)
            table.setItem(row_idx, 0, seq_item)

            # Col 1 — non-editable "Group · Action" label.
            action_item = QTableWidgetItem(_group_label(shortcut))
            action_item.setFlags(
                Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable,
            )
            action_item.setData(_ROLE_SHORTCUT_ID, shortcut.id)
            table.setItem(row_idx, 1, action_item)

            # Col 2 — inline Reset button styled to match the Glossary
            # tab's per-row Delete: borderless red link-style with
            # hover underline, fits a compact 60×20 cell with no
            # padding tweaks needed.  Visual escalation matches the
            # outlined-danger "Reset all" footer button.
            reset_btn = QPushButton("")
            _bind_text(reset_btn, "settings.shortcuts.reset")
            reset_btn.setStyleSheet(style_table_delete_button())
            reset_btn.setFixedSize(60, 20)
            reset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            reset_btn.clicked.connect(
                lambda _checked=False, sid=shortcut.id: reset_shortcut(sid),
            )
            reset_btns[shortcut.id] = reset_btn
            table.setCellWidget(row_idx, 2, reset_btn)
            _sync_reset_state(shortcut.id)

        # Sorting stays disabled so header clicks can't reshuffle the table.
        table.blockSignals(False)

    _populate()
    table.setSortingEnabled(False)
    # Remove the sort-indicator arrow and stop the header responding to clicks.
    _h = table.horizontalHeader()
    _h.setSortIndicatorShown(False)
    _h.setSectionsClickable(False)

    # ── Capture key presses on the table as the selected row's shortcut ──
    # Keys that must *not* be treated as shortcut captures: pure modifier
    # presses, focus-navigation keys, and arrow keys without a modifier (so
    # the user can still navigate the table).
    _MODIFIER_KEYS = {  # noqa: N806 — local constant set
        Qt.Key.Key_Shift,
        Qt.Key.Key_Control,
        Qt.Key.Key_Alt,
        Qt.Key.Key_AltGr,
        Qt.Key.Key_Meta,
        Qt.Key.Key_CapsLock,
        Qt.Key.Key_NumLock,
        Qt.Key.Key_ScrollLock,
    }
    _NAV_KEYS = {  # noqa: N806 — local constant set
        Qt.Key.Key_Tab,
        Qt.Key.Key_Backtab,
        Qt.Key.Key_PageUp,
        Qt.Key.Key_PageDown,
        Qt.Key.Key_Home,
        Qt.Key.Key_End,
    }
    _ARROW_KEYS = {  # noqa: N806 — local constant set
        Qt.Key.Key_Up,
        Qt.Key.Key_Down,
        Qt.Key.Key_Left,
        Qt.Key.Key_Right,
    }
    # Function keys (F1–F35) are valid bare-key shortcuts; everything
    # else outside this range needs a Ctrl/Alt/Meta modifier to bind.
    _FUNCTION_KEY_MIN = int(Qt.Key.Key_F1)  # noqa: N806
    _FUNCTION_KEY_MAX = int(Qt.Key.Key_F35)  # noqa: N806
    _BINDING_MODIFIERS = (  # noqa: N806
        Qt.KeyboardModifier.ControlModifier
        | Qt.KeyboardModifier.AltModifier
        | Qt.KeyboardModifier.MetaModifier
    )

    def _selected_shortcut_id() -> str | None:
        """Returns the shortcut ID of the currently selected row, or None."""
        rows = table.selectionModel().selectedRows()
        if not rows:
            return None
        seq_item = table.item(rows[0].row(), 0)
        if seq_item is None:
            return None
        sid = seq_item.data(_ROLE_SHORTCUT_ID)
        return sid or None

    def _capture_key_for_selected_row(event: QKeyEvent) -> bool:  # noqa: PLR0911
        """Turns a key press on the table into a shortcut update.

        Returns ``True`` when the event was consumed, ``False`` when it
        should fall through to the table's default handling.  Multiple
        early-returns track distinct rejection reasons so the noqa keeps
        the flat guard-clause structure.

        Special keys:
        * ``Esc`` clears the selection (exits capture mode without writing).
        * ``Delete`` / ``Backspace`` unbind the shortcut entirely.
        * Bare letter / digit / punctuation keys are rejected — a
          shortcut must include Ctrl, Alt, or Meta (Shift alone is not a
          binding modifier), or be a function key (F1–F35).
        """
        key = event.key()
        mods = event.modifiers()
        if key in _MODIFIER_KEYS or key in _NAV_KEYS:
            return False

        sid = _selected_shortcut_id()

        # Esc cancels capture even with no row selected — harmless no-op.
        if key == Qt.Key.Key_Escape and not mods & _BINDING_MODIFIERS:
            table.clearSelection()
            return True

        if sid is None:
            return False

        # Delete / Backspace unbinds the selected row's shortcut.
        if key in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace) and not (
            mods & _BINDING_MODIFIERS
        ):
            unbind_shortcut(sid)
            return True

        # Arrow keys without a binding modifier are reserved for navigation.
        if key in _ARROW_KEYS and not mods & _BINDING_MODIFIERS:
            return False

        # Reject bare keys without a binding modifier (Shift alone doesn't
        # count) unless they're function keys.  Prevents binding bare
        # letters that would steal ordinary typing on every page.
        is_function_key = _FUNCTION_KEY_MIN <= int(key) <= _FUNCTION_KEY_MAX
        if not (mods & _BINDING_MODIFIERS) and not is_function_key:
            return False

        # Qt < 6.7 needs modifier bits combined manually into the Key value.
        combo = (
            int(mods.value) | int(key)
            if hasattr(mods, "value")
            else int(mods) | int(key)
        )
        sequence = QKeySequence(combo)
        if sequence.isEmpty():
            return False
        canonical = sequence.toString(QKeySequence.SequenceFormat.PortableText)

        set_shortcut(sid, canonical)
        return True

    class _ShortcutCaptureFilter(QObject):
        """Routes table key-presses through ``_capture_key_for_selected_row``."""

        def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # noqa: N802, ARG002 — Qt override
            return (
                event.type() == QEvent.Type.KeyPress
                and _capture_key_for_selected_row(
                    event,
                )
            )

    _capture_filter = _ShortcutCaptureFilter(table)
    table.installEventFilter(_capture_filter)
    # Keep a reference alive for the lifetime of the widget.
    widget._shortcut_capture_filter = _capture_filter  # type: ignore[attr-defined]

    def _refresh_conflicts() -> None:
        """Updates the warning banner with any current shortcut collisions."""
        conflicts = find_conflicts()
        if not conflicts:
            conflict_banner.setVisible(False)
            return

        # Format each colliding sequence as ``Ctrl+S → Action A, Action B``.
        # Use the action labels (not the IDs) so the message is meaningful
        # to non-developers; group label is implied by the page tab.
        from src.constants.shortcuts import lookup  # noqa: PLC0415

        lines: list[str] = []
        for seq, ids in conflicts.items():
            labels = ", ".join(tr(lookup(sid).label_key) for sid in ids)
            lines.append(f"{_display_sequence(seq)} → {labels}")
        conflict_label.setText(
            tr("settings.shortcuts.conflict_warning") + "\n" + "\n".join(lines),
        )
        conflict_banner.setVisible(True)

    def _refresh_from_registry() -> None:
        """Re-reads every binding when the registry changes."""
        table.blockSignals(True)
        for row_idx in range(table.rowCount()):
            seq_item = table.item(row_idx, 0)
            if seq_item is None:
                continue
            sid = seq_item.data(_ROLE_SHORTCUT_ID)
            if not sid:
                continue
            current = get_shortcut(sid)
            pretty = _display_sequence(current)
            if seq_item.text() != pretty:
                seq_item.setText(pretty)
            seq_item.setData(_ROLE_ORIG_SEQUENCE, current)
            _sync_reset_state(sid)
        table.blockSignals(False)
        _refresh_conflicts()

    shortcuts_changed.connect(_refresh_from_registry)
    # Initial conflict scan so existing collisions surface on first open.
    _refresh_conflicts()

    def _on_selection_changed() -> None:
        """Shows the capture-mode hint while a row is selected."""
        hint_label.setVisible(_selected_shortcut_id() is not None)

    table.itemSelectionChanged.connect(_on_selection_changed)

    def _on_reset_all_clicked() -> None:
        """Confirms then wipes every per-action override."""
        from src.constants.shortcuts import (  # noqa: PLC0415
            reset_all_shortcuts,
        )
        from src.ui.dialogs import CustomConfirmDialog  # noqa: PLC0415

        if not CustomConfirmDialog.confirm(
            widget,
            tr("settings.shortcuts.reset_all_title"),
            tr("settings.shortcuts.reset_all_msg"),
        ):
            return
        reset_all_shortcuts()
        # ``shortcuts_changed`` emitted by the registry triggers
        # ``_refresh_from_registry`` which already rebuilds the table.

    reset_all_btn.clicked.connect(_on_reset_all_clicked)

    def _apply_language(*_args: object) -> None:
        """Re-translates headers and re-populates so rows stay alphabetised.

        Accepts ``*_args`` because :data:`language_changed` emits with
        the locale code; without the variadic this raises
        ``TypeError`` mid-emit and breaks every other ``apply_language``
        callback queued behind it (only one callback fires before the
        crash, leaving the rest of the UI in the previous locale —
        the exact symptom the user was seeing).
        """
        table.setHorizontalHeaderLabels(
            [
                tr("settings.shortcuts.col_shortcut"),
                tr("settings.shortcuts.col_action"),
                "",
            ],
        )
        hint_label.setText(tr("settings.shortcuts.capture_hint"))
        reset_all_btn.setText(tr("settings.shortcuts.reset_all"))
        # Action labels depend on the UI language, so rebuild the table
        # so each row's "Group · Action" cell picks up the new locale.
        # Source-order layout means row positions are language-stable.
        _populate()
        # Conflict text references action labels, which depend on language.
        _refresh_conflicts()

    language_changed.connect(_apply_language)

    # Expose hooks for tab-change / test monkey-patching.
    widget._refresh_shortcuts = _refresh_from_registry  # type: ignore[attr-defined]
    widget._apply_shortcut_labels = _apply_language  # type: ignore[attr-defined]
    widget._shortcut_table = table  # type: ignore[attr-defined]
    return widget


def create_settings_page() -> QWidget:  # noqa: PLR0915
    """Creates the Settings page content with General, Translation, OCR and LLM tabs.

    Returns:
        QWidget: The settings page widget.
    """
    page, layout = create_page_container(
        tr("page.settings"),
        tr_key="page.settings",
    )
    # Hide the page title — tabs already identify the page
    if layout.count() > 0:
        layout.itemAt(0).widget().setVisible(False)

    tabs = QTabWidget()
    tabs.setStyleSheet(style_tab_widget())
    tabs.tabBar().setCursor(Qt.CursorShape.PointingHandCursor)

    general_widget = create_general_settings()
    service_widget = create_service_settings()
    ocr_widget = create_ocr_settings()
    llm_widget = create_llm_settings()
    translate_text_widget = create_translate_text_settings()
    translation_widget = create_translation_settings()
    subtitle_widget = create_subtitle_settings()
    voice_widget = create_voice_settings()
    dubbing_widget = create_dubbing_settings()
    live_widget = create_live_settings()
    extract_widget = create_extract_text_settings()
    shortcuts_widget = create_shortcuts_settings()

    def _refresh_translation_state() -> None:
        """Re-checks OCR and office availability for the Translation tab."""
        for child in translation_widget.findChildren(QWidget):
            if hasattr(child, "_sync_ocr_state"):
                child._sync_ocr_state()
            if hasattr(child, "_sync_office_state"):
                child._sync_office_state()

    def _hook(w: QWidget, attr: str) -> Callable[[], None] | None:
        """Binds a late-lookup wrapper around a widget's refresh hook.

        Tests may monkey-patch the attribute after page construction, so we
        resolve it at call time rather than capturing a bound method here.
        """
        if not hasattr(w, attr):
            return None
        # Closure deliberately re-reads the attr each call; do not inline.
        return lambda: getattr(w, attr, lambda: None)()  # noqa: PLW0108

    # Tab order is the sole source of truth for index, tr-key, and refresh
    # callable. Adding / reordering a tab means touching one row here — the
    # dispatcher and apply_language loops below stay unchanged.
    _tab_specs: list[tuple[QWidget, str, Callable[[], None] | None]] = [
        (
            general_widget,
            "settings.general",
            _hook(general_widget, "_sync_office_availability"),
        ),
        (
            shortcuts_widget,
            "settings.shortcuts",
            _hook(shortcuts_widget, "_refresh_shortcuts"),
        ),
        (service_widget, "settings.service", None),
        (ocr_widget, "settings.ocr", _hook(ocr_widget, "_sync_ocr_availability")),
        (
            llm_widget,
            "settings.llm",
            _hook(llm_widget, "_refresh_default_model_combo"),
        ),
        (translate_text_widget, "settings.translate_text", None),
        (translation_widget, "settings.translation", _refresh_translation_state),
        (
            subtitle_widget,
            "settings.subtitle",
            _hook(subtitle_widget, "_sync_stt_availability"),
        ),
        (voice_widget, "settings.voice", _hook(voice_widget, "_sync_tts_availability")),
        # Dubbing tab no longer needs a refresh hook — the only thing
        # it used to refresh was the ffmpeg install banner, which now
        # lives on the Dubbing PAGE (auto-refreshed via showEvent).
        (dubbing_widget, "settings.dubbing", None),
        (live_widget, "settings.live", _hook(live_widget, "_sync_live_availability")),
        (
            extract_widget,
            "settings.extract_text",
            _hook(extract_widget, "_sync_method_availability"),
        ),
    ]

    _tab_tr_keys: list[str] = []
    _refresh_by_index: dict[int, Callable[[], None]] = {}
    for tab_widget, tr_key, refresh in _tab_specs:
        idx = tabs.count()
        tabs.addTab(create_scrollable_container(tab_widget), tr(tr_key))
        _tab_tr_keys.append(tr_key)
        if refresh is not None:
            _refresh_by_index[idx] = refresh

    def _on_tab_changed(idx: int) -> None:
        """Refreshes availability state when the user switches settings tabs."""
        fn = _refresh_by_index.get(idx)
        if fn is not None:
            fn()

    tabs.currentChanged.connect(_on_tab_changed)

    def switch_to_tab(index: int) -> None:
        """Programmatically activates a settings tab by index."""
        tabs.setCurrentIndex(index)

    _base_apply_theme = page.apply_theme

    def apply_theme() -> None:
        """Re-applies theme-dependent styles for the settings page."""
        _base_apply_theme()
        tabs.setStyleSheet(style_tab_widget())
        # Re-style all radio buttons in the settings page
        for radio in page.findChildren(QRadioButton):
            radio.setStyleSheet(style_radio_button())

    # Chain with the base apply_language from create_page_container
    _base_apply_language = page.apply_language

    def apply_language() -> None:
        """Re-applies translatable text for the settings page."""
        _base_apply_language()
        for i, key in enumerate(_tab_tr_keys):
            tabs.setTabText(i, tr(key))

    page.switch_to_tab = switch_to_tab
    page.apply_theme = apply_theme
    page.apply_language = apply_language

    # Re-mask any revealed API-key fields whenever the settings page is
    # navigated away from, so a key the user briefly toggled visible
    # doesn't stay readable on return.
    _base_hide_event = page.hideEvent

    def _hide_event(event: QHideEvent) -> None:
        remask_secrets(page)
        _base_hide_event(event)

    page.hideEvent = _hide_event

    layout.addWidget(tabs)
    return page
