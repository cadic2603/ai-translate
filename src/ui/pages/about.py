"""About page UI for the AI Translate application.

Carries: app icon + name + version, an inline "Check for updates"
button (uses :class:`UpdateChecker` to query GitHub Releases), four
external-link buttons (GitHub / Docs / Report an issue / License),
and a copyright + licence line at the bottom.

Designed to be the place users land when they want to:
- File a bug report (Issues link)
- Verify they're on the latest version (Check for updates button)
- Read the source / docs / licence (link buttons)
- Confirm they have the right contact for the project
"""

from __future__ import annotations

import importlib.metadata
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, QUrl, Slot
from PySide6.QtGui import QDesktopServices, QIcon
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
)

from src.constants import (
    HEIGHT_CONTROL,
    SPACING_SECTION,
    SPACING_SUBSECTION,
    color,
    style_outlined_primary_button,
    style_secondary_button,
    tr,
)
from src.constants.settings import (
    COPYRIGHT_HOLDER,
    DOCS_URL,
    ISSUES_URL,
    LICENSE_NAME,
    LICENSE_URL,
    REPO_URL,
)
from src.constants.ui import ASSETS_DIR
from src.ui.components import create_page_container

if TYPE_CHECKING:
    from src.utils.update_checker import UpdateChecker


# Icon size in the page header.  Big enough to read as the brand mark,
# small enough not to dominate the screen on smaller windows.
_ICON_PIXELS = 96


def _get_version() -> str:
    """Returns the application version from package metadata."""
    try:
        return importlib.metadata.version("ai-translate")
    except importlib.metadata.PackageNotFoundError:
        return "dev"


def _open_url(url: str) -> None:
    """Opens *url* in the user's default browser."""
    QDesktopServices.openUrl(QUrl(url))


def _make_link_button(label: str, url: str) -> QPushButton:
    """Builds a styled link button that opens *url* in the browser."""
    btn = QPushButton(label)
    btn.setFixedHeight(HEIGHT_CONTROL)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    btn.setStyleSheet(style_outlined_primary_button())
    btn.setAccessibleName(label)
    btn.clicked.connect(lambda: _open_url(url))
    return btn


def create_about_page(  # noqa: PLR0915
    update_checker: UpdateChecker | None = None,
) -> QWidget:
    """Creates the About page content.

    Args:
        update_checker: Optional ``UpdateChecker`` instance shared with
            the main window.  When provided, the "Check for updates"
            button reuses its ``update_available`` signal so the user
            sees the same banner the startup check would surface.
            When None, the button still works — it just constructs a
            local checker per click.

    Returns:
        QWidget: The about page widget.
    """
    page, layout = create_page_container(
        tr("page.about"),
        tr_key="page.about",
    )
    layout.setSpacing(SPACING_SECTION)
    # Hide the default page-container header — the icon + app name
    # block below acts as the visual title.
    page.header_label.setVisible(False)

    # ── Header: icon + app name + tagline ─────────────────────────
    icon_label = QLabel()
    icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    icon_pixmap = QIcon(str(ASSETS_DIR / "app-icon.svg")).pixmap(
        _ICON_PIXELS, _ICON_PIXELS,
    )
    icon_label.setPixmap(icon_pixmap)
    layout.addWidget(icon_label)

    app_name = QLabel("AI Translate")
    app_name.setAlignment(Qt.AlignmentFlag.AlignCenter)
    app_name.setStyleSheet(
        f"font-size: 22px; font-weight: 600; color: {color('text_primary')};",
    )
    layout.addWidget(app_name)

    description = QLabel(tr("about.description"))
    description.apply_language = lambda w=description: w.setText(
        tr("about.description"),
    )
    description.setWordWrap(True)
    description.setAlignment(Qt.AlignmentFlag.AlignCenter)
    description.setStyleSheet(f"color: {color('text_secondary')};")
    layout.addWidget(description)

    # ── Version row: label + Check-for-updates button ──────────────
    version_row = QHBoxLayout()
    version_row.setSpacing(SPACING_SUBSECTION)
    version_row.addStretch()
    version_label = QLabel(f"{tr('about.version_label')}: {_get_version()}")
    # Re-render the "<label>: <version>" composite when the user
    # switches locale; version itself is locale-invariant.
    version_label.apply_language = lambda w=version_label: w.setText(
        f"{tr('about.version_label')}: {_get_version()}",
    )
    version_label.setStyleSheet(
        f"color: {color('text_primary')}; font-weight: 500;",
    )
    version_row.addWidget(version_label)

    check_btn = QPushButton(tr("about.check_updates"))
    check_btn.setFixedHeight(HEIGHT_CONTROL)
    check_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    check_btn.setStyleSheet(style_secondary_button())
    check_btn.setAccessibleName(tr("about.check_updates"))
    version_row.addWidget(check_btn)

    update_status = QLabel("")
    update_status.setStyleSheet(f"color: {color('text_secondary')};")
    version_row.addWidget(update_status)
    version_row.addStretch()
    layout.addLayout(version_row)

    @Slot()
    def _check_for_updates() -> None:
        """Shows status, kicks off a background fetch via UpdateChecker.

        Reuses the private ``_fetch_latest_release`` / ``_is_newer``
        helpers from ``update_checker`` so the version comparison stays
        consistent with the startup throttled check (no risk of two
        different "is this newer?" implementations drifting apart).
        Bypasses the 24-hour throttle deliberately — manual clicks
        should always re-check, even right after the startup check.
        """
        import threading  # noqa: PLC0415

        from src.constants.settings import (  # noqa: PLC0415
            UPDATE_REPO_NAME,
            UPDATE_REPO_OWNER,
        )
        from src.utils.update_checker import (  # noqa: PLC0415
            _fetch_latest_release,
            _is_newer,
        )

        update_status.setText(tr("about.checking_updates"))
        check_btn.setEnabled(False)
        current = _get_version()

        def _run() -> None:
            """Worker — fetches and posts the result back to the GUI thread."""
            result = _fetch_latest_release(
                UPDATE_REPO_OWNER, UPDATE_REPO_NAME,
            )
            # Hop back to the GUI thread via a single-shot timer
            # parented to the page so the deferred ``_apply`` is
            # auto-cancelled when the page is destroyed.
            from PySide6.QtCore import QTimer  # noqa: PLC0415

            def _apply() -> None:
                check_btn.setEnabled(True)
                if result is None:
                    update_status.setText(tr("about.update_check_failed"))
                    return
                tag, url = result
                if _is_newer(tag, current):
                    update_status.setText(
                        tr("about.update_available", version=tag),
                    )
                    if update_checker is not None:
                        update_checker.update_available.emit(tag, url)
                else:
                    update_status.setText(tr("about.up_to_date"))

            QTimer.singleShot(0, page, _apply)

        threading.Thread(
            target=_run, daemon=True, name="about-update-check",
        ).start()

    check_btn.clicked.connect(_check_for_updates)

    # ── Link row: GitHub / Docs / Issues / License ─────────────────
    links_row = QHBoxLayout()
    links_row.setSpacing(SPACING_SUBSECTION)
    links_row.addStretch()
    github_btn = _make_link_button(tr("about.github"), REPO_URL)
    docs_btn = _make_link_button(tr("about.docs"), DOCS_URL)
    issues_btn = _make_link_button(tr("about.report_issue"), ISSUES_URL)
    license_btn = _make_link_button(
        f"{tr('about.license_label')}: {LICENSE_NAME}",
        LICENSE_URL,
    )
    for btn in (github_btn, docs_btn, issues_btn, license_btn):
        links_row.addWidget(btn)
    links_row.addStretch()
    layout.addLayout(links_row)

    # Stretch BEFORE the footer pushes copyright to the bottom of
    # the available space — gives the link row air to breathe and
    # plants the footer where users expect it on a tall window.
    layout.addStretch()

    # ── Copyright footer ───────────────────────────────────────────
    copyright_label = QLabel(
        tr("about.copyright", holder=COPYRIGHT_HOLDER, license=LICENSE_NAME),
    )
    # Copyright string is templated with locale-invariant holder + license
    # tokens; re-run the tr() call so the surrounding "Copyright … under
    # …" framing refreshes on language switch.
    copyright_label.apply_language = lambda w=copyright_label: w.setText(
        tr("about.copyright", holder=COPYRIGHT_HOLDER, license=LICENSE_NAME),
    )
    copyright_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    copyright_label.setStyleSheet(
        f"color: {color('text_secondary')}; font-size: 11px;",
    )
    layout.addWidget(copyright_label)

    # ── apply_language: refreshes every translatable string ────────
    _base_apply_language = page.apply_language

    def apply_language() -> None:
        """Re-applies all translatable text on this page."""
        _base_apply_language()
        description.setText(tr("about.description"))
        version_label.setText(
            f"{tr('about.version_label')}: {_get_version()}",
        )
        check_btn.setText(tr("about.check_updates"))
        check_btn.setAccessibleName(tr("about.check_updates"))
        # Update status text is dynamic — leave whatever the last
        # check produced; if the user wants a refresh, they click again.
        github_btn.setText(tr("about.github"))
        docs_btn.setText(tr("about.docs"))
        issues_btn.setText(tr("about.report_issue"))
        license_btn.setText(
            f"{tr('about.license_label')}: {LICENSE_NAME}",
        )
        copyright_label.setText(
            tr("about.copyright", holder=COPYRIGHT_HOLDER, license=LICENSE_NAME),
        )

    page.apply_language = apply_language

    return page
