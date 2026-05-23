"""Layout constants, asset paths, and typography settings.

Color palettes and QSS style generators live in ``src.constants.theme``.
"""

from pathlib import Path

# Path to assets
ASSETS_DIR = Path(__file__).parent.parent / "ui" / "assets"
CHEVRON_DOWN_PATH = (ASSETS_DIR / "chevron-down.svg").as_posix()
CHEVRON_DOWN_DISABLED_PATH = (ASSETS_DIR / "chevron-down-disabled.svg").as_posix()
CHECK_PATH = (ASSETS_DIR / "check.svg").as_posix()
EYE_PATH = (ASSETS_DIR / "eye.svg").as_posix()
EYE_OFF_PATH = (ASSETS_DIR / "eye-off.svg").as_posix()
EYE_PRIMARY_PATH = (ASSETS_DIR / "eye-primary.svg").as_posix()
EYE_OFF_PRIMARY_PATH = (ASSETS_DIR / "eye-off-primary.svg").as_posix()
ALERT_TRIANGLE_PATH = (ASSETS_DIR / "alert-triangle.svg").as_posix()
ALERT_CIRCLE_PATH = (ASSETS_DIR / "alert-circle.svg").as_posix()
CHECK_CIRCLE_PATH = (ASSETS_DIR / "check-circle.svg").as_posix()
INFO_PATH = (ASSETS_DIR / "info.svg").as_posix()
FLAGS_DIR = (ASSETS_DIR / "flags").as_posix()
FONTS_DIR = ASSETS_DIR / "fonts"

# Window and Layout
MIN_WINDOW_WIDTH = 700
MIN_WINDOW_HEIGHT = 450
SIDEBAR_WIDTH = 275
# Compact sidebar (icon-only) used when the window gets narrow.  80px clears
# the QListWidget's 24px horizontal padding on each side and still leaves
# enough room for a wide emoji glyph (e.g. 🎙️) without clipping.
SIDEBAR_COLLAPSED_WIDTH = 80
# Hysteresis-paired thresholds: collapse when the window shrinks below the
# first value, expand when it grows above the second.  The 80px gap stops
# the sidebar from flapping when the user drags the window edge near a
# single boundary.
SIDEBAR_COLLAPSE_THRESHOLD = 1100
SIDEBAR_EXPAND_THRESHOLD = 1180
RADIUS_BUTTON = 10

# Layout Constants
MARGIN_PAGE = 24
MARGIN_SECTION = 16
MARGIN_SUBSECTION = 12

SPACING_PAGE = 20
SPACING_SECTION = 20
SPACING_SUBSECTION = 16

LABEL_WIDTH = 220
LABEL_PADDING_LEFT = 80
HEIGHT_CONTROL = 42

# Banner
BANNER_PADDING = 12
BANNER_SPACING = 12
BANNER_ICON_SIZE = 20
BANNER_MARGIN_BOTTOM = 4
BANNER_FONT_SIZE = 14
BANNER_LINE_SPACING = 6

# Flag icon size (width × height) for language combo boxes
FLAG_ICON_WIDTH = 24
FLAG_ICON_HEIGHT = 18

# History table default column widths (px)
HISTORY_COL_WIDTH = 120
HISTORY_DATE_COL_WIDTH = 180

# Minimum width (px) for interactive table columns during drag-resize
MIN_COLUMN_WIDTH = 50

# Search debounce interval (ms) — used in glossary & history pages
SEARCH_DEBOUNCE_MS = 300

# Drop area height for file selection views
DROP_AREA_HEIGHT = 180

# FileItemWidget
FILE_ITEM_HEIGHT = 72
FILE_ITEM_BADGE_SIZE = 48

# Password toggle button
TOGGLE_ICON_SIZE = 20
TOGGLE_BUTTON_WIDTH = 40

# Browse button
BROWSE_BUTTON_WIDTH = 120

# Glossary page layout
GLOSSARY_SET_PANEL_MIN_WIDTH = 250
GLOSSARY_ENTRIES_PANEL_MIN_WIDTH = 350
GLOSSARY_ACTION_COL_WIDTH = 120
GLOSSARY_DEFAULT_SPLITTER_SIZES = [400, 800]
SPLITTER_HANDLE_WIDTH = 2

# Busy-state spinner frames shared by the sidebar and in-page buttons.
SPINNER_FRAMES: tuple[str, ...] = (
    "⠋",
    "⠙",
    "⠹",
    "⠸",
    "⠼",
    "⠴",
    "⠦",
    "⠧",
    "⠇",
    "⠏",
)
SPINNER_INTERVAL_MS = 100

# Typography & Rendering
FONT_SIZE_MIN = 4.0
FONT_SIZE_DEFAULT = 6.0
FONT_SIZE_STEP = 0.5  # Increment (pt) when iterating font sizes during fitting
FONT_SIZE_MAX_BOX_RATIO = 2.0  # Max font size as ratio of bounding-box height
