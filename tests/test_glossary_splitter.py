"""Unit tests for the glossary page QSplitter integration."""

from unittest.mock import MagicMock, patch

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QSplitter
from pytestqt.qtbot import QtBot

from src.ui.pages.glossary import _create_splitter

# ---------------------------------------------------------------------------
# _create_splitter() — widget configuration
# ---------------------------------------------------------------------------


def test_create_splitter_returns_qsplitter(qtbot: QtBot) -> None:
    """_create_splitter() returns a QSplitter widget."""
    left = QFrame()
    right = QFrame()
    qtbot.addWidget(left)
    qtbot.addWidget(right)

    with patch("src.ui.pages.glossary.load_setting", return_value=None):
        splitter = _create_splitter(left, right)
    qtbot.addWidget(splitter)

    assert isinstance(splitter, QSplitter)


def test_create_splitter_horizontal_orientation(qtbot: QtBot) -> None:
    """Splitter uses horizontal orientation."""
    left = QFrame()
    right = QFrame()
    qtbot.addWidget(left)
    qtbot.addWidget(right)

    with patch("src.ui.pages.glossary.load_setting", return_value=None):
        splitter = _create_splitter(left, right)
    qtbot.addWidget(splitter)

    assert splitter.orientation() == Qt.Orientation.Horizontal


def test_create_splitter_children_not_collapsible(qtbot: QtBot) -> None:
    """Splitter panes cannot be collapsed to zero width."""
    left = QFrame()
    right = QFrame()
    qtbot.addWidget(left)
    qtbot.addWidget(right)

    with patch("src.ui.pages.glossary.load_setting", return_value=None):
        splitter = _create_splitter(left, right)
    qtbot.addWidget(splitter)

    assert not splitter.childrenCollapsible()


def test_create_splitter_has_two_children(qtbot: QtBot) -> None:
    """Splitter contains exactly the two provided widgets."""
    left = QFrame()
    right = QFrame()
    qtbot.addWidget(left)
    qtbot.addWidget(right)

    with patch("src.ui.pages.glossary.load_setting", return_value=None):
        splitter = _create_splitter(left, right)
    qtbot.addWidget(splitter)

    assert splitter.count() == 2  # noqa: PLR2004
    assert splitter.widget(0) is left
    assert splitter.widget(1) is right


def test_create_splitter_handle_width(qtbot: QtBot) -> None:
    """Splitter handle width is 2px."""
    left = QFrame()
    right = QFrame()
    qtbot.addWidget(left)
    qtbot.addWidget(right)

    with patch("src.ui.pages.glossary.load_setting", return_value=None):
        splitter = _create_splitter(left, right)
    qtbot.addWidget(splitter)

    assert splitter.handleWidth() == 2  # noqa: PLR2004


def test_create_splitter_has_stylesheet(qtbot: QtBot) -> None:
    """Splitter has a non-empty stylesheet applied."""
    left = QFrame()
    right = QFrame()
    qtbot.addWidget(left)
    qtbot.addWidget(right)

    with patch("src.ui.pages.glossary.load_setting", return_value=None):
        splitter = _create_splitter(left, right)
    qtbot.addWidget(splitter)

    qss = splitter.styleSheet()
    assert "QSplitter::handle:horizontal" in qss


# ---------------------------------------------------------------------------
# _create_splitter() — persisted sizes
# ---------------------------------------------------------------------------


def test_create_splitter_uses_saved_sizes(qtbot: QtBot) -> None:
    """Splitter restores sizes from settings when available."""
    left = QFrame()
    right = QFrame()
    qtbot.addWidget(left)
    qtbot.addWidget(right)

    with patch(
        "src.ui.pages.glossary.load_setting",
        return_value=[300, 900],
    ):
        splitter = _create_splitter(left, right)
    qtbot.addWidget(splitter)

    # QSplitter.sizes() may adjust actual sizes based on widget policies,
    # but the requested sizes should be [300, 900].
    sizes = splitter.sizes()
    assert len(sizes) == 2  # noqa: PLR2004
    # Verify the ratio is roughly preserved (left < right)
    assert sizes[0] < sizes[1]


def test_create_splitter_uses_defaults_when_no_saved(qtbot: QtBot) -> None:
    """Splitter uses [400, 800] default when load_setting returns None."""
    left = QFrame()
    right = QFrame()
    qtbot.addWidget(left)
    qtbot.addWidget(right)

    with patch("src.ui.pages.glossary.load_setting", return_value=None):
        splitter = _create_splitter(left, right)
    qtbot.addWidget(splitter)

    sizes = splitter.sizes()
    assert len(sizes) == 2  # noqa: PLR2004


def test_create_splitter_uses_defaults_on_invalid_saved(qtbot: QtBot) -> None:
    """Splitter uses defaults for invalid saved data (wrong type/length)."""
    left = QFrame()
    right = QFrame()
    qtbot.addWidget(left)
    qtbot.addWidget(right)

    # Wrong type
    with patch("src.ui.pages.glossary.load_setting", return_value="invalid"):
        splitter = _create_splitter(left, right)
    qtbot.addWidget(splitter)
    assert splitter.count() == 2  # noqa: PLR2004

    # Wrong length
    left2, right2 = QFrame(), QFrame()
    qtbot.addWidget(left2)
    qtbot.addWidget(right2)
    with patch(
        "src.ui.pages.glossary.load_setting",
        return_value=[100],
    ):
        splitter2 = _create_splitter(left2, right2)
    qtbot.addWidget(splitter2)
    assert splitter2.count() == 2  # noqa: PLR2004


def test_create_splitter_persists_on_drag(qtbot: QtBot) -> None:
    """Splitter saves sizes via save_setting when the handle is dragged."""
    left = QFrame()
    right = QFrame()
    qtbot.addWidget(left)
    qtbot.addWidget(right)

    mock_save = MagicMock()
    with (
        patch("src.ui.pages.glossary.load_setting", return_value=None),
        patch("src.ui.pages.glossary.save_setting", mock_save),
    ):
        splitter = _create_splitter(left, right)
        qtbot.addWidget(splitter)

        # Simulate the splitterMoved signal
        splitter.splitterMoved.emit(200, 1)

    mock_save.assert_called_once()
    call_args = mock_save.call_args
    assert call_args[0][0] == "glossary_splitter_sizes"
    assert isinstance(call_args[0][1], list)


# ---------------------------------------------------------------------------
# apply_theme() — splitter style refresh
# ---------------------------------------------------------------------------


def test_create_glossary_page_apply_theme_updates_splitter(
    qtbot: QtBot,
) -> None:
    """apply_theme() on glossary page refreshes splitter stylesheet."""
    from src.ui.pages.glossary import create_glossary_page  # noqa: PLC0415

    page = create_glossary_page()
    qtbot.addWidget(page)

    # Find the QSplitter child widget
    splitter = page.findChild(QSplitter)
    assert splitter is not None

    # Clear stylesheet, then call apply_theme to verify it's re-applied
    splitter.setStyleSheet("")
    assert splitter.styleSheet() == ""

    page.apply_theme()
    assert "QSplitter::handle:horizontal" in splitter.styleSheet()
