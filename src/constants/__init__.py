"""Centralized access to all application constants."""

# Files
from .files import (
    ALL_SUPPORTED_EXTENSIONS as ALL_SUPPORTED_EXTENSIONS,
)
from .files import (
    EMBEDDED_IMAGE_EXTENSIONS as EMBEDDED_IMAGE_EXTENSIONS,
)
from .files import (
    FILE_FILTER as FILE_FILTER,
)
from .files import (
    SUPPORTED_IMAGES as SUPPORTED_IMAGES,
)
from .files import (
    SUPPORTED_MEDIA as SUPPORTED_MEDIA,
)
from .files import (
    SUPPORTED_TEXT as SUPPORTED_TEXT,
)
from .files import (
    SUPPORTED_VOICE_INPUT as SUPPORTED_VOICE_INPUT,
)

# History
from .history import (
    ACTIVE_STATUSES as ACTIVE_STATUSES,
)
from .history import (
    PROGRESS_COMPLETE as PROGRESS_COMPLETE,
)
from .history import (
    PROGRESS_IMAGE_LLM_WEIGHT as PROGRESS_IMAGE_LLM_WEIGHT,
)
from .history import (
    PROGRESS_INITIAL as PROGRESS_INITIAL,
)
from .history import (
    PROGRESS_LLM_DONE as PROGRESS_LLM_DONE,
)
from .history import (
    PROGRESS_OCR_DONE as PROGRESS_OCR_DONE,
)
from .history import (
    PROGRESS_TEXT_WEIGHT as PROGRESS_TEXT_WEIGHT,
)
from .history import (
    REPROCESSABLE_STATUSES as REPROCESSABLE_STATUSES,
)
from .history import (
    STATUS_DONE as STATUS_DONE,
)
from .history import (
    STATUS_FAILED as STATUS_FAILED,
)
from .history import (
    STATUS_PAUSED as STATUS_PAUSED,
)
from .history import (
    STATUS_PENDING as STATUS_PENDING,
)
from .history import (
    STATUS_TRANSLATING as STATUS_TRANSLATING,
)
from .history import (
    UNFINISHED_STATUSES as UNFINISHED_STATUSES,
)

# i18n - Core API
from .i18n import (
    UI_LANGUAGES as UI_LANGUAGES,
)
from .i18n import (
    current_language as current_language,
)
from .i18n import (
    language_changed as language_changed,
)
from .i18n import (
    set_language as set_language,
)
from .i18n import (
    tr as tr,
)

# Languages
from .languages import AVAILABLE_LANGUAGES as AVAILABLE_LANGUAGES
from .languages import LANGUAGES as LANGUAGES
from .languages import (
    format_language_picker_label as format_language_picker_label,
)
from .languages import (
    iter_languages_sorted_for_ui as iter_languages_sorted_for_ui,
)
from .languages import (
    localized_language_label as localized_language_label,
)

# LLM - Content Types
from .llm import (
    CONTENT_DATA_VALUES as CONTENT_DATA_VALUES,
)
from .llm import (
    CONTENT_EPUB as CONTENT_EPUB,
)
from .llm import (
    CONTENT_HTML as CONTENT_HTML,
)
from .llm import (
    CONTENT_MARKDOWN as CONTENT_MARKDOWN,
)
from .llm import (
    CONTENT_PDF as CONTENT_PDF,
)
from .llm import (
    CONTENT_PLAIN_TEXT as CONTENT_PLAIN_TEXT,
)
from .llm import (
    CONTENT_RTF as CONTENT_RTF,
)
from .llm import (
    CONTENT_XML as CONTENT_XML,
)
from .llm import (
    DOCUMENT_CONTENT_TYPES as DOCUMENT_CONTENT_TYPES,
)

# LLM - Providers & Models
from .llm import (
    GEMINI_MODELS as GEMINI_MODELS,
)
from .llm import (
    LLM_METHOD_CUSTOM as LLM_METHOD_CUSTOM,
)
from .llm import (
    LLM_METHOD_GEMINI as LLM_METHOD_GEMINI,
)
from .llm import (
    LLM_METHODS as LLM_METHODS,
)
from .llm import (
    TRANSLATION_BATCH_SIZE as TRANSLATION_BATCH_SIZE,
)
from .llm import (
    get_content_type as get_content_type,
)

# OCR
from .ocr import (
    EASYOCR_DEFAULT_LANGUAGES as EASYOCR_DEFAULT_LANGUAGES,
)
from .ocr import (
    GOOGLE_CLOUD_OCR_TIMEOUT as GOOGLE_CLOUD_OCR_TIMEOUT,
)
from .ocr import (
    OCR_HORIZONTAL_GAP_RATIO as OCR_HORIZONTAL_GAP_RATIO,
)
from .ocr import (
    OCR_METHOD_EASYOCR as OCR_METHOD_EASYOCR,
)
from .ocr import (
    OCR_METHOD_GOOGLE_CLOUD as OCR_METHOD_GOOGLE_CLOUD,
)
from .ocr import (
    OCR_METHOD_TESSERACT as OCR_METHOD_TESSERACT,
)
from .ocr import (
    OCR_METHODS as OCR_METHODS,
)
from .ocr import (
    OCR_VERTICAL_OVERLAP_RATIO as OCR_VERTICAL_OVERLAP_RATIO,
)
from .ocr import (
    TESSERACT_CONFIDENCE_SCALE as TESSERACT_CONFIDENCE_SCALE,
)
from .ocr import (
    TESSERACT_WORD_LEVEL as TESSERACT_WORD_LEVEL,
)

# Settings
from .settings import (
    SETTING_AUTO_CONVERT_LEGACY as SETTING_AUTO_CONVERT_LEGACY,
)
from .settings import (
    SETTING_AUTO_CONVERT_ODF as SETTING_AUTO_CONVERT_ODF,
)
from .settings import (
    SETTING_AUTO_REMOVE_HISTORY as SETTING_AUTO_REMOVE_HISTORY,
)
from .settings import (
    SETTING_GOOGLE_CLOUD_API_KEY as SETTING_GOOGLE_CLOUD_API_KEY,
)
from .settings import (
    SETTING_LAST_SOURCE_LANGUAGE as SETTING_LAST_SOURCE_LANGUAGE,
)
from .settings import (
    SETTING_LAST_TARGET_LANGUAGE as SETTING_LAST_TARGET_LANGUAGE,
)
from .settings import (
    SETTING_LIBREOFFICE_PATH as SETTING_LIBREOFFICE_PATH,
)
from .settings import (
    SETTING_LLM_CUSTOM_API_KEY as SETTING_LLM_CUSTOM_API_KEY,
)
from .settings import (
    SETTING_LLM_CUSTOM_ENDPOINT as SETTING_LLM_CUSTOM_ENDPOINT,
)
from .settings import (
    SETTING_LLM_CUSTOM_MODEL as SETTING_LLM_CUSTOM_MODEL,
)
from .settings import (
    SETTING_LLM_GEMINI_API_KEY as SETTING_LLM_GEMINI_API_KEY,
)
from .settings import (
    SETTING_LLM_GEMINI_MODEL as SETTING_LLM_GEMINI_MODEL,
)
from .settings import (
    SETTING_LLM_GEMINI_USE_VERTEX as SETTING_LLM_GEMINI_USE_VERTEX,
)
from .settings import (
    SETTING_LLM_METHOD as SETTING_LLM_METHOD,
)
from .settings import (
    SETTING_LLM_VERTEX_CREDENTIALS as SETTING_LLM_VERTEX_CREDENTIALS,
)
from .settings import (
    SETTING_LLM_VERTEX_LOCATION as SETTING_LLM_VERTEX_LOCATION,
)
from .settings import (
    SETTING_LLM_VERTEX_PROJECT as SETTING_LLM_VERTEX_PROJECT,
)
from .settings import (
    SETTING_OCR_METHOD as SETTING_OCR_METHOD,
)
from .settings import (
    SETTING_STORAGE_PATH as SETTING_STORAGE_PATH,
)
from .settings import (
    SETTING_THEME as SETTING_THEME,
)
from .settings import (
    SETTING_TRANSLATE_DOC_COMMENTS as SETTING_TRANSLATE_DOC_COMMENTS,
)
from .settings import (
    SETTING_TRANSLATE_DOC_IMAGES as SETTING_TRANSLATE_DOC_IMAGES,
)
from .settings import (
    SETTING_TRANSLATE_DOC_NOTES as SETTING_TRANSLATE_DOC_NOTES,
)
from .settings import (
    SETTING_TRANSLATE_DOC_SHAPES as SETTING_TRANSLATE_DOC_SHAPES,
)
from .settings import (
    SETTING_TRANSLATE_SHEET_NAMES as SETTING_TRANSLATE_SHEET_NAMES,
)
from .settings import (
    SETTING_UI_LANGUAGE as SETTING_UI_LANGUAGE,
)
from .settings import (
    VERTEX_DEFAULT_LOCATION as VERTEX_DEFAULT_LOCATION,
)
from .settings import (
    VERTEX_LOCATIONS as VERTEX_LOCATIONS,
)

# Shortcuts
from .shortcuts import SHORTCUTS as SHORTCUTS
from .shortcuts import Shortcut as Shortcut
from .shortcuts import find_conflicts as find_conflicts
from .shortcuts import get_default as get_default
from .shortcuts import get_shortcut as get_shortcut
from .shortcuts import iter_display_shortcuts as iter_display_shortcuts
from .shortcuts import reset_all_shortcuts as reset_all_shortcuts
from .shortcuts import reset_shortcut as reset_shortcut
from .shortcuts import set_shortcut as set_shortcut
from .shortcuts import shortcuts_changed as shortcuts_changed

# Theme - Core API
from .theme import (
    color as color,
)
from .theme import (
    current_theme as current_theme,
)
from .theme import (
    set_theme as set_theme,
)
from .theme import (
    style_banner as style_banner,
)

# Theme - Style generators
from .theme import (
    style_card_header as style_card_header,
)
from .theme import (
    style_card_light as style_card_light,
)
from .theme import (
    style_checkbox as style_checkbox,
)
from .theme import (
    style_danger_button as style_danger_button,
)
from .theme import (
    style_delete_button as style_delete_button,
)
from .theme import (
    style_input_field as style_input_field,
)
from .theme import (
    style_input_label as style_input_label,
)
from .theme import (
    style_link_button as style_link_button,
)
from .theme import (
    style_link_button_muted as style_link_button_muted,
)
from .theme import (
    style_list_widget as style_list_widget,
)
from .theme import (
    style_outlined_primary_button as style_outlined_primary_button,
)
from .theme import (
    style_page_header as style_page_header,
)
from .theme import (
    style_primary_button as style_primary_button,
)
from .theme import (
    style_radio_button as style_radio_button,
)
from .theme import (
    style_scrollbar as style_scrollbar,
)
from .theme import (
    style_secondary_button as style_secondary_button,
)
from .theme import (
    style_section_group as style_section_group,
)
from .theme import (
    style_section_title as style_section_title,
)
from .theme import (
    style_setting_combo as style_setting_combo,
)
from .theme import (
    style_setting_container as style_setting_container,
)
from .theme import (
    style_sidebar_list as style_sidebar_list,
)
from .theme import (
    style_splitter as style_splitter,
)
from .theme import (
    style_tab_widget as style_tab_widget,
)
from .theme import (
    style_table as style_table,
)
from .theme import (
    style_table_delete_button as style_table_delete_button,
)
from .theme import (
    style_toggle_button as style_toggle_button,
)
from .theme import (
    style_warning_button as style_warning_button,
)
from .theme import (
    theme_changed as theme_changed,
)

# UI - Assets & Layout
from .ui import (
    ALERT_CIRCLE_PATH as ALERT_CIRCLE_PATH,
)
from .ui import (
    ALERT_TRIANGLE_PATH as ALERT_TRIANGLE_PATH,
)
from .ui import (
    BANNER_FONT_SIZE as BANNER_FONT_SIZE,
)
from .ui import (
    BANNER_ICON_SIZE as BANNER_ICON_SIZE,
)
from .ui import (
    BANNER_LINE_SPACING as BANNER_LINE_SPACING,
)
from .ui import (
    BANNER_PADDING as BANNER_PADDING,
)
from .ui import (
    BANNER_SPACING as BANNER_SPACING,
)
from .ui import (
    BROWSE_BUTTON_WIDTH as BROWSE_BUTTON_WIDTH,
)
from .ui import (
    CHECK_CIRCLE_PATH as CHECK_CIRCLE_PATH,
)
from .ui import (
    CHECK_PATH as CHECK_PATH,
)
from .ui import (
    CHEVRON_DOWN_DISABLED_PATH as CHEVRON_DOWN_DISABLED_PATH,
)
from .ui import (
    CHEVRON_DOWN_PATH as CHEVRON_DOWN_PATH,
)
from .ui import (
    DROP_AREA_HEIGHT as DROP_AREA_HEIGHT,
)
from .ui import (
    EYE_OFF_PATH as EYE_OFF_PATH,
)
from .ui import (
    EYE_OFF_PRIMARY_PATH as EYE_OFF_PRIMARY_PATH,
)
from .ui import (
    EYE_PATH as EYE_PATH,
)
from .ui import (
    EYE_PRIMARY_PATH as EYE_PRIMARY_PATH,
)
from .ui import (
    FILE_ITEM_BADGE_SIZE as FILE_ITEM_BADGE_SIZE,
)
from .ui import (
    FILE_ITEM_HEIGHT as FILE_ITEM_HEIGHT,
)
from .ui import (
    FLAG_ICON_HEIGHT as FLAG_ICON_HEIGHT,
)
from .ui import (
    FLAG_ICON_WIDTH as FLAG_ICON_WIDTH,
)
from .ui import (
    FLAGS_DIR as FLAGS_DIR,
)
from .ui import (
    GLOSSARY_ACTION_COL_WIDTH as GLOSSARY_ACTION_COL_WIDTH,
)
from .ui import (
    GLOSSARY_DEFAULT_SPLITTER_SIZES as GLOSSARY_DEFAULT_SPLITTER_SIZES,
)
from .ui import (
    GLOSSARY_ENTRIES_PANEL_MIN_WIDTH as GLOSSARY_ENTRIES_PANEL_MIN_WIDTH,
)
from .ui import (
    GLOSSARY_SET_PANEL_MIN_WIDTH as GLOSSARY_SET_PANEL_MIN_WIDTH,
)
from .ui import (
    HEIGHT_CONTROL as HEIGHT_CONTROL,
)
from .ui import (
    HISTORY_COL_WIDTH as HISTORY_COL_WIDTH,
)
from .ui import (
    HISTORY_DATE_COL_WIDTH as HISTORY_DATE_COL_WIDTH,
)
from .ui import (
    INFO_PATH as INFO_PATH,
)
from .ui import (
    LABEL_PADDING_LEFT as LABEL_PADDING_LEFT,
)
from .ui import (
    LABEL_WIDTH as LABEL_WIDTH,
)
from .ui import (
    MARGIN_PAGE as MARGIN_PAGE,
)
from .ui import (
    MARGIN_SECTION as MARGIN_SECTION,
)
from .ui import (
    MARGIN_SUBSECTION as MARGIN_SUBSECTION,
)
from .ui import (
    MIN_COLUMN_WIDTH as MIN_COLUMN_WIDTH,
)
from .ui import (
    MIN_WINDOW_HEIGHT as MIN_WINDOW_HEIGHT,
)
from .ui import (
    MIN_WINDOW_WIDTH as MIN_WINDOW_WIDTH,
)
from .ui import (
    RADIUS_BUTTON as RADIUS_BUTTON,
)
from .ui import (
    SEARCH_DEBOUNCE_MS as SEARCH_DEBOUNCE_MS,
)
from .ui import (
    SIDEBAR_COLLAPSE_THRESHOLD as SIDEBAR_COLLAPSE_THRESHOLD,
)
from .ui import (
    SIDEBAR_COLLAPSED_WIDTH as SIDEBAR_COLLAPSED_WIDTH,
)
from .ui import (
    SIDEBAR_EXPAND_THRESHOLD as SIDEBAR_EXPAND_THRESHOLD,
)
from .ui import (
    SIDEBAR_WIDTH as SIDEBAR_WIDTH,
)
from .ui import (
    SPACING_PAGE as SPACING_PAGE,
)
from .ui import (
    SPACING_SECTION as SPACING_SECTION,
)
from .ui import (
    SPACING_SUBSECTION as SPACING_SUBSECTION,
)
from .ui import (
    SPINNER_FRAMES as SPINNER_FRAMES,
)
from .ui import (
    SPINNER_INTERVAL_MS as SPINNER_INTERVAL_MS,
)
from .ui import (
    SPLITTER_HANDLE_WIDTH as SPLITTER_HANDLE_WIDTH,
)
from .ui import (
    TOGGLE_BUTTON_WIDTH as TOGGLE_BUTTON_WIDTH,
)
from .ui import (
    TOGGLE_ICON_SIZE as TOGGLE_ICON_SIZE,
)
