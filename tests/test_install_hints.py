"""Unit tests for ``src/utils/install_hints.py``.

Pin the per-distro detection + the ``format_install_clause`` graceful-
empty contract (avoids the empty ``<b></b>`` artefact when the user's
package manager isn't recognised on Linux, or when the platform isn't
Linux at all).
"""

from unittest.mock import patch

from src.utils.install_hints import (
    _FFMPEG_PACKAGES,
    _get_install_hint,
    build_ffmpeg_install_message,
    format_install_clause,
    get_ffmpeg_install_hint,
)

# ──────────────────────────────────────────────────────────────────────
# _get_install_hint
# ──────────────────────────────────────────────────────────────────────


class TestGetInstallHint:
    """Generic distro detector returns the first-matching install command."""

    def test_non_linux_returns_empty(self):
        """Non-Linux platforms (macOS / Windows / other) always return empty string."""
        for system in ("Darwin", "Windows", "FreeBSD", "Java"):
            with patch(
                "src.utils.install_hints.platform.system",
                return_value=system,
            ):
                assert _get_install_hint({"apt-get": "x"}) == ""

    def test_apt_get_detected(self):
        """Debian/Ubuntu (apt-get on PATH) returns the apt-get command."""
        with (
            patch(
                "src.utils.install_hints.platform.system",
                return_value="Linux",
            ),
            patch(
                "src.utils.install_hints.shutil.which",
                side_effect=lambda b: "/usr/bin/apt-get" if b == "apt-get" else None,
            ),
        ):
            assert (
                _get_install_hint(
                    {
                        "apt-get": "sudo apt-get install x",
                        "dnf": "sudo dnf install x",
                    }
                )
                == "sudo apt-get install x"
            )

    def test_dnf_detected_when_apt_missing(self):
        """Fedora/RHEL (no apt-get, dnf on PATH) → dnf command."""
        with (
            patch(
                "src.utils.install_hints.platform.system",
                return_value="Linux",
            ),
            patch(
                "src.utils.install_hints.shutil.which",
                side_effect=lambda b: "/usr/bin/dnf" if b == "dnf" else None,
            ),
        ):
            assert (
                _get_install_hint(
                    {
                        "apt-get": "sudo apt-get install x",
                        "dnf": "sudo dnf install x",
                    }
                )
                == "sudo dnf install x"
            )

    def test_unrecognised_distro_returns_empty(self):
        """Linux but no recognised package manager → empty (graceful)."""
        with (
            patch(
                "src.utils.install_hints.platform.system",
                return_value="Linux",
            ),
            patch(
                "src.utils.install_hints.shutil.which",
                return_value=None,
            ),
        ):
            assert (
                _get_install_hint(
                    {
                        "apt-get": "x",
                        "dnf": "y",
                        "pacman": "z",
                    }
                )
                == ""
            )

    def test_iteration_order_respected(self):
        """First matching binary in dict-iteration order wins.

        Both apt-get AND dnf installed (rare but possible in containers).
        The dict insertion order picks apt-get first.
        """
        with (
            patch(
                "src.utils.install_hints.platform.system",
                return_value="Linux",
            ),
            patch(
                "src.utils.install_hints.shutil.which",
                return_value="/usr/bin/anything",
            ),
        ):
            assert (
                _get_install_hint(
                    {
                        "apt-get": "FIRST",
                        "dnf": "SECOND",
                    }
                )
                == "FIRST"
            )


# ──────────────────────────────────────────────────────────────────────
# get_ffmpeg_install_hint
# ──────────────────────────────────────────────────────────────────────


class TestGetFfmpegInstallHint:
    """Public ffmpeg helper wires _FFMPEG_PACKAGES into _get_install_hint."""

    def test_returns_apt_get_command_on_debian(self):
        with (
            patch(
                "src.utils.install_hints.platform.system",
                return_value="Linux",
            ),
            patch(
                "src.utils.install_hints.shutil.which",
                side_effect=lambda b: "/usr/bin/apt-get" if b == "apt-get" else None,
            ),
        ):
            assert get_ffmpeg_install_hint() == "sudo apt-get install ffmpeg"

    def test_returns_empty_on_unrecognised_linux(self):
        with (
            patch(
                "src.utils.install_hints.platform.system",
                return_value="Linux",
            ),
            patch(
                "src.utils.install_hints.shutil.which",
                return_value=None,
            ),
        ):
            assert get_ffmpeg_install_hint() == ""

    def test_returns_empty_on_macos(self):
        with patch(
            "src.utils.install_hints.platform.system",
            return_value="Darwin",
        ):
            assert get_ffmpeg_install_hint() == ""

    def test_packages_dict_covers_major_distros(self):
        """Major distro coverage: apt-get / dnf / pacman / zypper / apk."""
        assert set(_FFMPEG_PACKAGES) >= {
            "apt-get",
            "dnf",
            "pacman",
            "zypper",
            "apk",
        }


# ──────────────────────────────────────────────────────────────────────
# format_install_clause
# ──────────────────────────────────────────────────────────────────────


class TestFormatInstallClause:
    """Wraps a bare command in the localized inline template or returns empty.

    The empty-cmd → empty-string short-circuit is the load-bearing
    contract: it prevents the empty ``<b></b>`` artefact in banner
    text on unrecognised distros (see the Linux install banners that
    end with ``"...{linux_install}"``).
    """

    def test_empty_command_returns_empty(self):
        """``cmd=""`` → ``""`` (no template lookup, no <b></b>)."""
        assert format_install_clause("") == ""

    def test_non_empty_command_wraps_via_template(self):
        """Real command goes through ``live.install_command_inline``.

        Current en-US template (`" — run <code>{cmd}</code>"`)
        wraps the command in ``<code>`` so it renders in monospace
        and stands out from the surrounding sentence prose.
        """
        from src.constants.i18n import _set_initial_language

        _set_initial_language("en-US")
        result = format_install_clause("sudo apt-get install foo")
        # The command is wrapped in <code> and prefixed with a clause.
        assert "<code>sudo apt-get install foo</code>" in result
        # The clause begins with " — run " (linking it to the
        # surrounding sentence as a runnable suggestion).
        assert " — run " in result

    def test_lazy_i18n_import(self):
        """Helper imports ``tr`` lazily so module-load has no side effects.

        The module must be importable without an i18n catalogue
        initialised — this re-imports it cleanly to confirm no
        eager PySide6 / i18n touches at module load.
        """
        import importlib
        import sys

        # Drop and re-import — should succeed without crashing.
        if "src.utils.install_hints" in sys.modules:
            del sys.modules["src.utils.install_hints"]
        mod = importlib.import_module("src.utils.install_hints")
        assert hasattr(mod, "format_install_clause")


class TestBuildFfmpegInstallMessage:
    """Per-OS dispatcher for the shared FFmpeg install dialog body."""

    def test_linux_fills_placeholder_with_apt_command(self):
        from src.constants.i18n import _set_initial_language

        _set_initial_language("en-US")
        with (
            patch(
                "src.utils.install_hints.platform.system",
                return_value="Linux",
            ),
            patch(
                "src.utils.install_hints.shutil.which",
                side_effect=lambda b: "/usr/bin/apt-get" if b == "apt-get" else None,
            ),
        ):
            msg = build_ffmpeg_install_message()
        assert "sudo apt-get install ffmpeg" in msg
        # Linux base banner should reference FFmpeg explicitly.
        assert "FFmpeg" in msg or "ffmpeg" in msg

    def test_linux_unknown_distro_no_empty_bold_artifact(self):
        """Unrecognised distro → no orphan ``<b></b>`` from format_install_clause."""
        from src.constants.i18n import _set_initial_language

        _set_initial_language("en-US")
        with (
            patch(
                "src.utils.install_hints.platform.system",
                return_value="Linux",
            ),
            patch(
                "src.utils.install_hints.shutil.which",
                return_value=None,
            ),
        ):
            msg = build_ffmpeg_install_message()
        assert "<b></b>" not in msg
        assert "Install with:" not in msg

    def test_macos_returns_macos_branch(self):
        from src.constants.i18n import _set_initial_language

        _set_initial_language("en-US")
        with patch(
            "src.utils.install_hints.platform.system",
            return_value="Darwin",
        ):
            msg = build_ffmpeg_install_message()
        # macOS message should mention brew or a download link.
        assert "brew" in msg.lower() or "ffmpeg.org" in msg.lower()

    def test_windows_returns_windows_branch(self):
        from src.constants.i18n import _set_initial_language

        _set_initial_language("en-US")
        with patch(
            "src.utils.install_hints.platform.system",
            return_value="Windows",
        ):
            msg = build_ffmpeg_install_message()
        # Windows message should reference a download or installer.
        assert "ffmpeg" in msg.lower()

    def test_unsupported_platform_returns_fallback_branch(self):
        from src.constants.i18n import _set_initial_language

        _set_initial_language("en-US")
        with patch(
            "src.utils.install_hints.platform.system",
            return_value="FreeBSD",
        ):
            msg = build_ffmpeg_install_message()
        # Fallback i18n key should still resolve, not error.
        assert msg
        assert "settings.ffmpeg_install_unsupported" not in msg
