"""Constants for office document processing (font preservation)."""

# Win32com Font object property names to save/restore
WIN32COM_FONT_PROPERTIES: tuple[str, ...] = (
    "Name",
    "Size",
    "Bold",
    "Italic",
    "Color",
    "Underline",
    "StrikeThrough",
)

# Win32com sentinel returned when formatting is mixed/undefined across a selection
WIN32COM_UNDEFINED: int = 9999999

# UNO character property names to save/restore
UNO_CHAR_PROPERTIES: tuple[str, ...] = (
    "CharFontName",
    "CharHeight",
    "CharWeight",
    "CharPosture",
    "CharColor",
    "CharUnderline",
    "CharStrikeout",
    "CharHighlight",
    "CharBackColor",
)
