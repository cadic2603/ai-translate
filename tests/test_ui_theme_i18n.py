"""Unit tests for the theme engine (src/constants/theme.py) and the i18n engine."""

from pytestqt.qtbot import QtBot

from src.constants.i18n import (
    current_language,
    language_changed,
    set_language,
    tr,
)
from src.constants.theme import (
    color,
    current_theme,
    set_theme,
    theme_changed,
)

# ===========================================================================
# Theme engine
# ===========================================================================

# ---------------------------------------------------------------------------
# color()
# ---------------------------------------------------------------------------


def test_color_returns_non_empty_string() -> None:
    """color() returns a non-empty string for a known palette key."""
    val = color("primary")
    assert isinstance(val, str)
    assert val


def test_color_returns_hex_string() -> None:
    """color() values start with '#' (hex format)."""
    assert color("primary").startswith("#")
    assert color("error").startswith("#")
    assert color("success").startswith("#")


def test_color_all_palette_keys_non_empty() -> None:
    """Every known palette key returns a non-empty value."""
    keys = [
        "primary",
        "secondary",
        "sidebar_bg",
        "outline",
        "error",
        "success",
        "warning",
        "app_bg",
        "component_bg",
        "disabled_bg",
        "disabled_text",
        "border_light",
        "hover_light",
        "text_primary",
        "text_secondary",
    ]
    for key in keys:
        assert color(key), f"color('{key}') returned empty string"


# ---------------------------------------------------------------------------
# current_theme() / set_theme()
# ---------------------------------------------------------------------------


def test_current_theme_is_valid() -> None:
    """current_theme() returns 'light' or 'dark'."""
    assert current_theme() in ("light", "dark")


def test_set_theme_changes_current_theme() -> None:
    """set_theme() changes the active theme."""
    original = current_theme()
    try:
        new = "dark" if original == "light" else "light"
        set_theme(new)
        assert current_theme() == new
    finally:
        set_theme(original)  # Restore


def test_set_theme_unknown_name_does_not_change_theme() -> None:
    """set_theme() with an unknown name is silently ignored."""
    original = current_theme()
    set_theme("solarized")  # type: ignore[arg-type]
    assert current_theme() == original


def test_set_theme_same_name_emits_no_signal(qtbot: QtBot) -> None:
    """set_theme() with the current theme emits no signal (no-op)."""
    original = current_theme()
    received: list[str] = []

    theme_changed.connect(received.append)
    try:
        set_theme(original)  # Same theme — should be a no-op
    finally:
        theme_changed.disconnect(received.append)

    assert received == []


def test_set_theme_emits_signal_on_change(qtbot: QtBot) -> None:
    """set_theme() emits theme_changed with the new theme name."""
    original = current_theme()
    new = "dark" if original == "light" else "light"
    received: list[str] = []

    theme_changed.connect(received.append)
    try:
        set_theme(new)
    finally:
        theme_changed.disconnect(received.append)
        set_theme(original)  # Restore

    assert received == [new]


def test_color_changes_after_set_theme() -> None:
    """color() reflects the newly active theme after set_theme()."""
    original = current_theme()
    try:
        # Both palettes define "app_bg"; values differ between light and dark
        set_theme("light")
        light_val = color("app_bg")
        set_theme("dark")
        dark_val = color("app_bg")
        assert light_val != dark_val
    finally:
        set_theme(original)


# ===========================================================================
# i18n engine
# ===========================================================================

# ---------------------------------------------------------------------------
# current_language() / set_language()
# ---------------------------------------------------------------------------


def test_current_language_returns_non_empty_string() -> None:
    """current_language() returns a non-empty string."""
    lang = current_language()
    assert isinstance(lang, str)
    assert lang


def test_current_language_is_valid_code() -> None:
    """current_language() is one of the valid UI language codes."""
    assert current_language() in ("en-US", "en-UK", "vi")


def test_set_language_unknown_code_does_not_change_language() -> None:
    """set_language() with an unknown code is silently ignored."""
    original = current_language()
    set_language("klingon")
    assert current_language() == original


def test_set_language_same_code_emits_no_signal(qtbot: QtBot) -> None:
    """set_language() with the current code emits no signal (no-op)."""
    original = current_language()
    received: list[str] = []

    language_changed.connect(received.append)
    try:
        set_language(original)
    finally:
        language_changed.disconnect(received.append)

    assert received == []


def test_set_language_changes_current_language() -> None:
    """set_language() updates current_language()."""
    original = current_language()
    try:
        new = "vi" if original != "vi" else "en-US"
        set_language(new)
        assert current_language() == new
    finally:
        set_language(original)


def test_set_language_emits_signal_on_change(qtbot: QtBot) -> None:
    """set_language() emits language_changed with the new code."""
    original = current_language()
    new = "vi" if original != "vi" else "en-US"
    received: list[str] = []

    language_changed.connect(received.append)
    try:
        set_language(new)
    finally:
        language_changed.disconnect(received.append)
        set_language(original)

    assert received == [new]


# ---------------------------------------------------------------------------
# tr()
# ---------------------------------------------------------------------------


def test_tr_known_key_returns_non_empty_string() -> None:
    """tr() with a valid key returns a non-empty string."""
    result = tr("btn.ok")
    assert isinstance(result, str)
    assert result


def test_tr_unknown_key_returns_key_itself() -> None:
    """tr() with an unknown key returns the key as the fallback."""
    key = "nonexistent.key.xyz_abc_123"
    assert tr(key) == key


def test_tr_with_format_kwargs_substitutes() -> None:
    """tr() substitutes format kwargs into the template."""
    # Use a known key that has a {formats} placeholder, or construct a test
    # by relying on the fallback: unknown key = template = key itself.
    # "hello {name}" is not a real key, so template = "hello {name}"
    result = tr("hello {name}", name="World")
    # The "key" literal is "hello {name}" and kwargs = {"name": "World"}
    # template.format(name="World") = "hello World"
    assert result == "hello World"


def test_tr_unknown_key_with_extra_kwargs_no_substitution() -> None:
    """Unknown key template has no placeholders; extra kwargs are silently ignored."""
    result = tr("btn.ok", count=5)
    # "btn.ok" translation has no {count} — format() ignores extra kwargs
    assert isinstance(result, str)
    assert result  # not empty


def test_tr_with_bad_format_kwargs_returns_template() -> None:
    """tr() with a key that has {name} but kwargs missing 'name' returns template."""
    # Fake a key where template has {name} but we supply wrong kwargs
    result = tr("hello {name}", wrong_key="oops")
    # KeyError in format() → fallback to template
    assert result == "hello {name}"


# ---------------------------------------------------------------------------
# _set_initial_theme() — startup without signal
# ---------------------------------------------------------------------------


def test_set_initial_theme_sets_theme_without_signal(qtbot: QtBot) -> None:
    """_set_initial_theme() changes the theme without emitting a signal."""
    from src.constants.theme import _set_initial_theme  # noqa: PLC0415

    original = current_theme()
    new = "dark" if original == "light" else "light"
    received: list[str] = []

    theme_changed.connect(received.append)
    try:
        _set_initial_theme(new)
        assert current_theme() == new
    finally:
        theme_changed.disconnect(received.append)
        _set_initial_theme(original)

    # No signal should have been emitted
    assert received == []


def test_set_initial_theme_unknown_name_keeps_current() -> None:
    """_set_initial_theme() with an unknown name leaves current theme unchanged."""
    from src.constants.theme import _set_initial_theme  # noqa: PLC0415

    original = current_theme()
    _set_initial_theme("nonexistent")  # type: ignore[arg-type]
    assert current_theme() == original


# ---------------------------------------------------------------------------
# color() — invalid key
# ---------------------------------------------------------------------------


def test_color_invalid_key_raises_key_error() -> None:
    """color() with an unknown palette key raises KeyError."""
    import pytest  # noqa: PLC0415

    with pytest.raises(KeyError):
        color("this_key_does_not_exist_in_any_palette")


# ---------------------------------------------------------------------------
# Style generator functions — smoke tests
# ---------------------------------------------------------------------------


def test_style_generators_return_non_empty_strings() -> None:
    """All style generator functions return non-empty QSS strings."""
    from src.constants.theme import (  # noqa: PLC0415
        style_banner,
        style_checkbox,
        style_danger_button,
        style_delete_button,
        style_input_field,
        style_link_button,
        style_link_button_muted,
        style_page_header,
        style_primary_button,
        style_scrollbar,
        style_secondary_button,
        style_section_group,
        style_section_title,
        style_setting_combo,
        style_setting_container,
        style_splitter,
        style_table,
        style_toggle_button,
        style_warning_button,
    )

    generators = [
        style_banner,
        style_checkbox,
        style_danger_button,
        style_delete_button,
        style_input_field,
        style_link_button,
        style_link_button_muted,
        style_page_header,
        style_primary_button,
        style_scrollbar,
        style_secondary_button,
        style_section_group,
        style_section_title,
        style_setting_combo,
        style_setting_container,
        style_splitter,
        style_table,
        style_toggle_button,
        style_warning_button,
    ]

    for gen in generators:
        result = gen() if gen.__name__ != "style_banner" else gen("warning")
        assert isinstance(result, str), f"{gen.__name__} did not return str"
        assert result.strip(), f"{gen.__name__} returned empty string"


def test_style_link_button_muted_uses_text_secondary() -> None:
    """Muted-variant link button is visually subordinate to primary.

    ``style_link_button_muted`` is used by Reset buttons across 7+
    settings pickers (storage paths, Vertex credentials, etc.) so
    Reset reads as the secondary action next to Browse.  Pin two
    contracts:

    1. The base colour is ``text_secondary`` — NOT the brand primary
       (``primary`` / ``primary_light``).  A regression to the primary
       colour would make Reset compete with Browse for visual weight.
    2. The QSS is a transparent-background QPushButton — NOT a filled
       button.  A regression to filled style would break the "link
       button" appearance that pairs naturally with Browse.
    """
    from src.constants.theme import (  # noqa: PLC0415
        color,
        style_link_button,
        style_link_button_muted,
        style_primary_button,
    )

    muted = style_link_button_muted()

    # Contract 1: muted uses text_secondary, not the primary brand.
    assert color("text_secondary") in muted, (
        f"muted link must use text_secondary; got {muted!r}"
    )
    # Bonus check: primary brand colour must NOT appear as the base
    # colour (it may legitimately appear in :hover, so only check the
    # main ``QPushButton {`` block — slice before the first ``:hover``).
    main_block = muted.split(":hover")[0] if ":hover" in muted else muted
    assert color("primary") not in main_block, (
        f"muted link leaked primary colour into base state: {main_block!r}"
    )

    # Contract 2: transparent background — the "link button" shape.
    assert "background-color: transparent" in muted, (
        f"muted link should have transparent background; got {muted!r}"
    )

    # Sanity: muted differs from the brand-coloured link AND from the
    # filled primary button.  Otherwise the function is redundant.
    assert muted != style_link_button(), (
        "style_link_button_muted should differ from style_link_button"
    )
    assert muted != style_primary_button(), (
        "style_link_button_muted should differ from style_primary_button"
    )


def test_style_splitter_contains_handle_selector() -> None:
    """style_splitter() QSS targets the horizontal handle and its hover state."""
    from src.constants.theme import style_splitter  # noqa: PLC0415

    qss = style_splitter()
    assert "QSplitter::handle:horizontal" in qss
    assert "hover" in qss


def test_style_splitter_differs_between_themes() -> None:
    """style_splitter() returns different QSS in light vs dark mode."""
    from src.constants.theme import style_splitter  # noqa: PLC0415

    original = current_theme()
    try:
        set_theme("light")
        light_qss = style_splitter()
        set_theme("dark")
        dark_qss = style_splitter()
        assert light_qss != dark_qss
    finally:
        set_theme(original)


def test_style_banner_all_variants_return_different_qss() -> None:
    """style_banner() returns different QSS for each variant."""
    from src.constants.theme import style_banner  # noqa: PLC0415

    styles = {v: style_banner(v) for v in ("warning", "error", "success", "info")}
    # All should be non-empty
    for v, s in styles.items():
        assert s.strip(), f"style_banner('{v}') is empty"
    # At least warning vs error should differ (different accent colors)
    assert styles["warning"] != styles["error"]


# ---------------------------------------------------------------------------
# _set_initial_language() — startup without signal
# ---------------------------------------------------------------------------


def test_set_initial_language_sets_language_without_signal(
    qtbot: QtBot,
) -> None:
    """_set_initial_language() sets language without emitting a signal."""
    from src.constants.i18n import _set_initial_language  # noqa: PLC0415

    original = current_language()
    new = "vi" if original != "vi" else "en-US"
    received: list[str] = []

    language_changed.connect(received.append)
    try:
        _set_initial_language(new)
        assert current_language() == new
    finally:
        language_changed.disconnect(received.append)
        _set_initial_language(original)

    assert received == []


def test_set_initial_language_unknown_code_keeps_default() -> None:
    """_set_initial_language() with unknown code falls back to current."""
    from src.constants.i18n import _set_initial_language  # noqa: PLC0415

    original = current_language()
    _set_initial_language("klingon")
    # Still loads translations for the current language (unchanged)
    assert current_language() == original


# ---------------------------------------------------------------------------
# _load_translations() — error paths
# ---------------------------------------------------------------------------


def test_load_translations_missing_file_empties_dict() -> None:
    """Missing JSON file results in empty translation dict → tr() fallback."""
    from unittest.mock import patch  # noqa: PLC0415

    from src.constants.i18n import _load_translations  # noqa: PLC0415

    original = current_language()
    try:
        with patch("src.constants.i18n._TRANSLATIONS_DIR") as mock_dir:
            mock_dir.__truediv__ = lambda self, name: type(
                "P", (), {"exists": lambda _: False}
            )()
            _load_translations("en-US")
        # After loading from non-existent file, tr should fall back
        assert tr("btn.ok") == "btn.ok"
    finally:
        # Restore real translations
        set_language("en-UK" if original == "en-US" else "en-US")
        set_language(original)


# ---------------------------------------------------------------------------
# language_changed — module-level signal instance
# ---------------------------------------------------------------------------


def test_language_changed_is_signal_object() -> None:
    """language_changed is a CallbackSignal instance with connect/disconnect."""
    assert hasattr(language_changed, "connect")
    assert hasattr(language_changed, "disconnect")


# ---------------------------------------------------------------------------
# set_language() changes tr() results
# ---------------------------------------------------------------------------


def test_set_language_changes_tr_results() -> None:
    """Switching language changes what tr() returns for the same key."""
    original = current_language()
    try:
        set_language("en-US")
        en_text = tr("btn.cancel")
        set_language("vi")
        vi_text = tr("btn.cancel")
        # en-US "Cancel" vs vi "Hủy"
        assert en_text != vi_text
    finally:
        set_language(original)


# ---------------------------------------------------------------------------
# Additional style generator smoke tests (previously untested functions)
# ---------------------------------------------------------------------------


def test_style_generators_all_functions_return_non_empty_strings() -> None:
    """All remaining style generator functions return non-empty QSS strings."""
    from src.constants.theme import (  # noqa: PLC0415
        style_card_header,
        style_card_light,
        style_input_label,
        style_list_widget,
        style_outlined_primary_button,
        style_radio_button,
        style_sidebar_list,
        style_tab_widget,
        style_table_delete_button,
    )

    generators = [
        style_card_header,
        style_card_light,
        style_input_label,
        style_list_widget,
        style_outlined_primary_button,
        style_radio_button,
        style_sidebar_list,
        style_tab_widget,
        style_table_delete_button,
    ]

    for gen in generators:
        result = gen()
        assert isinstance(result, str), f"{gen.__name__} did not return str"
        assert result.strip(), f"{gen.__name__} returned empty string"


def test_style_list_widget_contains_key_selectors() -> None:
    """style_list_widget() QSS targets QListWidget items and indicators."""
    from src.constants.theme import style_list_widget  # noqa: PLC0415

    qss = style_list_widget()
    assert "QListWidget" in qss
    assert "::item" in qss
    assert "::indicator" in qss


def test_style_radio_button_contains_indicator_selector() -> None:
    """style_radio_button() QSS includes indicator checked/unchecked states."""
    from src.constants.theme import style_radio_button  # noqa: PLC0415

    qss = style_radio_button()
    assert "QRadioButton" in qss
    assert "::indicator:checked" in qss
    assert "::indicator:unchecked" in qss
    assert ":disabled" in qss


def test_style_tab_widget_contains_tab_selectors() -> None:
    """style_tab_widget() QSS includes tab bar and selected tab."""
    from src.constants.theme import style_tab_widget  # noqa: PLC0415

    qss = style_tab_widget()
    assert "QTabWidget" in qss
    assert "QTabBar::tab" in qss
    assert "tab:selected" in qss


def test_style_outlined_primary_button_has_border() -> None:
    """style_outlined_primary_button() QSS includes border: 1px solid."""
    from src.constants.theme import style_outlined_primary_button  # noqa: PLC0415

    qss = style_outlined_primary_button()
    assert "border: 1px solid" in qss
    assert "QPushButton" in qss


def test_style_card_light_differs_between_themes() -> None:
    """style_card_light() returns different QSS in light vs dark mode."""
    from src.constants.theme import style_card_light  # noqa: PLC0415

    original = current_theme()
    try:
        set_theme("light")
        light_qss = style_card_light()
        set_theme("dark")
        dark_qss = style_card_light()
        assert light_qss != dark_qss
    finally:
        set_theme(original)


def test_style_sidebar_list_contains_sidebar_selectors() -> None:
    """style_sidebar_list() QSS targets QListWidget and item states."""
    from src.constants.theme import style_sidebar_list  # noqa: PLC0415

    qss = style_sidebar_list()
    assert "QListWidget" in qss
    assert "::item:selected" in qss
    assert "::item:disabled" in qss
    # Sidebar uses a fixed dark background regardless of app theme
    assert "#283142" in qss


def test_style_table_delete_button_uses_error_color() -> None:
    """style_table_delete_button() QSS contains the error palette color."""
    from src.constants.theme import style_table_delete_button  # noqa: PLC0415

    qss = style_table_delete_button()
    assert color("error") in qss


def test_style_input_label_uses_text_secondary_color() -> None:
    """style_input_label() uses the text_secondary palette color."""
    from src.constants.theme import style_input_label  # noqa: PLC0415

    qss = style_input_label()
    assert color("text_secondary") in qss


# ---------------------------------------------------------------------------
# CallbackSignal — duplicate connect guard
# ---------------------------------------------------------------------------


def test_callback_signal_duplicate_connect_is_noop() -> None:
    """Connecting the same callback twice registers it only once."""
    from src.constants._signal import CallbackSignal  # noqa: PLC0415

    sig = CallbackSignal()
    calls: list[str] = []
    cb = calls.append

    sig.connect(cb)
    sig.connect(cb)  # second registration should be ignored

    sig.emit("ping")
    assert calls == ["ping"]  # emitted exactly once, not twice


# ---------------------------------------------------------------------------
# CallbackSignal — disconnect unregistered callback raises ValueError
# ---------------------------------------------------------------------------


def test_callback_signal_disconnect_unregistered_is_silent_noop() -> None:
    """Disconnecting a never-connected callback is a silent no-op.

    ``CallbackSignal.disconnect`` suppresses the ``ValueError`` that
    ``list.remove`` would otherwise raise — see the function's
    docstring for the widget-destroyed-race rationale.
    """
    from src.constants._signal import CallbackSignal  # noqa: PLC0415

    sig = CallbackSignal()

    # Silent — no exception expected.
    sig.disconnect(lambda: None)
    assert sig._callbacks == []


# ---------------------------------------------------------------------------
# _load_translations() — malformed JSON raises JSONDecodeError → empty dict
# ---------------------------------------------------------------------------


def test_load_translations_malformed_json_empties_dict() -> None:
    """Malformed JSON in a translation file resets translations to empty dict."""
    from unittest.mock import mock_open, patch  # noqa: PLC0415

    from src.constants.i18n import (  # noqa: PLC0415
        _load_translations,
        current_language,
        set_language,
        tr,
    )

    # Patch open() to return invalid JSON
    m = mock_open(read_data="{ this is not valid json }")
    with (
        patch("src.constants.i18n._TRANSLATIONS_DIR") as mock_dir,
        patch("builtins.open", m),
    ):
        # Make path.exists() return True so the file-open path is taken
        mock_path = type(
            "FakePath",
            (),
            {
                "exists": lambda self: True,
                "open": lambda self, **kw: m(),
                "__str__": lambda self: "fake.json",
            },
        )()
        mock_dir.__truediv__ = lambda self, name: mock_path

        _load_translations("en-US")

    # After malformed JSON, translations should be empty → tr() returns key
    assert tr("btn.ok") == "btn.ok"

    # Restore real translations
    set_language(current_language())


# ===========================================================================
# Expanded tests: color() for all palette keys in both themes
# ===========================================================================


_ALL_PALETTE_KEYS = [
    "primary",
    "secondary",
    "sidebar_bg",
    "outline",
    "error",
    "success",
    "warning",
    "app_bg",
    "component_bg",
    "disabled_bg",
    "disabled_text",
    "border_light",
    "hover_light",
    "text_primary",
    "text_secondary",
    "sidebar_text",
    "sidebar_disabled",
    "primary_hover",
    "primary_pressed",
    "primary_light",
    "error_hover",
    "error_pressed",
    "warning_hover",
    "scrollbar_handle",
    "scrollbar_hover",
    "highlight_bg",
    "highlight_text",
]


import pytest  # noqa: E402


@pytest.mark.parametrize("key", _ALL_PALETTE_KEYS)
def test_color_light_theme_key(key: str) -> None:
    """color(key) returns a valid hex color in light theme."""
    from src.constants.theme import _set_initial_theme  # noqa: PLC0415

    original = current_theme()
    try:
        _set_initial_theme("light")
        val = color(key)
        assert isinstance(val, str)
        assert val.startswith("#")
        assert len(val) in (4, 7)
    finally:
        _set_initial_theme(original)


@pytest.mark.parametrize("key", _ALL_PALETTE_KEYS)
def test_color_dark_theme_key(key: str) -> None:
    """color(key) returns a valid hex color in dark theme."""
    from src.constants.theme import _set_initial_theme  # noqa: PLC0415

    original = current_theme()
    try:
        _set_initial_theme("dark")
        val = color(key)
        assert isinstance(val, str)
        assert val.startswith("#")
        assert len(val) in (4, 7)
    finally:
        _set_initial_theme(original)


# ===========================================================================
# Expanded tests: set_theme() transitions
# ===========================================================================


def test_set_theme_light_to_dark_and_back() -> None:
    """set_theme light -> dark -> light round-trip restores original palette."""
    from src.constants.theme import _set_initial_theme  # noqa: PLC0415

    _set_initial_theme("light")
    light_bg = color("app_bg")
    set_theme("dark")
    assert color("app_bg") != light_bg
    set_theme("light")
    assert color("app_bg") == light_bg


def test_set_theme_dark_to_light_and_back() -> None:
    """set_theme dark -> light -> dark round-trip restores original palette."""
    from src.constants.theme import _set_initial_theme  # noqa: PLC0415

    original = current_theme()
    try:
        _set_initial_theme("dark")
        dark_bg = color("app_bg")
        set_theme("light")
        assert color("app_bg") != dark_bg
        set_theme("dark")
        assert color("app_bg") == dark_bg
    finally:
        _set_initial_theme(original)


def test_set_theme_multiple_invalid_names_keep_current() -> None:
    """Multiple invalid names leave the theme unchanged."""
    original = current_theme()
    for name in ["solarized", "monokai", "nord", "", "DARK", "Light"]:
        set_theme(name)  # type: ignore[arg-type]
    assert current_theme() == original


def test_set_theme_emits_signal_with_correct_name(qtbot: "QtBot") -> None:
    """Signal payload matches the requested theme name."""
    from src.constants.theme import _set_initial_theme  # noqa: PLC0415

    original = current_theme()
    _set_initial_theme("light")
    received: list[str] = []
    theme_changed.connect(received.append)
    try:
        set_theme("dark")
        assert received == ["dark"]
        set_theme("light")
        assert received == ["dark", "light"]
    finally:
        theme_changed.disconnect(received.append)
        _set_initial_theme(original)


def test_set_theme_no_signal_on_repeated_same_theme(qtbot: "QtBot") -> None:
    """Repeated set_theme() with same value never emits."""
    original = current_theme()
    received: list[str] = []
    theme_changed.connect(received.append)
    try:
        for _ in range(5):
            set_theme(original)
    finally:
        theme_changed.disconnect(received.append)
    assert received == []


# ===========================================================================
# Expanded tests: style_primary_button in both themes
# ===========================================================================


def test_style_primary_button_light_contains_primary_color() -> None:
    """style_primary_button() in light theme uses primary color."""
    from src.constants.theme import (  # noqa: PLC0415
        _set_initial_theme,
        style_primary_button,
    )

    original = current_theme()
    try:
        _set_initial_theme("light")
        qss = style_primary_button()
        assert color("primary") in qss
        assert "QPushButton" in qss
        assert "background-color" in qss
    finally:
        _set_initial_theme(original)


def test_style_primary_button_dark_contains_primary_color() -> None:
    """style_primary_button() in dark theme uses primary color."""
    from src.constants.theme import (  # noqa: PLC0415
        _set_initial_theme,
        style_primary_button,
    )

    original = current_theme()
    try:
        _set_initial_theme("dark")
        qss = style_primary_button()
        assert color("primary") in qss
        assert ":hover" in qss
        assert ":disabled" in qss
    finally:
        _set_initial_theme(original)


def test_style_primary_button_has_hover_and_pressed() -> None:
    """style_primary_button() QSS includes hover and pressed states."""
    from src.constants.theme import style_primary_button  # noqa: PLC0415

    qss = style_primary_button()
    assert ":hover" in qss
    assert ":pressed" in qss


def test_style_primary_button_has_border_radius() -> None:
    """style_primary_button() QSS includes border-radius."""
    from src.constants.theme import style_primary_button  # noqa: PLC0415

    qss = style_primary_button()
    assert "border-radius" in qss


# ===========================================================================
# Expanded tests: style_secondary_button in both themes
# ===========================================================================


def test_style_secondary_button_light_uses_text_secondary() -> None:
    """style_secondary_button() in light uses text_secondary color."""
    from src.constants.theme import (  # noqa: PLC0415
        _set_initial_theme,
        style_secondary_button,
    )

    original = current_theme()
    try:
        _set_initial_theme("light")
        qss = style_secondary_button()
        assert color("text_secondary") in qss
    finally:
        _set_initial_theme(original)


def test_style_secondary_button_dark_uses_text_secondary() -> None:
    """style_secondary_button() in dark uses text_secondary color."""
    from src.constants.theme import (  # noqa: PLC0415
        _set_initial_theme,
        style_secondary_button,
    )

    original = current_theme()
    try:
        _set_initial_theme("dark")
        qss = style_secondary_button()
        assert color("text_secondary") in qss
    finally:
        _set_initial_theme(original)


def test_style_secondary_button_has_hover_and_pressed() -> None:
    """style_secondary_button() includes hover and pressed states."""
    from src.constants.theme import style_secondary_button  # noqa: PLC0415

    qss = style_secondary_button()
    assert ":hover" in qss
    assert ":pressed" in qss


def test_style_secondary_button_differs_between_themes() -> None:
    """style_secondary_button() produces different QSS per theme."""
    from src.constants.theme import (  # noqa: PLC0415
        _set_initial_theme,
        style_secondary_button,
    )

    original = current_theme()
    try:
        _set_initial_theme("light")
        light_qss = style_secondary_button()
        _set_initial_theme("dark")
        dark_qss = style_secondary_button()
        assert light_qss != dark_qss
    finally:
        _set_initial_theme(original)


# ===========================================================================
# Expanded tests: style_delete_button in both themes
# ===========================================================================


def test_style_delete_button_light_uses_error_color() -> None:
    """style_delete_button() in light theme uses error color."""
    from src.constants.theme import (  # noqa: PLC0415
        _set_initial_theme,
        style_delete_button,
    )

    original = current_theme()
    try:
        _set_initial_theme("light")
        qss = style_delete_button()
        assert color("error") in qss
        assert "border: 1px solid" in qss
    finally:
        _set_initial_theme(original)


def test_style_delete_button_dark_uses_error_color() -> None:
    """style_delete_button() in dark theme uses error color."""
    from src.constants.theme import (  # noqa: PLC0415
        _set_initial_theme,
        style_delete_button,
    )

    original = current_theme()
    try:
        _set_initial_theme("dark")
        qss = style_delete_button()
        assert color("error") in qss
    finally:
        _set_initial_theme(original)


def test_style_delete_button_has_disabled_state() -> None:
    """style_delete_button() includes a :disabled selector."""
    from src.constants.theme import style_delete_button  # noqa: PLC0415

    qss = style_delete_button()
    assert ":disabled" in qss


def test_style_delete_button_transparent_bg() -> None:
    """style_delete_button() has transparent background."""
    from src.constants.theme import style_delete_button  # noqa: PLC0415

    qss = style_delete_button()
    assert "transparent" in qss


# ===========================================================================
# Expanded tests: style_warning_button in both themes
# ===========================================================================


def test_style_warning_button_light_uses_warning_color() -> None:
    """style_warning_button() in light theme uses warning color."""
    from src.constants.theme import (  # noqa: PLC0415
        _set_initial_theme,
        style_warning_button,
    )

    original = current_theme()
    try:
        _set_initial_theme("light")
        qss = style_warning_button()
        assert color("warning") in qss
    finally:
        _set_initial_theme(original)


def test_style_warning_button_dark_uses_warning_color() -> None:
    """style_warning_button() in dark theme uses warning color."""
    from src.constants.theme import (  # noqa: PLC0415
        _set_initial_theme,
        style_warning_button,
    )

    original = current_theme()
    try:
        _set_initial_theme("dark")
        qss = style_warning_button()
        assert color("warning") in qss
    finally:
        _set_initial_theme(original)


def test_style_warning_button_has_hover_and_disabled() -> None:
    """style_warning_button() includes hover and disabled states."""
    from src.constants.theme import style_warning_button  # noqa: PLC0415

    qss = style_warning_button()
    assert ":hover" in qss
    assert ":disabled" in qss


def test_style_warning_button_has_transparent_background() -> None:
    """style_warning_button() has transparent background."""
    from src.constants.theme import style_warning_button  # noqa: PLC0415

    qss = style_warning_button()
    assert "transparent" in qss


# ===========================================================================
# Expanded tests: style_outlined_primary_button in both themes
# ===========================================================================


def test_style_outlined_primary_button_light_primary_color() -> None:
    """style_outlined_primary_button() in light uses primary color."""
    from src.constants.theme import (  # noqa: PLC0415
        _set_initial_theme,
        style_outlined_primary_button,
    )

    original = current_theme()
    try:
        _set_initial_theme("light")
        qss = style_outlined_primary_button()
        assert color("primary") in qss
    finally:
        _set_initial_theme(original)


def test_style_outlined_primary_button_dark_primary_color() -> None:
    """style_outlined_primary_button() in dark uses primary color."""
    from src.constants.theme import (  # noqa: PLC0415
        _set_initial_theme,
        style_outlined_primary_button,
    )

    original = current_theme()
    try:
        _set_initial_theme("dark")
        qss = style_outlined_primary_button()
        assert color("primary") in qss
    finally:
        _set_initial_theme(original)


def test_style_outlined_primary_button_has_hover_and_disabled() -> None:
    """style_outlined_primary_button() includes hover and disabled."""
    from src.constants.theme import style_outlined_primary_button  # noqa: PLC0415

    qss = style_outlined_primary_button()
    assert ":hover" in qss
    assert ":disabled" in qss


def test_style_outlined_primary_button_transparent_bg() -> None:
    """style_outlined_primary_button() has transparent background."""
    from src.constants.theme import style_outlined_primary_button  # noqa: PLC0415

    qss = style_outlined_primary_button()
    assert "transparent" in qss


# ===========================================================================
# Expanded tests: style_input_field in both themes
# ===========================================================================


def test_style_input_field_light_contains_qlineedit() -> None:
    """style_input_field() in light theme targets QLineEdit."""
    from src.constants.theme import (  # noqa: PLC0415
        _set_initial_theme,
        style_input_field,
    )

    original = current_theme()
    try:
        _set_initial_theme("light")
        qss = style_input_field()
        assert "QLineEdit" in qss
        assert color("component_bg") in qss
    finally:
        _set_initial_theme(original)


def test_style_input_field_dark_contains_dark_colors() -> None:
    """style_input_field() in dark theme uses dark palette."""
    from src.constants.theme import (  # noqa: PLC0415
        _set_initial_theme,
        style_input_field,
    )

    original = current_theme()
    try:
        _set_initial_theme("dark")
        qss = style_input_field()
        assert color("component_bg") in qss
        assert color("text_primary") in qss
    finally:
        _set_initial_theme(original)


def test_style_input_field_has_focus_state() -> None:
    """style_input_field() includes :focus selector."""
    from src.constants.theme import style_input_field  # noqa: PLC0415

    qss = style_input_field()
    assert ":focus" in qss


def test_style_input_field_has_disabled_state() -> None:
    """style_input_field() includes :disabled selector."""
    from src.constants.theme import style_input_field  # noqa: PLC0415

    qss = style_input_field()
    assert ":disabled" in qss


def test_style_input_field_differs_between_themes() -> None:
    """style_input_field() differs between light and dark."""
    from src.constants.theme import (  # noqa: PLC0415
        _set_initial_theme,
        style_input_field,
    )

    original = current_theme()
    try:
        _set_initial_theme("light")
        light_qss = style_input_field()
        _set_initial_theme("dark")
        dark_qss = style_input_field()
        assert light_qss != dark_qss
    finally:
        _set_initial_theme(original)


# ===========================================================================
# Expanded tests: style_table in both themes
# ===========================================================================


def test_style_table_light_contains_qtablewidget() -> None:
    """style_table() in light theme targets QTableWidget."""
    from src.constants.theme import _set_initial_theme, style_table  # noqa: PLC0415

    original = current_theme()
    try:
        _set_initial_theme("light")
        qss = style_table()
        assert "QTableWidget" in qss
        assert "QHeaderView" in qss
    finally:
        _set_initial_theme(original)


def test_style_table_dark_uses_dark_palette() -> None:
    """style_table() in dark theme uses dark palette colors."""
    from src.constants.theme import (  # noqa: PLC0415
        _PALETTES,
        _set_initial_theme,
        style_table,
    )

    original = current_theme()
    try:
        _set_initial_theme("dark")
        qss = style_table()
        assert _PALETTES["dark"]["component_bg"] in qss
    finally:
        _set_initial_theme(original)


def test_style_table_has_selection_bg() -> None:
    """style_table() includes selection-background-color."""
    from src.constants.theme import style_table  # noqa: PLC0415

    qss = style_table()
    assert "selection-background-color" in qss


def test_style_table_has_header_section() -> None:
    """style_table() includes QHeaderView::section."""
    from src.constants.theme import style_table  # noqa: PLC0415

    qss = style_table()
    assert "QHeaderView::section" in qss


# ===========================================================================
# Expanded tests: style_scrollbar in both themes
# ===========================================================================


def test_style_scrollbar_light_contains_handle() -> None:
    """style_scrollbar() in light theme uses scrollbar_handle color."""
    from src.constants.theme import _set_initial_theme, style_scrollbar  # noqa: PLC0415

    original = current_theme()
    try:
        _set_initial_theme("light")
        qss = style_scrollbar()
        assert color("scrollbar_handle") in qss
    finally:
        _set_initial_theme(original)


def test_style_scrollbar_dark_contains_handle() -> None:
    """style_scrollbar() in dark theme uses scrollbar_handle color."""
    from src.constants.theme import _set_initial_theme, style_scrollbar  # noqa: PLC0415

    original = current_theme()
    try:
        _set_initial_theme("dark")
        qss = style_scrollbar()
        assert color("scrollbar_handle") in qss
    finally:
        _set_initial_theme(original)


def test_style_scrollbar_has_vertical_selector() -> None:
    """style_scrollbar() targets vertical scrollbar."""
    from src.constants.theme import style_scrollbar  # noqa: PLC0415

    qss = style_scrollbar()
    assert "QScrollBar:vertical" in qss
    assert "::handle:vertical" in qss


def test_style_scrollbar_has_hover_state() -> None:
    """style_scrollbar() has handle hover state."""
    from src.constants.theme import style_scrollbar  # noqa: PLC0415

    qss = style_scrollbar()
    assert "::handle:vertical:hover" in qss


def test_style_scrollbar_differs_between_themes() -> None:
    """style_scrollbar() differs between light and dark."""
    from src.constants.theme import _set_initial_theme, style_scrollbar  # noqa: PLC0415

    original = current_theme()
    try:
        _set_initial_theme("light")
        light_qss = style_scrollbar()
        _set_initial_theme("dark")
        dark_qss = style_scrollbar()
        assert light_qss != dark_qss
    finally:
        _set_initial_theme(original)


# ===========================================================================
# Expanded tests: style_link_button in both themes
# ===========================================================================


def test_style_link_button_light_uses_primary() -> None:
    """style_link_button() in light uses primary color."""
    from src.constants.theme import (  # noqa: PLC0415
        _set_initial_theme,
        style_link_button,
    )

    original = current_theme()
    try:
        _set_initial_theme("light")
        qss = style_link_button()
        assert color("primary") in qss
    finally:
        _set_initial_theme(original)


def test_style_link_button_dark_uses_primary() -> None:
    """style_link_button() in dark uses primary color."""
    from src.constants.theme import (  # noqa: PLC0415
        _set_initial_theme,
        style_link_button,
    )

    original = current_theme()
    try:
        _set_initial_theme("dark")
        qss = style_link_button()
        assert color("primary") in qss
    finally:
        _set_initial_theme(original)


def test_style_link_button_has_disabled() -> None:
    """style_link_button() has :disabled selector."""
    from src.constants.theme import style_link_button  # noqa: PLC0415

    qss = style_link_button()
    assert ":disabled" in qss


def test_style_link_button_transparent_bg() -> None:
    """style_link_button() has transparent background."""
    from src.constants.theme import style_link_button  # noqa: PLC0415

    qss = style_link_button()
    assert "transparent" in qss


# ===========================================================================
# Expanded tests: style_danger_button in both themes
# ===========================================================================


def test_style_danger_button_light_uses_error() -> None:
    """style_danger_button() in light uses error color for background."""
    from src.constants.theme import (  # noqa: PLC0415
        _set_initial_theme,
        style_danger_button,
    )

    original = current_theme()
    try:
        _set_initial_theme("light")
        qss = style_danger_button()
        assert color("error") in qss
    finally:
        _set_initial_theme(original)


def test_style_danger_button_dark_uses_error() -> None:
    """style_danger_button() in dark uses error color for background."""
    from src.constants.theme import (  # noqa: PLC0415
        _set_initial_theme,
        style_danger_button,
    )

    original = current_theme()
    try:
        _set_initial_theme("dark")
        qss = style_danger_button()
        assert color("error") in qss
    finally:
        _set_initial_theme(original)


def test_style_danger_button_has_hover_and_pressed() -> None:
    """style_danger_button() includes hover and pressed states."""
    from src.constants.theme import style_danger_button  # noqa: PLC0415

    qss = style_danger_button()
    assert ":hover" in qss
    assert ":pressed" in qss


def test_style_danger_button_uses_white_text() -> None:
    """style_danger_button() uses white text color."""
    from src.constants.theme import style_danger_button  # noqa: PLC0415

    qss = style_danger_button()
    assert "color: white" in qss


# ===========================================================================
# Expanded tests: theme_changed signal
# ===========================================================================


def test_theme_changed_signal_type() -> None:
    """theme_changed is a CallbackSignal instance."""
    from src.constants._signal import CallbackSignal  # noqa: PLC0415

    assert isinstance(theme_changed, CallbackSignal)


def test_theme_changed_signal_has_full_api() -> None:
    """theme_changed has connect, disconnect, and emit methods."""
    assert hasattr(theme_changed, "connect")
    assert hasattr(theme_changed, "disconnect")
    assert hasattr(theme_changed, "emit")


def test_theme_changed_counts_multiple_switches(qtbot: "QtBot") -> None:
    """Multiple theme switches emit the correct number of signals."""
    from src.constants.theme import _set_initial_theme  # noqa: PLC0415

    original = current_theme()
    _set_initial_theme("light")
    received: list[str] = []
    theme_changed.connect(received.append)
    try:
        set_theme("dark")
        set_theme("light")
        set_theme("dark")
    finally:
        theme_changed.disconnect(received.append)
        _set_initial_theme(original)
    assert received == ["dark", "light", "dark"]


# ===========================================================================
# Expanded tests: QSS correctness checks
# ===========================================================================


def test_style_checkbox_has_indicator_states() -> None:
    """style_checkbox() includes indicator checked/unchecked/disabled states."""
    from src.constants.theme import style_checkbox  # noqa: PLC0415

    qss = style_checkbox()
    assert "::indicator:checked" in qss
    assert "::indicator:unchecked" in qss
    assert ":disabled" in qss


def test_style_checkbox_differs_between_themes() -> None:
    """style_checkbox() differs between light and dark themes."""
    from src.constants.theme import _set_initial_theme, style_checkbox  # noqa: PLC0415

    original = current_theme()
    try:
        _set_initial_theme("light")
        light_qss = style_checkbox()
        _set_initial_theme("dark")
        dark_qss = style_checkbox()
        assert light_qss != dark_qss
    finally:
        _set_initial_theme(original)


def test_style_setting_combo_has_dropdown() -> None:
    """style_setting_combo() includes drop-down and down-arrow selectors."""
    from src.constants.theme import style_setting_combo  # noqa: PLC0415

    qss = style_setting_combo()
    assert "::drop-down" in qss
    assert "::down-arrow" in qss


def test_style_setting_combo_differs_between_themes() -> None:
    """style_setting_combo() differs between light and dark."""
    from src.constants.theme import (  # noqa: PLC0415
        _set_initial_theme,
        style_setting_combo,
    )

    original = current_theme()
    try:
        _set_initial_theme("light")
        light_qss = style_setting_combo()
        _set_initial_theme("dark")
        dark_qss = style_setting_combo()
        assert light_qss != dark_qss
    finally:
        _set_initial_theme(original)


def test_style_page_header_uses_text_primary() -> None:
    """style_page_header() uses text_primary color."""
    from src.constants.theme import style_page_header  # noqa: PLC0415

    qss = style_page_header()
    assert color("text_primary") in qss


def test_style_section_group_uses_component_bg() -> None:
    """style_section_group() uses component_bg color."""
    from src.constants.theme import style_section_group  # noqa: PLC0415

    qss = style_section_group()
    assert color("component_bg") in qss


def test_style_section_title_uses_text_secondary() -> None:
    """style_section_title() uses text_secondary color."""
    from src.constants.theme import style_section_title  # noqa: PLC0415

    qss = style_section_title()
    assert color("text_secondary") in qss


def test_style_setting_container_uses_component_bg() -> None:
    """style_setting_container() uses component_bg color."""
    from src.constants.theme import style_setting_container  # noqa: PLC0415

    qss = style_setting_container()
    assert color("component_bg") in qss


def test_style_card_header_has_text_transform() -> None:
    """style_card_header() includes text-transform: uppercase."""
    from src.constants.theme import style_card_header  # noqa: PLC0415

    qss = style_card_header()
    assert "text-transform: uppercase" in qss


def test_style_banner_info_uses_primary_color() -> None:
    """style_banner('info') uses the primary color as accent."""
    from src.constants.theme import style_banner  # noqa: PLC0415

    qss = style_banner("info")
    assert color("primary") in qss


def test_style_banner_success_uses_success_color() -> None:
    """style_banner('success') uses the success color as accent."""
    from src.constants.theme import style_banner  # noqa: PLC0415

    qss = style_banner("success")
    assert color("success") in qss


def test_style_banner_error_uses_error_color() -> None:
    """style_banner('error') uses the error color as accent."""
    from src.constants.theme import style_banner  # noqa: PLC0415

    qss = style_banner("error")
    assert color("error") in qss


def test_style_banner_warning_uses_warning_color() -> None:
    """style_banner('warning') uses the warning color as accent."""
    from src.constants.theme import style_banner  # noqa: PLC0415

    qss = style_banner("warning")
    assert color("warning") in qss


def test_style_table_delete_button_has_no_border() -> None:
    """style_table_delete_button() uses border: none."""
    from src.constants.theme import style_table_delete_button  # noqa: PLC0415

    qss = style_table_delete_button()
    assert "border: none" in qss


def test_style_radio_button_has_gradient() -> None:
    """style_radio_button() includes qradialgradient for checked state."""
    from src.constants.theme import style_radio_button  # noqa: PLC0415

    qss = style_radio_button()
    assert "qradialgradient" in qss


def test_style_tab_widget_has_border_bottom() -> None:
    """style_tab_widget() includes border-bottom for tabs."""
    from src.constants.theme import style_tab_widget  # noqa: PLC0415

    qss = style_tab_widget()
    assert "border-bottom" in qss


def test_all_style_functions_differ_between_themes() -> None:
    """Every style_*() function that uses theme colors produces different QSS."""
    from src.constants.theme import (  # noqa: PLC0415
        _set_initial_theme,
        style_card_light,
        style_checkbox,
        style_input_field,
        style_list_widget,
        style_primary_button,
        style_radio_button,
        style_secondary_button,
        style_setting_combo,
        style_table,
    )

    original = current_theme()
    try:
        fns = [
            style_card_light,
            style_checkbox,
            style_input_field,
            style_list_widget,
            style_primary_button,
            style_radio_button,
            style_secondary_button,
            style_setting_combo,
            style_table,
        ]
        for fn in fns:
            _set_initial_theme("light")
            light_qss = fn()
            _set_initial_theme("dark")
            dark_qss = fn()
            assert light_qss != dark_qss, f"{fn.__name__} is same across themes"
    finally:
        _set_initial_theme(original)
