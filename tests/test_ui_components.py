"""Unit tests for reusable UI components."""

import configparser
from collections.abc import Generator
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QFrame,
    QLineEdit,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)
from pytestqt.qtbot import QtBot

from src.constants.ui import MARGIN_PAGE, MARGIN_SECTION, MARGIN_SUBSECTION
from src.ui.components import (
    CaseInsensitiveSortItem,
    DateTimeSortItem,
    ElidedLabel,
    FileDropWidget,
    FileItemWidget,
    ForegroundPreservingDelegate,
    HighlightDelegate,
    HoverIconButton,
    NumericalSortItem,
    _TableResizeFilter,
    create_banner,
    create_page_container,
    create_scrollable_container,
    create_section_group,
    create_setting_checkbox,
    create_setting_combo,
    create_setting_input,
    create_setting_path,
    create_table,
)


def test_elided_label_text(qtbot: QtBot) -> None:
    """Verify that ElidedLabel stores full text and handles updates."""
    label = ElidedLabel("This is a very long text that might need elision")
    qtbot.addWidget(label)

    assert label._full_text == "This is a very long text that might need elision"

    label.set_text("Short text")
    assert label._full_text == "Short text"


def test_elided_label_click(qtbot: QtBot) -> None:
    """Verify that ElidedLabel triggers callback on click."""
    clicked = False

    def on_click() -> None:
        """Mock click handler."""
        nonlocal clicked
        clicked = True

    label = ElidedLabel("Click me", clicked=on_click)
    qtbot.addWidget(label)

    qtbot.mouseClick(label, Qt.MouseButton.LeftButton)
    assert clicked is True


def test_create_section_group(qtbot: QtBot) -> None:
    """Verify create_section_group returns frame, layout, and label."""
    group, layout, label = create_section_group("Test Section")
    qtbot.addWidget(group)

    assert isinstance(group, QFrame)
    assert label.text() == "Test Section"

    # Verify explicit content margins
    margins = layout.contentsMargins()
    assert margins.left() == MARGIN_SUBSECTION
    assert margins.right() == MARGIN_SUBSECTION
    assert margins.top() == MARGIN_SECTION
    assert margins.bottom() == MARGIN_SECTION


def test_file_item_widget_init(qtbot: QtBot, tmp_path: Path) -> None:
    """Verify FileItemWidget displays correct information."""
    test_file = tmp_path / "test_document.pdf"
    test_file.write_text("dummy content")

    def mock_format_size(size: int) -> str:
        """Mock size formatter."""
        return "13 B"

    widget = FileItemWidget(str(test_file), mock_format_size)
    qtbot.addWidget(widget)

    assert widget.file_path == str(test_file)
    # Check if name label has correct text (it's an ElidedLabel)
    # Finding children by type
    labels = widget.findChildren(ElidedLabel)
    # First ElidedLabel should be the name
    assert labels[0]._full_text == "test_document.pdf"

    # Check extension badge
    # There are multiple labels, need to be specific if possible or check all
    # The badge is the first QLabel that isn't an ElidedLabel
    all_labels = widget.findChildren(pytest.importorskip("PySide6.QtWidgets").QLabel)
    badge = next(lbl for lbl in all_labels if not isinstance(lbl, ElidedLabel))
    assert badge.text() == "PDF"


def test_file_item_widget_remove_signal(qtbot: QtBot, tmp_path: Path) -> None:
    """Verify FileItemWidget emits remove_requested signal."""
    test_file = tmp_path / "test.txt"
    test_file.touch()

    widget = FileItemWidget(str(test_file), lambda x: "0 B")
    qtbot.addWidget(widget)

    # Correct way to test signal
    with qtbot.waitSignal(widget.remove_requested, timeout=1000):
        # Find the remove button (the one with ✕)
        btns = widget.findChildren(pytest.importorskip("PySide6.QtWidgets").QPushButton)
        del_btn = next(b for b in btns if b.text() == "✕")
        qtbot.mouseClick(del_btn, Qt.MouseButton.LeftButton)


def test_file_drop_widget_click_signal(qtbot: QtBot) -> None:
    """Verify FileDropWidget emits empty list on click."""
    widget = FileDropWidget()
    qtbot.addWidget(widget)

    with qtbot.waitSignal(widget.files_dropped, timeout=1000) as blocker:
        qtbot.mouseClick(widget, Qt.MouseButton.LeftButton)

    assert blocker.args[0] == []


def test_highlight_delegate_search_text(qtbot: QtBot) -> None:
    """Verify HighlightDelegate stores and clears search text."""
    table = QTableWidget(1, 1)
    qtbot.addWidget(table)

    delegate = HighlightDelegate(table)
    table.setItemDelegateForColumn(0, delegate)

    # Initially empty
    assert delegate.search_text == ""

    delegate.set_search_text("hello")
    assert delegate.search_text == "hello"

    delegate.set_search_text("")
    assert delegate.search_text == ""


def test_highlight_delegate_on_table(qtbot: QtBot) -> None:
    """Verify HighlightDelegate can be applied to a table column."""
    table = QTableWidget(2, 2)
    qtbot.addWidget(table)

    delegate = HighlightDelegate(table)
    table.setItemDelegateForColumn(0, delegate)

    # Populate table
    table.setItem(0, 0, QTableWidgetItem("Hello World"))
    table.setItem(1, 0, QTableWidgetItem("Goodbye World"))

    # Set search text and verify delegate is active
    delegate.set_search_text("World")
    assert table.itemDelegateForColumn(0) is delegate


def test_highlight_delegate_normalize_flag(qtbot: QtBot) -> None:
    """Verify HighlightDelegate stores the normalize flag."""
    table = QTableWidget(1, 1)
    qtbot.addWidget(table)

    # Default: normalize is False
    delegate_default = HighlightDelegate(table)
    assert delegate_default.normalize is False

    # Explicit: normalize is True
    delegate_norm = HighlightDelegate(table, normalize=True)
    assert delegate_norm.normalize is True


def test_highlight_delegate_normalized_has_match(qtbot: QtBot) -> None:
    """Verify normalized delegate detects accent-insensitive matches."""
    table = QTableWidget(1, 1)
    qtbot.addWidget(table)

    delegate = HighlightDelegate(table, normalize=True)
    delegate.set_search_text("cafe")

    # "café" should match "cafe" with normalization
    assert delegate._has_match("Café au lait") is True
    # "xin chao" should match "Xin Chào"
    delegate.set_search_text("xin chao")
    assert delegate._has_match("Xin Chào") is True


def test_highlight_delegate_normalized_find_spans(qtbot: QtBot) -> None:
    """Verify normalized delegate computes correct highlight spans."""
    table = QTableWidget(1, 1)
    qtbot.addWidget(table)

    delegate = HighlightDelegate(table, normalize=True)

    # Search "cafe" in "Café au lait" → should highlight positions 0-3 ("Café")
    delegate.set_search_text("cafe")
    spans = delegate._find_highlight_spans("Café au lait")
    assert spans == [(0, 4)]

    # Search "strasse" in "Straße" → should highlight positions 0-5 (entire word)
    delegate.set_search_text("strasse")
    spans = delegate._find_highlight_spans("Straße")
    assert spans == [(0, 6)]  # noqa: PLR2004


def test_highlight_delegate_normalized_merges_overlapping_spans(qtbot: QtBot) -> None:
    """Overlapping spans from multi-char expansion (ß→ss) are merged."""
    table = QTableWidget(1, 1)
    qtbot.addWidget(table)

    delegate = HighlightDelegate(table, normalize=True)

    # Search "s" in "Straße": ß expands to "ss" in normalized text.
    # Without merging, two matches at normalized positions 4 and 5
    # both map to original position 4, producing duplicate spans.
    delegate.set_search_text("s")
    spans = delegate._find_highlight_spans("Straße")
    # Should be 2 merged spans: "S" at (0,1) and "ß" at (4,5)
    assert spans == [(0, 1), (4, 5)]
    # No duplicates — (4,5) appears only once
    assert len(spans) == 2  # noqa: PLR2004


def test_highlight_delegate_normalized_empty_norm_search(qtbot: QtBot) -> None:
    """Search that normalizes to empty returns no match."""
    table = QTableWidget(1, 1)
    qtbot.addWidget(table)

    delegate = HighlightDelegate(table, normalize=True)

    # Combining acute accent normalizes to "" after stripping Mn
    delegate.set_search_text("\u0300")
    assert delegate._has_match("anything") is False
    assert delegate._find_highlight_spans("anything") == []


# ---------------------------------------------------------------------------
# CaseInsensitiveSortItem tests
# ---------------------------------------------------------------------------


def test_case_insensitive_sort_item_lowercase_vs_upper(qtbot: QtBot) -> None:
    """Case-insensitive: 'apple' < 'Banana' is True."""
    table = QTableWidget(1, 1)
    qtbot.addWidget(table)

    item_a = CaseInsensitiveSortItem("apple")
    item_b = CaseInsensitiveSortItem("Banana")
    assert (item_a < item_b) is True
    assert (item_b < item_a) is False


def test_case_insensitive_sort_item_same_text(qtbot: QtBot) -> None:
    """Same text in different case is not less-than."""
    table = QTableWidget(1, 1)
    qtbot.addWidget(table)

    item_a = CaseInsensitiveSortItem("Hello")
    item_b = CaseInsensitiveSortItem("hello")
    assert (item_a < item_b) is False
    assert (item_b < item_a) is False


def test_case_insensitive_sort_item_ordering(qtbot: QtBot) -> None:
    """Multiple items sort case-insensitively."""
    table = QTableWidget(1, 1)
    qtbot.addWidget(table)

    items = [
        CaseInsensitiveSortItem("Charlie"),
        CaseInsensitiveSortItem("alpha"),
        CaseInsensitiveSortItem("BRAVO"),
    ]
    sorted_items = sorted(items)
    assert [i.text() for i in sorted_items] == ["alpha", "BRAVO", "Charlie"]


def test_case_insensitive_sort_item_unicode(qtbot: QtBot) -> None:
    """Unicode text sorts correctly."""
    table = QTableWidget(1, 1)
    qtbot.addWidget(table)

    item_a = CaseInsensitiveSortItem("café")
    item_b = CaseInsensitiveSortItem("Dog")
    # "café" < "dog" (c < d)
    assert (item_a < item_b) is True


def test_case_insensitive_sort_item_empty(qtbot: QtBot) -> None:
    """Empty string sorts before non-empty."""
    table = QTableWidget(1, 1)
    qtbot.addWidget(table)

    item_empty = CaseInsensitiveSortItem("")
    item_text = CaseInsensitiveSortItem("A")
    assert (item_empty < item_text) is True
    assert (item_text < item_empty) is False


# ---------------------------------------------------------------------------
# Settings UI component helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def _mock_keyring(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mock keyring for settings tests that touch secure keys."""
    storage: dict[str, str] = {}
    monkeypatch.setattr(
        "keyring.set_password",
        lambda s, u, p: storage.__setitem__(f"{s}:{u}", p),
    )
    monkeypatch.setattr(
        "keyring.get_password",
        lambda s, u: storage.get(f"{s}:{u}"),
    )
    monkeypatch.setattr(
        "keyring.delete_password",
        lambda s, u: storage.pop(f"{s}:{u}", None),
    )


@pytest.fixture
def settings_env(
    monkeypatch: pytest.MonkeyPatch,
    _mock_keyring: None,
    tmp_path: Path,
) -> Generator[configparser.ConfigParser, None, None]:
    """Provides an isolated configparser environment for UI setting tests."""
    config_path = tmp_path / "test_settings.ini"
    monkeypatch.setattr(
        "src.utils.config_manager._get_config_path",
        lambda: config_path,
    )
    config = configparser.ConfigParser()
    config.optionxform = str
    yield config


def test_setting_input_loads_saved_value(
    qtbot: QtBot,
    settings_env: configparser.ConfigParser,
) -> None:
    """create_setting_input loads a previously saved value."""
    from src.utils.config_manager import save_setting  # noqa: PLC0415

    save_setting("test/input_key", "preloaded")

    container, field = create_setting_input("Label", "test/input_key")
    qtbot.addWidget(container)

    assert field.text() == "preloaded"


def test_setting_input_saves_on_change(
    qtbot: QtBot,
    settings_env: configparser.ConfigParser,
) -> None:
    """create_setting_input saves to config when text changes."""
    from src.utils.config_manager import load_setting  # noqa: PLC0415

    container, field = create_setting_input("Label", "test/save_key")
    qtbot.addWidget(container)

    field.setText("new_value")
    assert load_setting("test/save_key", "") == "new_value"


def test_setting_input_strips_whitespace(
    qtbot: QtBot,
    settings_env: configparser.ConfigParser,
) -> None:
    """create_setting_input strips leading/trailing whitespace on save."""
    from src.utils.config_manager import load_setting  # noqa: PLC0415

    container, field = create_setting_input("Label", "test/strip_key")
    qtbot.addWidget(container)

    field.setText("  trimmed  ")
    assert load_setting("test/strip_key", "") == "trimmed"


def test_setting_input_password_mode(
    qtbot: QtBot,
    settings_env: configparser.ConfigParser,
) -> None:
    """create_setting_input with is_password sets Password echo mode."""
    container, field = create_setting_input(
        "API Key",
        "test/pw_key",
        is_password=True,
    )
    qtbot.addWidget(container)

    assert field.echoMode() == QLineEdit.EchoMode.Password


def test_password_field_marked_with_secret_property(
    qtbot: QtBot,
    settings_env: configparser.ConfigParser,
) -> None:
    """Mark ``is_password`` fields with the ``aitSecret`` property.

    Lets a parent page find every secret field and re-mask it on hide.
    """
    container, field = create_setting_input(
        "API Key",
        "test/secret_marker_key",
        is_password=True,
    )
    qtbot.addWidget(container)

    assert field.property("aitSecret") is True
    assert callable(getattr(field, "_remask_secret", None))


def test_remask_secrets_resets_revealed_password_field(
    qtbot: QtBot,
    settings_env: configparser.ConfigParser,
) -> None:
    """remask_secrets flips revealed secret fields back to Password mode."""
    from src.ui.components import remask_secrets

    container, field = create_setting_input(
        "API Key",
        "test/remask_key",
        is_password=True,
    )
    qtbot.addWidget(container)

    # Simulate the user clicking the eye icon — flip echo to Normal.
    field.setEchoMode(QLineEdit.EchoMode.Normal)
    assert field.echoMode() == QLineEdit.EchoMode.Normal

    remask_secrets(container)

    assert field.echoMode() == QLineEdit.EchoMode.Password


def test_remask_secrets_ignores_non_password_fields(
    qtbot: QtBot,
    settings_env: configparser.ConfigParser,
) -> None:
    """remask_secrets must not touch plain (non-password) inputs."""
    from src.ui.components import remask_secrets

    container, field = create_setting_input(
        "Plain field",
        "test/plain_key",
    )
    qtbot.addWidget(container)

    # Plain fields default to Normal echo mode and have no marker.
    assert field.property("aitSecret") in (False, None)
    remask_secrets(container)
    assert field.echoMode() == QLineEdit.EchoMode.Normal


def test_setting_input_empty_default(
    qtbot: QtBot,
    settings_env: configparser.ConfigParser,
) -> None:
    """create_setting_input shows empty text when no value saved."""
    container, field = create_setting_input("Label", "test/absent_key")
    qtbot.addWidget(container)

    assert field.text() == ""


def test_setting_combo_loads_saved_value(
    qtbot: QtBot,
    settings_env: configparser.ConfigParser,
) -> None:
    """create_setting_combo selects previously saved value."""
    from src.utils.config_manager import save_setting  # noqa: PLC0415

    save_setting("test/combo_key", "Option B")

    container, combo = create_setting_combo(
        "Method",
        "test/combo_key",
        ["Option A", "Option B", "Option C"],
    )
    qtbot.addWidget(container)

    assert combo.currentText() == "Option B"


def test_setting_combo_saves_on_change(
    qtbot: QtBot,
    settings_env: configparser.ConfigParser,
) -> None:
    """create_setting_combo saves to config when selection changes."""
    from src.utils.config_manager import load_setting  # noqa: PLC0415

    container, combo = create_setting_combo(
        "Method",
        "test/combo_save",
        ["A", "B", "C"],
    )
    qtbot.addWidget(container)

    combo.setCurrentIndex(2)  # noqa: PLR2004
    assert load_setting("test/combo_save", "") == "C"


def test_setting_combo_unknown_saved_value(
    qtbot: QtBot,
    settings_env: configparser.ConfigParser,
) -> None:
    """Combo falls back to first item when saved value is not in items."""
    from src.utils.config_manager import save_setting  # noqa: PLC0415

    save_setting("test/combo_miss", "Nonexistent")

    container, combo = create_setting_combo(
        "Method",
        "test/combo_miss",
        ["Alpha", "Beta"],
    )
    qtbot.addWidget(container)

    # findText returns -1, so index stays at 0 (default)
    assert combo.currentText() == "Alpha"


def test_setting_checkbox_loads_saved_true(
    qtbot: QtBot,
    settings_env: configparser.ConfigParser,
) -> None:
    """create_setting_checkbox loads True state from config."""
    from src.utils.config_manager import save_setting  # noqa: PLC0415

    save_setting("test/check_key", True)

    container, checkbox = create_setting_checkbox(
        "Enable feature",
        "test/check_key",
        default=False,
    )
    qtbot.addWidget(container)

    assert checkbox.isChecked() is True


def test_setting_checkbox_loads_default_false(
    qtbot: QtBot,
    settings_env: configparser.ConfigParser,
) -> None:
    """create_setting_checkbox uses default when no value saved."""
    container, checkbox = create_setting_checkbox(
        "Enable feature",
        "test/check_absent",
        default=False,
    )
    qtbot.addWidget(container)

    assert checkbox.isChecked() is False


def test_setting_checkbox_saves_on_toggle(
    qtbot: QtBot,
    settings_env: configparser.ConfigParser,
) -> None:
    """create_setting_checkbox saves to config when toggled."""
    from src.utils.config_manager import load_setting  # noqa: PLC0415

    container, checkbox = create_setting_checkbox(
        "Auto-save",
        "test/check_save",
        default=False,
    )
    qtbot.addWidget(container)

    checkbox.setChecked(True)
    assert load_setting("test/check_save", False) is True

    checkbox.setChecked(False)
    assert load_setting("test/check_save", True) is False


def test_setting_combo_single_item(
    qtbot: QtBot,
    settings_env: configparser.ConfigParser,
) -> None:
    """Combo with a single item selects it by default."""
    container, combo = create_setting_combo(
        "Only",
        "test/combo_single",
        ["OnlyOption"],
    )
    qtbot.addWidget(container)

    assert combo.currentText() == "OnlyOption"
    assert combo.count() == 1


def test_setting_input_unicode_value(
    qtbot: QtBot,
    settings_env: configparser.ConfigParser,
) -> None:
    """create_setting_input handles Unicode values correctly."""
    from src.utils.config_manager import load_setting, save_setting  # noqa: PLC0415

    save_setting("test/unicode_key", "日本語のテスト")

    container, field = create_setting_input("Label", "test/unicode_key")
    qtbot.addWidget(container)

    assert field.text() == "日本語のテスト"
    # Change to another unicode value
    field.setText("Straße Café")
    assert load_setting("test/unicode_key", "") == "Straße Café"


# ---------------------------------------------------------------------------
# NumericalSortItem tests
# ---------------------------------------------------------------------------


def test_numerical_sort_item_numeric_ordering(qtbot: QtBot) -> None:
    """NumericalSortItem uses float value for comparison, not text."""
    table = QTableWidget(1, 1)
    qtbot.addWidget(table)

    item_small = NumericalSortItem("1", 1.0)
    item_large = NumericalSortItem("10", 10.0)
    assert (item_small < item_large) is True
    assert (item_large < item_small) is False


def test_numerical_sort_item_equal_values(qtbot: QtBot) -> None:
    """Items with equal values are not less-than each other."""
    table = QTableWidget(1, 1)
    qtbot.addWidget(table)

    item_a = NumericalSortItem("5", 5.0)
    item_b = NumericalSortItem("5", 5.0)
    assert (item_a < item_b) is False
    assert (item_b < item_a) is False


def test_numerical_sort_item_negative_values(qtbot: QtBot) -> None:
    """Negative float values sort correctly."""
    table = QTableWidget(1, 1)
    qtbot.addWidget(table)

    item_neg = NumericalSortItem("-5", -5.0)
    item_zero = NumericalSortItem("0", 0.0)
    item_pos = NumericalSortItem("3", 3.0)
    assert (item_neg < item_zero) is True
    assert (item_zero < item_pos) is True
    assert (item_pos < item_neg) is False


def test_numerical_sort_item_multi_ordering(qtbot: QtBot) -> None:
    """Multiple NumericalSortItems sort by numeric value not text."""
    table = QTableWidget(1, 1)
    qtbot.addWidget(table)

    # Text-alphabetical order would be: "10" < "2" < "30", but numerically: 2 < 10 < 30
    items = [
        NumericalSortItem("30", 30.0),
        NumericalSortItem("2", 2.0),
        NumericalSortItem("10", 10.0),
    ]
    sorted_items = sorted(items)
    assert [i.text() for i in sorted_items] == ["2", "10", "30"]


def test_numerical_sort_item_falls_back_for_plain_item(qtbot: QtBot) -> None:
    """Falls back to super().__lt__() when compared with a plain QTableWidgetItem."""
    table = QTableWidget(1, 1)
    qtbot.addWidget(table)

    # Comparison with a plain item does not raise
    num_item = NumericalSortItem("abc", 1.0)
    plain_item = QTableWidgetItem("xyz")
    # The call should not raise; result type is bool
    result = num_item < plain_item
    assert isinstance(result, bool)


# ---------------------------------------------------------------------------
# DateTimeSortItem tests
# ---------------------------------------------------------------------------


def test_datetime_sort_item_sorts_by_iso_key(qtbot: QtBot) -> None:
    """DateTimeSortItem compares by ISO key, not display text."""
    table = QTableWidget(1, 1)
    qtbot.addWidget(table)

    # Display text is locale-formatted (would sort wrong lexicographically)
    item_feb = DateTimeSortItem("28/2/2026", "2026-02-28 10:00:00")
    item_mar = DateTimeSortItem("1/3/2026", "2026-03-01 09:00:00")
    assert item_feb < item_mar


def test_datetime_sort_item_equal_keys(qtbot: QtBot) -> None:
    """Items with the same ISO key are not less-than each other."""
    table = QTableWidget(1, 1)
    qtbot.addWidget(table)

    item_a = DateTimeSortItem("display A", "2026-01-15 12:00:00")
    item_b = DateTimeSortItem("display B", "2026-01-15 12:00:00")
    assert not (item_a < item_b)
    assert not (item_b < item_a)


def test_datetime_sort_item_descending_order(qtbot: QtBot) -> None:
    """Newer dates sort after older dates."""
    table = QTableWidget(1, 1)
    qtbot.addWidget(table)

    items = [
        DateTimeSortItem("1/3/2026", "2026-03-01 08:00:00"),
        DateTimeSortItem("28/2/2026", "2026-02-28 10:00:00"),
        DateTimeSortItem("26/2/2026", "2026-02-26 15:30:00"),
    ]
    sorted_items = sorted(items)
    assert [i.iso_key for i in sorted_items] == [
        "2026-02-26 15:30:00",
        "2026-02-28 10:00:00",
        "2026-03-01 08:00:00",
    ]


def test_datetime_sort_item_fallback_for_plain_item(qtbot: QtBot) -> None:
    """Falls back to super().__lt__() when compared with a plain QTableWidgetItem."""
    table = QTableWidget(1, 1)
    qtbot.addWidget(table)

    dt_item = DateTimeSortItem("1/3/2026", "2026-03-01 08:00:00")
    plain_item = QTableWidgetItem("xyz")
    result = dt_item < plain_item
    assert isinstance(result, bool)


# ---------------------------------------------------------------------------
# create_scrollable_container tests
# ---------------------------------------------------------------------------


def test_create_scrollable_container_returns_scroll_area(qtbot: QtBot) -> None:
    """create_scrollable_container wraps widget in a QScrollArea."""
    from PySide6.QtWidgets import QWidget  # noqa: PLC0415

    inner = QWidget()
    scroll = create_scrollable_container(inner)
    qtbot.addWidget(scroll)

    assert isinstance(scroll, QScrollArea)
    assert scroll.widgetResizable() is True
    assert scroll.frameShape() == QFrame.Shape.NoFrame


def test_create_scrollable_container_widget_is_set(qtbot: QtBot) -> None:
    """The inner widget is accessible via widget()."""
    from PySide6.QtWidgets import QWidget  # noqa: PLC0415

    inner = QWidget()
    scroll = create_scrollable_container(inner)
    qtbot.addWidget(scroll)

    assert scroll.widget() is inner


# ---------------------------------------------------------------------------
# create_page_container tests
# ---------------------------------------------------------------------------


def test_create_page_container_returns_widget_and_layout(qtbot: QtBot) -> None:
    """create_page_container returns (QWidget, QVBoxLayout)."""
    from PySide6.QtWidgets import QWidget  # noqa: PLC0415

    page, layout = create_page_container("My Page")
    qtbot.addWidget(page)

    assert isinstance(page, QWidget)
    assert isinstance(layout, QVBoxLayout)


def test_create_page_container_has_apply_theme(qtbot: QtBot) -> None:
    """create_page_container attaches apply_theme() to the page widget."""
    page, _ = create_page_container("Title")
    qtbot.addWidget(page)

    assert hasattr(page, "apply_theme")
    assert callable(page.apply_theme)
    # Calling it should not raise
    page.apply_theme()


def test_create_page_container_header_text_in_children(qtbot: QtBot) -> None:
    """The header label with the given title is added to the layout."""
    from PySide6.QtWidgets import QLabel  # noqa: PLC0415

    page, _ = create_page_container("Test Title")
    qtbot.addWidget(page)

    labels = page.findChildren(QLabel)
    texts = [lbl.text() for lbl in labels]
    assert "Test Title" in texts


def test_create_page_container_with_tr_key_has_apply_language(qtbot: QtBot) -> None:
    """When tr_key is provided, apply_language() is attached."""
    page, _ = create_page_container("Title", tr_key="btn.ok")
    qtbot.addWidget(page)

    assert hasattr(page, "apply_language")
    assert callable(page.apply_language)
    page.apply_language()  # Should not raise


# ---------------------------------------------------------------------------
# create_table tests
# ---------------------------------------------------------------------------


def test_create_table_returns_table_widget(qtbot: QtBot) -> None:
    """create_table returns a QTableWidget instance."""
    table = create_table(["Name", "Size", "Status"])
    qtbot.addWidget(table)

    assert isinstance(table, QTableWidget)


def test_create_table_column_count_matches_headers(qtbot: QtBot) -> None:
    """Column count equals the number of header strings."""
    headers = ["Col A", "Col B", "Col C", "Col D"]
    table = create_table(headers)
    qtbot.addWidget(table)

    assert table.columnCount() == len(headers)


def test_create_table_sorting_enabled(qtbot: QtBot) -> None:
    """Sorting is enabled by default."""
    table = create_table(["Name"])
    qtbot.addWidget(table)

    assert table.isSortingEnabled() is True


def test_create_table_vertical_header_hidden(qtbot: QtBot) -> None:
    """Vertical header (row numbers) is hidden."""
    table = create_table(["Name"])
    qtbot.addWidget(table)

    assert table.verticalHeader().isVisible() is False


def test_create_table_starts_with_zero_rows(qtbot: QtBot) -> None:
    """Table starts empty (zero rows)."""
    table = create_table(["Name", "Value"])
    qtbot.addWidget(table)

    assert table.rowCount() == 0


def test_create_table_custom_column_widths(qtbot: QtBot) -> None:
    """column_widths parameter sets fixed pixel widths for specified columns."""
    table = create_table(["A", "B", "C"], column_widths={1: 120, 2: 80})
    qtbot.addWidget(table)

    assert table.columnWidth(1) == 120  # noqa: PLR2004
    assert table.columnWidth(2) == 80  # noqa: PLR2004


def test_create_table_header_labels(qtbot: QtBot) -> None:
    """Header labels are set correctly."""
    headers = ["File", "Size", "Date"]
    table = create_table(headers)
    qtbot.addWidget(table)

    for col, label in enumerate(headers):
        assert table.horizontalHeaderItem(col).text() == label


# ---------------------------------------------------------------------------
# create_banner tests
# ---------------------------------------------------------------------------


def test_create_banner_returns_frame_and_label(qtbot: QtBot) -> None:
    """create_banner returns a (QFrame, QLabel) tuple."""
    from PySide6.QtWidgets import QLabel  # noqa: PLC0415

    frame, label = create_banner("Something went wrong", variant="error")
    qtbot.addWidget(frame)

    assert isinstance(frame, QFrame)
    assert isinstance(label, QLabel)


def test_create_banner_text_is_set(qtbot: QtBot) -> None:
    """The text label contains the initial message."""
    _, label = create_banner("Upload failed", variant="error")
    assert label.text() == "Upload failed"


def test_create_banner_all_variants_do_not_raise(qtbot: QtBot) -> None:
    """All four variant values produce a QFrame without errors."""
    for variant in ("warning", "error", "success", "info"):
        frame, _ = create_banner("msg", variant=variant)
        qtbot.addWidget(frame)
        assert isinstance(frame, QFrame)


def test_create_banner_unknown_variant_falls_back(qtbot: QtBot) -> None:
    """Unknown variant falls back to warning icon (no exception raised)."""
    frame, label = create_banner("msg", variant="unknown_variant")
    qtbot.addWidget(frame)
    assert isinstance(frame, QFrame)
    assert label.text() == "msg"


def test_create_banner_has_apply_theme(qtbot: QtBot) -> None:
    """create_banner attaches apply_theme() to the returned frame."""
    frame, _ = create_banner("msg", variant="info")
    qtbot.addWidget(frame)

    assert hasattr(frame, "apply_theme")
    assert callable(frame.apply_theme)
    frame.apply_theme()  # Should not raise


def test_create_banner_with_tr_key_has_apply_language(qtbot: QtBot) -> None:
    """When tr_key is provided, apply_language() is attached to frame."""
    frame, _ = create_banner("", variant="info", tr_key="btn.ok")
    qtbot.addWidget(frame)

    assert hasattr(frame, "apply_language")
    assert callable(frame.apply_language)
    frame.apply_language()  # Should not raise


def test_create_banner_empty_text(qtbot: QtBot) -> None:
    """Banner with empty text starts with empty label."""
    _, label = create_banner("", variant="warning")
    assert label.text() == ""


# ---------------------------------------------------------------------------
# HoverIconButton tests
# ---------------------------------------------------------------------------


def test_hover_icon_button_sets_normal_icon(qtbot: QtBot) -> None:
    """HoverIconButton starts with the normal icon set."""
    # Use empty paths — QIcon handles missing files gracefully
    btn = HoverIconButton("", "")
    qtbot.addWidget(btn)

    # After init the icon should be the normal (non-hover) icon
    assert btn.icon() is not None  # QIcon object exists
    assert btn.normal_icon is not None
    assert btn.hover_icon is not None


def test_hover_icon_button_set_icons_updates(qtbot: QtBot) -> None:
    """set_icons() replaces the normal and hover icon references."""
    btn = HoverIconButton("path_a", "path_b")
    qtbot.addWidget(btn)

    btn.set_icons("path_c", "path_d")
    # The icons are QIcon objects; verify they were re-created (not the original ones)
    # We can't easily compare QIcon objects, so just ensure no exception is raised
    # and the button still has normal/hover icon references
    assert btn.normal_icon is not None
    assert btn.hover_icon is not None


# ---------------------------------------------------------------------------
# create_setting_path tests
# ---------------------------------------------------------------------------


def test_create_setting_path_returns_container_and_elided_label(
    qtbot: QtBot,
    settings_env: configparser.ConfigParser,
) -> None:
    """create_setting_path returns (QWidget, ElidedLabel)."""
    from PySide6.QtWidgets import QWidget  # noqa: PLC0415

    container, path_label = create_setting_path("Output", "test/path_key")
    qtbot.addWidget(container)

    assert isinstance(container, QWidget)
    assert isinstance(path_label, ElidedLabel)


def test_create_setting_path_loads_saved_value(
    qtbot: QtBot,
    settings_env: configparser.ConfigParser,
) -> None:
    """create_setting_path shows the previously saved path."""
    from src.utils.config_manager import save_setting  # noqa: PLC0415

    save_setting("test/path_load", "/saved/output/dir")
    _, path_label = create_setting_path("Output", "test/path_load")

    assert path_label._full_text == "/saved/output/dir"


def test_create_setting_path_has_draw_border(
    qtbot: QtBot,
    settings_env: configparser.ConfigParser,
) -> None:
    """The ElidedLabel in create_setting_path has draw_border=True (mouse tracking)."""
    _, path_label = create_setting_path("Storage", "test/path_border")
    assert path_label.draw_border is True
    assert path_label.hasMouseTracking() is True


# ---------------------------------------------------------------------------
# ElidedLabel edge cases
# ---------------------------------------------------------------------------


def test_elided_label_no_callback_no_pointing_cursor(qtbot: QtBot) -> None:
    """ElidedLabel without a callback does not set PointingHandCursor."""
    label = ElidedLabel("no callback")
    qtbot.addWidget(label)

    assert label.cursor().shape() != Qt.CursorShape.PointingHandCursor


def test_elided_label_with_callback_sets_pointing_cursor(qtbot: QtBot) -> None:
    """ElidedLabel with a callback sets PointingHandCursor."""
    label = ElidedLabel("clickable", clicked=lambda: None)
    qtbot.addWidget(label)

    assert label.cursor().shape() == Qt.CursorShape.PointingHandCursor


def test_elided_label_draw_border_enables_mouse_tracking(qtbot: QtBot) -> None:
    """ElidedLabel with draw_border=True enables mouse tracking."""
    label = ElidedLabel("border", draw_border=True)
    qtbot.addWidget(label)

    assert label.hasMouseTracking() is True


def test_elided_label_no_draw_border_no_mouse_tracking(qtbot: QtBot) -> None:
    """ElidedLabel without draw_border does not enable mouse tracking."""
    label = ElidedLabel("no border")
    qtbot.addWidget(label)

    # Default QLabel does not have mouse tracking unless explicitly set
    assert label.hasMouseTracking() is False


# ---------------------------------------------------------------------------
# HighlightDelegate._has_match — non-normalize path
# ---------------------------------------------------------------------------


def test_highlight_delegate_plain_has_match_case_insensitive(qtbot: QtBot) -> None:
    """Non-normalized delegate matches case-insensitively."""
    table = QTableWidget(1, 1)
    qtbot.addWidget(table)

    delegate = HighlightDelegate(table, normalize=False)
    delegate.set_search_text("hello")

    assert delegate._has_match("Hello World") is True
    assert delegate._has_match("HELLO") is True
    assert delegate._has_match("say hello") is True


def test_highlight_delegate_plain_no_match(qtbot: QtBot) -> None:
    """Non-normalized delegate returns False when search text is absent."""
    table = QTableWidget(1, 1)
    qtbot.addWidget(table)

    delegate = HighlightDelegate(table, normalize=False)
    delegate.set_search_text("xyz")

    assert delegate._has_match("Hello World") is False


def test_highlight_delegate_plain_empty_search_always_matches(qtbot: QtBot) -> None:
    """Empty search string matches everything (empty string is in every string)."""
    table = QTableWidget(1, 1)
    qtbot.addWidget(table)

    delegate = HighlightDelegate(table, normalize=False)
    delegate.set_search_text("")

    # "" is in every string by Python's definition
    assert delegate._has_match("anything") is True


def test_highlight_delegate_plain_find_spans(qtbot: QtBot) -> None:
    """Non-normalized _find_highlight_spans returns correct span positions."""
    table = QTableWidget(1, 1)
    qtbot.addWidget(table)

    delegate = HighlightDelegate(table, normalize=False)
    delegate.set_search_text("World")

    spans = delegate._find_highlight_spans("Hello World")
    assert spans == [(6, 11)]  # noqa: PLR2004


def test_highlight_delegate_plain_multiple_spans(qtbot: QtBot) -> None:
    """Non-normalized delegate finds all occurrences in a string."""
    table = QTableWidget(1, 1)
    qtbot.addWidget(table)

    delegate = HighlightDelegate(table, normalize=False)
    delegate.set_search_text("ab")

    spans = delegate._find_highlight_spans("ab_AB_ab")
    # Matches at 0-2, 3-5, 6-8 (case-insensitive)
    assert len(spans) == 3  # noqa: PLR2004


# ---------------------------------------------------------------------------
# FileItemWidget edge cases
# ---------------------------------------------------------------------------


def test_file_item_widget_apply_theme_does_not_raise(
    qtbot: QtBot,
    tmp_path: Path,
) -> None:
    """Calling apply_theme() on FileItemWidget does not raise."""
    test_file = tmp_path / "test.txt"
    test_file.touch()
    widget = FileItemWidget(str(test_file), lambda x: "0 B")
    qtbot.addWidget(widget)

    widget.apply_theme()  # Should not raise


def test_file_item_widget_apply_language_updates_button(
    qtbot: QtBot,
    tmp_path: Path,
) -> None:
    """apply_language() updates the open button text."""
    from src.constants.i18n import tr  # noqa: PLC0415

    test_file = tmp_path / "test.txt"
    test_file.touch()
    widget = FileItemWidget(str(test_file), lambda x: "0 B")
    qtbot.addWidget(widget)

    widget.apply_language()
    assert widget.open_btn.text() == tr("btn.view")


def test_file_item_widget_badge_truncates_long_extension(
    qtbot: QtBot,
    tmp_path: Path,
) -> None:
    """Badge truncates extension to 4 chars max."""
    test_file = tmp_path / "test.extra_long"
    test_file.touch()
    widget = FileItemWidget(str(test_file), lambda x: "0 B")
    qtbot.addWidget(widget)

    assert len(widget.badge.text()) <= 4  # noqa: PLR2004


def test_file_item_widget_nonexistent_file_shows_unknown_size(
    qtbot: QtBot,
) -> None:
    """FileItemWidget with non-existent file shows 'unknown size' text."""
    from src.constants.i18n import tr  # noqa: PLC0415

    widget = FileItemWidget("/nonexistent/file.txt", lambda x: "0 B")
    qtbot.addWidget(widget)

    # File stat fails → size_label shows tr("files.unknown_size")
    assert widget.size_label.text() == tr("files.unknown_size")


def test_file_item_widget_no_extension_shows_fallback_badge(
    qtbot: QtBot,
    tmp_path: Path,
) -> None:
    """FileItemWidget with no file extension shows localized fallback badge."""
    from src.constants.i18n import tr  # noqa: PLC0415

    test_file = tmp_path / "Makefile"
    test_file.touch()
    widget = FileItemWidget(str(test_file), lambda x: "0 B")
    qtbot.addWidget(widget)

    # Badge should show tr("files.no_extension") (truncated to 4 chars)
    expected = tr("files.no_extension")[:4]
    assert widget.badge.text() == expected


# ---------------------------------------------------------------------------
# FileDropWidget edge cases
# ---------------------------------------------------------------------------


def test_file_drop_widget_apply_theme_does_not_raise(qtbot: QtBot) -> None:
    """Calling apply_theme() on FileDropWidget does not raise."""
    widget = FileDropWidget()
    qtbot.addWidget(widget)

    widget.apply_theme()


def test_file_drop_widget_apply_language_does_not_raise(qtbot: QtBot) -> None:
    """Calling apply_language() on FileDropWidget does not raise."""
    widget = FileDropWidget()
    qtbot.addWidget(widget)

    widget.apply_language()


def test_file_drop_widget_accepts_drops(qtbot: QtBot) -> None:
    """FileDropWidget has acceptDrops enabled."""
    widget = FileDropWidget()
    qtbot.addWidget(widget)

    assert widget.acceptDrops() is True


# ---------------------------------------------------------------------------
# HoverIconButton — enterEvent / leaveEvent icon changes
# ---------------------------------------------------------------------------


def test_hover_icon_button_enter_leave_changes_icon(
    qtbot: QtBot,
    tmp_path: Path,
) -> None:
    """Enter/leave events switch between normal and hover icons."""
    from PySide6.QtCore import QEvent, QPoint  # noqa: PLC0415
    from PySide6.QtGui import QEnterEvent, QPixmap  # noqa: PLC0415

    # Create two distinct 1x1 PNGs so QIcons have different cacheKeys
    normal_file = tmp_path / "normal.png"
    hover_file = tmp_path / "hover.png"
    pn = QPixmap(1, 1)
    pn.fill(Qt.GlobalColor.red)
    pn.save(str(normal_file))
    ph = QPixmap(1, 1)
    ph.fill(Qt.GlobalColor.blue)
    ph.save(str(hover_file))

    btn = HoverIconButton(str(normal_file), str(hover_file))
    qtbot.addWidget(btn)

    normal_key = btn.normal_icon.cacheKey()
    hover_key = btn.hover_icon.cacheKey()
    assert normal_key != hover_key

    # Initially shows normal icon
    assert btn.icon().cacheKey() == normal_key

    # Simulate mouse enter
    pos = QPoint(5, 5)
    enter_event = QEnterEvent(pos, pos, pos)
    btn.enterEvent(enter_event)
    assert btn.icon().cacheKey() == hover_key

    # Simulate mouse leave
    leave_event = QEvent(QEvent.Type.Leave)
    btn.leaveEvent(leave_event)
    assert btn.icon().cacheKey() == normal_key


# ---------------------------------------------------------------------------
# create_setting_path — apply_theme / apply_language
# ---------------------------------------------------------------------------


def test_create_setting_path_apply_theme_does_not_raise(
    qtbot: QtBot,
    settings_env: configparser.ConfigParser,
) -> None:
    """apply_theme() on create_setting_path container does not raise."""
    container, _ = create_setting_path("Output", "test/path_theme")
    qtbot.addWidget(container)

    container.apply_theme()  # Should not raise


def test_create_setting_path_apply_language_does_not_raise(
    qtbot: QtBot,
    settings_env: configparser.ConfigParser,
) -> None:
    """apply_language() on create_setting_path container does not raise."""
    container, _ = create_setting_path("Output", "test/path_lang")
    qtbot.addWidget(container)

    container.apply_language()  # Should not raise


# ---------------------------------------------------------------------------
# create_table — additional properties
# ---------------------------------------------------------------------------


def test_create_table_selection_behavior_is_select_rows(qtbot: QtBot) -> None:
    """Table uses row-based selection."""
    table = create_table(["A", "B"])
    qtbot.addWidget(table)

    assert table.selectionBehavior() == QTableWidget.SelectionBehavior.SelectRows


def test_create_table_alternating_row_colors_enabled(qtbot: QtBot) -> None:
    """Table has alternating row colors enabled."""
    table = create_table(["A"])
    qtbot.addWidget(table)

    assert table.alternatingRowColors() is True


def test_create_table_grid_hidden(qtbot: QtBot) -> None:
    """Table grid lines are hidden."""
    table = create_table(["A"])
    qtbot.addWidget(table)

    assert table.showGrid() is False


def test_create_table_pointing_hand_cursor(qtbot: QtBot) -> None:
    """Table uses pointing hand cursor."""
    table = create_table(["A"])
    qtbot.addWidget(table)

    assert table.cursor().shape() == Qt.CursorShape.PointingHandCursor


# ---------------------------------------------------------------------------
# ForegroundPreservingDelegate
# ---------------------------------------------------------------------------


def test_foreground_preserving_delegate_restores_color_on_selection(
    qtbot: QtBot,
) -> None:
    """Delegate sets HighlightedText color from item's ForegroundRole."""
    table = create_table(["Status"])
    qtbot.addWidget(table)
    table.setRowCount(1)

    item = QTableWidgetItem("Done")
    green = QColor("#04d182")
    item.setForeground(QBrush(green))
    table.setItem(0, 0, item)

    delegate = ForegroundPreservingDelegate(table)
    table.setItemDelegateForColumn(0, delegate)

    # initStyleOption must preserve the item's foreground on the palette
    from PySide6.QtWidgets import QStyleOptionViewItem  # noqa: PLC0415

    option = QStyleOptionViewItem()
    index = table.model().index(0, 0)
    delegate.initStyleOption(option, index)

    restored = option.palette.color(option.palette.ColorRole.HighlightedText)
    assert restored.name().lower() == green.name().lower()


def test_foreground_preserving_delegate_no_foreground_role_unchanged(
    qtbot: QtBot,
) -> None:
    """When ForegroundRole is None delegate does not crash."""
    table = create_table(["Col"])
    qtbot.addWidget(table)
    table.setRowCount(1)

    item = QTableWidgetItem("Pending")
    # Do NOT set a foreground — ForegroundRole returns None
    table.setItem(0, 0, item)

    delegate = ForegroundPreservingDelegate(table)
    table.setItemDelegateForColumn(0, delegate)

    from PySide6.QtWidgets import QStyleOptionViewItem  # noqa: PLC0415

    option = QStyleOptionViewItem()
    index = table.model().index(0, 0)
    # Should not raise
    delegate.initStyleOption(option, index)


def test_foreground_preserving_delegate_different_colors(
    qtbot: QtBot,
) -> None:
    """Two rows with different foreground colors are independently preserved."""
    table = create_table(["Status"])
    qtbot.addWidget(table)
    table.setRowCount(2)  # noqa: PLR2004

    red = QColor("#ff6b72")
    green = QColor("#04d182")

    item0 = QTableWidgetItem("Failed")
    item0.setForeground(QBrush(red))
    table.setItem(0, 0, item0)

    item1 = QTableWidgetItem("Done")
    item1.setForeground(QBrush(green))
    table.setItem(1, 0, item1)

    delegate = ForegroundPreservingDelegate(table)
    table.setItemDelegateForColumn(0, delegate)

    from PySide6.QtWidgets import QStyleOptionViewItem  # noqa: PLC0415

    opt0 = QStyleOptionViewItem()
    delegate.initStyleOption(opt0, table.model().index(0, 0))
    opt1 = QStyleOptionViewItem()
    delegate.initStyleOption(opt1, table.model().index(1, 0))

    color0 = opt0.palette.color(opt0.palette.ColorRole.HighlightedText)
    color1 = opt1.palette.color(opt1.palette.ColorRole.HighlightedText)
    assert color0.name().lower() == red.name().lower()
    assert color1.name().lower() == green.name().lower()


# ---------------------------------------------------------------------------
# _build_formats_string — pure function
# ---------------------------------------------------------------------------


def test_build_formats_string_returns_nonempty() -> None:
    """_build_formats_string concatenates image and text extensions."""
    from src.ui.components import _build_formats_string  # noqa: PLC0415

    result = _build_formats_string()
    assert isinstance(result, str)
    assert len(result) > 0
    # Should contain common extensions (without the leading dot)
    assert "png" in result
    assert "pdf" in result
    assert "docx" in result


# ---------------------------------------------------------------------------
# create_banner — rich_text=True
# ---------------------------------------------------------------------------


def test_create_banner_rich_text_converts_newlines(qtbot: QtBot) -> None:
    """create_banner with rich_text=True converts newlines to HTML paragraphs."""
    banner, text_label = create_banner(
        "Line1\nLine2",
        variant="info",
        rich_text=True,
    )
    qtbot.addWidget(banner)

    assert text_label is not None
    # With rich_text, text format is set to RichText
    assert text_label.textFormat() == Qt.TextFormat.RichText
    # Content should have <p> tags instead of raw newlines
    assert "<p" in text_label.text()


# ---------------------------------------------------------------------------
# _TableResizeFilter
# ---------------------------------------------------------------------------


class TestTableResizeFilter:
    """Tests for _TableResizeFilter event handling."""

    def test_filter_installed_on_table(self, qtbot: QtBot) -> None:
        """Filter can be installed on a QTableWidget without error."""
        table = QTableWidget(3, 4)
        qtbot.addWidget(table)
        table.show()

        resize_filter = _TableResizeFilter(
            table,
            interactive_cols=[1, 2],
            column_widths={0: 50, 3: 80},
        )
        table.viewport().installEventFilter(resize_filter)

        # Trigger a resize to exercise the eventFilter path
        table.resize(600, 300)

        # Verify the filter is alive and attached — no crash
        assert resize_filter._table is table
        assert resize_filter._interactive_cols == [1, 2]


# ===========================================================================
# create_table — additional tests
# ===========================================================================


def test_create_table_with_stretch_columns(qtbot: QtBot) -> None:
    """stretch_columns parameter sets Stretch resize mode."""
    from PySide6.QtWidgets import QHeaderView  # noqa: PLC0415

    table = create_table(["A", "B", "C"], stretch_columns=[1, 2])
    qtbot.addWidget(table)

    header = table.horizontalHeader()
    assert header.sectionResizeMode(1) == QHeaderView.ResizeMode.Stretch
    assert header.sectionResizeMode(2) == QHeaderView.ResizeMode.Stretch  # noqa: PLR2004


def test_create_table_default_stretch_first_column(qtbot: QtBot) -> None:
    """Without stretch_columns, column 0 is stretched by default."""
    from PySide6.QtWidgets import QHeaderView  # noqa: PLC0415

    table = create_table(["A", "B"])
    qtbot.addWidget(table)

    header = table.horizontalHeader()
    assert header.sectionResizeMode(0) == QHeaderView.ResizeMode.Stretch


def test_create_table_with_interactive_columns(qtbot: QtBot) -> None:
    """interactive_columns sets Interactive resize mode."""
    from PySide6.QtWidgets import QHeaderView  # noqa: PLC0415

    table = create_table(["A", "B", "C"], interactive_columns=[0, 1])
    qtbot.addWidget(table)

    header = table.horizontalHeader()
    assert header.sectionResizeMode(0) == QHeaderView.ResizeMode.Interactive
    assert header.sectionResizeMode(1) == QHeaderView.ResizeMode.Interactive


def test_create_table_with_enter_callback(qtbot: QtBot) -> None:
    """enter_callback installs a _TableKeyFilter."""
    from src.ui.components import _TableKeyFilter  # noqa: PLC0415

    called: list[bool] = []
    table = create_table(["A", "B"], enter_callback=lambda: called.append(True))
    qtbot.addWidget(table)

    # Verify a _TableKeyFilter was installed
    filters = [
        child for child in table.children() if isinstance(child, _TableKeyFilter)
    ]
    assert len(filters) == 1


def test_create_table_minimum_section_size(qtbot: QtBot) -> None:
    """Header minimum section size is 50."""
    table = create_table(["A", "B"])
    qtbot.addWidget(table)
    assert table.horizontalHeader().minimumSectionSize() == 50  # noqa: PLR2004


def test_create_table_default_section_height(qtbot: QtBot) -> None:
    """Vertical header default section size is 40."""
    table = create_table(["A"])
    qtbot.addWidget(table)
    assert table.verticalHeader().defaultSectionSize() == 40  # noqa: PLR2004


def test_create_table_header_cursor(qtbot: QtBot) -> None:
    """Horizontal header has PointingHandCursor."""
    table = create_table(["A"])
    qtbot.addWidget(table)
    assert (
        table.horizontalHeader().cursor().shape() == Qt.CursorShape.PointingHandCursor
    )


def test_create_table_single_column(qtbot: QtBot) -> None:
    """Single-column table is created correctly."""
    table = create_table(["Only"])
    qtbot.addWidget(table)
    assert table.columnCount() == 1
    assert table.horizontalHeaderItem(0).text() == "Only"


def test_create_table_many_columns(qtbot: QtBot) -> None:
    """Table with many columns (10) is created correctly."""
    headers = [f"Col{i}" for i in range(10)]
    table = create_table(headers)
    qtbot.addWidget(table)
    assert table.columnCount() == 10  # noqa: PLR2004


def test_create_table_column_widths_and_stretch(qtbot: QtBot) -> None:
    """Both column_widths and stretch_columns can be specified."""
    table = create_table(
        ["A", "B", "C"],
        stretch_columns=[0],
        column_widths={1: 100, 2: 80},
    )
    qtbot.addWidget(table)
    assert table.columnWidth(1) == 100  # noqa: PLR2004
    assert table.columnWidth(2) == 80  # noqa: PLR2004


def test_create_table_no_show_grid(qtbot: QtBot) -> None:
    """Table has showGrid set to False."""
    table = create_table(["A"])
    qtbot.addWidget(table)
    assert table.showGrid() is False


# ===========================================================================
# create_banner — additional tests
# ===========================================================================


def test_create_banner_warning_default(qtbot: QtBot) -> None:
    """Default variant is 'warning'."""
    frame, label = create_banner("A message")
    qtbot.addWidget(frame)
    assert isinstance(frame, QFrame)
    assert label.text() == "A message"


def test_create_banner_error_variant(qtbot: QtBot) -> None:
    """Error variant creates banner without error."""
    frame, label = create_banner("Error!", variant="error")
    qtbot.addWidget(frame)
    assert "error" in frame.styleSheet().lower() or "ff6b72" in frame.styleSheet()


def test_create_banner_success_variant(qtbot: QtBot) -> None:
    """Success variant creates banner with success color."""
    from src.constants.theme import color  # noqa: PLC0415

    frame, _ = create_banner("OK", variant="success")
    qtbot.addWidget(frame)
    assert color("success") in frame.styleSheet()


def test_create_banner_info_variant(qtbot: QtBot) -> None:
    """Info variant creates banner with primary color."""
    from src.constants.theme import color  # noqa: PLC0415

    frame, _ = create_banner("Info", variant="info")
    qtbot.addWidget(frame)
    assert color("primary") in frame.styleSheet()


def test_create_banner_label_word_wrap(qtbot: QtBot) -> None:
    """Banner text label has word wrap enabled."""
    _, label = create_banner("Test msg")
    assert label.wordWrap() is True


def test_create_banner_frame_object_name(qtbot: QtBot) -> None:
    """Banner frame has objectName 'Banner'."""
    frame, _ = create_banner("Test")
    qtbot.addWidget(frame)
    assert frame.objectName() == "Banner"


def test_create_banner_text_label_object_name(qtbot: QtBot) -> None:
    """Banner text label has objectName 'BannerText'."""
    _, label = create_banner("Test")
    assert label.objectName() == "BannerText"


def test_create_banner_rich_text_open_external_links(qtbot: QtBot) -> None:
    """Rich text banner has openExternalLinks enabled."""
    _, label = create_banner("Click <a href='#'>here</a>", rich_text=True)
    assert label.openExternalLinks() is True


def test_create_banner_no_tr_key_no_apply_language(qtbot: QtBot) -> None:
    """Without tr_key, no apply_language is attached."""
    frame, _ = create_banner("Test")
    qtbot.addWidget(frame)
    assert not hasattr(frame, "apply_language")


def test_create_banner_with_tr_key_apply_language_updates_text(qtbot: QtBot) -> None:
    """apply_language with tr_key updates the label text."""
    from src.constants.i18n import tr  # noqa: PLC0415

    frame, label = create_banner("", variant="info", tr_key="btn.ok")
    qtbot.addWidget(frame)

    frame.apply_language()
    assert label.text() == tr("btn.ok")


def test_create_banner_apply_theme_updates_stylesheet(qtbot: QtBot) -> None:
    """apply_theme updates the banner stylesheet."""
    frame, _ = create_banner("Test", variant="error")
    qtbot.addWidget(frame)

    frame.apply_theme()
    # Style should still be set (may or may not differ if theme unchanged)
    assert frame.styleSheet()


# ===========================================================================
# CaseInsensitiveSortItem — additional tests
# ===========================================================================


def test_case_insensitive_sort_item_numbers_as_text(qtbot: QtBot) -> None:
    """Numeric strings sort lexicographically."""
    item_1 = CaseInsensitiveSortItem("10")
    item_2 = CaseInsensitiveSortItem("2")
    # "10" < "2" lexicographically
    assert (item_1 < item_2) is True


def test_case_insensitive_sort_item_special_chars(qtbot: QtBot) -> None:
    """Special characters sort correctly."""
    item_a = CaseInsensitiveSortItem("!first")
    item_b = CaseInsensitiveSortItem("Zebra")
    assert (item_a < item_b) is True


def test_case_insensitive_sort_preserves_display_text(qtbot: QtBot) -> None:
    """The displayed text is preserved unchanged."""
    item = CaseInsensitiveSortItem("MiXeD CaSe")
    assert item.text() == "MiXeD CaSe"


# ===========================================================================
# NumericalSortItem — additional tests
# ===========================================================================


def test_numerical_sort_item_very_large_values(qtbot: QtBot) -> None:
    """Very large float values sort correctly."""
    item_small = NumericalSortItem("1M", 1e6)
    item_large = NumericalSortItem("1B", 1e9)
    assert (item_small < item_large) is True


def test_numerical_sort_item_decimal_values(qtbot: QtBot) -> None:
    """Decimal float values sort correctly."""
    item_a = NumericalSortItem("1.5 MB", 1.5)
    item_b = NumericalSortItem("2.3 MB", 2.3)
    assert (item_a < item_b) is True
    assert (item_b < item_a) is False


def test_numerical_sort_item_display_text_preserved(qtbot: QtBot) -> None:
    """Display text is preserved unchanged."""
    item = NumericalSortItem("1.2 MB", 1.2)
    assert item.text() == "1.2 MB"


def test_numerical_sort_item_zero_value(qtbot: QtBot) -> None:
    """Zero value sorts correctly."""
    item_zero = NumericalSortItem("0 B", 0.0)
    item_pos = NumericalSortItem("1 KB", 1024.0)
    assert (item_zero < item_pos) is True


def test_numerical_sort_item_value_attribute(qtbot: QtBot) -> None:
    """Value attribute is accessible."""
    item = NumericalSortItem("test", 42.5)
    assert item.value == 42.5  # noqa: PLR2004


# ===========================================================================
# DateTimeSortItem — additional tests
# ===========================================================================


def test_datetime_sort_item_same_day_different_times(qtbot: QtBot) -> None:
    """Items on the same day sort by time."""
    item_morning = DateTimeSortItem("Morning", "2026-03-25 08:00:00")
    item_evening = DateTimeSortItem("Evening", "2026-03-25 20:00:00")
    assert (item_morning < item_evening) is True


def test_datetime_sort_item_display_text_preserved(qtbot: QtBot) -> None:
    """Display text is preserved unchanged."""
    item = DateTimeSortItem("Mar 25, 2026", "2026-03-25 10:00:00")
    assert item.text() == "Mar 25, 2026"


def test_datetime_sort_item_iso_key_attribute(qtbot: QtBot) -> None:
    """iso_key attribute is accessible."""
    item = DateTimeSortItem("display", "2026-01-01 00:00:00")
    assert item.iso_key == "2026-01-01 00:00:00"


def test_datetime_sort_item_empty_iso_key(qtbot: QtBot) -> None:
    """Empty iso_key handles comparison without error."""
    item_a = DateTimeSortItem("A", "")
    item_b = DateTimeSortItem("B", "2026-01-01")
    assert (item_a < item_b) is True


def test_datetime_sort_item_sorting_list(qtbot: QtBot) -> None:
    """Sorting a list of DateTimeSortItems by iso_key works correctly."""
    items = [
        DateTimeSortItem("Third", "2026-03-25"),
        DateTimeSortItem("First", "2026-01-01"),
        DateTimeSortItem("Second", "2026-02-15"),
    ]
    sorted_items = sorted(items)
    assert [i.text() for i in sorted_items] == ["First", "Second", "Third"]


# ===========================================================================
# HighlightDelegate — additional tests
# ===========================================================================


def test_highlight_delegate_set_search_text_strips(qtbot: QtBot) -> None:
    """set_search_text strips whitespace."""
    table = QTableWidget(1, 1)
    qtbot.addWidget(table)
    delegate = HighlightDelegate(table)
    delegate.set_search_text("  hello  ")
    assert delegate.search_text == "hello"


def test_highlight_delegate_set_selected_color(qtbot: QtBot) -> None:
    """set_selected_color stores the hex color."""
    table = QTableWidget(1, 1)
    qtbot.addWidget(table)
    delegate = HighlightDelegate(table)
    delegate.set_selected_color("#FF0000")
    assert delegate._selected_color == "#FF0000"


def test_highlight_delegate_plain_find_spans_no_match(qtbot: QtBot) -> None:
    """_find_highlight_spans returns empty list on no match."""
    table = QTableWidget(1, 1)
    qtbot.addWidget(table)
    delegate = HighlightDelegate(table, normalize=False)
    delegate.set_search_text("xyz")
    spans = delegate._find_highlight_spans("Hello World")
    assert spans == []


def test_highlight_delegate_normalized_multiple_matches(qtbot: QtBot) -> None:
    """Normalized delegate finds multiple accent-insensitive matches."""
    table = QTableWidget(1, 1)
    qtbot.addWidget(table)
    delegate = HighlightDelegate(table, normalize=True)
    delegate.set_search_text("a")
    spans = delegate._find_highlight_spans("banana")
    assert len(spans) == 3  # noqa: PLR2004


def test_highlight_delegate_case_insensitive_match(qtbot: QtBot) -> None:
    """Non-normalized delegate matches case-insensitively across cases."""
    table = QTableWidget(1, 1)
    qtbot.addWidget(table)
    delegate = HighlightDelegate(table, normalize=False)
    delegate.set_search_text("HELLO")
    assert delegate._has_match("hello world") is True


def test_highlight_delegate_special_regex_chars(qtbot: QtBot) -> None:
    """Search text with regex special chars is escaped properly."""
    table = QTableWidget(1, 1)
    qtbot.addWidget(table)
    delegate = HighlightDelegate(table, normalize=False)
    delegate.set_search_text("a.b")
    # Should match literal "a.b", not regex "a" + any char + "b"
    assert delegate._has_match("a.b test") is True
    assert delegate._has_match("axb test") is False


def test_highlight_delegate_normalized_no_match(qtbot: QtBot) -> None:
    """Normalized delegate returns False when no match found."""
    table = QTableWidget(1, 1)
    qtbot.addWidget(table)
    delegate = HighlightDelegate(table, normalize=True)
    delegate.set_search_text("xyz")
    assert delegate._has_match("Hello World") is False


# ===========================================================================
# ElidedLabel — additional tests
# ===========================================================================


def test_elided_label_set_placeholder(qtbot: QtBot) -> None:
    """set_placeholder updates the placeholder text."""
    label = ElidedLabel("")
    qtbot.addWidget(label)
    label.set_placeholder("Enter text...")
    assert label._placeholder == "Enter text..."


def test_elided_label_initial_placeholder(qtbot: QtBot) -> None:
    """ElidedLabel stores the initial placeholder."""
    label = ElidedLabel("", placeholder="Placeholder text")
    qtbot.addWidget(label)
    assert label._placeholder == "Placeholder text"


def test_elided_label_right_click_does_not_trigger(qtbot: QtBot) -> None:
    """Right-click does not trigger the callback."""
    clicked: list[bool] = []
    label = ElidedLabel("Click", clicked=lambda: clicked.append(True))
    qtbot.addWidget(label)
    qtbot.mouseClick(label, Qt.MouseButton.RightButton)
    assert clicked == []


def test_elided_label_hover_state(qtbot: QtBot) -> None:
    """ElidedLabel with draw_border tracks hover state."""
    label = ElidedLabel("Border", draw_border=True)
    qtbot.addWidget(label)
    assert label._hovered is False


def test_elided_label_set_text_updates_full_text(qtbot: QtBot) -> None:
    """set_text updates _full_text."""
    label = ElidedLabel("Initial")
    qtbot.addWidget(label)
    label.set_text("Updated")
    assert label._full_text == "Updated"


# ===========================================================================
# ForegroundPreservingDelegate — additional tests
# ===========================================================================


def test_foreground_preserving_delegate_with_qcolor_directly(
    qtbot: QtBot,
) -> None:
    """Delegate handles QColor foreground set via setData."""
    table = create_table(["Col"])
    qtbot.addWidget(table)
    table.setRowCount(1)

    item = QTableWidgetItem("Test")
    blue = QColor("#0000ff")
    item.setForeground(QBrush(blue))
    table.setItem(0, 0, item)

    delegate = ForegroundPreservingDelegate(table)
    table.setItemDelegateForColumn(0, delegate)

    from PySide6.QtWidgets import QStyleOptionViewItem  # noqa: PLC0415

    option = QStyleOptionViewItem()
    index = table.model().index(0, 0)
    delegate.initStyleOption(option, index)

    restored = option.palette.color(option.palette.ColorRole.HighlightedText)
    assert restored.name().lower() == blue.name().lower()


# ===========================================================================
# _TableKeyFilter — tests
# ===========================================================================


class TestTableKeyFilter:
    """Tests for _TableKeyFilter event handling."""

    def test_enter_with_selection_calls_callback(self, qtbot: QtBot) -> None:
        """Enter key with selected items calls the enter_callback."""
        from src.ui.components import _TableKeyFilter  # noqa: PLC0415

        called: list[bool] = []
        table = QTableWidget(2, 2)
        qtbot.addWidget(table)
        table.setItem(0, 0, QTableWidgetItem("A"))
        table.setItem(1, 0, QTableWidgetItem("B"))

        key_filter = _TableKeyFilter(table, lambda: called.append(True), table)
        table.installEventFilter(key_filter)

        # Select a row
        table.selectRow(0)
        assert table.selectedItems()

        # Simulate Enter key
        qtbot.keyPress(table, Qt.Key.Key_Return)
        assert len(called) == 1

    def test_enter_without_selection_does_not_call(self, qtbot: QtBot) -> None:
        """Enter key without selection doesn't call callback."""
        from src.ui.components import _TableKeyFilter  # noqa: PLC0415

        called: list[bool] = []
        table = QTableWidget(2, 2)
        qtbot.addWidget(table)
        table.setItem(0, 0, QTableWidgetItem("A"))

        key_filter = _TableKeyFilter(table, lambda: called.append(True), table)
        table.installEventFilter(key_filter)

        # Clear any selection
        table.clearSelection()

        qtbot.keyPress(table, Qt.Key.Key_Return)
        assert len(called) == 0

    def test_ctrl_a_selects_all_rows(self, qtbot: QtBot) -> None:
        """Ctrl+A selects all rows in the table."""
        from src.ui.components import _TableKeyFilter  # noqa: PLC0415

        table = QTableWidget(3, 2)
        qtbot.addWidget(table)
        for r in range(3):
            table.setItem(r, 0, QTableWidgetItem(f"Row{r}"))
            table.setItem(r, 1, QTableWidgetItem(f"Val{r}"))

        key_filter = _TableKeyFilter(table, lambda: None, table)
        table.installEventFilter(key_filter)

        qtbot.keyPress(
            table,
            Qt.Key.Key_A,
            Qt.KeyboardModifier.ControlModifier,
        )

        # All rows should be selected
        selected_rows = {item.row() for item in table.selectedItems()}
        assert selected_rows == {0, 1, 2}

    def test_regular_key_passes_through(self, qtbot: QtBot) -> None:
        """Regular keys are not intercepted."""
        from src.ui.components import _TableKeyFilter  # noqa: PLC0415

        called: list[bool] = []
        table = QTableWidget(1, 1)
        qtbot.addWidget(table)
        table.setItem(0, 0, QTableWidgetItem("A"))
        table.selectRow(0)

        key_filter = _TableKeyFilter(table, lambda: called.append(True), table)
        table.installEventFilter(key_filter)

        qtbot.keyPress(table, Qt.Key.Key_B)
        assert len(called) == 0


# ===========================================================================
# _TableResizeFilter — additional tests
# ===========================================================================


class TestTableResizeFilterAdditional:
    """Additional tests for _TableResizeFilter."""

    def test_filter_initial_widths_stored(self, qtbot: QtBot) -> None:
        """Initial column widths are stored in the filter."""
        table = QTableWidget(1, 4)
        qtbot.addWidget(table)

        widths = {0: 50, 3: 80}
        resize_filter = _TableResizeFilter(
            table,
            interactive_cols=[1, 2],
            column_widths=widths,
        )
        assert resize_filter._initial_widths == widths

    def test_filter_no_column_widths(self, qtbot: QtBot) -> None:
        """Filter works with no initial column widths."""
        table = QTableWidget(1, 3)
        qtbot.addWidget(table)

        resize_filter = _TableResizeFilter(
            table,
            interactive_cols=[0, 1, 2],
        )
        assert resize_filter._initial_widths == {}

    def test_filter_interactive_set(self, qtbot: QtBot) -> None:
        """Interactive set is created from interactive_cols list."""
        table = QTableWidget(1, 4)
        qtbot.addWidget(table)

        resize_filter = _TableResizeFilter(
            table,
            interactive_cols=[1, 3],
        )
        assert resize_filter._interactive_set == {1, 3}


# ===========================================================================
# style_file_count_badge / style_section_label — pure functions
# ===========================================================================


def test_style_file_count_badge_returns_qss() -> None:
    """style_file_count_badge returns non-empty QSS string."""
    from src.ui.components import style_file_count_badge  # noqa: PLC0415

    result = style_file_count_badge()
    assert isinstance(result, str)
    assert "border-radius" in result


def test_style_section_label_returns_qss() -> None:
    """style_section_label returns non-empty QSS string."""
    from src.ui.components import style_section_label  # noqa: PLC0415

    result = style_section_label()
    assert isinstance(result, str)
    assert "font-size" in result


# ===========================================================================
# create_section_group — additional tests
# ===========================================================================


def test_create_section_group_with_tr_key(qtbot: QtBot) -> None:
    """Section group with tr_key has apply_language."""
    group, layout, label = create_section_group("Title", tr_key="btn.ok")
    qtbot.addWidget(group)
    assert hasattr(group, "apply_language")
    group.apply_language()


def test_create_section_group_apply_theme(qtbot: QtBot) -> None:
    """Section group apply_theme updates styles."""
    group, layout, label = create_section_group("Title")
    qtbot.addWidget(group)
    assert hasattr(group, "apply_theme")
    group.apply_theme()


def test_create_section_group_label_text(qtbot: QtBot) -> None:
    """Section group label displays the given title."""
    group, _, label = create_section_group("My Section")
    qtbot.addWidget(group)
    assert label.text() == "My Section"


# ===========================================================================
# create_page_container — additional tests
# ===========================================================================


def test_create_page_container_without_tr_key_no_apply_language(
    qtbot: QtBot,
) -> None:
    """Without tr_key, no apply_language is attached."""
    page, _ = create_page_container("Title")
    qtbot.addWidget(page)
    assert not hasattr(page, "apply_language")


def test_create_page_container_margins(qtbot: QtBot) -> None:
    """Page container has correct margins from MARGIN_PAGE."""
    page, layout = create_page_container("Title")
    qtbot.addWidget(page)
    margins = layout.contentsMargins()
    assert margins.left() == MARGIN_PAGE
    assert margins.right() == MARGIN_PAGE


# ===========================================================================
# create_scrollable_container — additional tests
# ===========================================================================


def test_create_scrollable_container_transparent_bg(qtbot: QtBot) -> None:
    """Scrollable container has transparent background."""
    from PySide6.QtWidgets import QWidget  # noqa: PLC0415

    inner = QWidget()
    scroll = create_scrollable_container(inner)
    qtbot.addWidget(scroll)
    assert "transparent" in scroll.styleSheet()


# ===========================================================================
# FileDropWidget — additional tests
# ===========================================================================


def test_file_drop_widget_has_pointing_hand_cursor(qtbot: QtBot) -> None:
    """FileDropWidget has PointingHandCursor."""
    widget = FileDropWidget()
    qtbot.addWidget(widget)
    assert widget.cursor().shape() == Qt.CursorShape.PointingHandCursor


def test_file_drop_widget_frame_shape(qtbot: QtBot) -> None:
    """FileDropWidget has StyledPanel frame shape."""
    widget = FileDropWidget()
    qtbot.addWidget(widget)
    assert widget.frameShape() == QFrame.Shape.StyledPanel


def test_file_drop_widget_info_label_text(qtbot: QtBot) -> None:
    """FileDropWidget info label has translated drop title."""
    from src.constants.i18n import tr  # noqa: PLC0415

    widget = FileDropWidget()
    qtbot.addWidget(widget)
    assert widget.info_label.text() == tr("drop.title")


# ===========================================================================
# TestSettingPathResetButton — Reset/Clear button tests
# ===========================================================================


class TestSettingPathResetButton:
    """Tests for the Reset/Clear button in create_setting_path."""

    def test_clear_button_exists(
        self,
        qtbot: QtBot,
        settings_env: configparser.ConfigParser,
    ) -> None:
        """Clear/reset button exists in the setting path widget."""
        from PySide6.QtWidgets import QPushButton  # noqa: PLC0415

        container, _ = create_setting_path("Output", "test/clear_exists")
        qtbot.addWidget(container)

        buttons = container.findChildren(QPushButton)
        # Expect at least 2 buttons: Browse and Reset
        assert len(buttons) >= 2  # noqa: PLR2004
        button_texts = [btn.text() for btn in buttons]
        from src.constants.i18n import tr  # noqa: PLC0415

        assert tr("btn.reset") in button_texts

    def test_click_clear_saves_empty_string(
        self,
        qtbot: QtBot,
        settings_env: configparser.ConfigParser,
    ) -> None:
        """Clicking clear calls save_setting with empty string."""
        from PySide6.QtWidgets import QPushButton  # noqa: PLC0415

        from src.constants.i18n import tr  # noqa: PLC0415
        from src.utils.config_manager import load_setting, save_setting  # noqa: PLC0415

        save_setting("test/clear_click", "/some/path")
        container, path_label = create_setting_path("Output", "test/clear_click")
        qtbot.addWidget(container)

        # Find the clear/reset button
        clear_btn = None
        for btn in container.findChildren(QPushButton):
            if btn.text() == tr("btn.reset"):
                clear_btn = btn
                break
        assert clear_btn is not None

        qtbot.mouseClick(clear_btn, Qt.MouseButton.LeftButton)
        assert load_setting("test/clear_click", "fallback") == ""

    def test_clear_button_visibility_syncs_with_browse(
        self,
        qtbot: QtBot,
        settings_env: configparser.ConfigParser,
    ) -> None:
        """Clear button visibility = (placeholder_tr_key AND saved_path).

        The Reset button is gated on BOTH conditions in production:
        ``placeholder_tr_key`` signals that empty is a meaningful
        state for this field (e.g. Auto-save), AND ``saved_path``
        means there's something to actually reset.  Pickers without
        a placeholder (LibreOffice path, credentials file) have no
        defensible empty state, so the button is hidden regardless.
        """
        from PySide6.QtWidgets import QPushButton  # noqa: PLC0415

        from src.constants.i18n import tr  # noqa: PLC0415
        from src.utils.config_manager import save_setting  # noqa: PLC0415

        save_setting("test/clear_sync", "/a/path")
        # Must pass placeholder_tr_key for Reset to be wired in —
        # otherwise the button is intentionally hidden (no defensible
        # empty state for the field).
        container, path_label = create_setting_path(
            "Output",
            "test/clear_sync",
            placeholder_tr_key="settings.save_to_auto",
        )
        qtbot.addWidget(container)

        clear_btn = None
        for btn in container.findChildren(QPushButton):
            if btn.text() == tr("btn.reset"):
                clear_btn = btn
                break
        assert clear_btn is not None

        # Path is set + placeholder is configured → clear button visible.
        # (``isVisibleTo`` works without the hierarchy being shown.)
        assert clear_btn.isVisibleTo(container)

        # Browse button should also be visible.
        browse_btn = None
        for btn in container.findChildren(QPushButton):
            if btn.text() == tr("btn.browse"):
                browse_btn = btn
                break
        assert browse_btn is not None
        assert browse_btn.isVisibleTo(container)

    def test_after_clear_path_label_shows_empty(
        self,
        qtbot: QtBot,
        settings_env: configparser.ConfigParser,
    ) -> None:
        """After clicking clear, the path label shows empty text."""
        from PySide6.QtWidgets import QPushButton  # noqa: PLC0415

        from src.constants.i18n import tr  # noqa: PLC0415
        from src.utils.config_manager import save_setting  # noqa: PLC0415

        save_setting("test/clear_label", "/existing/path")
        container, path_label = create_setting_path("Output", "test/clear_label")
        qtbot.addWidget(container)

        clear_btn = None
        for btn in container.findChildren(QPushButton):
            if btn.text() == tr("btn.reset"):
                clear_btn = btn
                break
        assert clear_btn is not None

        qtbot.mouseClick(clear_btn, Qt.MouseButton.LeftButton)
        assert path_label._full_text == ""

    def test_clear_button_hidden_when_no_path(
        self,
        qtbot: QtBot,
        settings_env: configparser.ConfigParser,
    ) -> None:
        """Clear button is hidden when no path is set initially."""
        from PySide6.QtWidgets import QPushButton  # noqa: PLC0415

        from src.constants.i18n import tr  # noqa: PLC0415

        # Do NOT save any path for this key
        container, _ = create_setting_path("Output", "test/clear_hidden")
        qtbot.addWidget(container)

        clear_btn = None
        for btn in container.findChildren(QPushButton):
            if btn.text() == tr("btn.reset"):
                clear_btn = btn
                break
        assert clear_btn is not None
        assert not clear_btn.isVisibleTo(container)
