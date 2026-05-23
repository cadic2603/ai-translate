"""GitHub Releases update check — minimal, non-blocking, headless-friendly.

Hits ``https://api.github.com/repos/<owner>/<repo>/releases/latest`` in a
daemon thread and emits :attr:`UpdateChecker.update_available` with the new
version label and the release page URL.  The main window uses the signal to
surface a dismissable banner.

The check is gated by two things:

* ``SETTING_AUTO_UPDATE_CHECK`` — user-facing toggle (Settings → General).
* ``SETTING_LAST_UPDATE_CHECK`` — ISO timestamp; we skip if the previous
  check ran within the last 24 hours so every launch doesn't pound the API.

If ``UPDATE_REPO_OWNER`` or ``UPDATE_REPO_NAME`` is empty the checker never
runs — lets the repo ship without a GitHub coordinate configured.
"""

from __future__ import annotations

import json
import logging
import threading
from datetime import UTC, datetime
from urllib.error import URLError
from urllib.request import Request, urlopen

from PySide6.QtCore import QObject, Signal

from src.constants.settings import (
    SETTING_AUTO_UPDATE_CHECK,
    SETTING_LAST_UPDATE_CHECK,
    UPDATE_REPO_NAME,
    UPDATE_REPO_OWNER,
)
from src.utils.config_manager import load_setting, save_setting

logger = logging.getLogger("update_checker")

# GitHub rate-limits unauthenticated requests (60/hr/IP); a 24h throttle
# keeps us well under the limit on any realistic user base.
_THROTTLE_SECONDS = 24 * 60 * 60

# Short timeout — network hiccups shouldn't delay banner rendering.
_REQUEST_TIMEOUT = 6.0


def _parse_version(raw: str) -> tuple[int, ...]:
    """Parses a tag / version string into a comparable integer tuple.

    Strips a leading ``v`` / ``V`` so ``v1.2.3`` compares equal to ``1.2.3``.
    Non-numeric trailing segments (``-beta``, ``+build``) are dropped to
    keep the comparison well-defined without pulling in ``packaging``.
    """
    stripped = raw.strip().lstrip("vV")
    # Cut at the first non-numeric-dot character.
    core = ""
    for ch in stripped:
        if ch.isdigit() or ch == ".":
            core += ch
        else:
            break
    parts = [int(p) for p in core.split(".") if p.isdigit()]
    return tuple(parts) if parts else (0,)


def _is_newer(remote: str, current: str) -> bool:
    """Returns True when the remote version tuple sorts above the current one."""
    return _parse_version(remote) > _parse_version(current)


def _fetch_latest_release(owner: str, repo: str) -> tuple[str, str] | None:
    """Returns ``(tag_name, html_url)`` for the latest GitHub release, or None."""
    url = f"https://api.github.com/repos/{owner}/{repo}/releases/latest"
    req = Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "ai-translate-update-check",
        },
    )
    try:
        with urlopen(req, timeout=_REQUEST_TIMEOUT) as response:  # noqa: S310
            payload = json.loads(response.read().decode("utf-8"))
    except (URLError, TimeoutError, ValueError, OSError) as exc:
        logger.debug("Update check failed: %s", exc)
        return None

    tag = payload.get("tag_name") or ""
    html_url = payload.get("html_url") or ""
    if not tag or not html_url:
        return None
    return tag, html_url


def _should_check_now() -> bool:
    """Returns True when the setting is enabled and the throttle has elapsed."""
    if not UPDATE_REPO_OWNER or not UPDATE_REPO_NAME:
        return False
    if not load_setting(SETTING_AUTO_UPDATE_CHECK, True):
        return False

    last_raw = load_setting(SETTING_LAST_UPDATE_CHECK, "")
    if not last_raw:
        return True
    try:
        last = datetime.fromisoformat(str(last_raw))
    except ValueError:
        return True
    delta = (datetime.now(tz=UTC) - last).total_seconds()
    return delta >= _THROTTLE_SECONDS


def _mark_checked() -> None:
    """Records the current time as the last update-check timestamp."""
    save_setting(
        SETTING_LAST_UPDATE_CHECK,
        datetime.now(tz=UTC).isoformat(),
    )


class UpdateChecker(QObject):
    """Runs the update check in a daemon thread; emits a Qt signal on hit."""

    # Emitted with ``(latest_version, release_url)`` when a newer release
    # is found.  No signal is emitted for "no update" / network failure —
    # the user shouldn't be bothered about silence.
    update_available = Signal(str, str)

    def check_async(self, current_version: str) -> None:
        """Starts the background check if gating conditions allow it.

        Safe to call on every app launch — internal gating handles the
        setting toggle, throttling, and missing-repo cases.
        """
        if not _should_check_now():
            return
        thread = threading.Thread(
            target=self._run,
            args=(current_version,),
            daemon=True,
            name="update-check",
        )
        thread.start()

    def _run(self, current_version: str) -> None:
        """Worker body — fetches and emits on the GUI thread via signal."""
        result = _fetch_latest_release(UPDATE_REPO_OWNER, UPDATE_REPO_NAME)
        _mark_checked()
        if result is None:
            return
        tag, url = result
        if _is_newer(tag, current_version):
            self.update_available.emit(tag, url)
