"""Reusable UI components and helpers for the AI Translate application."""

import pathlib
import re
from collections.abc import Callable
from dataclasses import dataclass
from html import escape

from PySide6.QtCore import QEvent, QModelIndex, QObject, QSize, Qt, QUrl, Signal
from PySide6.QtGui import (
    QAbstractTextDocumentLayout,
    QColor,
    QDesktopServices,
    QDragEnterEvent,
    QDragLeaveEvent,
    QDropEvent,
    QEnterEvent,
    QFontMetrics,
    QIcon,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QTextDocument,
)
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.constants import (
    ALERT_CIRCLE_PATH,
    ALERT_TRIANGLE_PATH,
    BANNER_ICON_SIZE,
    BANNER_LINE_SPACING,
    BANNER_PADDING,
    BANNER_SPACING,
    BROWSE_BUTTON_WIDTH,
    CHECK_CIRCLE_PATH,
    EYE_OFF_PATH,
    EYE_OFF_PRIMARY_PATH,
    EYE_PATH,
    EYE_PRIMARY_PATH,
    FILE_ITEM_BADGE_SIZE,
    FILE_ITEM_HEIGHT,
    HEIGHT_CONTROL,
    INFO_PATH,
    LABEL_WIDTH,
    MARGIN_PAGE,
    MARGIN_SECTION,
    MARGIN_SUBSECTION,
    MIN_COLUMN_WIDTH,
    RADIUS_BUTTON,
    SPACING_PAGE,
    SUPPORTED_IMAGES,
    SUPPORTED_TEXT,
    TOGGLE_BUTTON_WIDTH,
    TOGGLE_ICON_SIZE,
    color,
    style_banner,
    style_checkbox,
    style_input_field,
    style_input_label,
    style_link_button,
    style_link_button_muted,
    style_page_header,
    style_section_group,
    style_section_title,
    style_setting_combo,
    style_setting_container,
    style_table,
    tr,
)
from src.utils.config_manager import load_setting, save_setting
from src.utils.text_utils import build_norm_map, normalize_for_search

# ── Reusable sort-item subclasses for QTableWidget ──────────────────────


class CaseInsensitiveSortItem(QTableWidgetItem):
    """QTableWidgetItem subclass that compares items case-insensitively.

    Use this for text columns so that sorting ignores letter case.
    """

    def __lt__(self, other: QTableWidgetItem) -> bool:
        """Return True when this item's lowered text precedes *other*'s."""
        return self.text().lower() < other.text().lower()


class NumericalSortItem(QTableWidgetItem):
    """QTableWidgetItem subclass that sorts by a numeric value.

    The displayed text can be any formatted string (e.g. ``"1.2 MB"``);
    sorting is driven by the *value* stored at construction time.
    """

    def __init__(self, text: str, value: float) -> None:
        """Create item with *text* for display and *value* for ordering."""
        super().__init__(text)
        self.value = value

    def __lt__(self, other: QTableWidgetItem) -> bool:
        """Return True when this item's numeric value is less than *other*'s."""
        if isinstance(other, NumericalSortItem):
            return self.value < other.value
        # Avoid super().__lt__: PySide6 virtual dispatch would re-enter this
        # Python override and recurse. Compare on text directly instead.
        return self.text() < other.text()


class DateTimeSortItem(QTableWidgetItem):
    """QTableWidgetItem that displays a locale-formatted date but sorts by ISO key.

    Pass the human-readable *display_text* for rendering and the ISO-8601
    *iso_key* (e.g. ``"2026-03-25 14:30:00"``) for chronological ordering.
    """

    def __init__(self, display_text: str, iso_key: str) -> None:
        """Create item with *display_text* for display and *iso_key* for ordering."""
        super().__init__(display_text)
        self.iso_key = iso_key

    def __lt__(self, other: QTableWidgetItem) -> bool:
        """Return True when this item's ISO key precedes *other*'s."""
        if isinstance(other, DateTimeSortItem):
            return self.iso_key < other.iso_key
        # Avoid super().__lt__: PySide6 virtual dispatch would re-enter this
        # Python override and recurse. Compare on text directly instead.
        return self.text() < other.text()


def style_file_count_badge() -> str:
    """Generates QSS for the file count badge used in drop-area pages."""
    return (
        f"background-color: {color('primary')}; color: white; "
        "border-radius: 12px; font-size: 11px; font-weight: 800;"
    )


def style_section_label() -> str:
    """Generates QSS for the section header label used in drop-area pages."""
    return (
        f"color: {color('text_primary')}; font-size: 12px; "
        "font-weight: 700; letter-spacing: 0.5px;"
    )


def create_scrollable_container(widget: QWidget) -> QScrollArea:
    """Wraps a widget in a transparent, resizable QScrollArea."""
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setStyleSheet("background: transparent;")
    scroll.setWidget(widget)
    return scroll


@dataclass
class ControllerCard:
    """Bundle of widgets/layouts returned by :func:`create_controller_card`.

    Lets callers populate the standard two-row controller surface
    without re-writing the card frame, divider, or padding boilerplate.
    """

    card: QFrame
    """The outer rounded card frame.  Caller adds it to the page layout."""

    layout: QVBoxLayout
    """The card's main vertical layout.  Caller appends content widgets
    (transcript stack, empty state, etc.) here AFTER the divider."""

    controls_top_row: QHBoxLayout
    """First row of controls — typically session-config selectors."""

    controls_btm_row: QHBoxLayout
    """Second row of controls — typically Start + action buttons + status."""

    btm_row_parent: QWidget
    """The widget that wraps ``controls_btm_row``.  Exposed so callers
    can hide / re-style / re-parent the second row as a unit."""

    banners_layout: QVBoxLayout
    """Layout sitting between the controller block and the divider.
    Caller adds setup-hint banners (e.g. STT-key warnings) here so
    they appear above the divider, inside the same card."""


def create_controller_card() -> ControllerCard:
    """Creates the standard rounded controller card used by Live + Screen pages.

    Layout shape::

        ┌─────────────────────────────┐
        │  controls_top_row           │  ← session config (selectors)
        │  controls_btm_row           │  ← actions + status pill
        │  banners_layout (optional)  │  ← setup-hint warnings
        │  ─────────────────────────  │  ← 1px divider
        │  (caller appends content)   │  ← transcript stack / empty state
        └─────────────────────────────┘

    The Live Translation page uses this exact surface — rounded border,
    row padding, and divider line — so the helper keeps the chrome
    consistent if more pages adopt the pattern.

    Returns:
        :class:`ControllerCard` — the card frame plus references to
        every layout the caller needs to populate.
    """
    card = QFrame()
    # Reuse the existing ``QFrame#LivePageCard`` QSS selector that
    # ``_style_page_card`` in ``src.ui.pages.live`` already targets —
    # both pages render identically without any new styling helper.
    card.setObjectName("LivePageCard")
    card.setFrameShape(QFrame.Shape.NoFrame)
    card.setStyleSheet(
        "QFrame#LivePageCard {"
        f" background-color: {color('component_bg')};"
        f" border: 1px solid {color('border_light')};"
        f" border-radius: {RADIUS_BUTTON}px;"
        " }"
    )

    layout = QVBoxLayout(card)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)

    # Controller container holds both control rows so they share one
    # padding box (14px horizontal, 12px vertical).  Putting padding
    # on the container, not each row, prevents drift if either row's
    # padding ever changes — both must change together.
    controls_container = QWidget()
    controls_container.setStyleSheet("background: transparent;")
    controls_v = QVBoxLayout(controls_container)
    controls_v.setContentsMargins(14, 12, 14, 12)
    controls_v.setSpacing(10)

    controls_top_row = QHBoxLayout()
    controls_top_row.setSpacing(10)
    controls_v.addLayout(controls_top_row)

    # Bottom row is wrapped in its own QWidget so callers can grab
    # ``btm_row_parent`` and re-style / hide it as a unit if needed
    # (Live's overlay-config flow uses this exact handle).
    btm_row_parent = QWidget()
    btm_row_parent.setStyleSheet("background: transparent;")
    btm_wrap = QVBoxLayout(btm_row_parent)
    btm_wrap.setContentsMargins(0, 0, 0, 0)
    controls_btm_row = QHBoxLayout()
    controls_btm_row.setSpacing(10)
    btm_wrap.addLayout(controls_btm_row)
    controls_v.addWidget(btm_row_parent)

    layout.addWidget(controls_container)

    # Banners area sits BEFORE the divider so any setup-hint banner
    # the caller adds (Live: STT-setup + system-audio warnings) sits
    # inside the controller chrome — above the divider, not between
    # the divider and the content area.  Callers that don't need
    # banners just leave this empty; it renders nothing.
    #
    # Default contentsMargins keeps the bottom at 0 — so pages that
    # don't add banners (Translate Text, etc.) don't pay for dead
    # vertical space above the divider.  Pages that DO add banners
    # (e.g. Live) should bump the bottom margin to 12 px once they're
    # done populating, so the bottom-most banner gets breathing room
    # from the divider.  Horizontal margin matches ``controls_container``
    # (14 px) so banners visually align with the control row above
    # them.  Spacing between multiple stacked banners is 8 px so they
    # read as separate cards, not one wall of warning.
    banners_layout = QVBoxLayout()
    banners_layout.setContentsMargins(14, 0, 14, 0)
    banners_layout.setSpacing(8)
    layout.addLayout(banners_layout)

    # Divider closes off the controller block; the content area
    # starts immediately below.  Inline QSS instead of a stylesheet
    # function because it's only used here.
    divider = QFrame()
    divider.setFrameShape(QFrame.Shape.HLine)
    divider.setFrameShadow(QFrame.Shadow.Plain)
    divider.setStyleSheet(
        f"background-color: {color('border_light')};"
        " border: none; min-height: 1px; max-height: 1px;",
    )
    layout.addWidget(divider)

    return ControllerCard(
        card=card,
        layout=layout,
        controls_top_row=controls_top_row,
        controls_btm_row=controls_btm_row,
        btm_row_parent=btm_row_parent,
        banners_layout=banners_layout,
    )


class ElidedLabel(QLabel):
    """A label that elides text if it's too wide for the available space."""

    def __init__(
        self,
        text: str = "",
        parent: QWidget | None = None,
        clicked: Callable[[], None] | None = None,
        draw_border: bool = False,
        placeholder: str = "",
    ) -> None:
        """Initializes the ElidedLabel.

        Args:
            text: Initial text.
            parent: Optional parent widget.
            clicked: Optional callback for mouse click events.
            draw_border: Whether to draw a border and background.
            placeholder: Placeholder text shown when the label is empty.
        """
        super().__init__(text, parent)
        self._full_text = text
        self._placeholder = placeholder
        self.clicked_callback = clicked
        self.draw_border = draw_border
        self._hovered = False
        if draw_border:
            self.setMouseTracking(True)
        if clicked:
            self.setCursor(Qt.CursorShape.PointingHandCursor)

    def enterEvent(self, event: QEnterEvent) -> None:  # noqa: N802
        """Tracks hover state for border color change."""
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event: QEvent) -> None:  # noqa: N802
        """Resets hover state."""
        self._hovered = False
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        """Handles the mouse press event."""
        if self.clicked_callback and event.button() == Qt.MouseButton.LeftButton:
            self.clicked_callback()
        super().mousePressEvent(event)

    def set_text(self, text: str) -> None:
        """Sets the label text and updates the tooltip.

        Args:
            text: The new text to display.
        """
        self._full_text = text
        super().setText(text)
        self.update()

    def set_placeholder(self, text: str) -> None:
        """Sets the placeholder text shown when the label is empty.

        Args:
            text: The placeholder text.
        """
        self._placeholder = text
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:  # noqa: N802
        """Overrides the paint event to elide text if needed."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if self.draw_border:
            # Draw background
            painter.setBrush(QColor(color("component_bg")))
            border_color = color("primary") if self._hovered else color("secondary")
            painter.setPen(QColor(border_color))
            # Match style_input_field: border 1px, border-radius 8px
            painter.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), 8, 8)

        # Draw elided text or placeholder
        metrics = QFontMetrics(self.font())
        # Add padding (matches style_input_field: 10px 16px if border is enabled)
        padding = 16 if self.draw_border else 0
        text_rect = self.rect().adjusted(padding, 0, -padding, 0)

        if self._full_text:
            elided_text = metrics.elidedText(
                self._full_text, Qt.TextElideMode.ElideMiddle, text_rect.width()
            )
            painter.setPen(QColor(self.palette().color(self.foregroundRole())))
            painter.drawText(text_rect, self.alignment(), elided_text)
        elif self._placeholder:
            elided_placeholder = metrics.elidedText(
                self._placeholder, Qt.TextElideMode.ElideRight, text_rect.width()
            )
            painter.setPen(QColor(color("text_secondary")))
            painter.drawText(text_rect, self.alignment(), elided_placeholder)


class ForegroundPreservingDelegate(QStyledItemDelegate):
    """Delegate that keeps per-item foreground color when rows are selected.

    Qt's selection style overrides ``QTableWidgetItem.setForeground()``
    with a single ``selection-color``.  This delegate restores the
    item's foreground before painting so status colors (green for Done,
    red for Failed, etc.) remain visible on selected rows.
    """

    def initStyleOption(  # noqa: N802
        self,
        option: QStyleOptionViewItem,
        index: QModelIndex,
    ) -> None:
        """Override to preserve per-item foreground on selection."""
        super().initStyleOption(option, index)
        fg = index.data(Qt.ItemDataRole.ForegroundRole)
        if fg is not None:
            fg_color = fg.color() if hasattr(fg, "color") else QColor(fg)
            option.palette.setColor(
                option.palette.ColorRole.HighlightedText,
                fg_color,
            )


class HighlightDelegate(QStyledItemDelegate):
    """Delegate to highlight searched text in table cells.

    When *normalize* is True, matching uses accent/case-insensitive
    normalization (via ``normalize_for_search`` / ``build_norm_map``
    from ``src.utils.text_utils``).  Match spans are mapped back to
    the original text positions so the correct characters are
    highlighted.  When False (default), simple case-insensitive
    matching is used.
    """

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        normalize: bool = False,
    ) -> None:
        """Initializes the HighlightDelegate.

        Args:
            parent: Optional parent widget.
            normalize: If True, use accent/diacritic-insensitive matching.
        """
        super().__init__(parent)
        self.search_text = ""
        self.normalize = normalize

    def set_search_text(self, text: str) -> None:
        """Sets the current search text for highlighting."""
        self.search_text = text.strip()

    def set_selected_color(self, hex_color: str) -> None:
        """Sets the text color to use when the row is selected.

        Args:
            hex_color: Hex color string (e.g. ``"#3E79F7"``).
        """
        self._selected_color = hex_color

    def initStyleOption(  # noqa: N802
        self,
        option: QStyleOptionViewItem,
        index: QModelIndex,
    ) -> None:
        """Override to use a custom text color on selection."""
        super().initStyleOption(option, index)
        sel_color = getattr(self, "_selected_color", None)
        if sel_color and option.state & QStyle.StateFlag.State_Selected:
            option.palette.setColor(
                option.palette.ColorRole.HighlightedText,
                QColor(sel_color),
            )

    # ------------------------------------------------------------------
    # Highlight span computation
    # ------------------------------------------------------------------

    def _find_highlight_spans(self, text: str) -> list[tuple[int, int]]:
        """Returns (start, end) spans in *text* to highlight.

        When *self.normalize* is True, matching is accent/case-
        insensitive via ``build_norm_map``.  Otherwise plain
        case-insensitive regex is used.

        Args:
            text: The original cell text.

        Returns:
            List of (start, end) index pairs into *text*.
        """
        if self.normalize:
            norm_search = normalize_for_search(self.search_text)
            if not norm_search:
                return []
            norm_text, orig_map = build_norm_map(text)
            raw: list[tuple[int, int]] = []
            for m in re.finditer(re.escape(norm_search), norm_text):
                orig_start = orig_map[m.start()]
                orig_end = orig_map[m.end() - 1] + 1
                raw.append((orig_start, orig_end))
            # Merge overlapping/duplicate spans caused by multi-char
            # expansion (e.g. ß→ss produces two matches at same position)
            merged: list[tuple[int, int]] = []
            for start, end in raw:
                if merged and start < merged[-1][1]:
                    merged[-1] = (merged[-1][0], max(merged[-1][1], end))
                else:
                    merged.append((start, end))
            return merged

        # Default: plain case-insensitive regex
        return [
            m.span()
            for m in re.finditer(
                re.escape(self.search_text),
                text,
                re.IGNORECASE,
            )
        ]

    # ------------------------------------------------------------------
    # Paint
    # ------------------------------------------------------------------

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionViewItem,
        index: QModelIndex,
    ) -> None:
        """Paints the cell with highlighted search text."""
        text = index.data(Qt.ItemDataRole.DisplayRole)

        # Quick guard: skip highlighting when nothing can match
        if not self.search_text or not text or not self._has_match(text):
            super().paint(painter, option, index)
            return

        # Compute highlight spans and build HTML
        spans = self._find_highlight_spans(text)
        if not spans:
            super().paint(painter, option, index)
            return

        hl_bg = color("highlight_bg")
        hl_text = color("highlight_text")
        parts: list[str] = []
        last_end = 0
        for start, end in spans:
            parts.append(escape(text[last_end:start]))
            parts.append(
                f'<span style="background-color: {hl_bg}; color: {hl_text};">'
                f"{escape(text[start:end])}</span>",
            )
            last_end = end
        parts.append(escape(text[last_end:]))
        highlighted_html = "".join(parts)

        # Draw the standard background (selection, hover, etc.)
        self.initStyleOption(option, index)
        option.text = ""  # Prevent default text drawing
        widget = option.widget
        style = widget.style() if widget else None
        if style:
            style.drawControl(QStyle.ControlElement.CE_ItemViewItem, option, painter)

        # Draw the HTML text — use selected color when row is selected
        sel_color = getattr(self, "_selected_color", None)
        is_selected = bool(option.state & QStyle.StateFlag.State_Selected)
        base_color = (
            sel_color
            if sel_color and is_selected
            else (option.palette.text().color().name())
        )
        doc = QTextDocument()
        doc.setHtml(
            f'<div style="color: {base_color};">{highlighted_html}</div>',
        )

        painter.save()
        # Add padding similar to style_table (12px)
        painter.translate(option.rect.x() + 12, option.rect.y())

        # Center vertically
        text_height = doc.size().height()
        painter.translate(0, (option.rect.height() - text_height) / 2)

        ctx = QAbstractTextDocumentLayout.PaintContext()
        doc.documentLayout().draw(painter, ctx)
        painter.restore()

    def _has_match(self, text: str) -> bool:
        """Quick check whether the search text matches *text* at all."""
        if self.normalize:
            norm = normalize_for_search(self.search_text)
            if not norm:
                return False
            return norm in normalize_for_search(text)
        return self.search_text.lower() in text.lower()


def create_page_container(
    title: str,
    *,
    tr_key: str = "",
) -> tuple[QWidget, QVBoxLayout]:
    """Creates a standardized page container with a header and layout.

    Args:
        title: The header text.
        tr_key: Optional i18n key for automatic language updates.
    """
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(MARGIN_PAGE, MARGIN_PAGE, MARGIN_PAGE, MARGIN_PAGE)
    layout.setSpacing(SPACING_PAGE)

    header = QLabel(title)
    header.setStyleSheet(style_page_header())
    header.setAlignment(Qt.AlignmentFlag.AlignCenter)
    layout.addWidget(header)

    # Expose the header so embedders can hide or restyle it without
    # reaching into the layout by index or matching on translated text.
    page.header_label = header

    def apply_theme() -> None:
        header.setStyleSheet(style_page_header())

    page.apply_theme = apply_theme

    if tr_key:

        def apply_language() -> None:
            header.setText(tr(tr_key))

        page.apply_language = apply_language

    return page, layout


def create_section_group(
    title: str,
    *,
    tr_key: str = "",
    tr_kwargs: dict[str, str] | None = None,
) -> tuple[QFrame, QVBoxLayout, QLabel]:
    """Creates a titled bordered frame for a section.

    Args:
        title: The section title text.
        tr_key: Optional i18n key for automatic language updates.
        tr_kwargs: Optional keyword arguments for the tr() call.
    """
    group = QFrame()
    group.setStyleSheet(style_section_group())
    layout = QVBoxLayout(group)
    layout.setContentsMargins(
        MARGIN_SUBSECTION, MARGIN_SECTION, MARGIN_SUBSECTION, MARGIN_SECTION
    )

    label = QLabel(title)
    label.setStyleSheet(style_section_title())
    layout.addWidget(label)

    def apply_theme() -> None:
        group.setStyleSheet(style_section_group())
        label.setStyleSheet(style_section_title())

    group.apply_theme = apply_theme

    if tr_key:
        kw = tr_kwargs or {}

        def apply_language() -> None:
            label.setText(tr(tr_key, **kw))

        group.apply_language = apply_language

    return group, layout, label


def _build_formats_string() -> str:
    """Builds the supported formats display string."""
    img_exts = ", ".join([ext[1:] for ext in SUPPORTED_IMAGES])
    txt_exts = ", ".join([ext[1:] for ext in SUPPORTED_TEXT])
    return f"{img_exts}, {txt_exts}"


class FileDropWidget(QFrame):
    """A widget that supports dragging and dropping files."""

    files_dropped = Signal(list)

    def __init__(self, parent: QWidget | None = None) -> None:
        """Initializes the FileDropWidget.

        Args:
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFrameShape(QFrame.Shape.StyledPanel)

        self.layout = QVBoxLayout(self)
        self.layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.layout.setSpacing(15)

        self.icon_label = QLabel("📥")
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon_label.setStyleSheet(
            "font-size: 56px; border: none; background: transparent;"
        )
        self.layout.addWidget(self.icon_label)

        self.info_label = QLabel(tr("drop.title"))
        self.info_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._apply_info_label_style()
        self.layout.addWidget(self.info_label)

        self.sub_label = QLabel(tr("drop.subtitle"))
        self.sub_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._apply_sub_label_style()
        self.layout.addWidget(self.sub_label)

        # Supported formats display
        formats = _build_formats_string()
        self.supported_label = QLabel(tr("drop.supported", formats=formats))
        self.supported_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._apply_supported_label_style()
        self.layout.addWidget(self.supported_label)

        # Apply default frame + icon style after all children exist
        self._set_default_style()

    def _apply_info_label_style(self) -> None:
        """Applies theme-aware style to the info label."""
        self.info_label.setStyleSheet(
            f"color: {color('text_primary')}; font-size: 20px; "
            "font-weight: 600; border: none;"
        )

    def _apply_sub_label_style(self) -> None:
        """Applies theme-aware style to the sub label."""
        self.sub_label.setStyleSheet(
            f"color: {color('text_secondary')}; font-size: 14px; border: none;"
        )

    def _apply_supported_label_style(self) -> None:
        """Applies theme-aware style to the supported formats label."""
        self.supported_label.setStyleSheet(
            f"color: {color('text_secondary')}; font-size: 11px; "
            "margin-top: 5px; border: none;"
        )

    def apply_theme(self) -> None:
        """Re-applies all theme-dependent styles."""
        self._set_default_style()
        self._apply_info_label_style()
        self._apply_sub_label_style()
        self._apply_supported_label_style()

    def apply_language(self) -> None:
        """Re-applies all translatable text."""
        # ``info_label`` is the headline "Drag & Drop files here" — easy
        # to forget since the smaller sub/supported labels are more
        # visually obvious; without this line it stays in the boot locale.
        self.info_label.setText(tr("drop.title"))
        self.sub_label.setText(tr("drop.subtitle"))
        formats = _build_formats_string()
        self.supported_label.setText(tr("drop.supported", formats=formats))

    def _set_active_style(self) -> None:
        """Sets the active (drag-over) style."""
        self.setStyleSheet(
            f"""
            QFrame {{
                border: 2px dashed {color("primary")};
                border-radius: {RADIUS_BUTTON}px;
                background-color: {color("hover_light")};
            }}
        """
        )
        self.icon_label.setStyleSheet(
            "font-size: 56px; border: none; background: transparent; margin-top: -5px;"
        )

    def _set_default_style(self) -> None:
        """Sets the default (idle) style."""
        self.setStyleSheet(
            f"""
            QFrame {{
                border: 2px dashed {color("outline")};
                border-radius: {RADIUS_BUTTON}px;
                background-color: {color("app_bg")};
            }}
        """
        )
        self.icon_label.setStyleSheet(
            "font-size: 56px; border: none; background: transparent; margin-top: 0px;"
        )

    def enterEvent(self, event: QEnterEvent) -> None:  # noqa: N802
        """Handles the mouse enter event."""
        self._set_active_style()
        super().enterEvent(event)

    def leaveEvent(self, event: QEvent) -> None:  # noqa: N802
        """Handles the mouse leave event."""
        self._set_default_style()
        super().leaveEvent(event)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        """Handles the drag enter event."""
        if event.mimeData().hasUrls():
            self._set_active_style()
            event.accept()
        else:
            event.ignore()

    def dragLeaveEvent(self, event: QDragLeaveEvent) -> None:  # noqa: N802
        """Handles the drag leave event."""
        self._set_default_style()
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        """Handles the drop event."""
        self._set_default_style()
        dropped_files = [
            url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()
        ]

        if dropped_files:
            self.files_dropped.emit(dropped_files)
            event.accept()
        else:
            event.ignore()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        """Handles the mouse press event."""
        # Allow clicking to also trigger a browse action (handled by parent)
        if event.button() == Qt.MouseButton.LeftButton:
            self.files_dropped.emit([])
        super().mousePressEvent(event)


class FileItemWidget(QFrame):
    """A card-like widget representing a single uploaded file."""

    remove_requested = Signal()

    def __init__(
        self,
        file_path: str,
        format_size_func: Callable[[int], str],
        parent: QWidget | None = None,
    ) -> None:
        """Initializes the FileItemWidget.

        Args:
            file_path: Path to the file.
            format_size_func: Function to format file size.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self.file_path = file_path
        self.setFixedHeight(FILE_ITEM_HEIGHT)
        self._apply_frame_style()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(15)

        # EXTENSION-BASED TEXT BADGE
        p = pathlib.Path(file_path)
        ext = p.suffix[1:].upper() if p.suffix else tr("files.no_extension")
        self.badge = QLabel(ext[:4])
        self.badge.setFixedSize(FILE_ITEM_BADGE_SIZE, FILE_ITEM_BADGE_SIZE)
        self.badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._apply_badge_style()
        layout.addWidget(self.badge)

        # Details
        info_layout = QVBoxLayout()
        info_layout.setSpacing(2)
        info_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        self.name_label = ElidedLabel(p.name)
        self._apply_name_label_style()
        info_layout.addWidget(self.name_label)

        # File Size
        try:
            file_size = p.stat().st_size
            size_str = format_size_func(file_size)
        except OSError:
            size_str = tr("files.unknown_size")

        self.size_label = QLabel(size_str)
        self._apply_size_label_style()
        info_layout.addWidget(self.size_label)
        layout.addLayout(info_layout, 1)

        # Actions
        actions = QHBoxLayout()
        actions.setSpacing(8)

        self.open_btn = QPushButton(tr("btn.view"))
        self.open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._apply_open_btn_style()
        self.open_btn.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(file_path))
        )
        actions.addWidget(self.open_btn)

        self.del_btn = QPushButton("✕")
        self.del_btn.setFixedSize(36, 36)
        self.del_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._apply_del_btn_style()
        self.del_btn.clicked.connect(self.remove_requested.emit)
        actions.addWidget(self.del_btn)

        layout.addLayout(actions)

    def _apply_frame_style(self) -> None:
        """Applies theme-aware frame style."""
        self.setStyleSheet(
            f"""
            QFrame {{
                background-color: {color("component_bg")};
                border: 1px solid {color("border_light")};
                border-radius: {RADIUS_BUTTON}px;
            }}
            QFrame:hover {{
                background-color: {color("hover_light")};
            }}
        """
        )

    def _apply_badge_style(self) -> None:
        """Applies theme-aware badge style."""
        self.badge.setStyleSheet(
            f"""
            background-color: {color("hover_light")};
            color: {color("primary")};
            border-radius: 10px;
            font-size: 12px;
            font-weight: 800;
        """
        )

    def _apply_name_label_style(self) -> None:
        """Applies theme-aware name label style."""
        self.name_label.setStyleSheet(
            f"color: {color('text_primary')}; font-size: 15px; font-weight: 600; "
            "border: none; background: transparent;"
        )

    def _apply_size_label_style(self) -> None:
        """Applies theme-aware size label style."""
        self.size_label.setStyleSheet(
            f"color: {color('text_secondary')}; font-size: 12px; "
            "border: none; background: transparent;"
        )

    def _apply_open_btn_style(self) -> None:
        """Applies theme-aware open button style."""
        self.open_btn.setStyleSheet(
            f"""
            QPushButton {{
                background: transparent;
                border: none;
                border-radius: 8px;
                color: {color("text_secondary")};
                font-size: 13px;
                font-weight: 600;
                padding: 6px 14px;
            }}
            QPushButton:hover {{
                color: {color("primary")};
            }}
        """
        )

    def _apply_del_btn_style(self) -> None:
        """Applies theme-aware delete button style."""
        self.del_btn.setStyleSheet(
            f"""
            QPushButton {{
                background: transparent;
                border: none;
                color: {color("disabled_text")};
                font-size: 18px;
                font-weight: bold;
            }}
            QPushButton:hover {{ color: {color("error")}; }}
        """
        )

    def apply_theme(self) -> None:
        """Re-applies all theme-dependent styles."""
        self._apply_frame_style()
        self._apply_badge_style()
        self._apply_name_label_style()
        self._apply_size_label_style()
        self._apply_open_btn_style()
        self._apply_del_btn_style()

    def apply_language(self) -> None:
        """Re-applies all translatable text."""
        self.open_btn.setText(tr("btn.view"))


class HoverIconButton(QPushButton):
    """A QPushButton that changes its icon on hover to simulate color change."""

    def __init__(
        self,
        normal_icon_path: str,
        hover_icon_path: str,
        parent: QWidget | None = None,
    ) -> None:
        """Initializes the HoverIconButton.

        Args:
            normal_icon_path: Path to the normal icon.
            hover_icon_path: Path to the hover icon.
            parent: Optional parent widget.
        """
        super().__init__(parent)
        self.normal_icon = QIcon(normal_icon_path)
        self.hover_icon = QIcon(hover_icon_path)
        self.setIcon(self.normal_icon)

    def set_icons(self, normal_path: str, hover_path: str) -> None:
        """Updates the normal and hover icons.

        Args:
            normal_path: New normal icon path.
            hover_path: New hover icon path.
        """
        self.normal_icon = QIcon(normal_path)
        self.hover_icon = QIcon(hover_path)
        # Refresh current icon based on mouse position
        if self.underMouse():
            self.setIcon(self.hover_icon)
        else:
            self.setIcon(self.normal_icon)

    def enterEvent(self, event: QEnterEvent) -> None:  # noqa: N802
        """Handles mouse enter."""
        self.setIcon(self.hover_icon)
        super().enterEvent(event)

    def leaveEvent(self, event: QEvent) -> None:  # noqa: N802
        """Handles mouse leave."""
        self.setIcon(self.normal_icon)
        super().leaveEvent(event)


def remask_secrets(root: QWidget) -> None:
    """Re-mask every revealed secret QLineEdit under *root*.

    Walks descendants for fields tagged ``aitSecret`` (set by
    ``create_setting_input(is_password=True)``) and calls each field's
    ``_remask_secret`` helper to flip echo mode back to ``Password`` and
    reset the toggle icon.  Pages call this from their ``hideEvent`` so
    a revealed API key doesn't survive a navigation.
    """
    for field in root.findChildren(QLineEdit):
        if not field.property("aitSecret"):
            continue
        remask = getattr(field, "_remask_secret", None)
        if remask is not None:
            remask()


def create_setting_input(  # noqa: PLR0913, PLR0915
    label_text: str,
    setting_key: str,
    placeholder: str = "",
    is_password: bool = False,
    *,
    label_tr_key: str = "",
    placeholder_tr_key: str = "",
    placeholder_tr_kwargs: dict[str, str] | None = None,
) -> tuple[QWidget, QLineEdit]:
    """Creates a reusable setting input widget.

    Args:
        label_text: Display text for the label.
        setting_key: Persistent setting key for the value.
        placeholder: Placeholder text shown when the field is empty.
        is_password: Whether to mask input as a password field.
        label_tr_key: Translation key for the label text.
        placeholder_tr_key: Translation key for the placeholder text.
        placeholder_tr_kwargs: Extra keyword arguments for placeholder translation.
    """
    container = QWidget()
    container.setStyleSheet(style_setting_container())
    layout = QHBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)

    label = QLabel(label_text)
    label.setStyleSheet(style_input_label())
    label.setFixedWidth(LABEL_WIDTH)  # Fixed label width for alignment
    label.setFixedHeight(HEIGHT_CONTROL)
    label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

    input_field = QLineEdit()
    input_field.setPlaceholderText(placeholder)
    input_field.setStyleSheet(style_input_field())
    input_field.setFixedHeight(HEIGHT_CONTROL)

    if is_password:
        input_field.setEchoMode(QLineEdit.EchoMode.Password)
        # Marker so a parent page can find every secret field (e.g. to
        # re-mask them when the page is hidden).  See ``remask_secret``.
        input_field.setProperty("aitSecret", True)

        toggle_btn = HoverIconButton(EYE_PATH, EYE_PRIMARY_PATH)
        toggle_btn.setIconSize(QSize(TOGGLE_ICON_SIZE, TOGGLE_ICON_SIZE))
        toggle_btn.setFixedWidth(TOGGLE_BUTTON_WIDTH)
        toggle_btn.setFixedHeight(HEIGHT_CONTROL)
        toggle_btn.setFlat(True)
        toggle_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        toggle_btn.setStyleSheet(style_link_button())

        def _mask() -> None:
            input_field.setEchoMode(QLineEdit.EchoMode.Password)
            toggle_btn.set_icons(EYE_PATH, EYE_PRIMARY_PATH)

        def _reveal() -> None:
            input_field.setEchoMode(QLineEdit.EchoMode.Normal)
            toggle_btn.set_icons(EYE_OFF_PATH, EYE_OFF_PRIMARY_PATH)

        def toggle_visibility() -> None:
            """Toggles the password field between masked and visible modes."""
            if input_field.echoMode() == QLineEdit.EchoMode.Password:
                _reveal()
            else:
                _mask()

        toggle_btn.clicked.connect(toggle_visibility)
        # Expose the masking action so the owning page can re-mask the
        # field on hide without knowing which icons are in play.
        input_field._remask_secret = _mask  # type: ignore[attr-defined]

    # Load saved key
    input_field.blockSignals(True)
    input_field.setText(load_setting(setting_key, ""))
    input_field.blockSignals(False)

    input_field.textChanged.connect(
        lambda text: save_setting(setting_key, text.strip())
    )

    layout.addWidget(label)
    layout.addWidget(input_field)
    if is_password:
        layout.addWidget(toggle_btn)

    def apply_theme() -> None:
        container.setStyleSheet(style_setting_container())
        label.setStyleSheet(style_input_label())
        input_field.setStyleSheet(style_input_field())
        if is_password:
            toggle_btn.setStyleSheet(style_link_button())

    container.apply_theme = apply_theme

    if label_tr_key or placeholder_tr_key:
        ph_kw = placeholder_tr_kwargs or {}

        def apply_language() -> None:
            if label_tr_key:
                label.setText(tr(label_tr_key))
            if placeholder_tr_key:
                input_field.setPlaceholderText(tr(placeholder_tr_key, **ph_kw))

        container.apply_language = apply_language

    return container, input_field


def create_setting_combo(
    label_text: str,
    setting_key: str,
    items: list[str],
    *,
    label_tr_key: str = "",
) -> tuple[QWidget, QComboBox]:
    """Creates a reusable setting combo box widget.

    Args:
        label_text: Display text for the label.
        setting_key: Persistent setting key for the selected value.
        items: List of combo box option strings.
        label_tr_key: Translation key for the label text.
    """
    container = QWidget()
    container.setStyleSheet(style_setting_container())
    layout = QHBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)

    label = QLabel(label_text)
    label.setStyleSheet(style_input_label())
    label.setFixedWidth(LABEL_WIDTH)
    label.setFixedHeight(HEIGHT_CONTROL)
    label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

    combo = QComboBox()
    combo.addItems(items)
    combo.setCursor(Qt.CursorShape.PointingHandCursor)
    combo.view().setCursor(Qt.CursorShape.PointingHandCursor)
    # Tell Qt the popup view rows are uniform — without this the
    # ``combobox-popup: 0`` styled dropdown overestimates row height
    # and reserves an empty slot below the last item.
    combo.view().setUniformItemSizes(True)
    combo.view().setSpacing(0)
    combo.setStyleSheet(style_setting_combo())
    combo.setFixedHeight(HEIGHT_CONTROL)

    # Load saved value
    saved_val = load_setting(setting_key, items[0] if items else "")
    index = combo.findText(saved_val)
    if index >= 0:
        combo.blockSignals(True)
        combo.setCurrentIndex(index)
        combo.blockSignals(False)

    combo.currentTextChanged.connect(lambda text: save_setting(setting_key, text))

    layout.addWidget(label)
    layout.addWidget(combo, 1)

    def apply_theme() -> None:
        container.setStyleSheet(style_setting_container())
        label.setStyleSheet(style_input_label())
        combo.setStyleSheet(style_setting_combo())

    container.apply_theme = apply_theme

    if label_tr_key:

        def apply_language() -> None:
            label.setText(tr(label_tr_key))

        container.apply_language = apply_language

    return container, combo


def create_setting_path(  # noqa: PLR0913, PLR0915
    label_text: str,
    setting_key: str,
    parent: QWidget | None = None,
    custom_label_width: int | None = None,
    *,
    label_tr_key: str = "",
    browse_mode: str = "directory",
    dialog_title_tr_key: str = "dialog.select_storage",
    default_path: str = "",
    placeholder_tr_key: str = "",
) -> tuple[QWidget, ElidedLabel]:
    """Creates a reusable setting path selection widget with a Browse button.

    Args:
        label_text: Display text for the label.
        setting_key: Persistent setting key for the path.
        parent: Optional parent widget.
        custom_label_width: Override for the label width.
        label_tr_key: Translation key for the label text.
        browse_mode: "directory" for folder selection, "file" for file selection.
        dialog_title_tr_key: Translation key for the file dialog title.
        default_path: Fallback path when no saved value exists.
        placeholder_tr_key: Translation key for placeholder text shown when empty.
    """
    container = QWidget()
    container.setStyleSheet(style_setting_container())
    layout = QHBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)

    label = QLabel(label_text)
    label.setStyleSheet(style_input_label() + "margin-top: 4px;")
    label.setFixedWidth(custom_label_width or LABEL_WIDTH)
    label.setFixedHeight(HEIGHT_CONTROL)
    label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

    # Define on_browse first so it can be passed to ElidedLabel
    def on_browse() -> None:
        from src.utils.path_manager import get_desktop_path  # noqa: PLC0415

        start_dir = path_label._full_text or str(get_desktop_path())
        if browse_mode == "file":
            selected, _ = QFileDialog.getOpenFileName(
                container, tr(dialog_title_tr_key), start_dir
            )
        else:
            selected = QFileDialog.getExistingDirectory(
                container, tr(dialog_title_tr_key), start_dir
            )
        if selected:
            path_label.set_text(selected)
            save_setting(setting_key, selected)
            reset_btn.setVisible(bool(placeholder_tr_key))

    _fallback = default_path or ""
    _placeholder = tr(placeholder_tr_key) if placeholder_tr_key else ""

    path_label = ElidedLabel(
        clicked=on_browse, draw_border=True, placeholder=_placeholder
    )
    path_label.setStyleSheet(style_input_field().replace("QLineEdit", "QLabel"))
    path_label.setFixedHeight(HEIGHT_CONTROL)
    path_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

    # Load saved path; empty string shows placeholder text
    saved_path = load_setting(setting_key, _fallback)
    path_label.set_text(saved_path or "")

    browse_btn = QPushButton(tr("btn.browse"))
    browse_btn.setFixedHeight(HEIGHT_CONTROL)
    browse_btn.setFixedWidth(BROWSE_BUTTON_WIDTH)
    browse_btn.setCursor(Qt.CursorShape.PointingHandCursor)

    browse_btn.setStyleSheet(style_link_button() + "margin-top: 4px;")

    browse_btn.clicked.connect(on_browse)

    # Reset button — clears the picker back to its default (empty
    # string when no ``default_path`` was set, otherwise to the
    # supplied default).  Only shown when ``placeholder_tr_key`` was
    # passed by the caller — that signals "empty is a meaningful
    # state for this field" (e.g. Auto-save fallback to next-to-
    # source / Desktop).  Pickers without a placeholder (LibreOffice
    # binary path, credentials file path, etc.) have no defensible
    # empty state, so no Reset button.  Visibility tracks the path
    # field's content: hidden when the field is empty (nothing to
    # reset) so the button doesn't add noise to the default state.
    reset_btn = QPushButton(tr("btn.reset"))
    reset_btn.setFixedHeight(HEIGHT_CONTROL)
    reset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    reset_btn.setStyleSheet(style_link_button_muted() + "margin-top: 4px;")
    reset_btn.setVisible(
        bool(placeholder_tr_key) and bool(saved_path),
    )

    def on_reset() -> None:
        """Clears the picker back to the default (empty for Auto)."""
        path_label.set_text(_fallback)
        save_setting(setting_key, _fallback)
        reset_btn.setVisible(False)

    reset_btn.clicked.connect(on_reset)

    layout.addWidget(label)
    layout.addWidget(path_label, 1)
    layout.addWidget(browse_btn)
    layout.addWidget(reset_btn)

    def apply_theme() -> None:
        container.setStyleSheet(style_setting_container())
        label.setStyleSheet(style_input_label() + "margin-top: 4px;")
        path_label.setStyleSheet(style_input_field().replace("QLineEdit", "QLabel"))
        browse_btn.setStyleSheet(style_link_button() + "margin-top: 4px;")
        reset_btn.setStyleSheet(style_link_button_muted() + "margin-top: 4px;")

    container.apply_theme = apply_theme

    def apply_language() -> None:
        browse_btn.setText(tr("btn.browse"))
        reset_btn.setText(tr("btn.reset"))
        if label_tr_key:
            label.setText(tr(label_tr_key))
        if placeholder_tr_key:
            path_label.set_placeholder(tr(placeholder_tr_key))

    container.apply_language = apply_language

    def set_path(value: str) -> None:
        """Programmatically updates the path (display + persisted setting).

        Used by callers that want to auto-fill the path on a state
        change (e.g. Live's auto-save combo flipping from None to a
        save mode pre-fills the default folder so the user sees where
        files will land).
        """
        path_label.set_text(value or "")
        save_setting(setting_key, value or "")
        reset_btn.setVisible(bool(placeholder_tr_key) and bool(value))

    container.set_path = set_path

    return container, path_label


def create_setting_checkbox(
    label_text: str,
    setting_key: str,
    default: bool = False,
    *,
    label_tr_key: str = "",
) -> tuple[QWidget, QCheckBox]:
    """Creates a reusable setting checkbox widget.

    Args:
        label_text: Display text for the checkbox label.
        setting_key: Persistent setting key for the checked state.
        default: Default checked state when no saved value exists.
        label_tr_key: Translation key for the checkbox label text.
    """
    container = QWidget()
    container.setStyleSheet(style_setting_container())
    layout = QHBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)

    checkbox = QCheckBox(label_text)
    checkbox.setCursor(Qt.CursorShape.PointingHandCursor)
    checkbox.setStyleSheet(style_checkbox())
    checkbox.setFixedHeight(HEIGHT_CONTROL)

    # Load saved value
    saved_val = load_setting(setting_key, default)
    checkbox.blockSignals(True)
    checkbox.setChecked(bool(saved_val))
    checkbox.blockSignals(False)

    checkbox.toggled.connect(lambda checked: save_setting(setting_key, checked))

    layout.addWidget(checkbox)
    layout.addStretch()

    def apply_theme() -> None:
        container.setStyleSheet(style_setting_container())
        checkbox.setStyleSheet(style_checkbox())

    container.apply_theme = apply_theme

    if label_tr_key:

        def apply_language() -> None:
            checkbox.setText(tr(label_tr_key))

        container.apply_language = apply_language

    return container, checkbox


class _TableKeyFilter(QObject):
    """Event filter that adds keyboard shortcuts to a QTableWidget.

    - Enter / Return: invokes the provided callback (e.g. open file, view entry).
    - Ctrl+A: selects all rows (works even when the table already has focus).
    """

    def __init__(
        self,
        table: QTableWidget,
        enter_callback: Callable[[], None],
        parent: QObject | None = None,
    ) -> None:
        """Initializes the key filter.

        Args:
            table: The table widget to monitor.
            enter_callback: Called when Enter/Return is pressed with a selection.
            parent: Optional parent QObject.
        """
        super().__init__(parent)
        self._table = table
        self._enter_callback = enter_callback

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # noqa: N802
        """Handles Enter and Ctrl+A key presses on the table."""
        if event.type() == QEvent.Type.KeyPress:
            key_event: QKeyEvent = event  # type: ignore[assignment]
            key = key_event.key()

            # Enter / Return → trigger callback if rows are selected
            if (
                key in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
                and self._table.selectedItems()
            ):
                self._enter_callback()
                return True

            # Ctrl+A → select all rows
            if (
                key == Qt.Key.Key_A
                and key_event.modifiers() == Qt.KeyboardModifier.ControlModifier
            ):
                self._table.selectAll()
                return True

        return super().eventFilter(obj, event)


class _TableResizeFilter(QObject):
    """Event filter that proportionally distributes width among interactive columns.

    Installed on the table's viewport so that when the table is resized,
    interactive columns maintain their width ratios instead of staying fixed.
    """

    def __init__(
        self,
        table: QTableWidget,
        interactive_cols: list[int],
        column_widths: dict[int, int] | None = None,
        parent: QObject | None = None,
    ) -> None:
        """Initializes the resize filter.

        Args:
            table: The table widget to manage.
            interactive_cols: Column indices that participate in proportional resizing.
            column_widths: Initial fixed widths for specific columns. On window
                resize, columns with explicit widths keep them and remaining space
                is distributed to interactive columns without explicit widths.
            parent: Optional parent QObject.
        """
        super().__init__(parent)
        self._table = table
        self._interactive_cols = interactive_cols
        self._interactive_set = set(interactive_cols)
        self._initial_widths = dict(column_widths) if column_widths else {}
        self._adjusting = False
        self._min_section_width = MIN_COLUMN_WIDTH

        # Listen for user-drag column resizes
        table.horizontalHeader().sectionResized.connect(self._on_section_resized)

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # noqa: N802
        """Redistributes interactive column widths on viewport resize."""
        if event.type() == QEvent.Type.Resize:
            self._redistribute()
        return super().eventFilter(obj, event)

    def _redistribute(self) -> None:
        """On window resize, flex columns absorb size changes; pinned stay fixed."""
        if self._adjusting:
            return
        self._adjusting = True
        try:
            self._do_redistribute()
        finally:
            self._adjusting = False

    def _do_redistribute(self) -> None:
        """Calculates and applies proportional widths for flex columns."""
        header = self._table.horizontalHeader()
        viewport_width = self._table.viewport().width()

        # Sum widths of non-interactive columns
        non_interactive_width = sum(
            header.sectionSize(col)
            for col in range(header.count())
            if col not in self._interactive_set
        )
        available = viewport_width - non_interactive_width
        if available <= 0:
            return

        # Columns with explicit initial widths keep their current size;
        # only "flexible" columns (no explicit width) absorb size changes.
        pinned_cols = [
            col for col in self._interactive_cols if col in self._initial_widths
        ]
        flex_cols = [
            col for col in self._interactive_cols if col not in self._initial_widths
        ]

        pinned_total = sum(header.sectionSize(col) for col in pinned_cols)
        flex_available = available - pinned_total
        if flex_available <= 0 or not flex_cols:
            return

        flex_widths = [header.sectionSize(col) for col in flex_cols]
        flex_total = sum(flex_widths)

        if flex_total <= 0:
            # Uninitialized — distribute equally among flexible columns
            per_col = flex_available // len(flex_cols)
            for col in flex_cols:
                self._table.setColumnWidth(col, per_col)
        else:
            # Distribute proportionally among flexible columns
            for col, cur_w in zip(flex_cols, flex_widths, strict=True):
                new_w = int(flex_available * cur_w / flex_total)
                self._table.setColumnWidth(col, max(new_w, 1))

    # ------------------------------------------------------------------
    # User-drag column resize — column N+1 absorbs the delta
    # ------------------------------------------------------------------

    def _on_section_resized(
        self,
        logical_index: int,
        old_size: int,
        new_size: int,
    ) -> None:
        """When user drags column N, adjusts column N+1 to keep total constant."""
        if self._adjusting:
            return
        self._adjusting = True
        try:
            self._compensate_drag(logical_index, old_size, new_size)
        finally:
            self._adjusting = False

    def _compensate_drag(
        self,
        col: int,
        old_size: int,
        new_size: int,
    ) -> None:
        """Shifts the width delta from column *col* onto the next column."""
        header = self._table.horizontalHeader()
        col_count = header.count()
        delta = new_size - old_size
        if delta == 0 or col + 1 >= col_count:
            return

        neighbor = col + 1
        neighbor_width = header.sectionSize(neighbor)
        adjusted = neighbor_width - delta

        if adjusted < self._min_section_width:
            # Clamp neighbor at minimum and shrink col N back accordingly
            adjusted = self._min_section_width
            max_col_width = old_size + (neighbor_width - self._min_section_width)
            self._table.setColumnWidth(col, max_col_width)

        self._table.setColumnWidth(neighbor, adjusted)


def create_table(
    headers: list[str],
    stretch_columns: list[int] | None = None,
    column_widths: dict[int, int] | None = None,
    interactive_columns: list[int] | None = None,
    enter_callback: Callable[[], None] | None = None,
) -> QTableWidget:
    """Creates a standardized QTableWidget with consistent styling.

    Args:
        headers: Column header labels.
        stretch_columns: Column indices that stretch to fill space.
            Defaults to [0] (first column).
        column_widths: Mapping of column index to fixed pixel width.
        interactive_columns: Column indices that use Interactive resize mode
            (user can drag to resize). When the table resizes, these columns
            maintain their width ratios. Overrides stretch_columns for the
            specified indices.
        enter_callback: Called when Enter/Return is pressed with a selection.
            Also installs Ctrl+A to select all rows.
    """
    table = QTableWidget(0, len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.setStyleSheet(style_table())
    table.setAlternatingRowColors(True)
    table.setShowGrid(False)
    table.setSortingEnabled(True)
    table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
    table.setCursor(Qt.CursorShape.PointingHandCursor)

    # Vertical header
    table.verticalHeader().setVisible(False)
    table.verticalHeader().setDefaultSectionSize(40)

    # Horizontal header
    header = table.horizontalHeader()
    header.setMinimumSectionSize(50)
    header.setCursor(Qt.CursorShape.PointingHandCursor)
    header.setDefaultAlignment(
        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
    )

    # Column sizing
    if stretch_columns is None:
        stretch_columns = [0]
    interactive_set = set(interactive_columns) if interactive_columns else set()
    for col in range(len(headers)):
        if col in interactive_set:
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
        elif col in stretch_columns:
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Stretch)
        else:
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Fixed)

    if column_widths:
        for col, width in column_widths.items():
            table.setColumnWidth(col, width)

    # Install proportional resize filter for interactive columns
    if interactive_columns:
        resize_filter = _TableResizeFilter(
            table,
            interactive_columns,
            column_widths,
            table,
        )
        table.viewport().installEventFilter(resize_filter)

    # Install keyboard shortcut filter (Enter to act, Ctrl+A to select all)
    if enter_callback:
        key_filter = _TableKeyFilter(table, enter_callback, table)
        table.installEventFilter(key_filter)

    return table


def create_banner(  # noqa: PLR0915
    text: str,
    variant: str = "warning",
    tr_key: str | None = None,
    *,
    rich_text: bool = False,
) -> tuple[QFrame, QLabel]:
    """Creates a stylized banner with an icon for warning, error, success, or info.

    Args:
        text: The initial message text.
        variant: Visual style — "warning", "error", "success", or "info".
        tr_key: Optional translation key to dynamically update text on language change.
        rich_text: If True, render text as HTML (enables clickable links).

    Returns:
        A tuple of (the QFrame banner container, the QLabel containing the text).
    """
    banner = QFrame()
    banner.setObjectName("Banner")
    layout = QHBoxLayout(banner)
    layout.setContentsMargins(
        BANNER_PADDING,
        BANNER_PADDING,
        BANNER_PADDING,
        BANNER_PADDING,
    )
    layout.setSpacing(BANNER_SPACING)

    icon_map = {
        "warning": ALERT_TRIANGLE_PATH,
        "error": ALERT_CIRCLE_PATH,
        "success": CHECK_CIRCLE_PATH,
        "info": INFO_PATH,
    }
    icon_path = icon_map.get(variant, ALERT_TRIANGLE_PATH)

    icon_label = QLabel()
    icon_label.setObjectName("BannerIcon")
    icon_label.setPixmap(QIcon(icon_path).pixmap(BANNER_ICON_SIZE, BANNER_ICON_SIZE))
    icon_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
    layout.addWidget(icon_label)

    def _format_text(raw: str) -> str:
        """Converts newlines to HTML paragraphs for rich text mode."""
        if rich_text:
            lines = raw.split("\n")
            parts = [
                f"<p style='margin:0 0 {BANNER_LINE_SPACING}px 0;'>{line}</p>"
                for line in lines
            ]
            return "".join(parts)
        return raw

    text_label = QLabel(_format_text(text))
    text_label.setObjectName("BannerText")
    text_label.setWordWrap(True)
    text_label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)

    if rich_text:
        text_label.setTextFormat(Qt.TextFormat.RichText)
        text_label.setOpenExternalLinks(True)

    layout.addWidget(text_label, 1)

    banner.setStyleSheet(style_banner(variant))

    def _apply_theme() -> None:
        banner.setStyleSheet(style_banner(variant))
        icon_pixmap = QIcon(icon_path).pixmap(BANNER_ICON_SIZE, BANNER_ICON_SIZE)
        icon_label.setPixmap(icon_pixmap)

    banner.apply_theme = _apply_theme

    if tr_key:

        def _apply_language() -> None:
            text_label.setText(_format_text(tr(tr_key)))

        banner.apply_language = _apply_language

    return banner, text_label


def create_ffmpeg_install_banner() -> tuple[QFrame, Callable[[], None]]:
    """Creates a top-of-page FFmpeg-missing setup-hint banner.

    Shown at the top of every page that generates or saves audio files
    (Generate Voice, Dubbing, Live Translation) so users see the
    install instructions before kicking off a job that would otherwise
    fail at runtime.  The per-OS dispatcher follows the same pattern
    as ``LivePage._sync_system_audio_warning`` and the Dubbing /
    Voice settings-tab FFmpeg banners.

    Returns ``(banner_frame, refresh_callable)``.  The caller is
    responsible for:
      * Placing ``banner_frame`` at the top of the page layout.
      * Calling ``refresh_callable()`` once at construction.
      * Calling ``refresh_callable()`` from ``showEvent`` so a user
        who installs ffmpeg in another window doesn't have to restart
        the app — switching tabs once clears the banner.

    The banner is hidden when ffmpeg is on PATH and auto-localizes via
    ``apply_language`` on locale switch.
    """
    banner, label = create_banner("", variant="warning", rich_text=True)

    def _refresh() -> None:
        """Re-renders the per-OS install hint text + visibility."""
        import platform  # noqa: PLC0415
        import shutil  # noqa: PLC0415

        from src.utils.install_hints import (  # noqa: PLC0415
            format_install_clause,
            get_ffmpeg_install_hint,
        )

        system = platform.system()
        if system == "Linux":
            label.setText(
                tr(
                    "settings.ffmpeg_install_linux",
                    linux_install=format_install_clause(get_ffmpeg_install_hint()),
                ),
            )
        elif system == "Darwin":
            label.setText(tr("settings.ffmpeg_install_macos"))
        elif system == "Windows":
            label.setText(tr("settings.ffmpeg_install_windows"))
        else:
            label.setText(tr("settings.ffmpeg_install_unsupported"))
        banner.setVisible(shutil.which("ffmpeg") is None)

    banner.apply_language = _refresh
    return banner, _refresh


# ── Tag input widget ─────────────────────────────────────────────────────


def create_setting_tag_input(
    label_text: str,
    setting_key: str,
    placeholder: str = "",
    *,
    label_tr_key: str = "",
    placeholder_tr_key: str = "",
) -> tuple[QWidget, "TagInput"]:
    """Creates a setting row with a label and a tag input widget.

    Follows the same label+input layout pattern as ``create_setting_input``.

    Args:
        label_text: Display text for the label.
        setting_key: Persistent setting key (stored as comma-separated).
        placeholder: Placeholder text for the input field.
        label_tr_key: Translation key for the label text.
        placeholder_tr_key: Translation key for the placeholder text.

    Returns:
        Tuple of (container widget, TagInput instance).
    """
    container = QWidget()
    container.setStyleSheet(style_setting_container())
    row = QHBoxLayout(container)
    row.setContentsMargins(0, 0, 0, 0)

    label = QLabel(label_text)
    label.setStyleSheet(style_input_label())
    label.setFixedWidth(LABEL_WIDTH)
    label.setFixedHeight(HEIGHT_CONTROL)
    label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    row.addWidget(label, alignment=Qt.AlignmentFlag.AlignTop)

    tag_input = TagInput(placeholder=placeholder)
    # Callers that need a custom persistence path (e.g. the custom-LLM
    # provider's model tags, which round-trip through a JSON blob) pass an
    # empty ``setting_key`` and wire their own ``tags_changed`` handler.
    # Skip the built-in auto-save in that case — otherwise the lambda
    # below writes to the empty key and configparser emits bare "= value"
    # lines that corrupt neighbouring keys on reload.
    if setting_key:
        saved = load_setting(setting_key, "")
        if saved:
            tag_input.set_tags([t.strip() for t in saved.split(",") if t.strip()])
        tag_input.tags_changed.connect(
            lambda _tags: save_setting(setting_key, tag_input.text()),
        )
    tag_input.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    row.addWidget(tag_input)

    def apply_theme() -> None:
        """Refreshes styles on theme change."""
        container.setStyleSheet(style_setting_container())
        label.setStyleSheet(style_input_label())

    container.apply_theme = apply_theme  # type: ignore[attr-defined]

    if label_tr_key:

        def apply_language() -> None:
            """Refreshes label on language change."""
            label.setText(tr(label_tr_key))
            if placeholder_tr_key:
                tag_input._input.setPlaceholderText(tr(placeholder_tr_key))

        container.apply_language = apply_language  # type: ignore[attr-defined]

    return container, tag_input


class _TagFlowLayout(QHBoxLayout):
    """A wrapping flow layout for tag chips inside TagInput.

    Lays out items left-to-right, wrapping to the next row when the
    available width is exceeded.  The last item (the QLineEdit) fills
    the remaining space on its row.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._spacing = 4

    def setGeometry(self, rect) -> None:  # noqa: N802, ANN001
        """Arranges items with wrapping."""
        super().setGeometry(rect)
        self._do_layout(rect)

    def _do_layout(self, rect) -> int:  # noqa: ANN001
        """Positions items with word-wrap, returns total height."""
        x = rect.x() + self.contentsMargins().left()
        y = rect.y() + self.contentsMargins().top()
        margins = self.contentsMargins()
        max_w = rect.width() - margins.left() - margins.right()
        row_h = 0
        start_x = x

        for i in range(self.count()):
            item = self.itemAt(i)
            wid = item.widget()
            if wid is None or not wid.isVisible():
                continue
            hint = wid.sizeHint()
            is_last = i == self.count() - 1

            if is_last:
                # Last widget (the input) fills remaining width on current row
                remaining = max(80, start_x + max_w - x)  # noqa: PLR2004
                wid.setGeometry(x, y, remaining, hint.height())
                row_h = max(row_h, hint.height())
            else:
                if x + hint.width() > start_x + max_w and x > start_x:
                    x = start_x
                    y += row_h + self._spacing
                    row_h = 0
                wid.setGeometry(x, y, hint.width(), hint.height())
                x += hint.width() + self._spacing
                row_h = max(row_h, hint.height())

        return (
            y
            + row_h
            - rect.y()
            + self.contentsMargins().top()
            + self.contentsMargins().bottom()
        )

    def hasHeightForWidth(self) -> bool:  # noqa: N802
        """This layout's height depends on width."""
        return True

    def heightForWidth(self, width: int) -> int:  # noqa: N802
        """Calculates height needed for the given width."""
        from PySide6.QtCore import QRect  # noqa: PLC0415

        return self._do_layout(QRect(0, 0, width, 0))

    def sizeHint(self):  # noqa: N802, ANN201, ANN202
        """Returns default size."""
        return QSize(200, HEIGHT_CONTROL)

    def minimumSize(self):  # noqa: N802, ANN201, ANN202
        """Returns minimum size."""
        return QSize(0, HEIGHT_CONTROL)


class TagInput(QFrame):
    """Ant Design-style tag input — chips rendered inside the input field.

    Tags are shown as inline chips followed by a text input, all within
    a single bordered container.  Wraps to multiple lines when needed.
    New tags are added via Enter or comma.
    Emits ``tags_changed`` when the tag list is modified.
    """

    tags_changed = Signal(list)

    def __init__(
        self,
        parent: QWidget | None = None,
        placeholder: str = "",
    ) -> None:
        """Initializes the tag input widget."""
        super().__init__(parent)
        self._tags: list[str] = []
        self._placeholder = placeholder

        # Outer container styled like a standard input field
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self._apply_border_style()

        # Wrapping flow layout: chips + input inline
        self._flow = _TagFlowLayout()
        self._flow.setContentsMargins(8, 8, 8, 0)
        self.setLayout(self._flow)

        # Inline text input (borderless, grows to fill remaining space)
        self._input = QLineEdit()
        self._input.setPlaceholderText(placeholder)
        self._input.setFrame(False)
        self._input.setStyleSheet(
            f"background: transparent; color: {color('text_primary')};"
            " font-size: 14px; padding: 4px;"
        )
        self._input.setMinimumWidth(80)  # noqa: PLR2004
        self._input.returnPressed.connect(self._on_enter)
        self._input.textChanged.connect(self._on_text_changed)
        self._input.installEventFilter(self)
        self._flow.addWidget(self._input)

        self.setMinimumHeight(HEIGHT_CONTROL)

    def _apply_border_style(self, focused: bool = False) -> None:
        """Applies the container border style matching standard input fields."""
        if focused:
            self.setStyleSheet(
                f"TagInput {{ background: {color('component_bg')};"
                f" border: 2px solid {color('primary')};"
                f" border-radius: {RADIUS_BUTTON}px; }}"
            )
        else:
            self.setStyleSheet(
                f"TagInput {{ background: {color('component_bg')};"
                f" border: 1px solid {color('secondary')};"
                f" border-radius: {RADIUS_BUTTON}px; }}"
            )

    def eventFilter(  # noqa: N802
        self,
        obj: QObject,
        event: QEvent,
    ) -> bool:
        """Tracks focus and handles Backspace to remove the last tag."""
        if obj is self._input:
            if event.type() == QEvent.Type.FocusIn:
                self._apply_border_style(focused=True)
            elif event.type() == QEvent.Type.FocusOut:
                # Treat focus loss as confirmation: a typed-but-uncommitted
                # value would otherwise be silently discarded when the user
                # tabs / clicks away.  Backspace still removes a chip the
                # user added by accident.
                self._on_enter()
                self._apply_border_style(focused=False)
            elif (
                event.type() == QEvent.Type.KeyPress
                and event.key() == Qt.Key.Key_Backspace
                and not self._input.text()
                and self._tags
            ):
                self._remove_tag(self._tags[-1])
                return True
        return super().eventFilter(obj, event)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        """Clicking anywhere in the container focuses the input."""
        self._input.setFocus()
        super().mousePressEvent(event)

    def resizeEvent(self, event: QEvent) -> None:  # noqa: N802
        """Recalculates height when width changes."""
        super().resizeEvent(event)
        self._update_height()

    def tags(self) -> list[str]:
        """Returns the current list of tags."""
        return list(self._tags)

    def set_tags(self, tags: list[str]) -> None:
        """Replaces all tags with the given list."""
        # Remove existing chips
        for tag in list(self._tags):
            self._remove_chip(tag)
        self._tags.clear()
        for raw_tag in tags:
            tag = raw_tag.strip()
            if tag and tag not in self._tags:
                self._tags.append(tag)
                self._insert_chip(tag)
        self._update_placeholder()
        self._update_height()
        self.tags_changed.emit(self._tags)

    def text(self) -> str:
        """Returns tags as a comma-separated string (for settings compat)."""
        return ", ".join(self._tags)

    def _on_enter(self) -> None:
        """Adds the current input text as a tag."""
        raw = self._input.text().strip().rstrip(",").strip()
        if raw:
            self._add_tag(raw)
            self._input.clear()

    def _on_text_changed(self, text: str) -> None:
        """Detects comma input and splits into tags."""
        if "," in text:
            parts = text.split(",")
            for raw_part in parts[:-1]:
                cleaned = raw_part.strip()
                if cleaned:
                    self._add_tag(cleaned)
            self._input.blockSignals(True)
            self._input.setText(parts[-1].strip())
            self._input.blockSignals(False)

    def _add_tag(self, tag: str) -> None:
        """Adds a single tag if not already present."""
        if tag in self._tags:
            return
        self._tags.append(tag)
        self._insert_chip(tag)
        self._update_placeholder()
        self._update_height()
        self.tags_changed.emit(self._tags)

    def _remove_tag(self, tag: str) -> None:
        """Removes a tag and its chip widget."""
        if tag not in self._tags:
            return
        self._tags.remove(tag)
        self._remove_chip(tag)
        self._update_placeholder()
        self._update_height()
        self._input.setFocus()
        self.tags_changed.emit(self._tags)

    def _update_placeholder(self) -> None:
        """Shows placeholder only when there are no tags."""
        self._input.setPlaceholderText(
            "" if self._tags else self._placeholder,
        )

    def _update_height(self) -> None:
        """Schedules a deferred height recalculation after layout settles."""
        from PySide6.QtCore import QTimer  # noqa: PLC0415

        QTimer.singleShot(0, self._apply_height)

    def _apply_height(self) -> None:
        """Recalculates and sets the widget height based on flow layout."""
        needed = self._flow.heightForWidth(self.width())
        h = max(HEIGHT_CONTROL, needed)
        self.setMinimumHeight(h)
        self.setMaximumHeight(h)

    def _insert_chip(self, tag: str) -> None:
        """Creates a chip widget and inserts it before the input."""
        chip = QFrame()
        chip.setProperty("tag", tag)
        chip.setStyleSheet(
            f"QFrame {{ background: {color('secondary')};"
            f" border-radius: {RADIUS_BUTTON}px;"
            " border: none; }}"
        )
        chip_layout = QHBoxLayout(chip)
        chip_layout.setContentsMargins(8, 4, 4, 4)
        chip_layout.setSpacing(4)

        label = QLabel(tag)
        label.setStyleSheet(
            f"color: {color('text_primary')}; font-size: 13px;"
            " background: transparent; border: none;"
        )

        close_btn = QPushButton("\u2715")
        close_btn.setFixedSize(20, 20)
        close_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(
            f"QPushButton {{ color: {color('disabled_text')};"
            " background: transparent; border: none;"
            " font-size: 14px; }}"
            f" QPushButton:hover {{ color: {color('text_primary')}; }}"
        )
        close_btn.clicked.connect(lambda _=False, t=tag: self._remove_tag(t))

        chip_layout.addWidget(label)
        chip_layout.addWidget(close_btn)
        chip.setFixedHeight(self._input.sizeHint().height())
        chip.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

        # Insert before the input (which is always last)
        idx = self._flow.indexOf(self._input)
        self._flow.insertWidget(idx, chip)

    def _remove_chip(self, tag: str) -> None:
        """Finds and removes the chip widget for a tag."""
        for i in range(self._flow.count()):
            item = self._flow.itemAt(i)
            if item and item.widget() and item.widget().property("tag") == tag:
                w = self._flow.takeAt(i).widget()
                w.deleteLater()
                break
