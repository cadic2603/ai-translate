"""Centralized theming engine for light and dark modes.

Provides color palettes, a theme-change signal, a color() accessor,
and style generator functions that produce QSS for the current theme.
"""

import logging
from typing import Literal

from src.constants._signal import CallbackSignal
from src.constants.ui import (
    BANNER_FONT_SIZE,
    BANNER_MARGIN_BOTTOM,
    CHECK_PATH,
    CHEVRON_DOWN_DISABLED_PATH,
    CHEVRON_DOWN_PATH,
    LABEL_PADDING_LEFT,
    RADIUS_BUTTON,
)

logger = logging.getLogger("theme")

ThemeName = Literal["light", "dark"]

# ── Color Palettes ───────────────────────────────────────────────

_PALETTES: dict[ThemeName, dict[str, str]] = {
    "light": {
        "primary": "#3e79f7",
        "secondary": "#e6ebf1",
        "sidebar_bg": "#283142",
        "outline": "#72849a",
        "error": "#ff6b72",
        "success": "#04d182",
        "warning": "#ffc542",
        "app_bg": "#fafafb",
        "component_bg": "#ffffff",
        "disabled_bg": "#f7f7f8",
        "disabled_text": "#b8bec4",
        "border_light": "#e6ebf1",
        "hover_light": "#f5f5f5",
        "text_primary": "#1a3353",
        "text_secondary": "#455560",
        "sidebar_text": "#99abb4",
        "sidebar_disabled": "#5c6b7a",
        "primary_hover": "#3568db",
        "primary_pressed": "#2a56c0",
        "primary_light": "#6a97f9",
        "error_hover": "#ff868c",
        "error_pressed": "#e55f65",
        "warning_hover": "#ffd06a",
        "scrollbar_handle": "#C4C7C5",
        "scrollbar_hover": "#8E918F",
        "highlight_bg": "#ffeb3b",
        "highlight_text": "#000000",
    },
    "dark": {
        "primary": "#3e79f7",
        "secondary": "#4d5b75",
        "sidebar_bg": "#283142",
        "outline": "#617190",
        "error": "#ff6b72",
        "success": "#04d182",
        "warning": "#ffc542",
        "app_bg": "#1b2531",
        "component_bg": "#283142",
        "disabled_bg": "#586379",
        "disabled_text": "#6b7a8e",
        "border_light": "#4d5b75",
        "hover_light": "#364663",
        "text_primary": "#d6d7dc",
        "text_secondary": "#b4bed2",
        "sidebar_text": "#99abb4",
        "sidebar_disabled": "#5c6b7a",
        "primary_hover": "#5a8ef9",
        "primary_pressed": "#2a56c0",
        "primary_light": "#6a97f9",
        "error_hover": "#ff868c",
        "error_pressed": "#e55f65",
        "warning_hover": "#ffd06a",
        "scrollbar_handle": "#4d5b75",
        "scrollbar_hover": "#617190",
        "highlight_bg": "#ffc542",
        "highlight_text": "#1b2531",
    },
}

# ── Theme State ──────────────────────────────────────────────────

_current_theme: ThemeName = "light"


# Emitted when the active theme changes
theme_changed = CallbackSignal()


def current_theme() -> ThemeName:
    """Returns the name of the currently active theme."""
    return _current_theme


def set_theme(name: ThemeName) -> None:
    """Switches the active theme and emits the changed signal."""
    global _current_theme  # noqa: PLW0603
    if name not in _PALETTES:
        logger.warning("Unknown theme '%s', ignoring.", name)
        return
    if name == _current_theme:
        return
    _current_theme = name
    theme_changed.emit(name)


def _set_initial_theme(name: ThemeName) -> None:
    """Sets the theme at startup without emitting a signal."""
    global _current_theme  # noqa: PLW0603
    if name in _PALETTES:
        _current_theme = name


def color(key: str) -> str:
    """Returns the color value for *key* in the current theme."""
    return _PALETTES[_current_theme][key]


# ── Style Generator Functions ────────────────────────────────────


def style_sidebar_list() -> str:
    """QSS for the sidebar navigation list."""
    return f"""
        QListWidget {{
            background-color: {color("sidebar_bg")};
            color: {color("sidebar_text")};
            border: none;
            outline: none;
            font-size: 14px;
        }}
        QListWidget::item {{
            padding: 14px 24px;
            margin: 0px;
        }}
        QListWidget::item:selected {{
            background-color: rgba(255, 255, 255, 0.1);
            color: white;
        }}
        QListWidget::item:hover:!selected {{
            background-color: rgba(255, 255, 255, 0.05);
        }}
        QListWidget::item:disabled {{
            color: {color("sidebar_disabled")};
            background-color: transparent;
        }}
    """


def style_page_header() -> str:
    """QSS for page header labels."""
    return (
        f"font-size: 24px; font-weight: 400; color: {color('text_primary')};"
        " margin-bottom: 12px;"
    )


def style_section_group() -> str:
    """QSS for bordered section cards."""
    return (
        f"QFrame {{ border: 1px solid {color('border_light')}; "
        f"border-radius: {RADIUS_BUTTON}px; "
        f"background-color: {color('component_bg')}; "
        f"color: {color('text_primary')}; }}"
    )


def style_section_title() -> str:
    """QSS for section title labels."""
    return (
        f"font-weight: 500; font-size: 14px; color: {color('text_secondary')}; "
        "border: none; padding-bottom: 8px; text-transform: uppercase;"
        " letter-spacing: 1px;"
    )


def style_list_widget() -> str:
    """QSS for general list widgets (e.g. glossary sets)."""
    return f"""
        QListWidget {{
            border: 1px solid {color("border_light")};
            border-radius: {RADIUS_BUTTON}px;
            background-color: {color("component_bg")};
            color: {color("text_primary")};
            outline: none;
        }}
        QListWidget::item {{
            padding: 12px;
            color: {color("text_secondary")};
            border-radius: 8px;
            margin: 2px 4px;
        }}
        QListWidget::item:selected {{
            background-color: rgba(62, 121, 247, 0.1);
            color: {color("primary")};
            font-weight: 500;
        }}
        QListWidget::item:hover {{
            background-color: {color("hover_light")};
        }}
        QListWidget::item:disabled {{
            color: {color("disabled_text")};
            background-color: transparent;
        }}
        QListWidget::indicator {{
            width: 18px;
            height: 18px;
            border-radius: 4px;
            border: 1px solid {color("text_secondary")};
        }}
        QListWidget::indicator:unchecked {{
            background-color: {color("component_bg")};
        }}
        QListWidget::indicator:checked {{
            background-color: {color("primary")};
            image: url("{CHECK_PATH}");
        }}
        QListWidget::indicator:unchecked:hover,
        QListWidget::indicator:checked:hover {{
            border: 1px solid {color("primary")};
        }}
    """


def style_checkbox() -> str:
    """QSS for checkboxes."""
    return f"""
        QCheckBox {{
            spacing: 12px;
            color: {color("text_primary")};
            font-size: 14px;
            padding: 8px;
            background-color: {color("component_bg")};
            border: none;
        }}
        QCheckBox::indicator {{
            width: 20px;
            height: 20px;
            border-radius: 4px;
            border: 2px solid {color("outline")};
        }}
        QCheckBox::indicator:unchecked {{
            background-color: {color("component_bg")};
        }}
        QCheckBox::indicator:checked {{
            background-color: {color("primary")};
            border: 2px solid {color("primary")};
            image: url("{CHECK_PATH}");
        }}
        QCheckBox::indicator:unchecked:hover {{
            border-color: {color("primary")};
            background-color: {color("hover_light")};
        }}
        QCheckBox::indicator:checked:hover {{
            border-color: {color("primary")};
            background-color: {color("primary")};
        }}
        QCheckBox:disabled {{
            color: {color("disabled_text")};
        }}
        QCheckBox::indicator:disabled {{
            border-color: {color("disabled_text")};
            background-color: {color("disabled_bg")};
        }}
    """


def style_card_light() -> str:
    """QSS for light-tinted card backgrounds."""
    return (
        f"background-color: {color('disabled_bg')};"
        f" border-radius: {RADIUS_BUTTON}px; "
        f"border: none; color: {color('text_primary')};"
    )


def style_card_header() -> str:
    """QSS for card header labels."""
    return (
        "font-size: 11px; font-weight: 600;"
        f" color: {color('text_secondary')};"
        " text-transform: uppercase;"
    )


def style_link_button() -> str:
    """QSS for text-only link-style buttons (primary action variant)."""
    return f"""
        QPushButton {{
            border: 1px solid transparent;
            background-color: transparent;
            font-size: 14px;
            color: {color("primary")};
            font-weight: 500;
            padding: 10px 12px;
            border-radius: {RADIUS_BUTTON}px;
            outline: none;
        }}
        QPushButton:hover, QPushButton:focus {{
            color: {color("primary_light")};
        }}
        QPushButton:disabled {{
            color: {color("disabled_text")};
        }}
    """


def style_link_button_muted() -> str:
    """QSS for text-only secondary-action link buttons.

    Same shape as :func:`style_link_button` but uses
    ``text_secondary`` instead of the primary brand colour so a
    paired secondary action (Reset next to Browse, Cancel next to
    Confirm, etc.) reads as visually subordinate to the primary
    action.  Hover lifts to ``text_primary`` rather than
    ``primary_light`` for the same reason.
    """
    return f"""
        QPushButton {{
            border: 1px solid transparent;
            background-color: transparent;
            font-size: 14px;
            color: {color("text_secondary")};
            font-weight: 500;
            padding: 10px 12px;
            border-radius: {RADIUS_BUTTON}px;
            outline: none;
        }}
        QPushButton:hover, QPushButton:focus {{
            color: {color("text_primary")};
        }}
        QPushButton:disabled {{
            color: {color("disabled_text")};
        }}
    """


def style_setting_container() -> str:
    """QSS for settings section containers."""
    return f"background-color: {color('component_bg')}; border: none;"


def style_input_label() -> str:
    """QSS for settings input labels."""
    return (
        f"font-size: 14px; color: {color('text_secondary')};"
        f" font-weight: 500; padding-left: {LABEL_PADDING_LEFT}px;"
    )


def style_input_field() -> str:
    """QSS for text input fields."""
    return f"""
        QLineEdit {{
            font-size: 14px;
            padding: 10px 16px;
            border: 1px solid {color("secondary")};
            border-radius: {RADIUS_BUTTON}px;
            background: {color("component_bg")};
            color: {color("text_primary")};
        }}
        QLineEdit:hover {{
            border: 1px solid {color("primary")};
        }}
        QLineEdit:focus {{
            border: 2px solid {color("primary")};
            padding: 9px 15px;
        }}
        QLineEdit:disabled {{
            background-color: {color("disabled_bg")};
            color: {color("disabled_text")};
            border: 1px solid {color("border_light")};
        }}
    """


def style_setting_combo() -> str:
    """QSS for combo box dropdowns."""
    return f"""
        QComboBox {{
            font-size: 14px;
            /* Asymmetric padding: full 16px on the left for visual balance,
               minimal 4px on the right because the chevron sub-control
               already provides its own internal spacing.  Without this,
               long labels like "Chinese (Traditional)" truncate even
               though there's a visible gap before the chevron. */
            padding: 10px 4px 10px 16px;
            border: 1px solid {color("secondary")};
            border-radius: {RADIUS_BUTTON}px;
            background: {color("component_bg")};
            color: {color("text_primary")};
            combobox-popup: 0;
        }}
        QComboBox:hover {{
            border: 1px solid {color("primary")};
        }}
        QComboBox:focus {{
            border: 2px solid {color("primary")};
            padding: 9px 3px 9px 15px;
        }}
        QComboBox:on {{
            border: 2px solid {color("primary")};
            padding: 9px 3px 9px 15px;
        }}
        QComboBox:disabled {{
            background-color: {color("disabled_bg")};
            color: {color("disabled_text")};
            border: 1px solid {color("border_light")};
        }}
        QComboBox::drop-down {{
            subcontrol-origin: padding;
            subcontrol-position: top right;
            /* 24px = 18px chevron icon + 3px breathing room each side.
               Was 30px, which left the icon visibly floating with too
               much empty space on either side. */
            width: 24px;
            border: none;
        }}
        QComboBox::down-arrow {{
            image: url("{CHEVRON_DOWN_PATH}");
            width: 18px;
            height: 18px;
            subcontrol-position: center;
        }}
        QComboBox::down-arrow:disabled {{
            image: url("{CHEVRON_DOWN_DISABLED_PATH}");
        }}
        QComboBox QAbstractItemView {{
            border: 1px solid {color("border_light")};
            border-radius: 8px;
            background-color: {color("component_bg")};
            selection-background-color: rgba(62, 121, 247, 0.1);
            selection-color: {color("primary")};
            outline: none;
            /* Small inner padding so item hover backgrounds don't bleed
               into the rounded corners of the popup container. */
            padding: 4px;
            margin: 0px;
        }}
        QComboBox QAbstractItemView::item {{
            padding: 6px 12px;
            min-height: 24px;
            margin: 0px;
            border-radius: 4px;
        }}
        QComboBox QAbstractItemView::item:hover,
        QComboBox QAbstractItemView::item:selected {{
            background-color: rgba(62, 121, 247, 0.1);
            color: {color("primary")};
        }}
    """


def style_tab_widget() -> str:
    """QSS for tab widgets."""
    return f"""
        QTabWidget {{
            background-color: transparent;
        }}
        QTabWidget::pane {{
            border: none;
            background-color: transparent;
        }}
        QTabBar {{
            background-color: transparent;
            qproperty-drawBase: 0;
            alignment: center;
        }}
        QTabBar::tab {{
            background-color: transparent;
            color: {color("text_secondary")};
            padding: 12px 20px;
            margin: 0 4px;
            font-weight: 600;
            font-size: 15px;
            border-bottom: 3px solid transparent;
        }}
        QTabBar::tab:selected {{
            color: {color("primary")};
            border-bottom: 3px solid {color("primary")};
        }}
        QTabBar::tab:hover:!selected {{
            color: {color("primary")};
            background-color: {color("hover_light")};
            border-top-left-radius: 8px;
            border-top-right-radius: 8px;
        }}
    """


def style_radio_button() -> str:
    """QSS for radio buttons."""
    c = color("component_bg")
    return f"""
        QRadioButton {{
            spacing: 12px;
            color: {color("text_primary")};
            font-size: 14px;
            padding: 8px;
            background-color: {c};
            border: none;
        }}
        QRadioButton::indicator {{
            width: 20px;
            height: 20px;
            border-radius: 12px;
        }}
        QRadioButton::indicator:unchecked {{
            border: 2px solid {color("outline")};
            background-color: {c};
        }}
        QRadioButton::indicator:checked {{
            border: 2px solid {color("primary")};
            background-color: qradialgradient(
                cx:0.5, cy:0.5, radius:0.5, fx:0.5, fy:0.5,
                stop:0 {color("primary")},
                stop:0.45 {color("primary")},
                stop:0.46 {c},
                stop:1 {c}
            );
        }}
        QRadioButton::indicator:unchecked:hover {{
            border-color: {color("primary")};
            background-color: {color("hover_light")};
        }}
        QRadioButton::indicator:checked:hover {{
            border-color: {color("primary")};
            background-color: qradialgradient(
                cx:0.5, cy:0.5, radius:0.5, fx:0.5, fy:0.5,
                stop:0 {color("primary")},
                stop:0.45 {color("primary")},
                stop:0.46 {color("hover_light")},
                stop:1 {color("hover_light")}
            );
        }}
        QRadioButton:disabled {{
            color: {color("disabled_text")};
        }}
        QRadioButton::indicator:disabled {{
            border-color: {color("disabled_text")};
            background-color: {color("disabled_bg")};
        }}
        QRadioButton::indicator:checked:disabled {{
            background-color: qradialgradient(
                cx:0.5, cy:0.5, radius:0.5, fx:0.5, fy:0.5,
                stop:0 {color("disabled_text")},
                stop:0.45 {color("disabled_text")},
                stop:0.46 {color("disabled_bg")},
                stop:1 {color("disabled_bg")}
            );
        }}
    """


def style_primary_button() -> str:
    """QSS for primary action buttons."""
    return f"""
        QPushButton {{
            background-color: {color("primary")};
            color: white;
            border: none;
            border-radius: {RADIUS_BUTTON}px;
            padding: 10px 24px;
            font-weight: 400;
            font-size: 14px;
            outline: none;
        }}
        QPushButton:hover, QPushButton:focus {{
            background-color: {color("primary_hover")};
        }}
        QPushButton:pressed {{
            background-color: {color("primary_pressed")};
        }}
        QPushButton:disabled {{
            background-color: {color("disabled_bg")};
            color: {color("disabled_text")};
            border: 1px solid {color("border_light")};
        }}
    """


def style_danger_button() -> str:
    """QSS for filled destructive buttons."""
    return f"""
        QPushButton {{
            background-color: {color("error")};
            color: white;
            border: none;
            border-radius: {RADIUS_BUTTON}px;
            padding: 10px 24px;
            font-weight: 400;
            font-size: 14px;
            outline: none;
        }}
        QPushButton:hover, QPushButton:focus {{
            background-color: {color("error_hover")};
        }}
        QPushButton:pressed {{
            background-color: {color("error_pressed")};
        }}
        QPushButton:disabled {{
            background-color: {color("disabled_bg")};
            color: {color("disabled_text")};
            border: 1px solid {color("border_light")};
        }}
    """


def style_delete_button() -> str:
    """QSS for outlined destructive buttons."""
    return f"""
        QPushButton {{
            color: {color("error")};
            border: 1px solid {color("error")};
            background-color: transparent;
            font-size: 14px;
            font-weight: 400;
            padding: 10px 24px;
            border-radius: {RADIUS_BUTTON}px;
            outline: none;
        }}
        QPushButton:hover, QPushButton:focus {{
            color: {color("error_hover")};
            border: 1px solid {color("error_hover")};
            background-color: rgba(255, 107, 114, 0.1);
        }}
        QPushButton:disabled {{
            color: {color("disabled_text")};
            border: 1px solid {color("border_light")};
        }}
    """


def style_outlined_primary_button() -> str:
    """QSS for outlined primary buttons."""
    return f"""
        QPushButton {{
            color: {color("primary")};
            border: 1px solid {color("primary")};
            background-color: transparent;
            font-size: 14px;
            font-weight: 400;
            padding: 10px 24px;
            border-radius: {RADIUS_BUTTON}px;
            outline: none;
        }}
        QPushButton:hover, QPushButton:focus {{
            color: {color("primary_light")};
            border: 1px solid {color("primary_light")};
            background-color: rgba(62, 121, 247, 0.1);
        }}
        QPushButton:disabled {{
            color: {color("disabled_text")};
            border: 1px solid {color("border_light")};
        }}
    """


def style_warning_button() -> str:
    """QSS for outlined warning/pause buttons."""
    return f"""
        QPushButton {{
            color: {color("warning")};
            border: 1px solid {color("warning")};
            background-color: transparent;
            font-size: 14px;
            font-weight: 400;
            padding: 10px 24px;
            border-radius: {RADIUS_BUTTON}px;
            outline: none;
        }}
        QPushButton:hover, QPushButton:focus {{
            color: {color("warning_hover")};
            border: 1px solid {color("warning_hover")};
            background-color: rgba(255, 197, 66, 0.1);
        }}
        QPushButton:disabled {{
            color: {color("disabled_text")};
            border: 1px solid {color("border_light")};
        }}
    """


def style_secondary_button() -> str:
    """QSS for secondary action buttons."""
    return f"""
        QPushButton {{
            background-color: transparent;
            color: {color("text_secondary")};
            border: 1px solid {color("border_light")};
            border-radius: {RADIUS_BUTTON}px;
            padding: 10px 24px;
            font-weight: 400;
            font-size: 14px;
            outline: none;
        }}
        QPushButton:hover, QPushButton:focus {{
            background-color: {color("hover_light")};
            border-color: {color("primary")};
            color: {color("primary")};
        }}
        QPushButton:pressed {{
            background-color: {color("border_light")};
        }}
        QPushButton:checked {{
            background-color: {color("primary")};
            border-color: {color("primary")};
            color: white;
        }}
        QPushButton:disabled {{
            color: {color("disabled_text")};
            border-color: {color("border_light")};
        }}
    """


def style_toggle_button() -> str:
    """QSS for ``setCheckable(True)`` toggle buttons.

    Same neutral-by-default styling as ``style_secondary_button``,
    but the ``:checked`` state uses an outlined-primary look (blue
    border + blue text on a tinted background) instead of the
    secondary-button solid blue fill.  This keeps "on" clearly
    distinct from "off" without making the toggle compete with the
    page's actual primary action button (e.g. Start Listening) for
    visual weight.
    """
    return f"""
        QPushButton {{
            background-color: transparent;
            color: {color("text_secondary")};
            border: 1px solid {color("border_light")};
            border-radius: {RADIUS_BUTTON}px;
            padding: 10px 24px;
            font-weight: 400;
            font-size: 14px;
            outline: none;
        }}
        QPushButton:hover, QPushButton:focus {{
            background-color: {color("hover_light")};
            border-color: {color("primary")};
            color: {color("primary")};
        }}
        QPushButton:pressed {{
            background-color: {color("border_light")};
        }}
        QPushButton:checked {{
            background-color: rgba(62, 121, 247, 0.1);
            border-color: {color("primary")};
            color: {color("primary")};
        }}
        QPushButton:disabled {{
            color: {color("disabled_text")};
            border-color: {color("border_light")};
        }}
    """


def style_scrollbar() -> str:
    """QSS for custom scrollbars."""
    return f"""
        QScrollBar:vertical {{
            border: none;
            background: transparent;
            width: 8px;
        }}
        QScrollBar::handle:vertical {{
            background: {color("scrollbar_handle")};
            border-radius: 4px;
        }}
        QScrollBar::handle:vertical:hover {{
            background: {color("scrollbar_hover")};
        }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
            height: 0px;
        }}
    """


def style_table() -> str:
    """QSS for data tables."""
    return f"""
        QTableWidget {{
            background-color: {color("component_bg")};
            alternate-background-color: {color("hover_light")};
            color: {color("text_primary")};
            gridline-color: {color("hover_light")};
            selection-background-color: rgba(62, 121, 247, 0.1);
            selection-color: {color("text_primary")};
            border: none;
            outline: none;
        }}
        QTableWidget::item {{
            padding: 12px;
            outline: none;
        }}
        QHeaderView {{
            border: none;
            background-color: {color("hover_light")};
        }}
        QHeaderView::section {{
            background-color: {color("hover_light")};
            padding: 12px;
            font-weight: 600;
            color: {color("text_secondary")};
            border: none;
            border-bottom: 1px solid {color("border_light")};
            border-right: 1px solid {color("border_light")};
            outline: none;
        }}
        QHeaderView::section:last {{
            border-right: none;
        }}
    """


def style_table_delete_button() -> str:
    """QSS for inline table delete buttons."""
    return f"""
        QPushButton {{
            color: {color("error")};
            background-color: transparent;
            font-size: 12px;
            font-weight: 600;
            border: none;
            outline: none;
        }}
        QPushButton:hover, QPushButton:focus {{
            text-decoration: underline;
        }}
        QPushButton:disabled {{
            color: {color("disabled_text")};
        }}
    """


def style_splitter() -> str:
    """Returns QSS for a QSplitter with a subtle draggable handle."""
    return f"""
        QSplitter::handle:horizontal {{
            width: 2px;
            background: {color("border_light")};
            border-radius: 1px;
            margin: 8px 0;
        }}
        QSplitter::handle:horizontal:hover {{
            background: {color("primary")};
        }}
    """


def style_banner(variant: str = "warning") -> str:
    """QSS for warning, error, info, or success banners with an icon."""
    color_map = {
        "warning": color("warning"),
        "error": color("error"),
        "info": color("primary"),
        "success": color("success"),
    }
    accent = color_map.get(variant, color("warning"))
    return f"""
        QFrame#Banner {{
            background-color: {color("component_bg")};
            border: 1px solid {accent};
            border-radius: {RADIUS_BUTTON}px;
            margin-bottom: {BANNER_MARGIN_BOTTOM}px;
        }}
        QLabel#BannerText, QLabel#BannerIcon, QTextBrowser#BannerText {{
            border: none;
            background: transparent;
        }}
        QLabel#BannerText {{
            font-size: {BANNER_FONT_SIZE}px;
            font-weight: 500;
            color: {accent};
        }}
    """
