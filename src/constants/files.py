"""Constants for supported file types and extensions."""

# Image files supported by OCR
SUPPORTED_IMAGES = [".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tiff", ".tif"]

# PDF, text, office, subtitle, and localization files
SUPPORTED_TEXT = [
    ".pdf",
    ".txt",
    ".md",
    ".rst",
    ".csv",
    ".html",
    ".htm",
    ".xhtml",
    ".epub",
    ".json",
    ".xml",
    ".rtf",
    ".srt",
    ".vtt",
    ".ass",
    ".ssa",
    ".po",
    ".pot",
    ".xliff",
    ".xlf",
    ".yaml",
    ".yml",
    ".properties",
    ".strings",
    ".docx",
    ".xlsx",
    ".pptx",
    ".doc",
    ".xls",
    ".ppt",
    ".odt",
    ".ods",
    ".odp",
]

# Audio files supported for subtitle generation
SUPPORTED_AUDIO = [".mp3", ".wav", ".m4a", ".flac", ".ogg", ".aac", ".wma"]

# Video files supported for subtitle generation
SUPPORTED_VIDEO = [".mp4", ".webm", ".mkv", ".avi", ".mov", ".wmv"]

# Combined audio + video
SUPPORTED_MEDIA = SUPPORTED_AUDIO + SUPPORTED_VIDEO

# Subtitle/text files accepted as voice generation input
SUPPORTED_VOICE_INPUT = [".txt", ".srt", ".vtt", ".ass", ".ssa"]

# Extensions that may contain embedded images which would trigger OCR when
# ``SETTING_TRANSLATE_DOC_IMAGES`` is enabled. PDFs are included because
# scanned pages are rendered as images internally.
EMBEDDED_IMAGE_EXTENSIONS = [
    ".pdf",
    ".docx",
    ".pptx",
    ".xlsx",
    ".doc",
    ".ppt",
    ".xls",
    ".odt",
    ".odp",
    ".ods",
]

# Combined list of all supported extensions
ALL_SUPPORTED_EXTENSIONS = SUPPORTED_IMAGES + SUPPORTED_TEXT

# Filter string for QFileDialog
FILE_FILTER = (
    f"All Supported Files ({' '.join('*' + ext for ext in ALL_SUPPORTED_EXTENSIONS)});;"
    f"Images ({' '.join('*' + ext for ext in SUPPORTED_IMAGES)});;"
    f"Documents ({' '.join('*' + ext for ext in SUPPORTED_TEXT)});;"
    "All Files (*)"
)
