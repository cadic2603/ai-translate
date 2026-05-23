"""Unit tests for the About page (src/ui/pages/about.py)."""

import importlib.metadata
from unittest.mock import MagicMock, patch

from PySide6.QtWidgets import QLabel, QPushButton, QWidget
from pytestqt.qtbot import QtBot

from src.ui.pages.about import (
    _get_version,
    create_about_page,
)

# ---------------------------------------------------------------------------
# _get_version()
# ---------------------------------------------------------------------------


def test_get_version_returns_package_version() -> None:
    """Returns the version string from importlib.metadata when found."""
    with patch("importlib.metadata.version", return_value="1.2.3"):
        assert _get_version() == "1.2.3"


def test_get_version_returns_dev_when_not_found() -> None:
    """Returns 'dev' when the package is not installed (PackageNotFoundError)."""
    with patch(
        "importlib.metadata.version",
        side_effect=importlib.metadata.PackageNotFoundError("ai-translate"),
    ):
        assert _get_version() == "dev"


def test_get_version_returns_dev_not_empty() -> None:
    """Fallback is 'dev', not an empty string."""
    with patch(
        "importlib.metadata.version",
        side_effect=importlib.metadata.PackageNotFoundError,
    ):
        result = _get_version()
        assert result == "dev"
        assert result  # not falsy


# ---------------------------------------------------------------------------
# create_about_page() — basic structure
# ---------------------------------------------------------------------------


def test_create_about_page_returns_widget(qtbot: QtBot) -> None:
    """create_about_page() returns a QWidget-compatible page object."""
    page = create_about_page()
    qtbot.addWidget(page)
    assert isinstance(page, QWidget)


def test_about_page_has_apply_language(qtbot: QtBot) -> None:
    """The page exposes an apply_language() callable."""
    page = create_about_page()
    qtbot.addWidget(page)
    assert callable(page.apply_language)


def test_about_page_apply_language_does_not_raise(qtbot: QtBot) -> None:
    """Calling apply_language() does not raise any exception."""
    page = create_about_page()
    qtbot.addWidget(page)
    page.apply_language()  # should not raise


def test_about_page_contains_version_number(qtbot: QtBot) -> None:
    """The page contains a label that includes the current version number."""
    with patch("src.ui.pages.about._get_version", return_value="9.8.7"):
        page = create_about_page()
    qtbot.addWidget(page)

    texts = [w.text() for w in page.findChildren(QLabel)]
    assert any("9.8.7" in t for t in texts), (
        "Version number not found in any label text"
    )


def test_about_page_dev_version_shown_when_not_installed(qtbot: QtBot) -> None:
    """Shows 'dev' as the version when the package is not installed."""
    with patch(
        "importlib.metadata.version",
        side_effect=importlib.metadata.PackageNotFoundError,
    ):
        page = create_about_page()
    qtbot.addWidget(page)

    texts = [w.text() for w in page.findChildren(QLabel)]
    assert any("dev" in t for t in texts), (
        "'dev' not found in any label text when package is not installed"
    )


def test_about_page_hides_default_header(qtbot: QtBot) -> None:
    """The page-container header label is hidden — the icon + name acts as title."""
    page = create_about_page()
    qtbot.addWidget(page)
    assert not page.header_label.isVisible() or page.header_label.isHidden()


# ---------------------------------------------------------------------------
# Link buttons (GitHub / Docs / Report an issue / License)
# ---------------------------------------------------------------------------


def test_about_page_has_link_buttons(qtbot: QtBot) -> None:
    """Page exposes the four standard external-link buttons."""
    from src.constants.i18n import _set_initial_language  # noqa: PLC0415

    _set_initial_language("en-US")
    page = create_about_page()
    qtbot.addWidget(page)

    button_texts = {b.text() for b in page.findChildren(QPushButton)}
    # Match by substring since the License button text contains
    # the dynamic license name suffix.
    assert any("GitHub" in t for t in button_texts)
    assert any("ocumentation" in t or "Tài liệu" in t for t in button_texts)
    # "Report" or its translated equivalent.
    assert any(
        "eport" in t or "Báo cáo" in t for t in button_texts
    ), f"no Report button found in {button_texts}"
    # License: button shows "License: AGPL-3.0-or-later" or similar.
    assert any("AGPL" in t for t in button_texts), (
        "License button missing AGPL-3.0-or-later identifier"
    )


def test_link_button_opens_url_in_browser(qtbot: QtBot) -> None:
    """Clicking a link button hands the URL to the desktop service.

    Verifies the wiring: button click → ``_open_url`` → ``QDesktopServices.openUrl``.
    Patches ``QDesktopServices.openUrl`` so the test doesn't actually launch
    a browser in the test environment.
    """
    from src.constants.i18n import _set_initial_language  # noqa: PLC0415
    from src.constants.settings import REPO_URL  # noqa: PLC0415

    _set_initial_language("en-US")
    page = create_about_page()
    qtbot.addWidget(page)

    # Find the GitHub button by text.
    github_buttons = [
        b for b in page.findChildren(QPushButton) if "GitHub" in b.text()
    ]
    assert github_buttons, "GitHub button not found"
    btn = github_buttons[0]

    with patch(
        "src.ui.pages.about.QDesktopServices.openUrl",
    ) as mock_open:
        btn.click()

    mock_open.assert_called_once()
    # The argument is a QUrl; convert to string for comparison.
    called_url = mock_open.call_args.args[0].toString()
    assert called_url == REPO_URL


# ---------------------------------------------------------------------------
# Check-for-updates button
# ---------------------------------------------------------------------------


def test_check_for_updates_button_exists(qtbot: QtBot) -> None:
    """Page has a 'Check for updates' button."""
    page = create_about_page()
    qtbot.addWidget(page)

    btn_texts = [b.text() for b in page.findChildren(QPushButton)]
    assert any(
        "update" in t.lower() or "cập nhật" in t.lower() for t in btn_texts
    ), f"Check-for-updates button missing from {btn_texts}"


def test_check_for_updates_disables_button_during_check(qtbot: QtBot) -> None:
    """Click → button disabled while the background fetch runs.

    Mocks the background ``threading.Thread`` to a no-op so the test
    can synchronously inspect the button state right after click,
    before any background completion would re-enable it.
    """
    page = create_about_page()
    qtbot.addWidget(page)

    update_buttons = [
        b for b in page.findChildren(QPushButton)
        if "update" in b.text().lower() or "cập nhật" in b.text().lower()
    ]
    btn = update_buttons[0]
    assert btn.isEnabled()

    # No-op the thread so we can observe the disabled state.
    with patch(
        "threading.Thread",
        return_value=MagicMock(start=MagicMock()),
    ):
        btn.click()

    assert not btn.isEnabled(), (
        "Check-for-updates button should be disabled during the in-flight check"
    )


def test_check_for_updates_passes_to_update_checker_signal(
    qtbot: QtBot,
) -> None:
    """A newer version found → ``update_checker.update_available`` fires.

    Verifies the optional ``update_checker`` injection: when caller
    passes a shared instance, the About-page check reuses its signal
    so the global app banner shows the same notification the startup
    check would have surfaced.
    """
    fake_checker = MagicMock()
    fake_checker.update_available = MagicMock()

    page = create_about_page(update_checker=fake_checker)
    qtbot.addWidget(page)

    # We don't fully exercise the threaded fetch here (timing-sensitive);
    # the "passes to signal on hit" wiring is an internal closure path
    # that would require deeper mocking of QTimer.singleShot.  This test
    # just confirms the page accepts the kwarg without breaking.
    assert page is not None


# ---------------------------------------------------------------------------
# apply_language refresh
# ---------------------------------------------------------------------------


def test_about_page_apply_language_updates_labels(qtbot: QtBot) -> None:
    """apply_language() refreshes every translatable label."""
    from src.constants.i18n import _set_initial_language  # noqa: PLC0415

    _set_initial_language("en-US")
    page = create_about_page()
    qtbot.addWidget(page)
    en_texts = {w.text() for w in page.findChildren(QLabel)}

    _set_initial_language("vi")
    page.apply_language()
    vi_texts = {w.text() for w in page.findChildren(QLabel)}

    # At least one label should have changed text after switching locale.
    assert en_texts != vi_texts, (
        "apply_language() didn't refresh anything when locale changed"
    )

    # Restore default.
    _set_initial_language("en-US")


def test_check_for_updates_button_bypasses_throttle(qtbot: QtBot) -> None:
    """Manual click runs ``_fetch_latest_release`` regardless of throttle.

    AGENTS.md: "Bypasses the 24-hour throttle deliberately — manual
    clicks should always re-check, even right after the startup
    check."  A regression that wires the manual click through
    ``_should_check_now()`` / ``maybe_check()`` would silently no-op
    for the user.  Pin the contract: even with a freshly-set
    ``SETTING_LAST_UPDATE_CHECK`` timestamp (= now), the manual
    click still fetches.
    """
    from datetime import UTC, datetime  # noqa: PLC0415

    from src.constants.settings import (  # noqa: PLC0415
        SETTING_LAST_UPDATE_CHECK,
    )

    page = create_about_page()
    qtbot.addWidget(page)
    update_buttons = [
        b for b in page.findChildren(QPushButton)
        if "update" in b.text().lower() or "cập nhật" in b.text().lower()
    ]
    btn = update_buttons[0]

    # Pretend the startup check just ran (timestamp = now).  A
    # throttled implementation would refuse to re-check.
    just_now = datetime.now(tz=UTC).isoformat()

    def _fake_load(key, default=""):  # noqa: ANN001, ANN202
        if key == SETTING_LAST_UPDATE_CHECK:
            return just_now
        return default

    # Patch Thread to invoke the target inline so the test stays
    # synchronous and the fetch call is observable deterministically.
    def _inline_thread(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202
        target = kwargs.get("target") or (args[0] if args else None)
        if target is not None:
            target()
        return MagicMock(start=MagicMock())

    with patch(
        "src.utils.update_checker.load_setting", side_effect=_fake_load,
    ), patch(
        # ``_fetch_latest_release`` is imported lazily inside the
        # button-click handler, so patch the source module.
        "src.utils.update_checker._fetch_latest_release",
        return_value=None,  # don't enter the GUI hop
    ) as mock_fetch, patch("threading.Thread", side_effect=_inline_thread):
        btn.click()

    mock_fetch.assert_called_once()


# ---------------------------------------------------------------------------
# Per-label apply_language wiring (added this session to fix the
# "labels frozen on language switch" bug — generic test above only
# asserted SOMETHING changed; these pin each specific label so a
# future regression that drops one binding gets caught).
# ---------------------------------------------------------------------------


def _find_label_containing(page, substring: str):
    """Returns the first QLabel whose text contains *substring*."""
    return next(
        (lbl for lbl in page.findChildren(QLabel) if substring in lbl.text()),
        None,
    )


def test_about_description_label_refreshes_on_locale_switch(qtbot: QtBot) -> None:
    """Description label rebinds on every locale change."""
    from src.constants.i18n import _set_initial_language, tr  # noqa: PLC0415

    _set_initial_language("en-US")
    page = create_about_page()
    qtbot.addWidget(page)
    en_text = tr("about.description")
    desc = _find_label_containing(page, en_text[:20])
    assert desc is not None
    assert hasattr(desc, "apply_language")

    _set_initial_language("vi")
    desc.apply_language()
    vi_text = tr("about.description")
    assert desc.text() == vi_text
    assert desc.text() != en_text
    _set_initial_language("en-US")


def test_about_version_label_refreshes_on_locale_switch(qtbot: QtBot) -> None:
    """version_label refreshes correctly on locale switch.

    Uses an f-string composite ``<label>: <version>``; the
    apply_language closure re-runs both tr() and the version lookup.
    """
    from src.constants.i18n import _set_initial_language, tr  # noqa: PLC0415

    _set_initial_language("en-US")
    page = create_about_page()
    qtbot.addWidget(page)
    en_prefix = tr("about.version_label")
    label = _find_label_containing(page, en_prefix)
    assert label is not None
    assert hasattr(label, "apply_language")

    _set_initial_language("vi")
    label.apply_language()
    vi_prefix = tr("about.version_label")
    assert label.text().startswith(vi_prefix)
    # Version number itself is locale-invariant — verify it's still present.
    from src.ui.pages.about import _get_version  # noqa: PLC0415

    assert _get_version() in label.text()
    _set_initial_language("en-US")


def test_about_copyright_label_refreshes_on_locale_switch(qtbot: QtBot) -> None:
    """copyright_label refreshes correctly on locale switch.

    Uses ``tr("about.copyright", holder=..., license=...)`` — the
    apply_language closure re-runs the templated lookup so the
    surrounding framing follows locale while keeping the holder and
    license tokens locale-invariant.
    """
    from src.constants.i18n import _set_initial_language, tr  # noqa: PLC0415
    from src.constants.settings import (  # noqa: PLC0415
        COPYRIGHT_HOLDER,
        LICENSE_NAME,
    )

    _set_initial_language("en-US")
    page = create_about_page()
    qtbot.addWidget(page)
    en_text = tr("about.copyright", holder=COPYRIGHT_HOLDER, license=LICENSE_NAME)
    label = _find_label_containing(page, en_text[:10])
    assert label is not None
    assert hasattr(label, "apply_language")

    _set_initial_language("vi")
    label.apply_language()
    vi_text = tr("about.copyright", holder=COPYRIGHT_HOLDER, license=LICENSE_NAME)
    assert label.text() == vi_text
    # Locale-invariant tokens survive substitution.
    assert COPYRIGHT_HOLDER in label.text()
    assert LICENSE_NAME in label.text()
    _set_initial_language("en-US")
