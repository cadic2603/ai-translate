"""Tests for the GitHub Releases update checker."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import patch
from urllib.error import URLError

import pytest

from src.utils.update_checker import (
    _is_newer,
    _parse_version,
    _should_check_now,
)


class TestParseVersion:
    """Version-string tokenisation for comparisons."""

    def test_strips_leading_v(self) -> None:
        assert _parse_version("v1.2.3") == (1, 2, 3)
        assert _parse_version("V0.1.0") == (0, 1, 0)

    def test_plain_numeric(self) -> None:
        assert _parse_version("1.2.3") == (1, 2, 3)

    def test_drops_suffix(self) -> None:
        assert _parse_version("1.2.3-beta") == (1, 2, 3)
        assert _parse_version("v2.0+build.42") == (2, 0)

    def test_whitespace_tolerant(self) -> None:
        assert _parse_version("  v1.2  ") == (1, 2)

    def test_non_numeric_yields_zero(self) -> None:
        assert _parse_version("latest") == (0,)
        assert _parse_version("") == (0,)


class TestIsNewer:
    """Remote-vs-local version comparison."""

    def test_patch_bump_detected(self) -> None:
        assert _is_newer("1.2.4", "1.2.3")

    def test_major_bump_detected(self) -> None:
        assert _is_newer("2.0.0", "1.9.9")

    def test_equal_is_not_newer(self) -> None:
        assert not _is_newer("1.2.3", "1.2.3")

    def test_older_is_not_newer(self) -> None:
        assert not _is_newer("1.2.2", "1.2.3")

    def test_leading_v_does_not_affect_comparison(self) -> None:
        assert _is_newer("v1.2.4", "1.2.3")
        assert not _is_newer("v1.2.3", "1.2.3")


class TestShouldCheckNow:
    """Gating: toggle, throttle, and missing-repo short-circuits."""

    @pytest.fixture(autouse=True)
    def _reset_settings(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Default fixture: feature on, repo configured, never checked.
        monkeypatch.setattr(
            "src.utils.update_checker.UPDATE_REPO_OWNER",
            "owner",
        )
        monkeypatch.setattr(
            "src.utils.update_checker.UPDATE_REPO_NAME",
            "repo",
        )

    def test_skips_when_repo_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("src.utils.update_checker.UPDATE_REPO_OWNER", "")
        assert _should_check_now() is False

    def test_skips_when_feature_disabled(self) -> None:
        with patch("src.utils.update_checker.load_setting") as mock_load:
            mock_load.side_effect = lambda key, default: (
                False if "auto_update_check" in key else default
            )
            assert _should_check_now() is False

    def test_runs_on_first_launch(self) -> None:
        """No stored timestamp → check runs."""
        with patch("src.utils.update_checker.load_setting") as mock_load:
            mock_load.side_effect = lambda key, default: (
                True if "auto_update_check" in key else ""
            )
            assert _should_check_now() is True

    def test_throttles_within_24h(self) -> None:
        recent = (datetime.now(tz=UTC) - timedelta(hours=1)).isoformat()
        with patch("src.utils.update_checker.load_setting") as mock_load:
            mock_load.side_effect = lambda key, default: (
                True if "auto_update_check" in key else recent
            )
            assert _should_check_now() is False

    def test_runs_after_24h(self) -> None:
        stale = (datetime.now(tz=UTC) - timedelta(hours=25)).isoformat()
        with patch("src.utils.update_checker.load_setting") as mock_load:
            mock_load.side_effect = lambda key, default: (
                True if "auto_update_check" in key else stale
            )
            assert _should_check_now() is True

    def test_runs_when_timestamp_malformed(self) -> None:
        with patch("src.utils.update_checker.load_setting") as mock_load:
            mock_load.side_effect = lambda key, default: (
                True if "auto_update_check" in key else "garbage"
            )
            assert _should_check_now() is True


class TestFetchLatestRelease:
    """Network + response parsing edge cases."""

    def test_returns_none_on_network_error(self) -> None:
        """Urlopen raising propagates as None (not an exception)."""
        from src.utils.update_checker import _fetch_latest_release

        with patch(
            "src.utils.update_checker.urlopen",
            side_effect=URLError("dns fail"),
        ):
            assert _fetch_latest_release("owner", "repo") is None

    def test_returns_none_on_timeout(self) -> None:
        """TimeoutError is caught and normalised to None."""
        from src.utils.update_checker import _fetch_latest_release

        with patch(
            "src.utils.update_checker.urlopen",
            side_effect=TimeoutError("slow"),
        ):
            assert _fetch_latest_release("owner", "repo") is None

    def test_returns_none_on_malformed_json(self) -> None:
        """HTML response (captive portals) treated as failure, not crash."""
        from src.utils.update_checker import _fetch_latest_release

        class FakeResp:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return b"<html>not json</html>"

        with patch(
            "src.utils.update_checker.urlopen",
            return_value=FakeResp(),
        ):
            assert _fetch_latest_release("owner", "repo") is None

    def test_returns_none_when_html_url_missing(self) -> None:
        """Payload with tag_name but no html_url is treated as invalid."""
        from src.utils.update_checker import _fetch_latest_release

        class FakeResp:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return b'{"tag_name": "v2.0.0"}'

        with patch(
            "src.utils.update_checker.urlopen",
            return_value=FakeResp(),
        ):
            assert _fetch_latest_release("owner", "repo") is None

    def test_returns_tuple_on_well_formed_payload(self) -> None:
        """Happy path: tag_name + html_url round-trip into a 2-tuple."""
        from src.utils.update_checker import _fetch_latest_release

        class FakeResp:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return (
                    b'{"tag_name": "v2.0.0", "html_url": "https://example.com/release"}'
                )

        with patch(
            "src.utils.update_checker.urlopen",
            return_value=FakeResp(),
        ):
            result = _fetch_latest_release("owner", "repo")
        assert result == ("v2.0.0", "https://example.com/release")


# ---------------------------------------------------------------------------
# HTTP error codes — pin the URLError-subclass catch
# ---------------------------------------------------------------------------
#
# ``_fetch_latest_release`` catches ``URLError`` (and ``TimeoutError``,
# ``ValueError``, ``OSError``).  ``HTTPError`` is a ``URLError`` subclass,
# so 403 (rate-limited) and 404 (repo missing or renamed) responses
# from the GitHub Releases API are caught by the ``URLError`` arm and
# normalised to ``None``.  Pin both here so the ``URLError`` net never
# narrows past ``HTTPError`` without flagging.


class TestFetchLatestReleaseHttpStatus:
    """Graceful handling for GitHub Releases API HTTP error responses."""

    def test_returns_none_on_http_403_rate_limited(self) -> None:
        """GitHub rate-limit (403) caught by the URLError arm → None.

        Anonymous Releases API calls are limited to 60/hour/IP; once
        exhausted, GitHub returns 403 with an HTML body.  The check
        must degrade gracefully — the user sees no banner, the next
        24h-throttled attempt retries.
        """
        from urllib.error import HTTPError  # noqa: PLC0415

        from src.utils.update_checker import _fetch_latest_release  # noqa: PLC0415

        err = HTTPError(
            "https://api.github.com/repos/o/r/releases/latest",
            403,
            "rate limit exceeded",
            {"X-RateLimit-Remaining": "0"},
            None,
        )
        with patch(
            "src.utils.update_checker.urlopen",
            side_effect=err,
        ):
            assert _fetch_latest_release("owner", "repo") is None

    def test_returns_none_on_http_404_repo_missing(self) -> None:
        """Repo not found (404) → None, no exception leak.

        Triggered when ``UPDATE_REPO_OWNER`` / ``UPDATE_REPO_NAME``
        are stale (renamed, transferred, or never existed).  Same
        graceful-failure contract as 403.
        """
        from urllib.error import HTTPError  # noqa: PLC0415

        from src.utils.update_checker import _fetch_latest_release  # noqa: PLC0415

        err = HTTPError(
            "https://api.github.com/repos/o/r/releases/latest",
            404,
            "Not Found",
            {},
            None,
        )
        with patch(
            "src.utils.update_checker.urlopen",
            side_effect=err,
        ):
            assert _fetch_latest_release("owner", "repo") is None

    def test_returns_none_on_http_5xx_server_errors(self) -> None:
        """5xx server errors are also a graceful no-op.

        Covers GitHub maintenance windows (500), bad gateway (502),
        and overload (503).  None must bubble into the UI startup
        path.
        """
        from urllib.error import HTTPError  # noqa: PLC0415

        from src.utils.update_checker import _fetch_latest_release  # noqa: PLC0415

        for status in (500, 502, 503):
            err = HTTPError(
                "https://api.github.com/repos/o/r/releases/latest",
                status,
                f"status {status}",
                {},
                None,
            )
            with patch(
                "src.utils.update_checker.urlopen",
                side_effect=err,
            ):
                assert _fetch_latest_release("owner", "repo") is None, (
                    f"HTTP {status} should normalise to None"
                )


# ───────────────────────────────────────────────────────────────────────
# UpdateChecker class — public surface (signal + async wrapper).
# ───────────────────────────────────────────────────────────────────────


class TestMarkChecked:
    """The throttle timestamp writer must round-trip through fromisoformat."""

    def test_writes_iso_timestamp(self) -> None:
        from src.constants.settings import (  # noqa: PLC0415
            SETTING_LAST_UPDATE_CHECK,
        )
        from src.utils.config_manager import (  # noqa: PLC0415
            load_setting,
            save_setting,
        )
        from src.utils.update_checker import _mark_checked  # noqa: PLC0415

        save_setting(SETTING_LAST_UPDATE_CHECK, "")
        _mark_checked()
        raw = load_setting(SETTING_LAST_UPDATE_CHECK, "")
        # Must round-trip — corrupting the format would silently disable
        # throttling on every restart and we'd hammer the API.
        parsed = datetime.fromisoformat(str(raw))
        delta = (datetime.now(tz=UTC) - parsed).total_seconds()
        assert delta < 5, f"timestamp {raw} not recent (delta={delta}s)"


class TestUpdateCheckerCheckAsync:
    """The check_async gate + thread-spawn path."""

    def test_skips_when_should_check_now_false(self) -> None:
        """Refused gate → no thread spawned (zero network noise)."""
        from src.utils.update_checker import UpdateChecker  # noqa: PLC0415

        c = UpdateChecker()
        with (
            patch(
                "src.utils.update_checker._should_check_now",
                return_value=False,
            ),
            patch("src.utils.update_checker.threading.Thread") as thread_cls,
        ):
            c.check_async("1.0.0")
        thread_cls.assert_not_called()

    def test_starts_daemon_thread_when_gate_open(self) -> None:
        """daemon=True is non-negotiable — must not block app exit."""
        from src.utils.update_checker import UpdateChecker  # noqa: PLC0415

        c = UpdateChecker()
        with (
            patch(
                "src.utils.update_checker._should_check_now",
                return_value=True,
            ),
            patch("src.utils.update_checker.threading.Thread") as thread_cls,
        ):
            c.check_async("1.0.0")
        thread_cls.assert_called_once()
        assert thread_cls.call_args.kwargs.get("daemon") is True
        # Thread name aids debugging — check it's set.
        assert thread_cls.call_args.kwargs.get("name") == "update-check"


class TestUpdateCheckerRun:
    """The worker body — _run is the actual thread target."""

    def test_run_marks_checked_even_on_fetch_failure(self) -> None:
        """Failed fetch still bumps the timestamp — otherwise we'd retry on every launch."""
        from src.utils.update_checker import UpdateChecker  # noqa: PLC0415

        c = UpdateChecker()
        with (
            patch(
                "src.utils.update_checker._fetch_latest_release",
                return_value=None,
            ),
            patch("src.utils.update_checker._mark_checked") as mark,
        ):
            c._run("1.0.0")
        mark.assert_called_once()

    def test_run_emits_signal_when_remote_is_newer(self) -> None:
        """Real release → signal fires with (tag, url) tuple."""
        from unittest.mock import MagicMock  # noqa: PLC0415

        from src.utils.update_checker import UpdateChecker  # noqa: PLC0415

        c = UpdateChecker()
        receiver = MagicMock()
        c.update_available.connect(receiver)
        with (
            patch(
                "src.utils.update_checker._fetch_latest_release",
                return_value=("v9.9.9", "https://example.com/r/v9.9.9"),
            ),
            patch("src.utils.update_checker._mark_checked"),
        ):
            c._run("1.0.0")
        receiver.assert_called_once_with(
            "v9.9.9",
            "https://example.com/r/v9.9.9",
        )

    def test_run_silent_when_same_version(self) -> None:
        """Same version → no signal; user shouldn't see a 'no update' banner."""
        from unittest.mock import MagicMock  # noqa: PLC0415

        from src.utils.update_checker import UpdateChecker  # noqa: PLC0415

        c = UpdateChecker()
        receiver = MagicMock()
        c.update_available.connect(receiver)
        with (
            patch(
                "src.utils.update_checker._fetch_latest_release",
                return_value=("v1.0.0", "https://x"),
            ),
            patch("src.utils.update_checker._mark_checked"),
        ):
            c._run("1.0.0")
        receiver.assert_not_called()

    def test_run_silent_when_remote_is_older(self) -> None:
        """Older remote (downgrade scenario) → no signal."""
        from unittest.mock import MagicMock  # noqa: PLC0415

        from src.utils.update_checker import UpdateChecker  # noqa: PLC0415

        c = UpdateChecker()
        receiver = MagicMock()
        c.update_available.connect(receiver)
        with (
            patch(
                "src.utils.update_checker._fetch_latest_release",
                return_value=("v0.5.0", "https://x"),
            ),
            patch("src.utils.update_checker._mark_checked"),
        ):
            c._run("1.0.0")
        receiver.assert_not_called()
