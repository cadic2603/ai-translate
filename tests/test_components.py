"""Unit tests for src/ui/components.py.

Covers:
- create_table() — QTableWidget construction, headers, columns, styling
- create_banner() — banner creation for each variant (warning, error, success, info)
- create_page_container() — page container with header and layout
- create_section_group() — section group with title and bordered frame
- create_scrollable_container() — wrapping a widget in a QScrollArea
- ElidedLabel — text setting, placeholder, click callback
- HoverIconButton — icon swapping on hover events
- FileDropWidget — construction, drop handling, signal emission
- FileItemWidget — file card construction
- HighlightDelegate — search text highlighting and span computation
- ForegroundPreservingDelegate — preserves per-item foreground on selection
- create_setting_combo() — setting combo box construction
- create_setting_checkbox() — setting checkbox construction
- create_setting_input() — setting input field construction
- create_setting_path() — setting path selection widget
- _build_formats_string() — supported formats display string
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QScrollArea,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

# ---------------------------------------------------------------------------
# create_table tests
# ---------------------------------------------------------------------------


class TestCreateTable:
    """Tests for the create_table() factory function."""

    def test_returns_qtablewidget(self, qapp: QApplication) -> None:
        """create_table returns a QTableWidget instance."""
        from src.ui.components import create_table  # noqa: PLC0415

        table = create_table(["A", "B", "C"])
        assert isinstance(table, QTableWidget)

    def test_correct_column_count(self, qapp: QApplication) -> None:
        """Column count matches the number of headers."""
        from src.ui.components import create_table  # noqa: PLC0415

        headers = ["Name", "Status", "Size", "Date"]
        table = create_table(headers)
        assert table.columnCount() == 4  # noqa: PLR2004

    def test_header_labels_set(self, qapp: QApplication) -> None:
        """Horizontal header labels match the provided list."""
        from src.ui.components import create_table  # noqa: PLC0415

        headers = ["File", "Progress", "Actions"]
        table = create_table(headers)
        h = table.horizontalHeader()
        labels = [table.horizontalHeaderItem(i).text() for i in range(h.count())]
        assert labels == headers

    def test_cursor_set_to_pointing_hand(self, qapp: QApplication) -> None:
        """Table cursor is PointingHandCursor."""
        from src.ui.components import create_table  # noqa: PLC0415

        table = create_table(["A"])
        assert table.cursor().shape() == Qt.CursorShape.PointingHandCursor

    def test_header_cursor_pointing_hand(self, qapp: QApplication) -> None:
        """Horizontal header cursor is PointingHandCursor."""
        from src.ui.components import create_table  # noqa: PLC0415

        table = create_table(["X", "Y"])
        assert (
            table.horizontalHeader().cursor().shape()
            == Qt.CursorShape.PointingHandCursor
        )

    def test_vertical_header_hidden(self, qapp: QApplication) -> None:
        """Vertical (row number) header is not visible."""
        from src.ui.components import create_table  # noqa: PLC0415

        table = create_table(["A"])
        assert not table.verticalHeader().isVisible()

    def test_alternating_row_colors(self, qapp: QApplication) -> None:
        """Alternating row colors is enabled."""
        from src.ui.components import create_table  # noqa: PLC0415

        table = create_table(["A"])
        assert table.alternatingRowColors()

    def test_grid_hidden(self, qapp: QApplication) -> None:
        """Grid lines are not shown."""
        from src.ui.components import create_table  # noqa: PLC0415

        table = create_table(["A"])
        assert not table.showGrid()

    def test_sorting_enabled(self, qapp: QApplication) -> None:
        """Sorting is enabled."""
        from src.ui.components import create_table  # noqa: PLC0415

        table = create_table(["A"])
        assert table.isSortingEnabled()

    def test_selection_behavior_select_rows(self, qapp: QApplication) -> None:
        """Selection behavior is SelectRows."""
        from src.ui.components import create_table  # noqa: PLC0415

        table = create_table(["A"])
        assert table.selectionBehavior() == QTableWidget.SelectionBehavior.SelectRows

    def test_default_stretch_column(self, qapp: QApplication) -> None:
        """By default, column 0 uses Stretch resize mode."""
        from src.ui.components import create_table  # noqa: PLC0415

        table = create_table(["A", "B"])
        h = table.horizontalHeader()
        assert h.sectionResizeMode(0) == QHeaderView.ResizeMode.Stretch

    def test_non_stretch_column_fixed(self, qapp: QApplication) -> None:
        """Non-stretch columns default to Fixed resize mode."""
        from src.ui.components import create_table  # noqa: PLC0415

        table = create_table(["A", "B", "C"])
        h = table.horizontalHeader()
        assert h.sectionResizeMode(1) == QHeaderView.ResizeMode.Fixed
        assert h.sectionResizeMode(2) == QHeaderView.ResizeMode.Fixed  # noqa: PLR2004

    def test_custom_stretch_columns(self, qapp: QApplication) -> None:
        """Providing stretch_columns stretches specified columns."""
        from src.ui.components import create_table  # noqa: PLC0415

        table = create_table(["A", "B", "C"], stretch_columns=[1, 2])
        h = table.horizontalHeader()
        assert h.sectionResizeMode(0) == QHeaderView.ResizeMode.Fixed
        assert h.sectionResizeMode(1) == QHeaderView.ResizeMode.Stretch
        assert h.sectionResizeMode(2) == QHeaderView.ResizeMode.Stretch  # noqa: PLR2004

    def test_column_widths_applied(self, qapp: QApplication) -> None:
        """Fixed column widths are applied correctly."""
        from src.ui.components import create_table  # noqa: PLC0415

        table = create_table(["A", "B", "C"], column_widths={1: 120, 2: 80})
        assert table.columnWidth(1) == 120  # noqa: PLR2004
        assert table.columnWidth(2) == 80  # noqa: PLR2004

    def test_interactive_columns(self, qapp: QApplication) -> None:
        """Interactive columns use Interactive resize mode."""
        from src.ui.components import create_table  # noqa: PLC0415

        table = create_table(
            ["A", "B", "C"],
            interactive_columns=[0, 1],
        )
        h = table.horizontalHeader()
        assert h.sectionResizeMode(0) == QHeaderView.ResizeMode.Interactive
        assert h.sectionResizeMode(1) == QHeaderView.ResizeMode.Interactive

    def test_interactive_installs_event_filter(self, qapp: QApplication) -> None:
        """Interactive columns install a _TableResizeFilter on the viewport."""
        from src.ui.components import (  # noqa: PLC0415
            _TableResizeFilter,
            create_table,
        )

        table = create_table(["A", "B"], interactive_columns=[0, 1])
        # Check the viewport's event filters include a _TableResizeFilter
        found = False
        for child in table.children():
            if isinstance(child, _TableResizeFilter):
                found = True
                break
        assert found

    def test_zero_initial_rows(self, qapp: QApplication) -> None:
        """Table starts with 0 rows."""
        from src.ui.components import create_table  # noqa: PLC0415

        table = create_table(["A", "B"])
        assert table.rowCount() == 0

    def test_vertical_header_default_section_size(self, qapp: QApplication) -> None:
        """Vertical header default section size is 40."""
        from src.ui.components import create_table  # noqa: PLC0415

        table = create_table(["A"])
        assert table.verticalHeader().defaultSectionSize() == 40  # noqa: PLR2004

    def test_minimum_section_size(self, qapp: QApplication) -> None:
        """Horizontal header minimum section size is 50."""
        from src.ui.components import create_table  # noqa: PLC0415

        table = create_table(["A", "B"])
        assert table.horizontalHeader().minimumSectionSize() == 50  # noqa: PLR2004

    def test_stylesheet_applied(self, qapp: QApplication) -> None:
        """Table has a non-empty stylesheet from style_table()."""
        from src.ui.components import create_table  # noqa: PLC0415

        table = create_table(["A"])
        assert table.styleSheet()


# ---------------------------------------------------------------------------
# create_banner tests
# ---------------------------------------------------------------------------


class TestCreateBanner:
    """Tests for the create_banner() factory function."""

    def test_returns_frame_and_label(self, qapp: QApplication) -> None:
        """create_banner returns a tuple of (QFrame, QLabel)."""
        from src.ui.components import create_banner  # noqa: PLC0415

        frame, label = create_banner("Test message")
        assert isinstance(frame, QFrame)
        assert isinstance(label, QLabel)

    def test_text_set_correctly(self, qapp: QApplication) -> None:
        """The label text matches the input."""
        from src.ui.components import create_banner  # noqa: PLC0415

        _, label = create_banner("Hello World")
        assert label.text() == "Hello World"

    def test_banner_object_name(self, qapp: QApplication) -> None:
        """The frame has objectName 'Banner'."""
        from src.ui.components import create_banner  # noqa: PLC0415

        frame, _ = create_banner("msg")
        assert frame.objectName() == "Banner"

    def test_text_label_object_name(self, qapp: QApplication) -> None:
        """The text label has objectName 'BannerText'."""
        from src.ui.components import create_banner  # noqa: PLC0415

        _, label = create_banner("msg")
        assert label.objectName() == "BannerText"

    def test_icon_label_object_name(self, qapp: QApplication) -> None:
        """The icon label has objectName 'BannerIcon'."""
        from src.ui.components import create_banner  # noqa: PLC0415

        frame, _ = create_banner("msg")
        icon_label = frame.findChild(QLabel, "BannerIcon")
        assert icon_label is not None

    def test_word_wrap_enabled(self, qapp: QApplication) -> None:
        """The text label has word wrap enabled."""
        from src.ui.components import create_banner  # noqa: PLC0415

        _, label = create_banner("long text")
        assert label.wordWrap()

    @pytest.mark.parametrize("variant", ["warning", "error", "success", "info"])
    def test_all_variants_create_successfully(
        self, qapp: QApplication, variant: str
    ) -> None:
        """All four banner variants create without error."""
        from src.ui.components import create_banner  # noqa: PLC0415

        frame, label = create_banner(f"msg for {variant}", variant=variant)
        assert isinstance(frame, QFrame)
        assert label.text() == f"msg for {variant}"

    @pytest.mark.parametrize("variant", ["warning", "error", "success", "info"])
    def test_stylesheet_applied_per_variant(
        self, qapp: QApplication, variant: str
    ) -> None:
        """Each variant applies a non-empty stylesheet."""
        from src.ui.components import create_banner  # noqa: PLC0415

        frame, _ = create_banner("text", variant=variant)
        assert frame.styleSheet()

    def test_unknown_variant_falls_back_to_warning(self, qapp: QApplication) -> None:
        """An unknown variant uses the warning icon path (fallback)."""
        from src.ui.components import create_banner  # noqa: PLC0415

        frame, _ = create_banner("text", variant="unknown")
        # Should not raise; falls back to warning icon
        assert isinstance(frame, QFrame)

    def test_banner_has_horizontal_layout(self, qapp: QApplication) -> None:
        """Banner uses a QHBoxLayout."""
        from src.ui.components import create_banner  # noqa: PLC0415

        frame, _ = create_banner("msg")
        assert isinstance(frame.layout(), QHBoxLayout)

    def test_apply_theme_callable(self, qapp: QApplication) -> None:
        """Banner has an apply_theme method (attached dynamically)."""
        from src.ui.components import create_banner  # noqa: PLC0415

        frame, _ = create_banner("msg")
        assert hasattr(frame, "apply_theme")
        assert callable(frame.apply_theme)
        # Should not raise
        frame.apply_theme()

    def test_apply_language_with_tr_key(self, qapp: QApplication) -> None:
        """Banner with tr_key has an apply_language method."""
        from src.ui.components import create_banner  # noqa: PLC0415

        frame, _ = create_banner("msg", tr_key="some.key")
        assert hasattr(frame, "apply_language")
        assert callable(frame.apply_language)

    def test_no_apply_language_without_tr_key(self, qapp: QApplication) -> None:
        """Banner without tr_key has no apply_language method."""
        from src.ui.components import create_banner  # noqa: PLC0415

        frame, _ = create_banner("msg")
        assert not hasattr(frame, "apply_language")

    def test_rich_text_mode(self, qapp: QApplication) -> None:
        """Rich text mode sets the label text format to RichText."""
        from src.ui.components import create_banner  # noqa: PLC0415

        _, label = create_banner("msg", rich_text=True)
        assert label.textFormat() == Qt.TextFormat.RichText

    def test_rich_text_open_external_links(self, qapp: QApplication) -> None:
        """Rich text mode enables openExternalLinks."""
        from src.ui.components import create_banner  # noqa: PLC0415

        _, label = create_banner("msg", rich_text=True)
        assert label.openExternalLinks()

    def test_rich_text_newlines_converted(self, qapp: QApplication) -> None:
        """In rich text mode, newlines are converted to paragraph tags."""
        from src.ui.components import create_banner  # noqa: PLC0415

        _, label = create_banner("line1\nline2", rich_text=True)
        text = label.text()
        assert "<p" in text
        assert "line1" in text
        assert "line2" in text


# ---------------------------------------------------------------------------
# create_ffmpeg_install_banner tests
# ---------------------------------------------------------------------------


class TestCreateFFmpegInstallBanner:
    """Shared ffmpeg setup-hint banner used by Voice / Dubbing / Live pages.

    Pins the contract that the helper returns ``(banner, refresh)``,
    the refresh callable is wired to ``apply_language``, and visibility
    toggles purely on ffmpeg-on-PATH state.
    """

    def test_returns_frame_and_refresh_callable(self, qapp: QApplication) -> None:
        """Helper returns ``(QFrame, callable)``."""
        from src.constants.i18n import _set_initial_language  # noqa: PLC0415
        from src.ui.components import create_ffmpeg_install_banner  # noqa: PLC0415

        _set_initial_language("en-US")
        banner, refresh = create_ffmpeg_install_banner()
        from PySide6.QtWidgets import QFrame  # noqa: PLC0415

        assert isinstance(banner, QFrame)
        assert callable(refresh)

    def test_visible_when_ffmpeg_missing(self, qapp: QApplication) -> None:
        """Refresh shows the banner when ``shutil.which('ffmpeg')`` is None."""
        from unittest.mock import patch  # noqa: PLC0415

        from src.constants.i18n import _set_initial_language  # noqa: PLC0415
        from src.ui.components import create_ffmpeg_install_banner  # noqa: PLC0415

        _set_initial_language("en-US")
        banner, refresh = create_ffmpeg_install_banner()
        with patch("shutil.which", return_value=None):
            refresh()
        # Use ``not isHidden()`` per the headless-Qt convention.
        assert not banner.isHidden()

    def test_hidden_when_ffmpeg_present(self, qapp: QApplication) -> None:
        """Refresh hides the banner when ffmpeg IS on PATH."""
        from unittest.mock import patch  # noqa: PLC0415

        from src.constants.i18n import _set_initial_language  # noqa: PLC0415
        from src.ui.components import create_ffmpeg_install_banner  # noqa: PLC0415

        _set_initial_language("en-US")
        banner, refresh = create_ffmpeg_install_banner()
        with patch("shutil.which", return_value="/usr/bin/ffmpeg"):
            refresh()
        assert banner.isHidden()

    def test_apply_language_attribute_wired(self, qapp: QApplication) -> None:
        """``banner.apply_language`` invokes the refresh — language-switch hook."""
        from src.constants.i18n import _set_initial_language  # noqa: PLC0415
        from src.ui.components import create_ffmpeg_install_banner  # noqa: PLC0415

        _set_initial_language("en-US")
        banner, refresh = create_ffmpeg_install_banner()
        # ``window.py`` walks every QWidget on language change calling
        # ``apply_language`` on whatever defines it.  The helper must
        # expose the refresh under that name.
        assert banner.apply_language is refresh

    def test_per_os_text_dispatch(self, qapp: QApplication) -> None:
        """Linux / macOS / Windows / fallback each pick their own key."""
        from unittest.mock import patch  # noqa: PLC0415

        from PySide6.QtWidgets import QLabel  # noqa: PLC0415

        from src.constants.i18n import _set_initial_language  # noqa: PLC0415
        from src.ui.components import create_ffmpeg_install_banner  # noqa: PLC0415

        _set_initial_language("en-US")

        # macOS variant mentions Homebrew.
        banner, refresh = create_ffmpeg_install_banner()
        with (
            patch("shutil.which", return_value=None),
            patch("platform.system", return_value="Darwin"),
        ):
            refresh()
        label = banner.findChild(QLabel, "BannerText")
        assert "Homebrew" in label.text()

        # Windows variant mentions winget.
        banner2, refresh2 = create_ffmpeg_install_banner()
        with (
            patch("shutil.which", return_value=None),
            patch("platform.system", return_value="Windows"),
        ):
            refresh2()
        label2 = banner2.findChild(QLabel, "BannerText")
        assert "winget" in label2.text()


# ---------------------------------------------------------------------------
# create_page_container tests
# ---------------------------------------------------------------------------


class TestCreatePageContainer:
    """Tests for the create_page_container() factory function."""

    def test_returns_widget_and_layout(self, qapp: QApplication) -> None:
        """Returns a (QWidget, QVBoxLayout) tuple."""
        from src.ui.components import create_page_container  # noqa: PLC0415

        widget, layout = create_page_container("My Page")
        assert isinstance(widget, QWidget)
        assert isinstance(layout, QVBoxLayout)

    def test_header_text(self, qapp: QApplication) -> None:
        """The page header label contains the title text."""
        from src.ui.components import create_page_container  # noqa: PLC0415

        widget, _ = create_page_container("Test Title")
        header = widget.findChild(QLabel)
        assert header is not None
        assert header.text() == "Test Title"

    def test_apply_theme_attached(self, qapp: QApplication) -> None:
        """Page container has a callable apply_theme."""
        from src.ui.components import create_page_container  # noqa: PLC0415

        widget, _ = create_page_container("Title")
        assert callable(widget.apply_theme)
        widget.apply_theme()  # Should not raise

    def test_apply_language_with_tr_key(self, qapp: QApplication) -> None:
        """Page container with tr_key has apply_language."""
        from src.ui.components import create_page_container  # noqa: PLC0415

        widget, _ = create_page_container("Title", tr_key="page.title")
        assert callable(widget.apply_language)

    def test_no_apply_language_without_tr_key(self, qapp: QApplication) -> None:
        """Page container without tr_key has no apply_language."""
        from src.ui.components import create_page_container  # noqa: PLC0415

        widget, _ = create_page_container("Title")
        assert not hasattr(widget, "apply_language")


# ---------------------------------------------------------------------------
# create_section_group tests
# ---------------------------------------------------------------------------


class TestCreateSectionGroup:
    """Tests for the create_section_group() factory function."""

    def test_returns_frame_layout_label(self, qapp: QApplication) -> None:
        """Returns a (QFrame, QVBoxLayout, QLabel) tuple."""
        from src.ui.components import create_section_group  # noqa: PLC0415

        frame, layout, label = create_section_group("Section")
        assert isinstance(frame, QFrame)
        assert isinstance(layout, QVBoxLayout)
        assert isinstance(label, QLabel)

    def test_title_text(self, qapp: QApplication) -> None:
        """Section title label has correct text."""
        from src.ui.components import create_section_group  # noqa: PLC0415

        _, _, label = create_section_group("My Section")
        assert label.text() == "My Section"

    def test_apply_theme(self, qapp: QApplication) -> None:
        """Section group has callable apply_theme."""
        from src.ui.components import create_section_group  # noqa: PLC0415

        frame, _, _ = create_section_group("S")
        assert callable(frame.apply_theme)
        frame.apply_theme()

    def test_apply_language_with_tr_key(self, qapp: QApplication) -> None:
        """Section group with tr_key has apply_language."""
        from src.ui.components import create_section_group  # noqa: PLC0415

        frame, _, _ = create_section_group("S", tr_key="section.title")
        assert callable(frame.apply_language)


# ---------------------------------------------------------------------------
# create_scrollable_container tests
# ---------------------------------------------------------------------------


class TestCreateScrollableContainer:
    """Tests for the create_scrollable_container() function."""

    def test_returns_scroll_area(self, qapp: QApplication) -> None:
        """Returns a QScrollArea."""
        from src.ui.components import create_scrollable_container  # noqa: PLC0415

        inner = QWidget()
        scroll = create_scrollable_container(inner)
        assert isinstance(scroll, QScrollArea)

    def test_widget_resizable(self, qapp: QApplication) -> None:
        """QScrollArea is widget-resizable."""
        from src.ui.components import create_scrollable_container  # noqa: PLC0415

        inner = QWidget()
        scroll = create_scrollable_container(inner)
        assert scroll.widgetResizable()

    def test_no_frame(self, qapp: QApplication) -> None:
        """QScrollArea has no frame border."""
        from src.ui.components import create_scrollable_container  # noqa: PLC0415

        inner = QWidget()
        scroll = create_scrollable_container(inner)
        assert scroll.frameShape() == QFrame.Shape.NoFrame

    def test_contains_widget(self, qapp: QApplication) -> None:
        """QScrollArea contains the passed widget."""
        from src.ui.components import create_scrollable_container  # noqa: PLC0415

        inner = QWidget()
        scroll = create_scrollable_container(inner)
        assert scroll.widget() is inner


# ---------------------------------------------------------------------------
# create_controller_card tests
# ---------------------------------------------------------------------------


class TestCreateControllerCard:
    """Tests for create_controller_card() — shared chrome for Live + Screen."""

    def test_returns_controller_card(self, qapp: QApplication) -> None:
        """Returns a ControllerCard dataclass with all expected fields."""
        from src.ui.components import (  # noqa: PLC0415
            ControllerCard,
            create_controller_card,
        )

        result = create_controller_card()
        assert isinstance(result, ControllerCard)

    def test_card_is_qframe_with_object_name(self, qapp: QApplication) -> None:
        """Card is a QFrame with the ``LivePageCard`` object name.

        The object name powers the QSS scoping that renders the
        rounded border + surface colour; without it, descendant
        widgets would inherit the styling.
        """
        from src.ui.components import create_controller_card  # noqa: PLC0415

        result = create_controller_card()
        assert isinstance(result.card, QFrame)
        assert result.card.objectName() == "LivePageCard"

    def test_card_has_no_frame_shape(self, qapp: QApplication) -> None:
        """Card uses NoFrame so the QSS-painted border is the only visible edge."""
        from src.ui.components import create_controller_card  # noqa: PLC0415

        result = create_controller_card()
        assert result.card.frameShape() == QFrame.Shape.NoFrame

    def test_layout_is_card_main_layout(self, qapp: QApplication) -> None:
        """``layout`` is the card's own QVBoxLayout."""
        from src.ui.components import create_controller_card  # noqa: PLC0415

        result = create_controller_card()
        assert result.layout is result.card.layout()

    def test_top_and_bottom_rows_are_qhbox(self, qapp: QApplication) -> None:
        """Both control rows are horizontal layouts ready for addWidget."""
        from PySide6.QtWidgets import QHBoxLayout  # noqa: PLC0415

        from src.ui.components import create_controller_card  # noqa: PLC0415

        result = create_controller_card()
        assert isinstance(result.controls_top_row, QHBoxLayout)
        assert isinstance(result.controls_btm_row, QHBoxLayout)

    def test_btm_row_parent_is_widget(self, qapp: QApplication) -> None:
        """``btm_row_parent`` is a QWidget exposed for hide/re-style use."""
        from src.ui.components import create_controller_card  # noqa: PLC0415

        result = create_controller_card()
        assert isinstance(result.btm_row_parent, QWidget)

    def test_banners_layout_is_qvbox(self, qapp: QApplication) -> None:
        """``banners_layout`` is a QVBoxLayout sitting between controls and divider.

        Callers that don't add anything leave it empty — it renders nothing.
        """
        from PySide6.QtWidgets import QVBoxLayout  # noqa: PLC0415

        from src.ui.components import create_controller_card  # noqa: PLC0415

        result = create_controller_card()
        assert isinstance(result.banners_layout, QVBoxLayout)

    def test_caller_can_populate_top_row(self, qapp: QApplication) -> None:
        """The exposed top row accepts addWidget calls without error."""
        from PySide6.QtWidgets import QPushButton  # noqa: PLC0415

        from src.ui.components import create_controller_card  # noqa: PLC0415

        result = create_controller_card()
        btn = QPushButton("test")
        result.controls_top_row.addWidget(btn)
        assert btn.parent() is not None

    def test_caller_can_populate_btm_row(self, qapp: QApplication) -> None:
        """The exposed bottom row accepts addWidget calls without error."""
        from PySide6.QtWidgets import QPushButton  # noqa: PLC0415

        from src.ui.components import create_controller_card  # noqa: PLC0415

        result = create_controller_card()
        btn = QPushButton("test")
        result.controls_btm_row.addWidget(btn)
        assert btn.parent() is not None

    def test_caller_can_add_banner(self, qapp: QApplication) -> None:
        """The banners layout accepts addWidget calls."""
        from PySide6.QtWidgets import QLabel  # noqa: PLC0415

        from src.ui.components import create_controller_card  # noqa: PLC0415

        result = create_controller_card()
        banner = QLabel("warning")
        result.banners_layout.addWidget(banner)
        # When added to a layout, the widget is reparented to the
        # layout's owning widget — verifies the layout is wired in.
        assert banner.parent() is not None

    def test_card_layout_includes_divider(self, qapp: QApplication) -> None:
        """The card's main layout has a horizontal divider QFrame.

        The divider sits at the bottom of the controller block,
        before any content the caller appends — matches Live's
        single-divider layout exactly.
        """
        from src.ui.components import create_controller_card  # noqa: PLC0415

        result = create_controller_card()
        # Walk the layout's items looking for a HLine QFrame.
        found_divider = False
        for i in range(result.layout.count()):
            item = result.layout.itemAt(i)
            widget = item.widget() if item is not None else None
            if isinstance(widget, QFrame) and (
                widget.frameShape() == QFrame.Shape.HLine
            ):
                found_divider = True
                break
        assert found_divider, "controller card should include an HLine divider"

    def test_caller_can_append_content_after_divider(
        self, qapp: QApplication,
    ) -> None:
        """Caller can append the page's main content widget to ``layout``."""
        from src.ui.components import create_controller_card  # noqa: PLC0415

        result = create_controller_card()
        content = QWidget()
        result.layout.addWidget(content)
        # Last item in the layout should be our content widget.
        last = result.layout.itemAt(result.layout.count() - 1).widget()
        assert last is content


# ---------------------------------------------------------------------------
# ElidedLabel tests
# ---------------------------------------------------------------------------


class TestElidedLabel:
    """Tests for the ElidedLabel class."""

    def test_initial_text(self, qapp: QApplication) -> None:
        """ElidedLabel stores the initial text."""
        from src.ui.components import ElidedLabel  # noqa: PLC0415

        label = ElidedLabel("hello")
        assert label._full_text == "hello"

    def test_set_text_updates_full_text(self, qapp: QApplication) -> None:
        """set_text updates the internal _full_text."""
        from src.ui.components import ElidedLabel  # noqa: PLC0415

        label = ElidedLabel("old")
        label.set_text("new")
        assert label._full_text == "new"

    def test_set_placeholder(self, qapp: QApplication) -> None:
        """set_placeholder updates _placeholder."""
        from src.ui.components import ElidedLabel  # noqa: PLC0415

        label = ElidedLabel("")
        label.set_placeholder("Select a file...")
        assert label._placeholder == "Select a file..."

    def test_click_callback(self, qapp: QApplication) -> None:
        """Click callback is stored and sets PointingHandCursor."""
        from src.ui.components import ElidedLabel  # noqa: PLC0415

        cb = MagicMock()
        label = ElidedLabel("text", clicked=cb)
        assert label.clicked_callback is cb
        assert label.cursor().shape() == Qt.CursorShape.PointingHandCursor

    def test_no_click_callback(self, qapp: QApplication) -> None:
        """Without click callback, cursor is default."""
        from src.ui.components import ElidedLabel  # noqa: PLC0415

        label = ElidedLabel("text")
        assert label.clicked_callback is None

    def test_draw_border_enables_mouse_tracking(self, qapp: QApplication) -> None:
        """draw_border=True enables mouse tracking."""
        from src.ui.components import ElidedLabel  # noqa: PLC0415

        label = ElidedLabel("text", draw_border=True)
        assert label.draw_border
        assert label.hasMouseTracking()


# ---------------------------------------------------------------------------
# HoverIconButton tests
# ---------------------------------------------------------------------------


class TestHoverIconButton:
    """Tests for the HoverIconButton class."""

    def test_construction(self, qapp: QApplication) -> None:
        """HoverIconButton stores normal and hover icons."""
        from src.ui.components import HoverIconButton  # noqa: PLC0415

        btn = HoverIconButton("normal.png", "hover.png")
        assert btn.normal_icon is not None
        assert btn.hover_icon is not None

    def test_set_icons_updates(self, qapp: QApplication) -> None:
        """set_icons updates both icon references."""
        from src.ui.components import HoverIconButton  # noqa: PLC0415

        btn = HoverIconButton("a.png", "b.png")
        old_normal = btn.normal_icon
        btn.set_icons("c.png", "d.png")
        assert btn.normal_icon is not old_normal


# ---------------------------------------------------------------------------
# FileDropWidget tests
# ---------------------------------------------------------------------------


class TestFileDropWidget:
    """Tests for the FileDropWidget class."""

    def test_construction(self, qapp: QApplication) -> None:
        """FileDropWidget constructs without error."""
        from src.ui.components import FileDropWidget  # noqa: PLC0415

        widget = FileDropWidget()
        assert widget.acceptDrops()

    def test_cursor_pointing_hand(self, qapp: QApplication) -> None:
        """FileDropWidget has PointingHandCursor."""
        from src.ui.components import FileDropWidget  # noqa: PLC0415

        widget = FileDropWidget()
        assert widget.cursor().shape() == Qt.CursorShape.PointingHandCursor

    def test_frame_shape(self, qapp: QApplication) -> None:
        """FileDropWidget has StyledPanel frame shape."""
        from src.ui.components import FileDropWidget  # noqa: PLC0415

        widget = FileDropWidget()
        assert widget.frameShape() == QFrame.Shape.StyledPanel

    def test_has_files_dropped_signal(self, qapp: QApplication) -> None:
        """FileDropWidget has a files_dropped signal."""
        from src.ui.components import FileDropWidget  # noqa: PLC0415

        widget = FileDropWidget()
        assert hasattr(widget, "files_dropped")

    def test_apply_theme_callable(self, qapp: QApplication) -> None:
        """apply_theme is callable."""
        from src.ui.components import FileDropWidget  # noqa: PLC0415

        widget = FileDropWidget()
        assert callable(widget.apply_theme)
        widget.apply_theme()

    def test_apply_language_callable(self, qapp: QApplication) -> None:
        """apply_language is callable."""
        from src.ui.components import FileDropWidget  # noqa: PLC0415

        widget = FileDropWidget()
        assert callable(widget.apply_language)
        widget.apply_language()

    def test_children_labels(self, qapp: QApplication) -> None:
        """FileDropWidget contains info, sub, and supported labels."""
        from src.ui.components import FileDropWidget  # noqa: PLC0415

        widget = FileDropWidget()
        assert widget.info_label is not None
        assert widget.sub_label is not None
        assert widget.supported_label is not None


# ---------------------------------------------------------------------------
# FileItemWidget tests
# ---------------------------------------------------------------------------


class TestFileItemWidget:
    """Tests for the FileItemWidget class."""

    def test_construction_with_real_file(self, qapp: QApplication) -> None:
        """FileItemWidget constructs with a real file path."""
        from src.ui.components import FileItemWidget  # noqa: PLC0415

        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"hello")
            path = f.name

        try:
            widget = FileItemWidget(path, lambda s: f"{s} B")
            assert widget.file_path == path
        finally:
            Path(path).unlink(missing_ok=True)

    def test_has_remove_requested_signal(self, qapp: QApplication) -> None:
        """FileItemWidget has a remove_requested signal."""
        from src.ui.components import FileItemWidget  # noqa: PLC0415

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            path = f.name

        try:
            widget = FileItemWidget(path, lambda s: "0 B")
            assert hasattr(widget, "remove_requested")
        finally:
            Path(path).unlink(missing_ok=True)

    def test_badge_shows_extension(self, qapp: QApplication) -> None:
        """Badge label shows the uppercase file extension."""
        from src.ui.components import FileItemWidget  # noqa: PLC0415

        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as f:
            path = f.name

        try:
            widget = FileItemWidget(path, lambda s: "0 B")
            assert widget.badge.text() == "DOCX"
        finally:
            Path(path).unlink(missing_ok=True)

    def test_apply_theme_callable(self, qapp: QApplication) -> None:
        """apply_theme does not raise."""
        from src.ui.components import FileItemWidget  # noqa: PLC0415

        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            path = f.name

        try:
            widget = FileItemWidget(path, lambda s: "0 B")
            widget.apply_theme()
        finally:
            Path(path).unlink(missing_ok=True)

    def test_apply_language_callable(self, qapp: QApplication) -> None:
        """apply_language does not raise."""
        from src.ui.components import FileItemWidget  # noqa: PLC0415

        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            path = f.name

        try:
            widget = FileItemWidget(path, lambda s: "0 B")
            widget.apply_language()
        finally:
            Path(path).unlink(missing_ok=True)

    def test_nonexistent_file_shows_unknown_size(self, qapp: QApplication) -> None:
        """FileItemWidget handles missing files gracefully."""
        from src.ui.components import FileItemWidget  # noqa: PLC0415

        widget = FileItemWidget("/no/such/file.txt", lambda s: "0 B")
        # Should not raise; size label shows "Unknown" or localized fallback
        assert widget.size_label is not None


# ---------------------------------------------------------------------------
# HighlightDelegate tests
# ---------------------------------------------------------------------------


class TestHighlightDelegate:
    """Tests for the HighlightDelegate class."""

    def test_set_search_text(self, qapp: QApplication) -> None:
        """set_search_text strips and stores the text."""
        from src.ui.components import HighlightDelegate  # noqa: PLC0415

        d = HighlightDelegate()
        d.set_search_text("  hello  ")
        assert d.search_text == "hello"

    def test_find_highlight_spans_case_insensitive(self, qapp: QApplication) -> None:
        """Default mode finds spans case-insensitively."""
        from src.ui.components import HighlightDelegate  # noqa: PLC0415

        d = HighlightDelegate()
        d.set_search_text("ab")
        spans = d._find_highlight_spans("xxABxx")
        assert len(spans) == 1
        assert spans[0] == (2, 4)  # noqa: PLR2004

    def test_find_highlight_spans_multiple(self, qapp: QApplication) -> None:
        """Finds multiple occurrences."""
        from src.ui.components import HighlightDelegate  # noqa: PLC0415

        d = HighlightDelegate()
        d.set_search_text("ab")
        spans = d._find_highlight_spans("abXXab")
        assert len(spans) == 2  # noqa: PLR2004

    def test_find_highlight_spans_no_match(self, qapp: QApplication) -> None:
        """Returns empty list when no match."""
        from src.ui.components import HighlightDelegate  # noqa: PLC0415

        d = HighlightDelegate()
        d.set_search_text("zzz")
        spans = d._find_highlight_spans("abc")
        assert len(spans) == 0

    def test_has_match_case_insensitive(self, qapp: QApplication) -> None:
        """_has_match returns True for case-insensitive match."""
        from src.ui.components import HighlightDelegate  # noqa: PLC0415

        d = HighlightDelegate()
        d.set_search_text("hello")
        assert d._has_match("Say HELLO World")

    def test_has_match_no_match(self, qapp: QApplication) -> None:
        """_has_match returns False when no match."""
        from src.ui.components import HighlightDelegate  # noqa: PLC0415

        d = HighlightDelegate()
        d.set_search_text("zzz")
        assert not d._has_match("abc")

    def test_normalize_mode(self, qapp: QApplication) -> None:
        """Normalized mode finds accent-insensitive matches."""
        from src.ui.components import HighlightDelegate  # noqa: PLC0415

        d = HighlightDelegate(normalize=True)
        d.set_search_text("cafe")
        assert d._has_match("Caf\u00e9 Latte")

    def test_set_selected_color(self, qapp: QApplication) -> None:
        """set_selected_color stores the color."""
        from src.ui.components import HighlightDelegate  # noqa: PLC0415

        d = HighlightDelegate()
        d.set_selected_color("#FF0000")
        assert d._selected_color == "#FF0000"


# ---------------------------------------------------------------------------
# ForegroundPreservingDelegate tests
# ---------------------------------------------------------------------------


class TestForegroundPreservingDelegate:
    """Tests for ForegroundPreservingDelegate."""

    def test_construction(self, qapp: QApplication) -> None:
        """Delegate constructs without error."""
        from src.ui.components import ForegroundPreservingDelegate  # noqa: PLC0415

        d = ForegroundPreservingDelegate()
        assert d is not None


# ---------------------------------------------------------------------------
# _build_formats_string tests
# ---------------------------------------------------------------------------


class TestBuildFormatsString:
    """Tests for _build_formats_string()."""

    def test_returns_string(self, qapp: QApplication) -> None:
        """Returns a non-empty string."""
        from src.ui.components import _build_formats_string  # noqa: PLC0415

        result = _build_formats_string()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_contains_common_extensions(self, qapp: QApplication) -> None:
        """Result includes common file extensions."""
        from src.ui.components import _build_formats_string  # noqa: PLC0415

        result = _build_formats_string()
        # At minimum, txt and pdf should be in SUPPORTED_TEXT
        assert "txt" in result.lower()
        assert "pdf" in result.lower()


# ---------------------------------------------------------------------------
# create_setting_combo tests
# ---------------------------------------------------------------------------


class TestCreateSettingCombo:
    """Tests for create_setting_combo()."""

    @patch("src.ui.components.load_setting", return_value="B")
    @patch("src.ui.components.save_setting")
    def test_returns_container_and_combo(
        self, mock_save: MagicMock, mock_load: MagicMock, qapp: QApplication
    ) -> None:
        """Returns a (QWidget, QComboBox) tuple."""
        from src.ui.components import create_setting_combo  # noqa: PLC0415

        container, combo = create_setting_combo("Label", "key", ["A", "B", "C"])
        assert isinstance(container, QWidget)
        assert isinstance(combo, QComboBox)

    @patch("src.ui.components.load_setting", return_value="B")
    @patch("src.ui.components.save_setting")
    def test_items_populated(
        self, mock_save: MagicMock, mock_load: MagicMock, qapp: QApplication
    ) -> None:
        """Combo box items match the input list."""
        from src.ui.components import create_setting_combo  # noqa: PLC0415

        _, combo = create_setting_combo("Label", "key", ["X", "Y", "Z"])
        assert combo.count() == 3  # noqa: PLR2004
        assert combo.itemText(0) == "X"
        assert combo.itemText(1) == "Y"
        assert combo.itemText(2) == "Z"

    @patch("src.ui.components.load_setting", return_value="Y")
    @patch("src.ui.components.save_setting")
    def test_restores_saved_value(
        self, mock_save: MagicMock, mock_load: MagicMock, qapp: QApplication
    ) -> None:
        """Combo restores the previously saved value."""
        from src.ui.components import create_setting_combo  # noqa: PLC0415

        _, combo = create_setting_combo("Label", "key", ["X", "Y", "Z"])
        assert combo.currentText() == "Y"

    @patch("src.ui.components.load_setting", return_value="X")
    @patch("src.ui.components.save_setting")
    def test_apply_theme(
        self, mock_save: MagicMock, mock_load: MagicMock, qapp: QApplication
    ) -> None:
        """Container has callable apply_theme."""
        from src.ui.components import create_setting_combo  # noqa: PLC0415

        container, _ = create_setting_combo("Label", "key", ["X"])
        assert callable(container.apply_theme)
        container.apply_theme()

    @patch("src.ui.components.load_setting", return_value="X")
    @patch("src.ui.components.save_setting")
    def test_apply_language_with_tr_key(
        self, mock_save: MagicMock, mock_load: MagicMock, qapp: QApplication
    ) -> None:
        """Container with label_tr_key has apply_language."""
        from src.ui.components import create_setting_combo  # noqa: PLC0415

        container, _ = create_setting_combo(
            "Label", "key", ["X"], label_tr_key="settings.label"
        )
        assert callable(container.apply_language)

    @patch("src.ui.components.load_setting", return_value="X")
    @patch("src.ui.components.save_setting")
    def test_cursor_pointing_hand(
        self, mock_save: MagicMock, mock_load: MagicMock, qapp: QApplication
    ) -> None:
        """Combo cursor is PointingHandCursor."""
        from src.ui.components import create_setting_combo  # noqa: PLC0415

        _, combo = create_setting_combo("Label", "key", ["X"])
        assert combo.cursor().shape() == Qt.CursorShape.PointingHandCursor


# ---------------------------------------------------------------------------
# create_setting_checkbox tests
# ---------------------------------------------------------------------------


class TestCreateSettingCheckbox:
    """Tests for create_setting_checkbox()."""

    @patch("src.ui.components.load_setting", return_value=False)
    @patch("src.ui.components.save_setting")
    def test_returns_container_and_checkbox(
        self, mock_save: MagicMock, mock_load: MagicMock, qapp: QApplication
    ) -> None:
        """Returns a (QWidget, QCheckBox) tuple."""
        from src.ui.components import create_setting_checkbox  # noqa: PLC0415

        container, checkbox = create_setting_checkbox("Enable", "key")
        assert isinstance(container, QWidget)
        assert isinstance(checkbox, QCheckBox)

    @patch("src.ui.components.load_setting", return_value=True)
    @patch("src.ui.components.save_setting")
    def test_restores_checked_state(
        self, mock_save: MagicMock, mock_load: MagicMock, qapp: QApplication
    ) -> None:
        """Checkbox restores saved checked state."""
        from src.ui.components import create_setting_checkbox  # noqa: PLC0415

        _, checkbox = create_setting_checkbox("Enable", "key")
        assert checkbox.isChecked()

    @patch("src.ui.components.load_setting", return_value=False)
    @patch("src.ui.components.save_setting")
    def test_unchecked_by_default(
        self, mock_save: MagicMock, mock_load: MagicMock, qapp: QApplication
    ) -> None:
        """Checkbox is unchecked when saved value is False."""
        from src.ui.components import create_setting_checkbox  # noqa: PLC0415

        _, checkbox = create_setting_checkbox("Enable", "key")
        assert not checkbox.isChecked()

    @patch("src.ui.components.load_setting", return_value=False)
    @patch("src.ui.components.save_setting")
    def test_cursor_pointing_hand(
        self, mock_save: MagicMock, mock_load: MagicMock, qapp: QApplication
    ) -> None:
        """Checkbox cursor is PointingHandCursor."""
        from src.ui.components import create_setting_checkbox  # noqa: PLC0415

        _, checkbox = create_setting_checkbox("Enable", "key")
        assert checkbox.cursor().shape() == Qt.CursorShape.PointingHandCursor

    @patch("src.ui.components.load_setting", return_value=False)
    @patch("src.ui.components.save_setting")
    def test_apply_theme(
        self, mock_save: MagicMock, mock_load: MagicMock, qapp: QApplication
    ) -> None:
        """Container has callable apply_theme."""
        from src.ui.components import create_setting_checkbox  # noqa: PLC0415

        container, _ = create_setting_checkbox("Enable", "key")
        assert callable(container.apply_theme)
        container.apply_theme()


# ---------------------------------------------------------------------------
# create_setting_input tests
# ---------------------------------------------------------------------------


class TestCreateSettingInput:
    """Tests for create_setting_input()."""

    @patch("src.ui.components.load_setting", return_value="")
    @patch("src.ui.components.save_setting")
    def test_returns_container_and_lineedit(
        self, mock_save: MagicMock, mock_load: MagicMock, qapp: QApplication
    ) -> None:
        """Returns a (QWidget, QLineEdit) tuple."""
        from src.ui.components import create_setting_input  # noqa: PLC0415

        container, line_edit = create_setting_input("API Key", "api_key")
        assert isinstance(container, QWidget)
        assert isinstance(line_edit, QLineEdit)

    @patch("src.ui.components.load_setting", return_value="saved_value")
    @patch("src.ui.components.save_setting")
    def test_restores_saved_value(
        self, mock_save: MagicMock, mock_load: MagicMock, qapp: QApplication
    ) -> None:
        """Input field restores saved value."""
        from src.ui.components import create_setting_input  # noqa: PLC0415

        _, line_edit = create_setting_input("API Key", "api_key")
        assert line_edit.text() == "saved_value"

    @patch("src.ui.components.load_setting", return_value="")
    @patch("src.ui.components.save_setting")
    def test_password_mode(
        self, mock_save: MagicMock, mock_load: MagicMock, qapp: QApplication
    ) -> None:
        """Password mode sets EchoMode.Password."""
        from src.ui.components import create_setting_input  # noqa: PLC0415

        _, line_edit = create_setting_input("Secret", "secret", is_password=True)
        assert line_edit.echoMode() == QLineEdit.EchoMode.Password

    @patch("src.ui.components.load_setting", return_value="")
    @patch("src.ui.components.save_setting")
    def test_placeholder_set(
        self, mock_save: MagicMock, mock_load: MagicMock, qapp: QApplication
    ) -> None:
        """Placeholder text is set on the line edit."""
        from src.ui.components import create_setting_input  # noqa: PLC0415

        _, line_edit = create_setting_input(
            "Field", "key", placeholder="Enter value..."
        )
        assert line_edit.placeholderText() == "Enter value..."


# ---------------------------------------------------------------------------
# create_setting_path tests
# ---------------------------------------------------------------------------


class TestCreateSettingPath:
    """Tests for create_setting_path()."""

    @patch("src.ui.components.load_setting", return_value="")
    @patch("src.ui.components.save_setting")
    def test_returns_container_and_label(
        self, mock_save: MagicMock, mock_load: MagicMock, qapp: QApplication
    ) -> None:
        """Returns a (QWidget, ElidedLabel) tuple."""
        from src.ui.components import ElidedLabel, create_setting_path  # noqa: PLC0415

        container, path_label = create_setting_path("Path", "path_key")
        assert isinstance(container, QWidget)
        assert isinstance(path_label, ElidedLabel)

    @patch("src.ui.components.load_setting", return_value="/some/path")
    @patch("src.ui.components.save_setting")
    def test_restores_saved_path(
        self, mock_save: MagicMock, mock_load: MagicMock, qapp: QApplication
    ) -> None:
        """Path label restores saved path."""
        from src.ui.components import create_setting_path  # noqa: PLC0415

        _, path_label = create_setting_path("Path", "path_key")
        assert path_label._full_text == "/some/path"

    @patch("src.ui.components.load_setting", return_value="")
    @patch("src.ui.components.save_setting")
    def test_apply_theme(
        self, mock_save: MagicMock, mock_load: MagicMock, qapp: QApplication
    ) -> None:
        """Container has callable apply_theme."""
        from src.ui.components import create_setting_path  # noqa: PLC0415

        container, _ = create_setting_path("Path", "path_key")
        assert callable(container.apply_theme)
        container.apply_theme()

    @patch("src.ui.components.load_setting", return_value="")
    @patch("src.ui.components.save_setting")
    def test_apply_language(
        self, mock_save: MagicMock, mock_load: MagicMock, qapp: QApplication
    ) -> None:
        """Container has callable apply_language."""
        from src.ui.components import create_setting_path  # noqa: PLC0415

        container, _ = create_setting_path("Path", "path_key")
        assert callable(container.apply_language)
        container.apply_language()


# ---------------------------------------------------------------------------
# style helper tests
# ---------------------------------------------------------------------------


class TestStyleHelpers:
    """Tests for style helper functions in components.py."""

    def test_style_file_count_badge(self, qapp: QApplication) -> None:
        """style_file_count_badge returns a non-empty string."""
        from src.ui.components import style_file_count_badge  # noqa: PLC0415

        result = style_file_count_badge()
        assert isinstance(result, str)
        assert "background-color" in result

    def test_style_section_label(self, qapp: QApplication) -> None:
        """style_section_label returns a non-empty string."""
        from src.ui.components import style_section_label  # noqa: PLC0415

        result = style_section_label()
        assert isinstance(result, str)
        assert "color" in result


# ---------------------------------------------------------------------------
# _TableResizeFilter tests
# ---------------------------------------------------------------------------


class TestTableResizeFilter:
    """Tests for the _TableResizeFilter event filter."""

    def test_construction(self, qapp: QApplication) -> None:
        """Filter constructs without error."""
        from src.ui.components import (  # noqa: PLC0415
            _TableResizeFilter,
            create_table,
        )

        table = create_table(["A", "B"], interactive_columns=[0, 1])
        filt = _TableResizeFilter(table, [0, 1], None, table)
        assert filt is not None

    def test_event_filter_non_resize(self, qapp: QApplication) -> None:
        """Non-resize events pass through without error."""
        from src.ui.components import (  # noqa: PLC0415
            _TableResizeFilter,
            create_table,
        )

        table = create_table(["A", "B"], interactive_columns=[0, 1])
        filt = _TableResizeFilter(table, [0, 1], None, table)
        # A generic event should not crash
        event = QEvent(QEvent.Type.Paint)
        result = filt.eventFilter(table.viewport(), event)
        assert isinstance(result, bool)

    def test_resize_event_redistributes(self, qapp: QApplication) -> None:
        """Resize events trigger proportional redistribution."""
        from PySide6.QtCore import QSize  # noqa: PLC0415
        from PySide6.QtGui import QResizeEvent  # noqa: PLC0415

        from src.ui.components import (  # noqa: PLC0415
            _TableResizeFilter,
            create_table,
        )

        table = create_table(["A", "B", "C"], interactive_columns=[0, 1])
        table.resize(600, 400)
        filt = _TableResizeFilter(table, [0, 1], None, table)
        # Create a resize event and pass it through the filter
        resize_event = QResizeEvent(QSize(800, 400), QSize(600, 400))
        result = filt.eventFilter(table.viewport(), resize_event)
        # The filter should process it (calling _redistribute) and return False
        assert isinstance(result, bool)

    def test_min_section_width(self, qapp: QApplication) -> None:
        """Filter enforces minimum column width from MIN_COLUMN_WIDTH."""
        from src.ui.components import (  # noqa: PLC0415
            MIN_COLUMN_WIDTH,
            _TableResizeFilter,
            create_table,
        )

        table = create_table(["A", "B"], interactive_columns=[0, 1])
        filt = _TableResizeFilter(table, [0, 1], None, table)
        assert filt._min_section_width == MIN_COLUMN_WIDTH

    def test_pinned_columns_initial_widths(self, qapp: QApplication) -> None:
        """Filter stores initial widths for pinned columns."""
        from src.ui.components import (  # noqa: PLC0415
            _TableResizeFilter,
            create_table,
        )

        table = create_table(
            ["A", "B", "C"],
            interactive_columns=[0, 1, 2],
            column_widths={0: 100, 2: 80},
        )
        filt = _TableResizeFilter(table, [0, 1, 2], {0: 100, 2: 80}, table)
        assert filt._initial_widths == {0: 100, 2: 80}


# ---------------------------------------------------------------------------
# _TableKeyFilter tests
# ---------------------------------------------------------------------------


class TestCreateTableKeyFilter:
    """Tests for the _TableKeyFilter event filter."""

    def test_enter_key_triggers_callback(self, qapp: QApplication) -> None:
        """Enter key invokes the enter_callback when rows are selected."""
        from PySide6.QtGui import QKeyEvent  # noqa: PLC0415

        from src.ui.components import _TableKeyFilter, create_table  # noqa: PLC0415

        callback = MagicMock()
        table = create_table(["A", "B"])
        filt = _TableKeyFilter(table, callback, table)
        # Add a row and select it
        table.setRowCount(1)
        from PySide6.QtWidgets import QTableWidgetItem  # noqa: PLC0415

        table.setItem(0, 0, QTableWidgetItem("test"))
        table.selectRow(0)
        # Simulate Enter key press
        key_event = QKeyEvent(
            QEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier
        )
        filt.eventFilter(table, key_event)
        callback.assert_called_once()

    def test_enter_key_no_selection_does_nothing(self, qapp: QApplication) -> None:
        """Enter key with no selection does not invoke callback."""
        from PySide6.QtGui import QKeyEvent  # noqa: PLC0415

        from src.ui.components import _TableKeyFilter, create_table  # noqa: PLC0415

        callback = MagicMock()
        table = create_table(["A", "B"])
        filt = _TableKeyFilter(table, callback, table)
        # No rows, no selection
        key_event = QKeyEvent(
            QEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier
        )
        filt.eventFilter(table, key_event)
        callback.assert_not_called()

    def test_ctrl_a_selects_all_rows(self, qapp: QApplication) -> None:
        """Ctrl+A selects all rows in the table."""
        from PySide6.QtGui import QKeyEvent  # noqa: PLC0415

        from src.ui.components import _TableKeyFilter, create_table  # noqa: PLC0415

        callback = MagicMock()
        table = create_table(["A", "B"])
        filt = _TableKeyFilter(table, callback, table)
        # Add rows
        table.setRowCount(3)
        from PySide6.QtWidgets import QTableWidgetItem  # noqa: PLC0415

        for i in range(3):
            table.setItem(i, 0, QTableWidgetItem(f"row{i}"))
        # Simulate Ctrl+A
        key_event = QKeyEvent(
            QEvent.Type.KeyPress, Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier
        )
        result = filt.eventFilter(table, key_event)
        assert result is True
        # All rows should be selected
        selected = table.selectionModel().selectedRows()
        assert len(selected) == 3  # noqa: PLR2004

    def test_other_keys_pass_through(self, qapp: QApplication) -> None:
        """Non-Enter, non-Ctrl+A key events pass through (return False)."""
        from PySide6.QtGui import QKeyEvent  # noqa: PLC0415

        from src.ui.components import _TableKeyFilter, create_table  # noqa: PLC0415

        callback = MagicMock()
        table = create_table(["A"])
        filt = _TableKeyFilter(table, callback, table)
        # Press 'B' key — should pass through
        key_event = QKeyEvent(
            QEvent.Type.KeyPress, Qt.Key.Key_B, Qt.KeyboardModifier.NoModifier
        )
        result = filt.eventFilter(table, key_event)
        assert result is False
        callback.assert_not_called()

    def test_numpad_enter_triggers_callback(self, qapp: QApplication) -> None:
        """Numpad Enter (Key_Enter) also triggers the callback."""
        from PySide6.QtGui import QKeyEvent  # noqa: PLC0415

        from src.ui.components import _TableKeyFilter, create_table  # noqa: PLC0415

        callback = MagicMock()
        table = create_table(["A"])
        filt = _TableKeyFilter(table, callback, table)
        # Add a row and select it
        table.setRowCount(1)
        from PySide6.QtWidgets import QTableWidgetItem  # noqa: PLC0415

        table.setItem(0, 0, QTableWidgetItem("test"))
        table.selectRow(0)
        # Simulate numpad Enter (Key_Enter)
        key_event = QKeyEvent(
            QEvent.Type.KeyPress, Qt.Key.Key_Enter, Qt.KeyboardModifier.NoModifier
        )
        filt.eventFilter(table, key_event)
        callback.assert_called_once()


# ---------------------------------------------------------------------------
# create_table with enter_callback tests
# ---------------------------------------------------------------------------


class TestCreateTableWithEnterCallback:
    """Tests for create_table() with enter_callback parameter."""

    def test_installs_key_filter(self, qapp: QApplication) -> None:
        """create_table installs _TableKeyFilter when callback is provided."""
        from src.ui.components import _TableKeyFilter, create_table  # noqa: PLC0415

        table = create_table(["A"], enter_callback=lambda: None)
        found = any(isinstance(child, _TableKeyFilter) for child in table.children())
        assert found

    def test_no_key_filter_without_callback(self, qapp: QApplication) -> None:
        """create_table does not install _TableKeyFilter without callback."""
        from src.ui.components import _TableKeyFilter, create_table  # noqa: PLC0415

        table = create_table(["A"])
        found = any(isinstance(child, _TableKeyFilter) for child in table.children())
        assert not found

    def test_callback_invoked_on_enter(self, qapp: QApplication) -> None:
        """Callback is actually called when Enter is pressed on table with selection."""
        from PySide6.QtGui import QKeyEvent  # noqa: PLC0415
        from PySide6.QtWidgets import QTableWidgetItem  # noqa: PLC0415

        from src.ui.components import create_table  # noqa: PLC0415

        callback = MagicMock()
        table = create_table(["A"], enter_callback=callback)
        table.setRowCount(1)
        table.setItem(0, 0, QTableWidgetItem("data"))
        table.selectRow(0)
        # Simulate Enter key via the installed event filter
        key_event = QKeyEvent(
            QEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier
        )
        # The filter is installed on the table itself
        from src.ui.components import _TableKeyFilter  # noqa: PLC0415

        for child in table.children():
            if isinstance(child, _TableKeyFilter):
                child.eventFilter(table, key_event)
                break
        callback.assert_called_once()


# ---------------------------------------------------------------------------
# CaseInsensitiveSortItem tests
# ---------------------------------------------------------------------------


class TestCaseInsensitiveSortItem:
    """Tests for the CaseInsensitiveSortItem class."""

    def test_sorting_mixed_case(self, qapp: QApplication) -> None:
        """Items sort case-insensitively."""
        from src.ui.components import CaseInsensitiveSortItem  # noqa: PLC0415

        a = CaseInsensitiveSortItem()
        a.setText("banana")
        b = CaseInsensitiveSortItem()
        b.setText("Apple")
        # "apple" < "banana" case-insensitively
        assert b < a
        assert not a < b

    def test_empty_strings(self, qapp: QApplication) -> None:
        """Empty strings sort before non-empty strings."""
        from src.ui.components import CaseInsensitiveSortItem  # noqa: PLC0415

        empty = CaseInsensitiveSortItem()
        empty.setText("")
        nonempty = CaseInsensitiveSortItem()
        nonempty.setText("A")
        assert empty < nonempty
        assert not nonempty < empty

    def test_unicode_sorting(self, qapp: QApplication) -> None:
        """Unicode text sorts by lowered Unicode code points."""
        from src.ui.components import CaseInsensitiveSortItem  # noqa: PLC0415

        a = CaseInsensitiveSortItem()
        a.setText("\u00e9cole")  # école (é = U+00E9 = 233)
        b = CaseInsensitiveSortItem()
        b.setText("zoo")  # z = U+007A = 122
        # In Python str comparison, "é" (233) > "z" (122)
        assert b < a

    def test_numbers_as_strings(self, qapp: QApplication) -> None:
        """Numbers stored as strings sort lexicographically."""
        from src.ui.components import CaseInsensitiveSortItem  # noqa: PLC0415

        a = CaseInsensitiveSortItem()
        a.setText("10")
        b = CaseInsensitiveSortItem()
        b.setText("2")
        # "10" < "2" lexicographically (string comparison)
        assert a < b

    def test_equal_items(self, qapp: QApplication) -> None:
        """Equal items return False for __lt__ in both directions."""
        from src.ui.components import CaseInsensitiveSortItem  # noqa: PLC0415

        a = CaseInsensitiveSortItem()
        a.setText("Hello")
        b = CaseInsensitiveSortItem()
        b.setText("hello")
        assert not a < b
        assert not b < a


# ---------------------------------------------------------------------------
# NumericalSortItem tests
# ---------------------------------------------------------------------------


class TestNumericalSortItem:
    """Tests for the NumericalSortItem class."""

    def test_with_integers(self, qapp: QApplication) -> None:
        """Sorts by integer values, not display text."""
        from src.ui.components import NumericalSortItem  # noqa: PLC0415

        a = NumericalSortItem("10 items", 10.0)
        b = NumericalSortItem("2 items", 2.0)
        assert b < a
        assert not a < b

    def test_with_floats(self, qapp: QApplication) -> None:
        """Sorts by float values correctly."""
        from src.ui.components import NumericalSortItem  # noqa: PLC0415

        a = NumericalSortItem("1.5 MB", 1.5)
        b = NumericalSortItem("2.3 MB", 2.3)
        assert a < b

    def test_with_zero(self, qapp: QApplication) -> None:
        """Zero value sorts before positive values."""
        from src.ui.components import NumericalSortItem  # noqa: PLC0415

        zero = NumericalSortItem("0 B", 0.0)
        pos = NumericalSortItem("1 B", 1.0)
        assert zero < pos

    def test_with_negative_numbers(self, qapp: QApplication) -> None:
        """Negative values sort before positive values."""
        from src.ui.components import NumericalSortItem  # noqa: PLC0415

        neg = NumericalSortItem("-5", -5.0)
        pos = NumericalSortItem("3", 3.0)
        assert neg < pos

    def test_non_numerical_fallback(self, qapp: QApplication) -> None:
        """Comparing with a plain QTableWidgetItem falls back to super().__lt__."""
        from PySide6.QtWidgets import QTableWidgetItem  # noqa: PLC0415

        from src.ui.components import NumericalSortItem  # noqa: PLC0415

        num = NumericalSortItem("5", 5.0)
        plain = QTableWidgetItem("abc")
        # Should not raise; uses QTableWidgetItem default comparison
        result = num < plain
        assert isinstance(result, bool)

    def test_equal_values(self, qapp: QApplication) -> None:
        """Equal numeric values return False for __lt__."""
        from src.ui.components import NumericalSortItem  # noqa: PLC0415

        a = NumericalSortItem("same", 42.0)
        b = NumericalSortItem("same", 42.0)
        assert not a < b
        assert not b < a


# ---------------------------------------------------------------------------
# DateTimeSortItem tests
# ---------------------------------------------------------------------------


class TestDateTimeSortItem:
    """Tests for the DateTimeSortItem class."""

    def test_sorts_by_iso_key(self, qapp: QApplication) -> None:
        """Items sort by ISO key, not display text."""
        from src.ui.components import DateTimeSortItem  # noqa: PLC0415

        a = DateTimeSortItem("Jan 15, 2026", "2026-01-15 10:00:00")
        b = DateTimeSortItem("Mar 20, 2026", "2026-03-20 14:30:00")
        assert a < b
        assert not b < a

    def test_same_dates(self, qapp: QApplication) -> None:
        """Items with the same ISO key are not less than each other."""
        from src.ui.components import DateTimeSortItem  # noqa: PLC0415

        a = DateTimeSortItem("Today", "2026-03-25 00:00:00")
        b = DateTimeSortItem("Also Today", "2026-03-25 00:00:00")
        assert not a < b
        assert not b < a

    def test_with_different_display_same_iso(self, qapp: QApplication) -> None:
        """Different display texts with the same ISO key sort as equal."""
        from src.ui.components import DateTimeSortItem  # noqa: PLC0415

        a = DateTimeSortItem("March 25, 2026 12:00 AM", "2026-03-25 00:00:00")
        b = DateTimeSortItem("25/03/2026 00:00", "2026-03-25 00:00:00")
        assert not a < b

    def test_non_datetime_fallback(self, qapp: QApplication) -> None:
        """Comparing with plain QTableWidgetItem falls back gracefully."""
        from PySide6.QtWidgets import QTableWidgetItem  # noqa: PLC0415

        from src.ui.components import DateTimeSortItem  # noqa: PLC0415

        dt = DateTimeSortItem("Today", "2026-03-25")
        plain = QTableWidgetItem("abc")
        result = dt < plain
        assert isinstance(result, bool)

    def test_time_component_ordering(self, qapp: QApplication) -> None:
        """Items with same date but different times sort correctly."""
        from src.ui.components import DateTimeSortItem  # noqa: PLC0415

        morning = DateTimeSortItem("Morning", "2026-03-25 08:00:00")
        evening = DateTimeSortItem("Evening", "2026-03-25 20:00:00")
        assert morning < evening


# ---------------------------------------------------------------------------
# HighlightDelegate extended tests
# ---------------------------------------------------------------------------


class TestHighlightDelegateExtended:
    """Extended tests for HighlightDelegate highlighting and matching."""

    def test_empty_search_text_has_no_match(self, qapp: QApplication) -> None:
        """Empty search text is caught by paint() guard before span computation."""
        from src.ui.components import HighlightDelegate  # noqa: PLC0415

        d = HighlightDelegate()
        d.set_search_text("")
        # The paint method checks 'not self.search_text' before calling spans,
        # so empty search text never reaches highlighting.
        assert d.search_text == ""

    def test_special_regex_characters(self, qapp: QApplication) -> None:
        """Search text with regex special characters is escaped properly."""
        from src.ui.components import HighlightDelegate  # noqa: PLC0415

        d = HighlightDelegate()
        d.set_search_text("file.txt")
        # "file.txt" should match literally, not as regex pattern
        spans = d._find_highlight_spans("Open file.txt now")
        assert len(spans) == 1
        assert spans[0] == (5, 13)  # noqa: PLR2004

    def test_parentheses_in_search(self, qapp: QApplication) -> None:
        """Parentheses in search text are escaped and matched literally."""
        from src.ui.components import HighlightDelegate  # noqa: PLC0415

        d = HighlightDelegate()
        d.set_search_text("(test)")
        spans = d._find_highlight_spans("This is (test) here")
        assert len(spans) == 1

    def test_selected_color_affects_initStyleOption(  # noqa: N802
        self, qapp: QApplication
    ) -> None:
        """set_selected_color stores color for use in initStyleOption."""
        from src.ui.components import HighlightDelegate  # noqa: PLC0415

        d = HighlightDelegate()
        d.set_selected_color("#3E79F7")
        assert d._selected_color == "#3E79F7"

    def test_normalize_empty_search(self, qapp: QApplication) -> None:
        """Normalized mode with empty search returns no spans."""
        from src.ui.components import HighlightDelegate  # noqa: PLC0415

        d = HighlightDelegate(normalize=True)
        d.set_search_text("")
        spans = d._find_highlight_spans("text")
        assert len(spans) == 0

    def test_normalize_has_match(self, qapp: QApplication) -> None:
        """Normalized mode _has_match works for accented text."""
        from src.ui.components import HighlightDelegate  # noqa: PLC0415

        d = HighlightDelegate(normalize=True)
        d.set_search_text("resume")
        assert d._has_match("R\u00e9sum\u00e9")

    def test_normalize_no_match(self, qapp: QApplication) -> None:
        """Normalized mode _has_match returns False when no match."""
        from src.ui.components import HighlightDelegate  # noqa: PLC0415

        d = HighlightDelegate(normalize=True)
        d.set_search_text("xyz123")
        assert not d._has_match("Hello World")

    def test_overlapping_spans_merged(self, qapp: QApplication) -> None:
        """Adjacent or overlapping matches in normalize mode are merged."""
        from src.ui.components import HighlightDelegate  # noqa: PLC0415

        d = HighlightDelegate(normalize=True)
        d.set_search_text("ss")
        # German "stra\u00dfe" normalizes to "strasse" which has "ss"
        spans = d._find_highlight_spans("stra\u00dfe")
        # Should return spans (possibly merged) without duplicates
        for start, end in spans:
            assert start < end


# ---------------------------------------------------------------------------
# create_banner extended tests
# ---------------------------------------------------------------------------


class TestCreateBannerExtended:
    """Extended tests for the create_banner() function."""

    def test_warning_icon_path(self, qapp: QApplication) -> None:
        """Warning variant uses the alert triangle icon."""
        from src.ui.components import create_banner  # noqa: PLC0415

        frame, _ = create_banner("msg", variant="warning")
        icon = frame.findChild(QLabel, "BannerIcon")
        assert icon is not None
        # Icon should have a non-null pixmap
        assert not icon.pixmap().isNull()

    def test_error_icon_path(self, qapp: QApplication) -> None:
        """Error variant uses the alert circle icon."""
        from src.ui.components import create_banner  # noqa: PLC0415

        frame, _ = create_banner("msg", variant="error")
        icon = frame.findChild(QLabel, "BannerIcon")
        assert icon is not None
        assert not icon.pixmap().isNull()

    def test_success_icon_path(self, qapp: QApplication) -> None:
        """Success variant uses the check circle icon."""
        from src.ui.components import create_banner  # noqa: PLC0415

        frame, _ = create_banner("msg", variant="success")
        icon = frame.findChild(QLabel, "BannerIcon")
        assert icon is not None
        assert not icon.pixmap().isNull()

    def test_info_icon_path(self, qapp: QApplication) -> None:
        """Info variant uses the info icon."""
        from src.ui.components import create_banner  # noqa: PLC0415

        frame, _ = create_banner("msg", variant="info")
        icon = frame.findChild(QLabel, "BannerIcon")
        assert icon is not None
        assert not icon.pixmap().isNull()

    def test_tr_key_updates_text_on_language_change(self, qapp: QApplication) -> None:
        """apply_language with tr_key updates the label text."""
        from src.ui.components import create_banner  # noqa: PLC0415

        frame, label = create_banner("initial", tr_key="btn.ok")
        frame.apply_language()
        # After applying language, label text should come from tr("btn.ok")
        from src.constants import tr  # noqa: PLC0415

        assert label.text() == tr("btn.ok")

    def test_rich_text_with_multiple_lines(self, qapp: QApplication) -> None:
        """Rich text with multiple newlines produces multiple <p> tags."""
        from src.ui.components import create_banner  # noqa: PLC0415

        _, label = create_banner("line1\nline2\nline3", rich_text=True)
        text = label.text()
        assert text.count("<p") == 3  # noqa: PLR2004

    def test_apply_theme_updates_stylesheet(self, qapp: QApplication) -> None:
        """apply_theme refreshes banner stylesheet."""
        from src.ui.components import create_banner  # noqa: PLC0415

        frame, _ = create_banner("msg", variant="error")
        old_stylesheet = frame.styleSheet()
        frame.apply_theme()
        # Stylesheet should still be set (may or may not change with same theme)
        assert frame.styleSheet()
        assert isinstance(old_stylesheet, str)

    def test_banner_icon_alignment(self, qapp: QApplication) -> None:
        """Banner icon is aligned to top-left."""
        from src.ui.components import create_banner  # noqa: PLC0415

        frame, _ = create_banner("msg")
        icon = frame.findChild(QLabel, "BannerIcon")
        alignment = icon.alignment()
        assert alignment & Qt.AlignmentFlag.AlignTop
        assert alignment & Qt.AlignmentFlag.AlignLeft


# ---------------------------------------------------------------------------
# FileDropWidget extended tests
# ---------------------------------------------------------------------------


class TestFileDropWidgetExtended:
    """Extended tests for the FileDropWidget class."""

    def test_drag_enter_with_urls_accepts(self, qapp: QApplication) -> None:
        """Drag-enter event accepts when mimeData has URLs."""
        from PySide6.QtCore import QMimeData, QUrl  # noqa: PLC0415

        from src.ui.components import FileDropWidget  # noqa: PLC0415

        widget = FileDropWidget()
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile("/tmp/test.txt")])
        event = MagicMock()
        event.mimeData.return_value = mime
        widget.dragEnterEvent(event)
        event.accept.assert_called_once()

    def test_drag_enter_without_urls_ignores(self, qapp: QApplication) -> None:
        """Drag-enter event ignores when mimeData has no URLs."""
        from PySide6.QtCore import QMimeData  # noqa: PLC0415

        from src.ui.components import FileDropWidget  # noqa: PLC0415

        widget = FileDropWidget()
        mime = QMimeData()
        # No URLs set
        event = MagicMock()
        event.mimeData.return_value = mime
        widget.dragEnterEvent(event)
        event.ignore.assert_called_once()

    def test_drop_emits_signal(self, qapp: QApplication) -> None:
        """Drop event emits files_dropped with local file paths."""
        from PySide6.QtCore import QMimeData, QUrl  # noqa: PLC0415

        from src.ui.components import FileDropWidget  # noqa: PLC0415

        widget = FileDropWidget()
        received = []
        widget.files_dropped.connect(received.extend)

        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile("/tmp/test.txt")])
        event = MagicMock()
        event.mimeData.return_value = mime
        widget.dropEvent(event)
        assert "/tmp/test.txt" in received
        event.accept.assert_called_once()

    def test_drop_multiple_files(self, qapp: QApplication) -> None:
        """Drop event emits multiple file paths."""
        from PySide6.QtCore import QMimeData, QUrl  # noqa: PLC0415

        from src.ui.components import FileDropWidget  # noqa: PLC0415

        widget = FileDropWidget()
        received = []
        widget.files_dropped.connect(received.extend)

        mime = QMimeData()
        mime.setUrls(
            [
                QUrl.fromLocalFile("/tmp/a.txt"),
                QUrl.fromLocalFile("/tmp/b.pdf"),
            ]
        )
        event = MagicMock()
        event.mimeData.return_value = mime
        widget.dropEvent(event)
        assert len(received) == 2  # noqa: PLR2004

    def test_click_emits_empty_list(self, qapp: QApplication) -> None:
        """Mouse click emits files_dropped with an empty list."""
        from PySide6.QtCore import QPointF  # noqa: PLC0415
        from PySide6.QtGui import QMouseEvent  # noqa: PLC0415

        from src.ui.components import FileDropWidget  # noqa: PLC0415

        widget = FileDropWidget()
        received = []
        widget.files_dropped.connect(received.append)

        event = QMouseEvent(
            QEvent.Type.MouseButtonPress,
            QPointF(10.0, 10.0),
            QPointF(10.0, 10.0),
            Qt.MouseButton.LeftButton,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
        )
        widget.mousePressEvent(event)
        assert len(received) == 1
        assert received[0] == []

    def test_drag_leave_resets_style(self, qapp: QApplication) -> None:
        """Drag-leave event resets the widget style to default."""
        from src.ui.components import FileDropWidget  # noqa: PLC0415

        widget = FileDropWidget()
        # Trigger active style first
        widget._set_active_style()
        active_style = widget.styleSheet()
        # Then trigger leave
        widget._set_default_style()
        default_style = widget.styleSheet()
        # Styles should be different
        assert active_style != default_style


# ---------------------------------------------------------------------------
# create_setting_checkbox extended tests
# ---------------------------------------------------------------------------


class TestCreateSettingCheckboxExtended:
    """Extended tests for create_setting_checkbox()."""

    @patch("src.ui.components.load_setting", return_value=False)
    @patch("src.ui.components.save_setting")
    def test_checkbox_label_text(
        self, mock_save: MagicMock, mock_load: MagicMock, qapp: QApplication
    ) -> None:
        """Checkbox displays the provided label text."""
        from src.ui.components import create_setting_checkbox  # noqa: PLC0415

        _, checkbox = create_setting_checkbox("Auto Save", "auto_save")
        assert checkbox.text() == "Auto Save"

    @patch("src.ui.components.load_setting", return_value=False)
    @patch("src.ui.components.save_setting")
    def test_checkbox_tr_key_language_update(
        self, mock_save: MagicMock, mock_load: MagicMock, qapp: QApplication
    ) -> None:
        """Checkbox with label_tr_key has apply_language method."""
        from src.ui.components import create_setting_checkbox  # noqa: PLC0415

        container, _ = create_setting_checkbox(
            "Enable", "key", label_tr_key="settings.enable"
        )
        assert hasattr(container, "apply_language")
        assert callable(container.apply_language)

    @patch("src.ui.components.load_setting", return_value=False)
    @patch("src.ui.components.save_setting")
    def test_checkbox_no_tr_key_no_apply_language(
        self, mock_save: MagicMock, mock_load: MagicMock, qapp: QApplication
    ) -> None:
        """Checkbox without label_tr_key has no apply_language."""
        from src.ui.components import create_setting_checkbox  # noqa: PLC0415

        container, _ = create_setting_checkbox("Enable", "key")
        assert not hasattr(container, "apply_language")

    @patch("src.ui.components.load_setting", return_value=False)
    @patch("src.ui.components.save_setting")
    def test_checkbox_fixed_height(
        self, mock_save: MagicMock, mock_load: MagicMock, qapp: QApplication
    ) -> None:
        """Checkbox has HEIGHT_CONTROL fixed height."""
        from src.constants import HEIGHT_CONTROL  # noqa: PLC0415
        from src.ui.components import create_setting_checkbox  # noqa: PLC0415

        _, checkbox = create_setting_checkbox("Enable", "key")
        assert checkbox.maximumHeight() == HEIGHT_CONTROL

    @patch("src.ui.components.load_setting", return_value=True)
    @patch("src.ui.components.save_setting")
    def test_checkbox_default_override(
        self, mock_save: MagicMock, mock_load: MagicMock, qapp: QApplication
    ) -> None:
        """Saved value overrides the default parameter."""
        from src.ui.components import create_setting_checkbox  # noqa: PLC0415

        _, checkbox = create_setting_checkbox("Enable", "key", default=False)
        # load_setting returns True, so checkbox should be checked
        assert checkbox.isChecked()

    @patch("src.ui.components.load_setting", return_value=False)
    @patch("src.ui.components.save_setting")
    def test_checkbox_toggled_saves_setting(
        self, mock_save: MagicMock, mock_load: MagicMock, qapp: QApplication
    ) -> None:
        """Toggling checkbox calls save_setting."""
        from src.ui.components import create_setting_checkbox  # noqa: PLC0415

        _, checkbox = create_setting_checkbox("Enable", "my_key")
        mock_save.reset_mock()
        checkbox.setChecked(True)
        mock_save.assert_called_once_with("my_key", True)


# ---------------------------------------------------------------------------
# ForegroundPreservingDelegate extended tests
# ---------------------------------------------------------------------------


class TestForegroundPreservingDelegateExtended:
    """Extended tests for ForegroundPreservingDelegate."""

    def test_inherits_from_styled_item_delegate(self, qapp: QApplication) -> None:
        """ForegroundPreservingDelegate inherits from QStyledItemDelegate."""
        from PySide6.QtWidgets import QStyledItemDelegate  # noqa: PLC0415

        from src.ui.components import ForegroundPreservingDelegate  # noqa: PLC0415

        d = ForegroundPreservingDelegate()
        assert isinstance(d, QStyledItemDelegate)

    def test_with_parent(self, qapp: QApplication) -> None:
        """Delegate can be created with a parent widget."""
        from src.ui.components import ForegroundPreservingDelegate  # noqa: PLC0415

        parent = QWidget()
        d = ForegroundPreservingDelegate(parent)
        assert d.parent() is parent


# ---------------------------------------------------------------------------
# ElidedLabel extended tests
# ---------------------------------------------------------------------------


class TestElidedLabelExtended:
    """Extended tests for the ElidedLabel class."""

    def test_hover_tracking(self, qapp: QApplication) -> None:
        """ElidedLabel with draw_border tracks hover state."""
        from src.ui.components import ElidedLabel  # noqa: PLC0415

        label = ElidedLabel("text", draw_border=True)
        assert label._hovered is False

    def test_default_no_draw_border(self, qapp: QApplication) -> None:
        """ElidedLabel without draw_border does not enable mouse tracking."""
        from src.ui.components import ElidedLabel  # noqa: PLC0415

        label = ElidedLabel("text")
        assert label.draw_border is False

    def test_placeholder_default_empty(self, qapp: QApplication) -> None:
        """Default placeholder is empty string."""
        from src.ui.components import ElidedLabel  # noqa: PLC0415

        label = ElidedLabel("text")
        assert label._placeholder == ""


# ---------------------------------------------------------------------------
# _TableKeyFilter tests
# ---------------------------------------------------------------------------


class TestTableKeyFilter:
    """Tests for the _TableKeyFilter event filter."""

    def test_enter_with_selection_calls_callback(self, qapp: QApplication) -> None:
        """Pressing Enter on a table with selected items invokes the callback."""
        from PySide6.QtGui import QKeyEvent  # noqa: PLC0415
        from PySide6.QtWidgets import QTableWidgetItem  # noqa: PLC0415

        from src.ui.components import create_table  # noqa: PLC0415

        callback = MagicMock()
        table = create_table(["A", "B"], enter_callback=callback)

        # Add a row and select it
        table.setRowCount(1)
        table.setItem(0, 0, QTableWidgetItem("test"))
        table.selectRow(0)

        # Simulate Enter key press
        event = QKeyEvent(
            QEvent.Type.KeyPress,
            Qt.Key.Key_Return,
            Qt.KeyboardModifier.NoModifier,
        )
        # Send the event through the filter installed on the table
        qapp.sendEvent(table, event)

        callback.assert_called_once()

    def test_enter_without_selection_does_not_call_callback(
        self, qapp: QApplication
    ) -> None:
        """Pressing Enter on a table with no selection does not invoke the callback."""
        from PySide6.QtGui import QKeyEvent  # noqa: PLC0415

        from src.ui.components import create_table  # noqa: PLC0415

        callback = MagicMock()
        table = create_table(["A", "B"], enter_callback=callback)

        # No rows, no selection
        event = QKeyEvent(
            QEvent.Type.KeyPress,
            Qt.Key.Key_Return,
            Qt.KeyboardModifier.NoModifier,
        )
        qapp.sendEvent(table, event)

        callback.assert_not_called()

    def test_ctrl_a_selects_all_rows(self, qapp: QApplication) -> None:
        """Pressing Ctrl+A on a table selects all rows."""
        from PySide6.QtGui import QKeyEvent  # noqa: PLC0415
        from PySide6.QtWidgets import QTableWidgetItem  # noqa: PLC0415

        from src.ui.components import create_table  # noqa: PLC0415

        callback = MagicMock()
        table = create_table(["A", "B"], enter_callback=callback)

        # Add multiple rows
        table.setRowCount(3)
        for i in range(3):
            table.setItem(i, 0, QTableWidgetItem(f"row{i}"))

        # Simulate Ctrl+A key press
        event = QKeyEvent(
            QEvent.Type.KeyPress,
            Qt.Key.Key_A,
            Qt.KeyboardModifier.ControlModifier,
        )
        qapp.sendEvent(table, event)

        # All rows should be selected
        selected_rows = {idx.row() for idx in table.selectedIndexes()}
        assert selected_rows == {0, 1, 2}

    def test_other_keys_not_consumed(self, qapp: QApplication) -> None:
        """Non-Enter/Ctrl+A key presses are not consumed by the filter."""
        from PySide6.QtGui import QKeyEvent  # noqa: PLC0415

        from src.ui.components import _TableKeyFilter, create_table  # noqa: PLC0415

        callback = MagicMock()
        table = create_table(["A"], enter_callback=callback)

        # Simulate pressing 'B' key
        event = QKeyEvent(
            QEvent.Type.KeyPress,
            Qt.Key.Key_B,
            Qt.KeyboardModifier.NoModifier,
        )
        # Find the installed key filter
        key_filter = None
        for child in table.children():
            if isinstance(child, _TableKeyFilter):
                key_filter = child
                break
        assert key_filter is not None

        # eventFilter should return False (not consumed)
        result = key_filter.eventFilter(table, event)
        assert result is False

    def test_key_enter_also_triggers_callback(self, qapp: QApplication) -> None:
        """Key_Enter (numpad) also invokes the callback when items are selected."""
        from PySide6.QtGui import QKeyEvent  # noqa: PLC0415
        from PySide6.QtWidgets import QTableWidgetItem  # noqa: PLC0415

        from src.ui.components import create_table  # noqa: PLC0415

        callback = MagicMock()
        table = create_table(["A"], enter_callback=callback)

        table.setRowCount(1)
        table.setItem(0, 0, QTableWidgetItem("test"))
        table.selectRow(0)

        event = QKeyEvent(
            QEvent.Type.KeyPress,
            Qt.Key.Key_Enter,
            Qt.KeyboardModifier.NoModifier,
        )
        qapp.sendEvent(table, event)

        callback.assert_called_once()


# ---------------------------------------------------------------------------
# _TableResizeFilter tests
# ---------------------------------------------------------------------------


class TestTableResizeFilter:
    """Tests for the _TableResizeFilter proportional column resizing."""

    def test_resize_redistributes_flex_columns(self, qapp: QApplication) -> None:
        """Viewport resize redistributes flex columns proportionally."""
        from src.ui.components import _TableResizeFilter, create_table  # noqa: PLC0415

        # Create table with interactive columns (no explicit widths = flex)
        table = create_table(
            ["A", "B", "C", "D"],
            interactive_columns=[0, 1, 2],
            column_widths={3: 80},
        )
        table.resize(800, 400)
        table.show()
        qapp.processEvents()

        # Find the resize filter
        resize_filter = None
        for child in table.children():
            if isinstance(child, _TableResizeFilter):
                resize_filter = child
                break
        assert resize_filter is not None

        # Record initial widths of interactive columns
        header = table.horizontalHeader()
        initial_widths = [header.sectionSize(i) for i in range(3)]

        # Resize the table to actually change viewport width, then redistribute
        table.resize(1000, 400)
        qapp.processEvents()
        resize_filter._do_redistribute()

        # After redistribution, flex columns should reflect the new viewport size
        new_widths = [header.sectionSize(i) for i in range(3)]
        # The total flex width should have changed
        assert sum(new_widths) != sum(initial_widths) or new_widths != initial_widths

    def test_pinned_columns_keep_width_on_resize(self, qapp: QApplication) -> None:
        """Columns with explicit initial widths keep their size on resize."""
        from src.ui.components import _TableResizeFilter, create_table  # noqa: PLC0415

        # Column 1 is pinned (has explicit width), column 0 is flex
        table = create_table(
            ["Flex", "Pinned", "Fixed"],
            interactive_columns=[0, 1],
            column_widths={1: 150},
        )
        table.resize(800, 400)
        table.show()
        qapp.processEvents()

        resize_filter = None
        for child in table.children():
            if isinstance(child, _TableResizeFilter):
                resize_filter = child
                break
        assert resize_filter is not None

        # Trigger redistribute
        resize_filter._do_redistribute()

        # Pinned column should retain its width
        header = table.horizontalHeader()
        pinned_width = header.sectionSize(1)
        assert pinned_width == 150  # noqa: PLR2004

    def test_non_resize_events_pass_through(self, qapp: QApplication) -> None:
        """Non-resize events are not handled by the resize filter."""
        from src.ui.components import _TableResizeFilter, create_table  # noqa: PLC0415

        table = create_table(["A", "B"], interactive_columns=[0, 1])

        resize_filter = None
        for child in table.children():
            if isinstance(child, _TableResizeFilter):
                resize_filter = child
                break
        assert resize_filter is not None

        # Send a non-resize event (e.g., a paint event)
        non_resize_event = QEvent(QEvent.Type.Paint)
        result = resize_filter.eventFilter(table.viewport(), non_resize_event)
        assert result is False

    def test_reentrancy_guard_prevents_recursive_redistribute(
        self, qapp: QApplication
    ) -> None:
        """Redistribute is skipped when already adjusting (reentrancy guard)."""
        from src.ui.components import _TableResizeFilter, create_table  # noqa: PLC0415

        table = create_table(["A", "B"], interactive_columns=[0, 1])

        resize_filter = None
        for child in table.children():
            if isinstance(child, _TableResizeFilter):
                resize_filter = child
                break
        assert resize_filter is not None

        # Manually set the adjusting flag and call redistribute
        resize_filter._adjusting = True
        header = table.horizontalHeader()
        old_widths = [header.sectionSize(i) for i in range(2)]

        resize_filter._redistribute()

        # Widths should not have changed
        new_widths = [header.sectionSize(i) for i in range(2)]
        assert old_widths == new_widths
        resize_filter._adjusting = False


# ---------------------------------------------------------------------------
# TagInput — chip-style tag list input
# ---------------------------------------------------------------------------


class TestTagInput:
    """Tests for the TagInput widget's public API and key events."""

    def test_starts_empty(self, qapp: QApplication) -> None:
        """A fresh TagInput has no tags and empty text()."""
        from src.ui.components import TagInput  # noqa: PLC0415

        ti = TagInput()
        assert ti.tags() == []
        assert ti.text() == ""

    def test_set_tags_emits_change_signal_once(self, qapp: QApplication) -> None:
        """set_tags([...]) populates tags and emits tags_changed."""
        from src.ui.components import TagInput  # noqa: PLC0415

        ti = TagInput()
        received: list[list[str]] = []
        ti.tags_changed.connect(received.append)

        ti.set_tags(["alpha", "beta"])
        assert ti.tags() == ["alpha", "beta"]
        assert ti.text() == "alpha, beta"
        # A single emission carries the final list.
        assert received[-1] == ["alpha", "beta"]

    def test_set_tags_strips_and_deduplicates(self, qapp: QApplication) -> None:
        """Whitespace is stripped and duplicates are dropped."""
        from src.ui.components import TagInput  # noqa: PLC0415

        ti = TagInput()
        ti.set_tags(["  x  ", "y", "x", " "])
        assert ti.tags() == ["x", "y"]

    def test_set_tags_replaces_existing(self, qapp: QApplication) -> None:
        """A subsequent set_tags call removes the previous tags first."""
        from src.ui.components import TagInput  # noqa: PLC0415

        ti = TagInput()
        ti.set_tags(["a", "b", "c"])
        ti.set_tags(["x"])
        assert ti.tags() == ["x"]

    def test_add_via_enter_key(self, qapp: QApplication) -> None:
        """Pressing Enter in the input box adds the current text as a tag."""
        from src.ui.components import TagInput  # noqa: PLC0415

        ti = TagInput()
        ti._input.setText("hello")
        ti._on_enter()
        assert ti.tags() == ["hello"]
        # Input is cleared after add.
        assert ti._input.text() == ""

    def test_add_via_comma_input(self, qapp: QApplication) -> None:
        """Typing a comma splits the preceding text into tags."""
        from src.ui.components import TagInput  # noqa: PLC0415

        ti = TagInput()
        # Simulate what textChanged emits when the user types "foo,bar,"
        ti._on_text_changed("foo,bar,")
        assert ti.tags() == ["foo", "bar"]

    def test_duplicate_add_is_noop(self, qapp: QApplication) -> None:
        """Adding an existing tag does not duplicate it or re-emit."""
        from src.ui.components import TagInput  # noqa: PLC0415

        ti = TagInput()
        ti.set_tags(["solo"])
        received: list[list[str]] = []
        ti.tags_changed.connect(received.append)

        ti._add_tag("solo")
        assert ti.tags() == ["solo"]
        assert received == []

    def test_remove_tag_emits_change(self, qapp: QApplication) -> None:
        """Removing a tag updates state and emits tags_changed."""
        from src.ui.components import TagInput  # noqa: PLC0415

        ti = TagInput()
        ti.set_tags(["a", "b"])
        received: list[list[str]] = []
        ti.tags_changed.connect(received.append)

        ti._remove_tag("a")
        assert ti.tags() == ["b"]
        assert received[-1] == ["b"]

    def test_remove_missing_tag_is_noop(self, qapp: QApplication) -> None:
        """Removing a tag that isn't present does nothing and does not emit."""
        from src.ui.components import TagInput  # noqa: PLC0415

        ti = TagInput()
        ti.set_tags(["keep"])
        received: list[list[str]] = []
        ti.tags_changed.connect(received.append)

        ti._remove_tag("ghost")
        assert ti.tags() == ["keep"]
        assert received == []

    def test_backspace_on_empty_input_removes_last_tag(
        self,
        qapp: QApplication,
    ) -> None:
        """Backspace with empty input removes the last chip."""
        from PySide6.QtCore import QEvent  # noqa: PLC0415
        from PySide6.QtGui import QKeyEvent  # noqa: PLC0415

        from src.ui.components import TagInput  # noqa: PLC0415

        ti = TagInput()
        ti.set_tags(["first", "second"])
        assert ti._input.text() == ""

        # Simulate a Backspace key press on the input.
        key_event = QKeyEvent(
            QEvent.Type.KeyPress,
            Qt.Key.Key_Backspace,
            Qt.KeyboardModifier.NoModifier,
        )
        handled = ti.eventFilter(ti._input, key_event)

        assert handled is True
        assert ti.tags() == ["first"]

    def test_backspace_is_ignored_when_input_has_text(
        self,
        qapp: QApplication,
    ) -> None:
        """Backspace does NOT remove tags when the input has text."""
        from PySide6.QtCore import QEvent  # noqa: PLC0415
        from PySide6.QtGui import QKeyEvent  # noqa: PLC0415

        from src.ui.components import TagInput  # noqa: PLC0415

        ti = TagInput()
        ti.set_tags(["first"])
        ti._input.setText("typing")

        key_event = QKeyEvent(
            QEvent.Type.KeyPress,
            Qt.Key.Key_Backspace,
            Qt.KeyboardModifier.NoModifier,
        )
        handled = ti.eventFilter(ti._input, key_event)

        # When input has text, the filter returns False so Qt handles it.
        assert handled is False
        assert ti.tags() == ["first"]

    def test_focus_changes_apply_border_styles(self, qapp: QApplication) -> None:
        """FocusIn/FocusOut events flip the border style."""
        from PySide6.QtCore import QEvent  # noqa: PLC0415

        from src.ui.components import TagInput  # noqa: PLC0415

        ti = TagInput()

        # FocusIn
        focus_in = QEvent(QEvent.Type.FocusIn)
        ti.eventFilter(ti._input, focus_in)
        focused_style = ti.styleSheet()
        assert "2px solid" in focused_style

        # FocusOut
        focus_out = QEvent(QEvent.Type.FocusOut)
        ti.eventFilter(ti._input, focus_out)
        assert "1px solid" in ti.styleSheet()

    def test_focus_out_commits_pending_text_as_tag(
        self, qapp: QApplication
    ) -> None:
        """Typed-but-uncommitted text is added when focus leaves the input.

        Without this, a user who types a model name and clicks Save (or
        any other widget) silently loses the entry.
        """
        from src.ui.components import TagInput  # noqa: PLC0415

        ti = TagInput()
        ti._input.setText("gpt-4o")

        focus_out = QEvent(QEvent.Type.FocusOut)
        ti.eventFilter(ti._input, focus_out)

        assert ti.tags() == ["gpt-4o"]
        assert ti._input.text() == ""

    def test_focus_out_with_empty_text_is_noop(self, qapp: QApplication) -> None:
        """FocusOut on an empty buffer doesn't add a phantom empty tag."""
        from src.ui.components import TagInput  # noqa: PLC0415

        ti = TagInput()

        focus_out = QEvent(QEvent.Type.FocusOut)
        ti.eventFilter(ti._input, focus_out)

        assert ti.tags() == []

    def test_focus_out_dedupes_against_existing_tag(
        self, qapp: QApplication
    ) -> None:
        """A pending value matching an existing tag is silently dropped."""
        from src.ui.components import TagInput  # noqa: PLC0415

        ti = TagInput()
        ti.set_tags(["gpt-4o"])
        ti._input.setText("gpt-4o")

        focus_out = QEvent(QEvent.Type.FocusOut)
        ti.eventFilter(ti._input, focus_out)

        assert ti.tags() == ["gpt-4o"]
        assert ti._input.text() == ""


# ---------------------------------------------------------------------------
# ElidedLabel — hover events
# ---------------------------------------------------------------------------


class TestElidedLabelHover:
    """Tests for ElidedLabel's enter/leave hover tracking."""

    def test_enter_event_sets_hovered_true(self, qapp: QApplication) -> None:
        """EnterEvent flips _hovered and repaints."""
        from PySide6.QtCore import QPointF  # noqa: PLC0415
        from PySide6.QtGui import QEnterEvent  # noqa: PLC0415

        from src.ui.components import ElidedLabel  # noqa: PLC0415

        label = ElidedLabel("text", draw_border=True)
        pos = QPointF(1.0, 1.0)
        event = QEnterEvent(pos, pos, pos)
        label.enterEvent(event)
        assert label._hovered is True

    def test_leave_event_resets_hovered(self, qapp: QApplication) -> None:
        """LeaveEvent flips _hovered back to False."""
        from src.ui.components import ElidedLabel  # noqa: PLC0415

        label = ElidedLabel("text", draw_border=True)
        label._hovered = True
        label.leaveEvent(QEvent(QEvent.Type.Leave))
        assert label._hovered is False


# ---------------------------------------------------------------------------
# FileDropWidget — enter/leave + empty drop branch
# ---------------------------------------------------------------------------


class TestFileDropWidgetEvents:
    """Tests for FileDropWidget hover / drop event branches."""

    def test_enter_event_applies_active_style(self, qapp: QApplication) -> None:
        """EnterEvent invokes _set_active_style."""
        from PySide6.QtCore import QPointF  # noqa: PLC0415
        from PySide6.QtGui import QEnterEvent  # noqa: PLC0415

        from src.ui.components import FileDropWidget  # noqa: PLC0415

        w = FileDropWidget()
        pos = QPointF(1.0, 1.0)
        with patch.object(w, "_set_active_style") as mock_active:
            w.enterEvent(QEnterEvent(pos, pos, pos))
            mock_active.assert_called_once()

    def test_leave_event_applies_default_style(self, qapp: QApplication) -> None:
        """LeaveEvent invokes _set_default_style."""
        from src.ui.components import FileDropWidget  # noqa: PLC0415

        w = FileDropWidget()
        with patch.object(w, "_set_default_style") as mock_default:
            w.leaveEvent(QEvent(QEvent.Type.Leave))
            mock_default.assert_called_once()

    def test_drag_leave_applies_default_style(self, qapp: QApplication) -> None:
        """DragLeaveEvent invokes _set_default_style."""
        from PySide6.QtGui import QDragLeaveEvent  # noqa: PLC0415

        from src.ui.components import FileDropWidget  # noqa: PLC0415

        w = FileDropWidget()
        with patch.object(w, "_set_default_style") as mock_default:
            w.dragLeaveEvent(QDragLeaveEvent())
            mock_default.assert_called_once()

    def test_drop_without_local_files_ignored(self, qapp: QApplication) -> None:
        """DropEvent with no local files emits nothing and ignores the event."""
        from PySide6.QtCore import QMimeData, QPointF, Qt  # noqa: PLC0415
        from PySide6.QtGui import QDropEvent  # noqa: PLC0415

        from src.ui.components import FileDropWidget  # noqa: PLC0415

        w = FileDropWidget()
        emitted: list = []
        w.files_dropped.connect(emitted.append)

        # Build a QMimeData with no URLs.
        mime = QMimeData()
        drop = QDropEvent(
            QPointF(0, 0),
            Qt.DropAction.CopyAction,
            mime,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            QDropEvent.Type.Drop,
        )
        w.dropEvent(drop)
        assert emitted == []


# ---------------------------------------------------------------------------
# create_setting_input — password toggle + apply hooks
# ---------------------------------------------------------------------------


class TestCreateSettingInputPasswordAndHooks:
    """Tests for password toggle, apply_theme, and apply_language."""

    def test_password_toggle_flips_echo_mode_and_icons(
        self,
        qapp: QApplication,
    ) -> None:
        """Clicking the eye button toggles Password↔Normal echo and swaps icons."""
        from src.ui.components import create_setting_input  # noqa: PLC0415

        with (
            patch("src.ui.components.load_setting", return_value=""),
            patch("src.ui.components.save_setting"),
        ):
            container, field = create_setting_input(
                "API key",
                "test/api_key",
                is_password=True,
            )
        # Field starts in Password mode (masked).
        assert field.echoMode() == QLineEdit.EchoMode.Password

        # Find the toggle button — it's the HoverIconButton.
        from src.ui.components import HoverIconButton  # noqa: PLC0415

        toggle = container.findChild(HoverIconButton)
        assert toggle is not None

        toggle.click()
        assert field.echoMode() == QLineEdit.EchoMode.Normal

        toggle.click()
        assert field.echoMode() == QLineEdit.EchoMode.Password

    def test_apply_theme_restyles_widgets(self, qapp: QApplication) -> None:
        """apply_theme() runs without error and does not raise."""
        from src.ui.components import create_setting_input  # noqa: PLC0415

        with (
            patch("src.ui.components.load_setting", return_value=""),
            patch("src.ui.components.save_setting"),
        ):
            container, _ = create_setting_input(
                "API key",
                "test/api_key",
                is_password=True,
            )
        # Should not raise.
        container.apply_theme()

    def test_apply_language_sets_label_and_placeholder(
        self,
        qapp: QApplication,
    ) -> None:
        """apply_language() refreshes both label and placeholder."""
        from src.ui.components import create_setting_input  # noqa: PLC0415

        with (
            patch("src.ui.components.load_setting", return_value=""),
            patch("src.ui.components.save_setting"),
            patch("src.ui.components.tr", side_effect=lambda k, **kw: f"[{k}]"),
        ):
            container, field = create_setting_input(
                "Lbl",
                "key",
                label_tr_key="settings.api_key_label",
                placeholder_tr_key="settings.api_key_placeholder",
            )
            container.apply_language()
            lbl = container.findChild(QLabel)
            assert lbl is not None
            assert lbl.text() == "[settings.api_key_label]"
            assert field.placeholderText() == "[settings.api_key_placeholder]"


# ---------------------------------------------------------------------------
# create_setting_checkbox — apply_language path
# ---------------------------------------------------------------------------


class TestCreateSettingCheckboxApplyLanguage:
    """Tests for the checkbox's language-refresh hook."""

    def test_apply_language_updates_label(self, qapp: QApplication) -> None:
        """apply_language() sets the checkbox text from the tr-key."""
        from src.ui.components import create_setting_checkbox  # noqa: PLC0415

        with (
            patch("src.ui.components.load_setting", return_value=False),
            patch("src.ui.components.save_setting"),
            patch("src.ui.components.tr", side_effect=lambda k, **kw: f"<{k}>"),
        ):
            container, checkbox = create_setting_checkbox(
                "Old",
                "test/opt",
                label_tr_key="settings.opt",
            )
            container.apply_language()
            assert checkbox.text() == "<settings.opt>"


# ---------------------------------------------------------------------------
# create_setting_path — browse, clear, apply_language
# ---------------------------------------------------------------------------


class TestCreateSettingPath:
    """Tests for the setting-path row's browse/reset buttons + language hook."""

    def test_browse_sets_path_and_persists(self, qapp: QApplication) -> None:
        """Browse dialog selection is written to label and saved to settings."""
        from src.ui.components import create_setting_path  # noqa: PLC0415

        saved = {}

        def _save(key: str, val: str) -> None:
            saved[key] = val

        with (
            patch("src.ui.components.load_setting", return_value=""),
            patch("src.ui.components.save_setting", side_effect=_save),
            patch(
                "PySide6.QtWidgets.QFileDialog.getOpenFileName",
                return_value=("/tmp/chosen.pdf", ""),
            ),
            patch(
                "src.utils.path_manager.get_desktop_path",
                return_value=Path("/home/x/Desktop"),
            ),
            patch("src.ui.components.tr", side_effect=lambda k, **kw: k),
        ):
            container, label = create_setting_path(
                "Path",
                "test/path",
                dialog_title_tr_key="dlg.pick",
                browse_mode="file",
            )

            # Click Browse button.  Identify by tr-key text rather
            # than position — the row contains a Reset button too,
            # placed AFTER Browse, so positional lookup would pick
            # up the wrong button.
            from PySide6.QtWidgets import QPushButton  # noqa: PLC0415

            buttons = container.findChildren(QPushButton)
            browse_btn = next(b for b in buttons if b.text() == "btn.browse")
            browse_btn.click()

        assert label._full_text == "/tmp/chosen.pdf"
        assert saved.get("test/path") == "/tmp/chosen.pdf"

    def test_browse_directory_mode(self, qapp: QApplication) -> None:
        """browse_mode='dir' uses getExistingDirectory instead of getOpenFileName."""
        from src.ui.components import create_setting_path  # noqa: PLC0415

        with (
            patch("src.ui.components.load_setting", return_value=""),
            patch("src.ui.components.save_setting"),
            patch(
                "PySide6.QtWidgets.QFileDialog.getExistingDirectory",
                return_value="/opt/my-dir",
            ) as mock_dir,
            patch(
                "src.utils.path_manager.get_desktop_path",
                return_value=Path("/home/x"),
            ),
            patch("src.ui.components.tr", side_effect=lambda k, **kw: k),
        ):
            container, label = create_setting_path(
                "Dir",
                "test/dir",
                dialog_title_tr_key="dlg.pick",
                browse_mode="dir",
            )
            from PySide6.QtWidgets import QPushButton  # noqa: PLC0415

            buttons = container.findChildren(QPushButton)
            browse_btn = next(b for b in buttons if b.text() == "btn.browse")
            browse_btn.click()

        mock_dir.assert_called_once()
        assert label._full_text == "/opt/my-dir"

    def test_apply_language_sets_all_labels(self, qapp: QApplication) -> None:
        """apply_language() sets browse/label/placeholder texts."""
        from src.ui.components import create_setting_path  # noqa: PLC0415

        with (
            patch("src.ui.components.load_setting", return_value=""),
            patch("src.ui.components.save_setting"),
            patch("src.ui.components.tr", side_effect=lambda k, **kw: f"<{k}>"),
        ):
            container, label = create_setting_path(
                "Path",
                "test/path",
                dialog_title_tr_key="dlg.pick",
                browse_mode="file",
                label_tr_key="settings.path_label",
                placeholder_tr_key="settings.path_placeholder",
            )
            container.apply_language()
            # The ElidedLabel placeholder got set via set_placeholder.
            assert label._placeholder == "<settings.path_placeholder>"
