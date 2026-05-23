"""Unit tests for file extension constants."""

from src.constants.files import (
    ALL_SUPPORTED_EXTENSIONS,
    FILE_FILTER,
    SUPPORTED_IMAGES,
    SUPPORTED_TEXT,
)


def test_extensions_lowercase_and_dotted() -> None:
    """All extensions must be lowercase and start with a dot."""
    for ext in ALL_SUPPORTED_EXTENSIONS:
        assert ext.startswith("."), f"{ext} missing leading dot"
        assert ext == ext.lower(), f"{ext} is not lowercase"


def test_no_duplicate_extensions() -> None:
    """No extension appears in more than one category."""
    all_exts = SUPPORTED_IMAGES + SUPPORTED_TEXT
    assert len(all_exts) == len(set(all_exts))


def test_all_supported_is_union() -> None:
    """ALL_SUPPORTED_EXTENSIONS is the union of the two lists."""
    expected = set(SUPPORTED_IMAGES + SUPPORTED_TEXT)
    assert set(ALL_SUPPORTED_EXTENSIONS) == expected


def test_common_formats_present() -> None:
    """Key formats expected by the app are included."""
    assert ".png" in SUPPORTED_IMAGES
    assert ".jpg" in SUPPORTED_IMAGES
    assert ".pdf" in SUPPORTED_TEXT
    assert ".docx" in SUPPORTED_TEXT
    assert ".txt" in SUPPORTED_TEXT
    assert ".csv" in SUPPORTED_TEXT
    assert ".epub" in SUPPORTED_TEXT


def test_file_filter_contains_all_extensions() -> None:
    """FILE_FILTER string references every supported extension."""
    for ext in ALL_SUPPORTED_EXTENSIONS:
        assert f"*{ext}" in FILE_FILTER


# ---------------------------------------------------------------------------
# FILE_FILTER structure
# ---------------------------------------------------------------------------


def test_file_filter_has_four_sections() -> None:
    """FILE_FILTER has four sections separated by ;;."""
    sections = FILE_FILTER.split(";;")
    assert len(sections) == 4  # noqa: PLR2004


def test_file_filter_ends_with_all_files() -> None:
    """Last section is the 'All Files (*)' fallback."""
    sections = FILE_FILTER.split(";;")
    assert sections[-1].strip() == "All Files (*)"


def test_file_filter_sections_named_correctly() -> None:
    """Each section has a descriptive label before the extension list."""
    assert "All Supported Files" in FILE_FILTER
    assert "Images" in FILE_FILTER
    assert "Documents" in FILE_FILTER


# ---------------------------------------------------------------------------
# Category validity
# ---------------------------------------------------------------------------


def test_each_category_is_non_empty() -> None:
    """Each extension category has at least one entry."""
    assert len(SUPPORTED_IMAGES) >= 1
    assert len(SUPPORTED_TEXT) >= 1


def test_image_extensions_are_image_formats() -> None:
    """SUPPORTED_IMAGES contains only image file extensions."""
    known_image_exts = {
        ".png",
        ".jpg",
        ".jpeg",
        ".bmp",
        ".webp",
        ".tiff",
        ".tif",
        ".gif",
        ".svg",
    }
    for ext in SUPPORTED_IMAGES:
        assert ext in known_image_exts, f"{ext} is not a known image format"


def test_text_extensions_include_office_formats() -> None:
    """SUPPORTED_TEXT includes both plain text and Office document formats."""
    plain_text = {".txt", ".md", ".csv", ".html", ".htm", ".json", ".xml", ".rtf"}
    office = {".docx", ".xlsx", ".pptx", ".doc", ".xls", ".ppt"}
    odf = {".odt", ".ods", ".odp"}

    text_set = set(SUPPORTED_TEXT)
    # At least one from each sub-category is present
    assert plain_text & text_set, "No plain text formats in SUPPORTED_TEXT"
    assert office & text_set, "No Office formats in SUPPORTED_TEXT"
    assert odf & text_set, "No ODF formats in SUPPORTED_TEXT"


def test_epub_in_supported_text() -> None:
    """EPUB format is in SUPPORTED_TEXT (key use case)."""
    assert ".epub" in SUPPORTED_TEXT


def test_pdf_in_supported_text() -> None:
    """PDF is in SUPPORTED_TEXT (translated via extract-overlay)."""
    assert ".pdf" in SUPPORTED_TEXT
    assert ".pdf" not in SUPPORTED_IMAGES


# ---------------------------------------------------------------------------
# FILE_FILTER section ordering
# ---------------------------------------------------------------------------


def test_file_filter_section_order() -> None:
    """FILE_FILTER sections appear in the correct order."""
    sections = FILE_FILTER.split(";;")
    # Extract the label (text before the opening parenthesis)
    labels = [s.split("(")[0].strip() for s in sections]
    assert labels[0] == "All Supported Files"
    assert labels[1] == "Images"
    assert labels[2] == "Documents"
    assert sections[-1].strip() == "All Files (*)"


# ---------------------------------------------------------------------------
# Specific format presence
# ---------------------------------------------------------------------------


def test_supported_text_has_legacy_office_formats() -> None:
    """Legacy Office formats (.doc, .xls, .ppt) are in SUPPORTED_TEXT."""
    assert ".doc" in SUPPORTED_TEXT
    assert ".xls" in SUPPORTED_TEXT
    assert ".ppt" in SUPPORTED_TEXT


def test_supported_text_has_htm_alias() -> None:
    """.htm is explicitly supported alongside .html."""
    assert ".htm" in SUPPORTED_TEXT


def test_supported_text_has_subtitle_formats() -> None:
    """Subtitle formats (.srt, .vtt, .ass, .ssa) are in SUPPORTED_TEXT."""
    assert ".srt" in SUPPORTED_TEXT
    assert ".vtt" in SUPPORTED_TEXT
    assert ".ass" in SUPPORTED_TEXT
    assert ".ssa" in SUPPORTED_TEXT


def test_supported_text_has_localization_formats() -> None:
    """Localization formats (.po, .pot, .xliff, .xlf) are in SUPPORTED_TEXT."""
    assert ".po" in SUPPORTED_TEXT
    assert ".pot" in SUPPORTED_TEXT
    assert ".xliff" in SUPPORTED_TEXT
    assert ".xlf" in SUPPORTED_TEXT


def test_supported_text_has_keyvalue_formats() -> None:
    """Key-value formats (.yaml, .yml, .properties, .strings) are in SUPPORTED_TEXT."""
    assert ".yaml" in SUPPORTED_TEXT
    assert ".yml" in SUPPORTED_TEXT
    assert ".properties" in SUPPORTED_TEXT
    assert ".strings" in SUPPORTED_TEXT


def test_supported_text_has_rst() -> None:
    """ReStructuredText format (.rst) is in SUPPORTED_TEXT."""
    assert ".rst" in SUPPORTED_TEXT
