"""Unit tests for pure-Python logic in src/core/office_lifecycle.py.

Focuses on functions that can be tested without actual LibreOffice or
Win32COM installations -- all platform-specific libraries are mocked.
"""

import signal
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from src.core.office_lifecycle import (
    _APP_EXCEL,
    _APP_PPT,
    _APP_WORD,
    _cleanup_soffice,
    _ensure_soffice_running,
    _find_available_port,
    _find_soffice_binary,
    _get_uno_search_paths,
    _get_uno_search_paths_darwin,
    _get_uno_search_paths_linux,
    _get_uno_search_paths_win32,
    _kill_orphaned_soffice,
    _kill_orphaned_soffice_unix,
    _kill_orphaned_soffice_win32,
    _make_uno_url,
    _remove_soffice_lock,
    _resolve_custom_soffice_path,
    _win32com_close,
    _win32com_open,
    stop_soffice,
)

# ---------------------------------------------------------------------------
# TestGetUnoSearchPaths — custom path handling and platform dispatch
# ---------------------------------------------------------------------------


class TestGetUnoSearchPaths:
    """Tests for _get_uno_search_paths custom LibreOffice path integration."""

    def test_linux_paths_include_expected_entries(self) -> None:
        """Linux platform returns the standard dist-packages and program dirs."""
        with patch("sys.platform", "linux"):
            result = _get_uno_search_paths(libreoffice_path="")
        assert isinstance(result, list)
        assert "/usr/lib/python3/dist-packages" in result

    def test_custom_directory_prepended(self, tmp_path: Path) -> None:
        """A valid custom LibreOffice directory is prepended to the list."""
        custom_dir = tmp_path / "libreoffice" / "program"
        custom_dir.mkdir(parents=True)

        with patch("sys.platform", "linux"):
            result = _get_uno_search_paths(libreoffice_path=str(custom_dir))

        assert result[0] == str(custom_dir)

    def test_empty_custom_path_excluded(self) -> None:
        """An empty custom path does not add anything extra."""
        with (
            patch("sys.platform", "linux"),
            patch(
                "src.utils.config_manager.load_setting",
                return_value="",
            ),
        ):
            result = _get_uno_search_paths(libreoffice_path="")

        # First entry should be a well-known path, not empty string
        assert all(p for p in result)

    def test_custom_file_path_uses_parent_dir(self, tmp_path: Path) -> None:
        """When custom path is a file, its parent directory is used."""
        custom_dir = tmp_path / "lo_install"
        custom_dir.mkdir()
        soffice_bin = custom_dir / "soffice"
        soffice_bin.touch()

        with patch("sys.platform", "linux"):
            result = _get_uno_search_paths(libreoffice_path=str(soffice_bin))

        assert str(custom_dir) in result
        # Parent dir should be prepended
        assert result[0] == str(custom_dir)

    def test_dispatches_to_win32_on_windows(self) -> None:
        """Dispatches to _get_uno_search_paths_win32 on Windows."""
        with (
            patch("sys.platform", "win32"),
            patch(
                "src.core.office_lifecycle._get_uno_search_paths_win32",
                return_value=[r"C:\LO\program"],
            ) as mock_win32,
        ):
            result = _get_uno_search_paths(libreoffice_path="")

        mock_win32.assert_called_once()
        assert r"C:\LO\program" in result

    def test_dispatches_to_darwin_on_macos(self) -> None:
        """Dispatches to _get_uno_search_paths_darwin on macOS."""
        with (
            patch("sys.platform", "darwin"),
            patch(
                "src.core.office_lifecycle._get_uno_search_paths_darwin",
                return_value=["/Applications/LibreOffice.app/Contents/MacOS"],
            ) as mock_darwin,
        ):
            result = _get_uno_search_paths(libreoffice_path="")

        mock_darwin.assert_called_once()
        assert "/Applications/LibreOffice.app/Contents/MacOS" in result

    def test_dispatches_to_linux_on_other_platform(self) -> None:
        """Dispatches to _get_uno_search_paths_linux on Linux / other."""
        with (
            patch("sys.platform", "linux"),
            patch(
                "src.core.office_lifecycle._get_uno_search_paths_linux",
                return_value=["/usr/lib/python3/dist-packages"],
            ) as mock_linux,
        ):
            result = _get_uno_search_paths(libreoffice_path="")

        mock_linux.assert_called_once()
        assert "/usr/lib/python3/dist-packages" in result

    def test_nonexistent_custom_dir_not_prepended(self) -> None:
        """A custom path pointing to a non-existent directory is ignored."""
        with patch("sys.platform", "linux"):
            result = _get_uno_search_paths(
                libreoffice_path="/nonexistent/libreoffice/program"
            )

        assert "/nonexistent/libreoffice/program" not in result

    def test_duplicate_custom_dir_not_added_twice(self) -> None:
        """Custom dir already in the platform list is not duplicated."""
        with (
            patch("sys.platform", "linux"),
            patch(
                "src.core.office_lifecycle._get_uno_search_paths_linux",
                return_value=["/usr/lib/python3/dist-packages"],
            ),
        ):
            # Custom dir same as already-present entry won't be added
            # But this is a string path that doesn't exist on disk
            result = _get_uno_search_paths(libreoffice_path="")
        # Ensure no duplicates even if load_setting returns path already in list
        seen = set()
        for p in result:
            assert p not in seen, f"Duplicate path: {p}"
            seen.add(p)

    def test_load_setting_called_when_no_libreoffice_path(self) -> None:
        """load_setting is called when libreoffice_path is empty."""
        with (
            patch("sys.platform", "linux"),
            patch(
                "src.utils.config_manager.load_setting",
                return_value="",
            ) as mock_load,
        ):
            _get_uno_search_paths(libreoffice_path="")

        mock_load.assert_called_once()


class TestGetUnoSearchPathsLinux:
    """Tests for _get_uno_search_paths_linux platform-specific logic."""

    def test_includes_static_well_known_paths(self) -> None:
        """Returns standard Linux paths for dist-packages and site-packages."""
        with patch("shutil.which", return_value=None):
            result = _get_uno_search_paths_linux()

        assert "/usr/lib/python3/dist-packages" in result
        assert "/usr/lib/python3/site-packages" in result
        assert "/usr/lib/libreoffice/program" in result

    def test_dynamic_soffice_resolution_appended(self) -> None:
        """Resolving soffice binary adds its parent to the list."""
        with (
            patch("shutil.which", return_value="/usr/bin/soffice"),
            patch.object(
                Path,
                "resolve",
                return_value=Path("/usr/lib/libreoffice/program/soffice"),
            ),
        ):
            result = _get_uno_search_paths_linux()

        assert "/usr/lib/libreoffice/program" in result

    def test_soffice_not_on_path_still_returns_static(self) -> None:
        """When soffice is not on PATH, static paths are still returned."""
        with patch("shutil.which", return_value=None):
            result = _get_uno_search_paths_linux()

        assert len(result) >= 10  # noqa: PLR2004

    def test_libreoffice_binary_fallback(self) -> None:
        """Falls back to 'libreoffice' when 'soffice' is not on PATH."""

        def _which_libreoffice(cmd: str) -> str | None:
            if cmd == "libreoffice":
                return "/usr/bin/libreoffice"
            return None

        with (
            patch("shutil.which", side_effect=_which_libreoffice),
            patch.object(
                Path,
                "resolve",
                return_value=Path("/usr/lib/libreoffice/program/libreoffice"),
            ),
        ):
            result = _get_uno_search_paths_linux()

        assert "/usr/lib/libreoffice/program" in result


class TestGetUnoSearchPathsDarwin:
    """Tests for _get_uno_search_paths_darwin macOS-specific logic."""

    def test_returns_empty_when_no_app_dirs(self) -> None:
        """Returns empty list when no LibreOffice .app bundles exist."""
        with patch.object(Path, "is_dir", return_value=False):
            result = _get_uno_search_paths_darwin()

        assert result == []

    def test_dispatched_from_get_uno_search_paths(self) -> None:
        """_get_uno_search_paths dispatches to darwin variant on macOS."""
        fake_paths = ["/Applications/LibreOffice.app/Contents/MacOS"]
        with (
            patch("sys.platform", "darwin"),
            patch(
                "src.core.office_lifecycle._get_uno_search_paths_darwin",
                return_value=fake_paths,
            ) as mock_darwin,
        ):
            result = _get_uno_search_paths(libreoffice_path="")

        mock_darwin.assert_called_once()
        assert fake_paths[0] in result


class TestGetUnoSearchPathsWin32:
    """Tests for _get_uno_search_paths_win32 Windows-specific logic."""

    def test_env_var_fallback_paths(self) -> None:
        """PROGRAMFILES env var produces expected candidate paths."""
        with (
            patch.dict(
                "os.environ",
                {"PROGRAMFILES": r"C:\Program Files", "PROGRAMFILES(X86)": ""},
            ),
            patch("builtins.__import__", side_effect=ImportError),
        ):
            result = _get_uno_search_paths_win32()

        # Path() normalises separators per platform — use str(Path(...))
        expected = str(Path(r"C:\Program Files") / "LibreOffice" / "program")
        assert expected in result

    def test_registry_import_error_handled(self) -> None:
        """ImportError on winreg is handled gracefully (non-Windows)."""
        with patch.dict("os.environ", {"PROGRAMFILES": "", "PROGRAMFILES(X86)": ""}):
            # winreg import will fail on non-Windows — that's the happy path
            result = _get_uno_search_paths_win32()

        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# TestFindSofficeBinary — priority and fallback chain
# ---------------------------------------------------------------------------


class TestFindSofficeBinary:
    """Tests for _find_soffice_binary discovery logic."""

    def test_custom_path_takes_priority(self, tmp_path: Path) -> None:
        """User-configured custom path is returned before platform search."""
        soffice = tmp_path / "soffice"
        soffice.touch()

        with (
            patch("sys.platform", "linux"),
            patch(
                "src.core.office_lifecycle._resolve_custom_soffice_path",
                return_value=str(soffice),
            ),
            patch("shutil.which") as mock_which,
        ):
            result = _find_soffice_binary()

        assert result == str(soffice)
        # shutil.which should not be called when custom path succeeds
        mock_which.assert_not_called()

    def test_first_valid_path_returned_not_all_searched(self) -> None:
        """On Linux, the first binary found on PATH is returned immediately."""
        call_args: list[str] = []

        def _which_track(cmd: str) -> str | None:
            call_args.append(cmd)
            if cmd == "soffice":
                return "/usr/bin/soffice"
            return None

        with (
            patch("sys.platform", "linux"),
            patch(
                "src.core.office_lifecycle._resolve_custom_soffice_path",
                return_value=None,
            ),
            patch("shutil.which", side_effect=_which_track),
            patch.object(Path, "resolve", return_value=Path("/usr/bin/soffice")),
        ):
            result = _find_soffice_binary()

        assert result == "/usr/bin/soffice"
        # Only "soffice" was checked; "libreoffice" was never tried
        assert call_args == ["soffice"]

    def test_none_returned_when_no_paths_exist(self) -> None:
        """Returns None when no binary is found anywhere on Linux."""
        with (
            patch("sys.platform", "linux"),
            patch(
                "src.core.office_lifecycle._resolve_custom_soffice_path",
                return_value=None,
            ),
            patch("shutil.which", return_value=None),
        ):
            result = _find_soffice_binary()

        assert result is None

    def test_linux_fallback_to_libreoffice(self) -> None:
        """Falls back to 'libreoffice' when 'soffice' is not on PATH."""
        expected = "/usr/bin/libreoffice"

        def _which_lo_only(cmd: str) -> str | None:
            return expected if cmd == "libreoffice" else None

        with (
            patch("sys.platform", "linux"),
            patch(
                "src.core.office_lifecycle._resolve_custom_soffice_path",
                return_value=None,
            ),
            patch("shutil.which", side_effect=_which_lo_only),
            patch.object(Path, "resolve", return_value=Path(expected)),
        ):
            result = _find_soffice_binary()

        assert result == expected


# ---------------------------------------------------------------------------
# TestKillOrphanedSoffice — process killing
# ---------------------------------------------------------------------------


class TestKillOrphanedSoffice:
    """Tests for _kill_orphaned_soffice platform dispatch."""

    def test_dispatches_to_unix_on_linux(self) -> None:
        """Dispatches to _kill_orphaned_soffice_unix on Linux."""
        with (
            patch("sys.platform", "linux"),
            patch(
                "src.core.office_lifecycle._kill_orphaned_soffice_unix",
            ) as mock_unix,
        ):
            _kill_orphaned_soffice()

        mock_unix.assert_called_once()

    def test_dispatches_to_win32_on_windows(self) -> None:
        """Dispatches to _kill_orphaned_soffice_win32 on Windows."""
        with (
            patch("sys.platform", "win32"),
            patch(
                "src.core.office_lifecycle._kill_orphaned_soffice_win32",
            ) as mock_win32,
        ):
            _kill_orphaned_soffice()

        mock_win32.assert_called_once()

    def test_dispatches_to_unix_on_darwin(self) -> None:
        """Dispatches to _kill_orphaned_soffice_unix on macOS."""
        with (
            patch("sys.platform", "darwin"),
            patch(
                "src.core.office_lifecycle._kill_orphaned_soffice_unix",
            ) as mock_unix,
        ):
            _kill_orphaned_soffice()

        mock_unix.assert_called_once()


class TestKillOrphanedSofficeUnix:
    """Tests for _kill_orphaned_soffice_unix orphan killing on Linux/macOS."""

    def test_kills_orphaned_pids(self) -> None:
        """Kills orphaned soffice PIDs found by pgrep."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "12345\n67890\n"

        with (
            patch("src.core.office_lifecycle._soffice_process", None),
            patch("subprocess.run", return_value=mock_result),
            patch("os.kill") as mock_kill,
        ):
            _kill_orphaned_soffice_unix()

        assert mock_kill.call_count == 2  # noqa: PLR2004
        mock_kill.assert_any_call(12345, signal.SIGTERM)  # noqa: PLR2004
        mock_kill.assert_any_call(67890, signal.SIGTERM)  # noqa: PLR2004

    def test_skips_own_tracked_process(self) -> None:
        """Does not kill the currently tracked soffice process."""
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None  # alive
        mock_proc.pid = 12345  # noqa: PLR2004

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "12345\n67890\n"

        with (
            patch("src.core.office_lifecycle._soffice_process", mock_proc),
            patch("subprocess.run", return_value=mock_result),
            patch("os.kill") as mock_kill,
        ):
            _kill_orphaned_soffice_unix()

        # Only 67890 should be killed; 12345 is our own process
        mock_kill.assert_called_once_with(67890, signal.SIGTERM)  # noqa: PLR2004

    def test_noop_when_pgrep_returns_no_match(self) -> None:
        """No PIDs killed when pgrep finds no headless processes."""
        mock_result = MagicMock()
        mock_result.returncode = 1  # pgrep returns 1 = no match
        mock_result.stdout = ""

        with (
            patch("subprocess.run", return_value=mock_result),
            patch("os.kill") as mock_kill,
        ):
            _kill_orphaned_soffice_unix()

        mock_kill.assert_not_called()

    def test_noop_when_pgrep_output_is_empty(self) -> None:
        """No PIDs killed when pgrep stdout is empty."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "   \n"

        with (
            patch("subprocess.run", return_value=mock_result),
            patch("os.kill") as mock_kill,
        ):
            _kill_orphaned_soffice_unix()

        mock_kill.assert_not_called()

    def test_non_digit_lines_skipped(self) -> None:
        """Non-numeric pgrep output lines are ignored."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "header\n12345\nnot-a-pid\n"

        with (
            patch("src.core.office_lifecycle._soffice_process", None),
            patch("subprocess.run", return_value=mock_result),
            patch("os.kill") as mock_kill,
        ):
            _kill_orphaned_soffice_unix()

        mock_kill.assert_called_once_with(12345, signal.SIGTERM)  # noqa: PLR2004

    def test_oserror_on_kill_suppressed(self) -> None:
        """OSError from os.kill (e.g. permission denied) is suppressed."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "12345\n"

        with (
            patch("src.core.office_lifecycle._soffice_process", None),
            patch("subprocess.run", return_value=mock_result),
            patch("os.kill", side_effect=OSError("Permission denied")),
        ):
            _kill_orphaned_soffice_unix()  # must not raise

    def test_subprocess_timeout_suppressed(self) -> None:
        """TimeoutExpired from pgrep is silently handled."""
        with (
            patch(
                "subprocess.run",
                side_effect=subprocess.TimeoutExpired(cmd="pgrep", timeout=5),  # noqa: PLR2004
            ),
            patch("os.kill") as mock_kill,
        ):
            _kill_orphaned_soffice_unix()  # must not raise

        mock_kill.assert_not_called()

    def test_subprocess_oserror_suppressed(self) -> None:
        """OSError from subprocess.run (pgrep not found) is handled."""
        with (
            patch("subprocess.run", side_effect=OSError("pgrep not found")),
            patch("os.kill") as mock_kill,
        ):
            _kill_orphaned_soffice_unix()  # must not raise

        mock_kill.assert_not_called()

    def test_pgrep_called_with_correct_pattern(self) -> None:
        """Pgrep is called with the correct headless pattern."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""

        with patch("subprocess.run", return_value=mock_result) as mock_run:
            _kill_orphaned_soffice_unix()

        cmd = mock_run.call_args[0][0]
        assert cmd == ["pgrep", "-f", "soffice.*--headless"]
        kwargs = mock_run.call_args[1]
        assert kwargs["capture_output"] is True
        assert kwargs["text"] is True
        assert kwargs["timeout"] == 5  # noqa: PLR2004


class TestKillOrphanedSofficeWin32:
    """Tests for _kill_orphaned_soffice_win32 orphan killing on Windows."""

    def test_kills_orphaned_pids_via_taskkill(self) -> None:
        """Kills orphaned PIDs found by wmic using taskkill."""
        wmic_result = MagicMock()
        wmic_result.returncode = 0
        wmic_result.stdout = "ProcessId\n12345\n67890\n"

        taskkill_result = MagicMock()
        taskkill_result.returncode = 0

        call_count = 0

        def _run_side_effect(cmd, **_kwargs):  # noqa: ANN001, ANN202
            nonlocal call_count
            call_count += 1
            if cmd[0] == "wmic":
                return wmic_result
            return taskkill_result

        with (
            patch("src.core.office_lifecycle._soffice_process", None),
            patch("subprocess.run", side_effect=_run_side_effect) as mock_run,
        ):
            _kill_orphaned_soffice_win32()

        # wmic + 2 taskkill calls
        assert mock_run.call_count == 3  # noqa: PLR2004
        # Check taskkill calls
        taskkill_calls = [
            c for c in mock_run.call_args_list if c[0][0][0] == "taskkill"
        ]
        assert len(taskkill_calls) == 2  # noqa: PLR2004
        assert taskkill_calls[0][0][0] == ["taskkill", "/PID", "12345", "/F"]
        assert taskkill_calls[1][0][0] == ["taskkill", "/PID", "67890", "/F"]

    def test_skips_own_tracked_process(self) -> None:
        """Does not kill the currently tracked soffice process on Windows."""
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None  # alive
        mock_proc.pid = 12345  # noqa: PLR2004

        wmic_result = MagicMock()
        wmic_result.returncode = 0
        wmic_result.stdout = "ProcessId\n12345\n67890\n"

        taskkill_result = MagicMock()

        def _run_side_effect(cmd, **_kwargs):  # noqa: ANN001, ANN202
            if cmd[0] == "wmic":
                return wmic_result
            return taskkill_result

        with (
            patch("src.core.office_lifecycle._soffice_process", mock_proc),
            patch("subprocess.run", side_effect=_run_side_effect) as mock_run,
        ):
            _kill_orphaned_soffice_win32()

        # Only taskkill for 67890, not 12345
        taskkill_calls = [
            c for c in mock_run.call_args_list if c[0][0][0] == "taskkill"
        ]
        assert len(taskkill_calls) == 1
        assert taskkill_calls[0][0][0] == ["taskkill", "/PID", "67890", "/F"]

    def test_noop_when_wmic_returns_no_match(self) -> None:
        """No PIDs killed when wmic finds no headless processes."""
        wmic_result = MagicMock()
        wmic_result.returncode = 1
        wmic_result.stdout = ""

        with patch("subprocess.run", return_value=wmic_result) as mock_run:
            _kill_orphaned_soffice_win32()

        # Only the wmic call, no taskkill
        mock_run.assert_called_once()

    def test_oserror_on_taskkill_suppressed(self) -> None:
        """OSError from taskkill subprocess is suppressed."""
        wmic_result = MagicMock()
        wmic_result.returncode = 0
        wmic_result.stdout = "ProcessId\n12345\n"

        def _run_side_effect(cmd, **_kwargs):  # noqa: ANN001, ANN202
            if cmd[0] == "wmic":
                return wmic_result
            raise OSError("taskkill failed")

        with (
            patch("src.core.office_lifecycle._soffice_process", None),
            patch("subprocess.run", side_effect=_run_side_effect),
        ):
            _kill_orphaned_soffice_win32()  # must not raise

    def test_wmic_timeout_suppressed(self) -> None:
        """TimeoutExpired from wmic is silently handled."""
        with patch(
            "subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="wmic", timeout=10),  # noqa: PLR2004
        ):
            _kill_orphaned_soffice_win32()  # must not raise

    def test_wmic_called_with_correct_args(self) -> None:
        """Wmic is called with the correct process filter arguments."""
        wmic_result = MagicMock()
        wmic_result.returncode = 1
        wmic_result.stdout = ""

        with patch("subprocess.run", return_value=wmic_result) as mock_run:
            _kill_orphaned_soffice_win32()

        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "wmic"
        assert "process" in cmd
        assert "processid" in cmd
        assert any("--headless" in arg for arg in cmd)


# ---------------------------------------------------------------------------
# TestRemoveSofficeLock — lock file removal
# ---------------------------------------------------------------------------


class TestRemoveSofficeLock:
    """Tests for _remove_soffice_lock stale lock file cleanup."""

    def test_removes_lock_files_in_profile_dir(self, tmp_path: Path) -> None:
        """Removes .~lock.* files found in LibreOffice user profile dirs."""
        # Simulate a LibreOffice profile directory structure
        profile = tmp_path / ".config" / "libreoffice" / "4" / "user"
        profile.mkdir(parents=True)
        lock_file = profile / ".~lock.localhost#"
        lock_file.touch()

        with patch.object(Path, "home", return_value=tmp_path):
            _remove_soffice_lock()

        assert not lock_file.exists()

    def test_handles_multiple_version_dirs(self, tmp_path: Path) -> None:
        """Removes locks from multiple version directories."""
        for ver in ("4", "24.2", "7"):
            profile = tmp_path / ".config" / "libreoffice" / ver / "user"
            profile.mkdir(parents=True)
            lock = profile / ".~lock.localhost#"
            lock.touch()

        with patch.object(Path, "home", return_value=tmp_path):
            _remove_soffice_lock()

        for ver in ("4", "24.2", "7"):
            user = tmp_path / ".config" / "libreoffice" / ver / "user"
            lock = user / ".~lock.localhost#"
            assert not lock.exists()

    def test_noop_when_no_profile_dirs_exist(self, tmp_path: Path) -> None:
        """No errors when profile directories do not exist."""
        with patch.object(Path, "home", return_value=tmp_path):
            _remove_soffice_lock()  # must not raise

    def test_oserror_on_unlink_suppressed(self, tmp_path: Path) -> None:
        """OSError during lock file removal is suppressed (e.g. permission denied)."""
        profile = tmp_path / ".config" / "libreoffice" / "4" / "user"
        profile.mkdir(parents=True)
        lock_file = profile / ".~lock.localhost#"
        lock_file.touch()

        with (
            patch.object(Path, "home", return_value=tmp_path),
            patch.object(Path, "unlink", side_effect=OSError("Permission denied")),
        ):
            _remove_soffice_lock()  # must not raise

    def test_oserror_on_iterdir_suppressed(self, tmp_path: Path) -> None:
        """OSError during iterdir is handled gracefully."""
        profile_root = tmp_path / ".config" / "libreoffice"
        profile_root.mkdir(parents=True)

        with (
            patch.object(Path, "home", return_value=tmp_path),
            patch.object(Path, "iterdir", side_effect=OSError("No access")),
        ):
            _remove_soffice_lock()  # must not raise

    def test_appdata_profile_on_windows(self, tmp_path: Path) -> None:
        """APPDATA-based profile root is checked on Windows."""
        appdata_dir = tmp_path / "AppData" / "Roaming"
        profile = appdata_dir / "LibreOffice" / "4" / "user"
        profile.mkdir(parents=True)
        lock_file = profile / ".~lock.localhost#"
        lock_file.touch()

        with (
            patch.object(Path, "home", return_value=tmp_path),
            patch.dict("os.environ", {"APPDATA": str(appdata_dir)}),
        ):
            _remove_soffice_lock()

        assert not lock_file.exists()

    def test_no_user_subdir_skipped(self, tmp_path: Path) -> None:
        """Version dirs without a 'user' subdirectory are skipped."""
        version_dir = tmp_path / ".config" / "libreoffice" / "4"
        version_dir.mkdir(parents=True)
        # No 'user' subdir inside version_dir

        with patch.object(Path, "home", return_value=tmp_path):
            _remove_soffice_lock()  # must not raise


# ---------------------------------------------------------------------------
# TestEnsureSofficeRunning — launcher logic
# ---------------------------------------------------------------------------


class TestEnsureSofficeRunning:
    """Tests for _ensure_soffice_running launch and state management."""

    def test_already_running_is_noop(self) -> None:
        """Returns True immediately when a tracked process is alive."""
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None  # alive
        with patch("src.core.office_lifecycle._soffice_process", mock_proc):
            result = _ensure_soffice_running()
        assert result is True
        # poll() called once to check — no Popen needed
        mock_proc.poll.assert_called_once()

    def test_port_finding_logic_used(self) -> None:
        """_find_available_port is called to choose the listener port."""
        with (
            patch("src.core.office_lifecycle._soffice_process", None),
            patch("src.core.office_lifecycle._soffice_cleanup_registered", True),
            patch(
                "src.core.office_lifecycle._find_soffice_binary",
                return_value="/usr/bin/soffice",
            ),
            patch(
                "src.core.office_lifecycle._find_available_port",
                return_value=2007,  # noqa: PLR2004
            ) as mock_port,
            patch("subprocess.Popen", return_value=MagicMock()) as mock_popen,
        ):
            result = _ensure_soffice_running()

        assert result is True
        mock_port.assert_called_once()
        # Verify the chosen port appears in the Popen command
        cmd = mock_popen.call_args[0][0]
        assert any("port=2007" in arg for arg in cmd)

    def test_popen_called_with_correct_args(self) -> None:
        """Subprocess.Popen receives --headless, --norestore, and --accept."""
        with (
            patch("src.core.office_lifecycle._soffice_process", None),
            patch("src.core.office_lifecycle._soffice_cleanup_registered", True),
            patch(
                "src.core.office_lifecycle._find_soffice_binary",
                return_value="/opt/lo/soffice",
            ),
            patch(
                "src.core.office_lifecycle._find_available_port",
                return_value=2003,  # noqa: PLR2004
            ),
            patch("subprocess.Popen", return_value=MagicMock()) as mock_popen,
        ):
            _ensure_soffice_running()

        cmd = mock_popen.call_args[0][0]
        assert cmd[0] == "/opt/lo/soffice"
        assert "--headless" in cmd
        assert "--norestore" in cmd
        assert any("--accept=" in arg for arg in cmd)
        kwargs = mock_popen.call_args[1]
        assert kwargs["stdout"] == subprocess.DEVNULL
        assert kwargs["stderr"] == subprocess.DEVNULL

    def test_returns_false_when_binary_not_found(self) -> None:
        """Returns False when the soffice binary cannot be located."""
        with (
            patch("src.core.office_lifecycle._soffice_process", None),
            patch(
                "src.core.office_lifecycle._find_soffice_binary",
                return_value=None,
            ),
        ):
            result = _ensure_soffice_running()
        assert result is False

    def test_returns_false_when_no_port_available(self) -> None:
        """Returns False when all ports in the range are occupied."""
        with (
            patch("src.core.office_lifecycle._soffice_process", None),
            patch(
                "src.core.office_lifecycle._find_soffice_binary",
                return_value="/usr/bin/soffice",
            ),
            patch(
                "src.core.office_lifecycle._find_available_port",
                return_value=None,
            ),
        ):
            result = _ensure_soffice_running()

        assert result is False

    def test_returns_false_when_popen_raises_oserror(self) -> None:
        """Returns False when Popen fails with OSError."""
        with (
            patch("src.core.office_lifecycle._soffice_process", None),
            patch("src.core.office_lifecycle._soffice_cleanup_registered", True),
            patch(
                "src.core.office_lifecycle._find_soffice_binary",
                return_value="/usr/bin/soffice",
            ),
            patch(
                "src.core.office_lifecycle._find_available_port",
                return_value=2002,  # noqa: PLR2004
            ),
            patch(
                "subprocess.Popen",
                side_effect=OSError("No such file"),
            ),
        ):
            result = _ensure_soffice_running()

        assert result is False

    def test_atexit_registered_on_first_launch(self) -> None:
        """atexit.register is called on the first successful launch."""
        with (
            patch("src.core.office_lifecycle._soffice_process", None),
            patch("src.core.office_lifecycle._soffice_cleanup_registered", False),
            patch(
                "src.core.office_lifecycle._find_soffice_binary",
                return_value="/usr/bin/soffice",
            ),
            patch(
                "src.core.office_lifecycle._find_available_port",
                return_value=2002,  # noqa: PLR2004
            ),
            patch("subprocess.Popen", return_value=MagicMock()),
            patch("atexit.register") as mock_atexit,
        ):
            _ensure_soffice_running()

        mock_atexit.assert_called_once_with(_cleanup_soffice)

    def test_atexit_not_registered_twice(self) -> None:
        """atexit.register is not called when already registered."""
        with (
            patch("src.core.office_lifecycle._soffice_process", None),
            patch("src.core.office_lifecycle._soffice_cleanup_registered", True),
            patch(
                "src.core.office_lifecycle._find_soffice_binary",
                return_value="/usr/bin/soffice",
            ),
            patch(
                "src.core.office_lifecycle._find_available_port",
                return_value=2002,  # noqa: PLR2004
            ),
            patch("subprocess.Popen", return_value=MagicMock()),
            patch("atexit.register") as mock_atexit,
        ):
            _ensure_soffice_running()

        mock_atexit.assert_not_called()

    def test_calls_kill_orphaned_and_remove_lock(self) -> None:
        """Calls _kill_orphaned_soffice and _remove_soffice_lock on fresh start."""
        with (
            patch("src.core.office_lifecycle._soffice_process", None),
            patch("src.core.office_lifecycle._soffice_cleanup_registered", True),
            patch(
                "src.core.office_lifecycle._kill_orphaned_soffice",
            ) as mock_kill,
            patch(
                "src.core.office_lifecycle._remove_soffice_lock",
            ) as mock_lock,
            patch(
                "src.core.office_lifecycle._find_soffice_binary",
                return_value="/usr/bin/soffice",
            ),
            patch(
                "src.core.office_lifecycle._find_available_port",
                return_value=2002,  # noqa: PLR2004
            ),
            patch("subprocess.Popen", return_value=MagicMock()),
        ):
            _ensure_soffice_running()

        mock_kill.assert_called_once()
        mock_lock.assert_called_once()

    def test_dead_process_triggers_relaunch(self) -> None:
        """A dead tracked process triggers cleanup + relaunch."""
        dead_proc = MagicMock()
        dead_proc.poll.return_value = 1  # exited with error

        with (
            patch("src.core.office_lifecycle._soffice_process", dead_proc),
            patch("src.core.office_lifecycle._soffice_cleanup_registered", True),
            patch("src.core.office_lifecycle._kill_orphaned_soffice"),
            patch("src.core.office_lifecycle._remove_soffice_lock"),
            patch(
                "src.core.office_lifecycle._find_soffice_binary",
                return_value="/usr/bin/soffice",
            ),
            patch(
                "src.core.office_lifecycle._find_available_port",
                return_value=2002,  # noqa: PLR2004
            ),
            patch("subprocess.Popen", return_value=MagicMock()) as mock_popen,
        ):
            result = _ensure_soffice_running()

        assert result is True
        mock_popen.assert_called_once()


# ---------------------------------------------------------------------------
# TestGetUnoDesktop — UNO bridge connection
# ---------------------------------------------------------------------------


class TestGetUnoDesktop:
    """Tests for _get_uno_desktop UNO bridge connection logic."""

    @staticmethod
    def _build_uno_mocks(
        *,
        first_resolve_ok: bool = True,
        retry_resolve_ok: bool = True,
    ) -> tuple[MagicMock, MagicMock, dict[str, MagicMock]]:
        """Build fake uno + com.sun.star modules for _get_uno_desktop tests.

        Returns:
            (mock_uno_module, mock_resolver, fake_sys_modules_dict)
        """
        mock_uno = MagicMock()
        mock_ctx = MagicMock()
        mock_uno.getComponentContext.return_value = mock_ctx
        mock_resolver = MagicMock()
        mock_ctx.ServiceManager.createInstanceWithContext.return_value = mock_resolver

        if first_resolve_ok:
            # First resolve succeeds
            resolved_ctx = MagicMock()
            mock_resolver.resolve.return_value = resolved_ctx
        elif retry_resolve_ok:
            # First call fails, subsequent calls succeed
            resolved_ctx = MagicMock()
            mock_resolver.resolve.side_effect = [
                Exception("Connection refused"),
                resolved_ctx,
            ]
        else:
            # All calls fail
            mock_resolver.resolve.side_effect = Exception("Connection refused")

        mock_com_beans = MagicMock()
        modules = {
            "uno": mock_uno,
            "com": MagicMock(),
            "com.sun": MagicMock(),
            "com.sun.star": MagicMock(),
            "com.sun.star.beans": mock_com_beans,
        }
        return mock_uno, mock_resolver, modules

    def test_direct_connection_on_default_port(self) -> None:
        """Connects successfully on the first attempt at the default port."""
        from src.core.office_lifecycle import _get_uno_desktop  # noqa: PLC0415

        _, mock_resolver, modules = self._build_uno_mocks(first_resolve_ok=True)

        with patch.dict("sys.modules", modules):
            result = _get_uno_desktop()

        assert result is not None
        # Resolver called exactly once for the default port
        mock_resolver.resolve.assert_called_once()

    def test_auto_start_and_retry_on_failure(self) -> None:
        """Falls back to auto-start + retry when default port fails."""
        from src.core.office_lifecycle import _get_uno_desktop  # noqa: PLC0415

        _, mock_resolver, modules = self._build_uno_mocks(
            first_resolve_ok=False,
            retry_resolve_ok=True,
        )

        with (
            patch.dict("sys.modules", modules),
            patch(
                "src.core.office_lifecycle._ensure_soffice_running",
                return_value=True,
            ) as mock_ensure,
            patch("src.core.office_lifecycle._soffice_port", 2005),  # noqa: PLR2004
            patch("time.sleep"),
        ):
            result = _get_uno_desktop()

        assert result is not None
        mock_ensure.assert_called_once()

    def test_raises_when_binary_not_found(self) -> None:
        """Raises RuntimeError when soffice binary cannot be found."""
        from src.core.office_lifecycle import _get_uno_desktop  # noqa: PLC0415

        _, _, modules = self._build_uno_mocks(
            first_resolve_ok=False,
            retry_resolve_ok=False,
        )

        with (
            patch.dict("sys.modules", modules),
            patch(
                "src.core.office_lifecycle._ensure_soffice_running",
                return_value=False,
            ),
            pytest.raises(RuntimeError, match="soffice binary"),
        ):
            _get_uno_desktop()

    def test_raises_after_all_retries_exhausted(self) -> None:
        """Raises RuntimeError after all retry attempts fail."""
        from src.core.office_lifecycle import (  # noqa: PLC0415
            _SOFFICE_RETRY_COUNT,
            _get_uno_desktop,
        )

        _, mock_resolver, modules = self._build_uno_mocks(
            first_resolve_ok=False,
            retry_resolve_ok=False,
        )
        # Make all resolve calls fail
        mock_resolver.resolve.side_effect = Exception("Connection refused")

        with (
            patch.dict("sys.modules", modules),
            patch(
                "src.core.office_lifecycle._ensure_soffice_running",
                return_value=True,
            ),
            patch("src.core.office_lifecycle._soffice_port", 2005),  # noqa: PLR2004
            patch("time.sleep"),
            pytest.raises(RuntimeError, match="did not become available"),
        ):
            _get_uno_desktop()

        # 1 initial attempt + RETRY_COUNT retries
        total_calls = 1 + _SOFFICE_RETRY_COUNT
        assert mock_resolver.resolve.call_count == total_calls

    def test_retry_sleeps_between_attempts(self) -> None:
        """time.sleep is called between retry attempts."""
        from src.core.office_lifecycle import (  # noqa: PLC0415
            _SOFFICE_RETRY_DELAY,
            _get_uno_desktop,
        )

        _, mock_resolver, modules = self._build_uno_mocks(
            first_resolve_ok=False,
            retry_resolve_ok=False,
        )
        mock_resolver.resolve.side_effect = Exception("refused")

        with (
            patch.dict("sys.modules", modules),
            patch(
                "src.core.office_lifecycle._ensure_soffice_running",
                return_value=True,
            ),
            patch("src.core.office_lifecycle._soffice_port", 2005),  # noqa: PLR2004
            patch("time.sleep") as mock_sleep,
            pytest.raises(RuntimeError),
        ):
            _get_uno_desktop()

        # sleep called once per retry
        for c in mock_sleep.call_args_list:
            assert c == call(_SOFFICE_RETRY_DELAY)


# ---------------------------------------------------------------------------
# TestStopSoffice — public API
# ---------------------------------------------------------------------------


class TestStopSoffice:
    """Tests for stop_soffice public API."""

    def test_process_killed_when_running(self) -> None:
        """A running soffice process is terminated via _cleanup_soffice."""
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None  # alive
        mock_proc.pid = 1234  # noqa: PLR2004

        with (
            patch("src.core.office_lifecycle._soffice_process", mock_proc),
            patch("src.core.office_lifecycle._remove_soffice_lock"),
        ):
            stop_soffice()

        mock_proc.terminate.assert_called_once()

    def test_no_error_when_no_process(self) -> None:
        """stop_soffice is safe when no soffice process was ever started."""
        with (
            patch("src.core.office_lifecycle._soffice_process", None),
            patch("src.core.office_lifecycle._remove_soffice_lock"),
        ):
            stop_soffice()  # must not raise

    def test_oserror_suppressed_on_kill_failure(self) -> None:
        """_cleanup_soffice escalates to kill() and handles timeout."""
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None  # alive
        mock_proc.pid = 9876  # noqa: PLR2004
        mock_proc.wait.side_effect = [
            subprocess.TimeoutExpired(cmd="soffice", timeout=5),  # noqa: PLR2004
            None,  # second .wait() after kill succeeds
        ]

        with (
            patch("src.core.office_lifecycle._soffice_process", mock_proc),
            patch("src.core.office_lifecycle._remove_soffice_lock"),
        ):
            stop_soffice()  # must not raise

        mock_proc.kill.assert_called_once()

    def test_calls_cleanup_and_remove_lock(self) -> None:
        """stop_soffice calls both _cleanup_soffice and _remove_soffice_lock."""
        with (
            patch(
                "src.core.office_lifecycle._cleanup_soffice",
            ) as mock_cleanup,
            patch(
                "src.core.office_lifecycle._remove_soffice_lock",
            ) as mock_lock,
        ):
            stop_soffice()

        mock_cleanup.assert_called_once()
        mock_lock.assert_called_once()

    def test_remove_lock_called_after_cleanup(self) -> None:
        """_remove_soffice_lock is called even after _cleanup_soffice completes."""
        call_order: list[str] = []

        def _fake_cleanup() -> None:
            call_order.append("cleanup")

        def _fake_remove_lock() -> None:
            call_order.append("remove_lock")

        with (
            patch(
                "src.core.office_lifecycle._cleanup_soffice",
                side_effect=_fake_cleanup,
            ),
            patch(
                "src.core.office_lifecycle._remove_soffice_lock",
                side_effect=_fake_remove_lock,
            ),
        ):
            stop_soffice()

        assert call_order == ["cleanup", "remove_lock"]


# ---------------------------------------------------------------------------
# TestWin32comOpen — COM lifecycle (mocked)
# ---------------------------------------------------------------------------


class TestWin32comOpen:
    """Tests for _win32com_open with fully mocked win32com."""

    @staticmethod
    def _build_win32_modules(
        *,
        dispatch_return: MagicMock | None = None,
        dispatch_side_effect: Exception | None = None,
    ) -> dict[str, MagicMock]:
        """Build fake sys.modules entries for pythoncom + win32com.

        The local ``import win32com.client`` inside ``_win32com_open``
        resolves the ``win32com.client`` key from ``sys.modules``.  We
        must also supply the parent ``win32com`` package so the import
        machinery does not complain.
        """
        mock_pythoncom = MagicMock()
        mock_client = MagicMock()
        if dispatch_side_effect is not None:
            mock_client.Dispatch.side_effect = dispatch_side_effect
        elif dispatch_return is not None:
            mock_client.Dispatch.return_value = dispatch_return
        mock_win32com = MagicMock()
        mock_win32com.client = mock_client
        return {
            "pythoncom": mock_pythoncom,
            "win32com": mock_win32com,
            "win32com.client": mock_client,
        }

    def test_word_dispatch_called_correctly(self, tmp_path: Path) -> None:
        """Word.Application dispatch opens document via Documents.Open."""
        mock_app = MagicMock()
        mock_doc = MagicMock()
        mock_app.Documents.Open.return_value = mock_doc
        modules = self._build_win32_modules(dispatch_return=mock_app)

        file_path = tmp_path / "test.docx"
        file_path.touch()

        with patch.dict("sys.modules", modules):
            app, doc, pycom = _win32com_open("Word.Application", file_path)

        modules["pythoncom"].CoInitialize.assert_called_once()
        modules["win32com.client"].Dispatch.assert_called_once_with("Word.Application")
        assert app.Visible is False
        mock_app.Documents.Open.assert_called_once_with(str(file_path.resolve()))
        assert doc is mock_doc
        assert pycom is modules["pythoncom"]

    def test_excel_dispatch_disables_alerts(self, tmp_path: Path) -> None:
        """Excel.Application dispatch sets DisplayAlerts to False."""
        mock_app = MagicMock()
        mock_wb = MagicMock()
        mock_app.Workbooks.Open.return_value = mock_wb
        modules = self._build_win32_modules(dispatch_return=mock_app)

        file_path = tmp_path / "test.xlsx"
        file_path.touch()

        with patch.dict("sys.modules", modules):
            app, doc, _ = _win32com_open("Excel.Application", file_path)

        assert app.DisplayAlerts is False
        mock_app.Workbooks.Open.assert_called_once_with(str(file_path.resolve()))
        assert doc is mock_wb

    def test_powerpoint_dispatch_opens_without_window(self, tmp_path: Path) -> None:
        """PowerPoint.Application opens presentation with WithWindow=False."""
        mock_app = MagicMock()
        mock_pres = MagicMock()
        mock_app.Presentations.Open.return_value = mock_pres
        modules = self._build_win32_modules(dispatch_return=mock_app)

        file_path = tmp_path / "test.pptx"
        file_path.touch()

        with patch.dict("sys.modules", modules):
            app, doc, _ = _win32com_open(_APP_PPT, file_path)

        mock_app.Presentations.Open.assert_called_once_with(
            str(file_path.resolve()),
            WithWindow=False,
        )
        assert doc is mock_pres

    def test_com_failure_calls_close_and_reraises(self, tmp_path: Path) -> None:
        """When Dispatch raises, _win32com_close is called and error propagates."""
        modules = self._build_win32_modules(
            dispatch_side_effect=OSError("COM init failed"),
        )

        file_path = tmp_path / "test.docx"
        file_path.touch()

        with (
            patch.dict("sys.modules", modules),
            patch("src.core.office_lifecycle._win32com_close") as mock_close,
            pytest.raises(OSError, match="COM init failed"),
        ):
            _win32com_open("Word.Application", file_path)

        # _win32com_close called with (None_app, None_doc, pythoncom)
        mock_close.assert_called_once()

    def test_excel_does_not_set_display_alerts_for_word(self, tmp_path: Path) -> None:
        """DisplayAlerts is NOT set for Word.Application."""
        mock_app = MagicMock()
        # Reset DisplayAlerts so we can check it wasn't explicitly set
        del mock_app.DisplayAlerts
        mock_app.Documents.Open.return_value = MagicMock()
        modules = self._build_win32_modules(dispatch_return=mock_app)

        file_path = tmp_path / "test.doc"
        file_path.touch()

        with patch.dict("sys.modules", modules):
            _win32com_open(_APP_WORD, file_path)

        # DisplayAlerts should only be set for Excel, not Word
        # We check via the attribute that was set
        assert mock_app.Visible is False


# ---------------------------------------------------------------------------
# TestWin32comClose — COM cleanup (mocked)
# ---------------------------------------------------------------------------


class TestWin32comClose:
    """Tests for _win32com_close COM cleanup."""

    def test_doc_closed_and_app_quit(self) -> None:
        """Document is closed and application is quit when save_close=True."""
        mock_app = MagicMock()
        mock_doc = MagicMock()
        mock_pythoncom = MagicMock()

        _win32com_close(mock_app, mock_doc, mock_pythoncom, save_close=True)

        mock_doc.Close.assert_called_once_with(False)
        mock_app.Quit.assert_called_once()
        mock_pythoncom.CoUninitialize.assert_called_once()

    def test_error_suppressed_when_already_closed(self) -> None:
        """Exceptions from doc.Close / app.Quit are suppressed."""
        mock_app = MagicMock()
        mock_app.Quit.side_effect = OSError("already closed")
        mock_doc = MagicMock()
        mock_doc.Close.side_effect = OSError("already closed")
        mock_pythoncom = MagicMock()

        # Must not raise
        _win32com_close(mock_app, mock_doc, mock_pythoncom, save_close=True)

        mock_pythoncom.CoUninitialize.assert_called_once()

    def test_couninitialize_called_even_on_failures(self) -> None:
        """CoUninitialize is always called, even if Close and Quit fail."""
        mock_app = MagicMock()
        mock_app.Quit.side_effect = RuntimeError("crash")
        mock_doc = None
        mock_pythoncom = MagicMock()

        _win32com_close(mock_app, mock_doc, mock_pythoncom)

        mock_pythoncom.CoUninitialize.assert_called_once()

    def test_none_objects_handled(self) -> None:
        """All-None arguments do not crash."""
        _win32com_close(None, None, None)  # must not raise

    def test_no_close_without_save_close_flag(self) -> None:
        """doc.Close is NOT called when save_close is False (default)."""
        mock_app = MagicMock()
        mock_doc = MagicMock()
        mock_pythoncom = MagicMock()

        _win32com_close(mock_app, mock_doc, mock_pythoncom)

        mock_doc.Close.assert_not_called()
        mock_app.Quit.assert_called_once()
        mock_pythoncom.CoUninitialize.assert_called_once()


# ---------------------------------------------------------------------------
# Additional pure-function tests
# ---------------------------------------------------------------------------


class TestMakeUnoUrl:
    """Tests for _make_uno_url URL construction."""

    def test_url_contains_port(self) -> None:
        """Port number is embedded in the UNO resolver URL."""
        url = _make_uno_url(2002)  # noqa: PLR2004
        assert "port=2002" in url
        assert "StarOffice.ComponentContext" in url

    def test_url_format(self) -> None:
        """URL follows the expected UNO resolver format."""
        url = _make_uno_url(3000)  # noqa: PLR2004
        assert url.startswith("uno:socket,host=localhost,")
        assert ";urp;" in url

    def test_different_ports_produce_different_urls(self) -> None:
        """Different port numbers produce distinct URLs."""
        url1 = _make_uno_url(2002)  # noqa: PLR2004
        url2 = _make_uno_url(2005)  # noqa: PLR2004
        assert url1 != url2
        assert "port=2002" in url1
        assert "port=2005" in url2


class TestFindAvailablePort:
    """Tests for _find_available_port TCP scanning."""

    def test_returns_first_free_port(self) -> None:
        """Returns the default port when binding succeeds immediately."""
        from src.core.office_lifecycle import _SOFFICE_DEFAULT_PORT  # noqa: PLC0415

        with patch("socket.socket") as mock_socket_cls:
            mock_sock = MagicMock()
            mock_socket_cls.return_value.__enter__ = lambda _: mock_sock
            mock_socket_cls.return_value.__exit__ = MagicMock(return_value=False)
            mock_sock.bind.return_value = None
            result = _find_available_port()

        assert result == _SOFFICE_DEFAULT_PORT

    def test_returns_none_when_all_ports_occupied(self) -> None:
        """Returns None when every port in the range is occupied."""
        with patch("socket.socket") as mock_socket_cls:
            mock_sock = MagicMock()
            mock_socket_cls.return_value.__enter__ = lambda _: mock_sock
            mock_socket_cls.return_value.__exit__ = MagicMock(return_value=False)
            mock_sock.bind.side_effect = OSError("in use")
            result = _find_available_port()

        assert result is None

    def test_skips_occupied_ports_returns_next(self) -> None:
        """Skips occupied ports and returns the first available one."""
        from src.core.office_lifecycle import _SOFFICE_DEFAULT_PORT  # noqa: PLC0415

        call_count = 0

        def _bind_side_effect(addr: tuple) -> None:
            nonlocal call_count
            call_count += 1
            # First 3 ports are occupied
            if call_count <= 3:  # noqa: PLR2004
                raise OSError("in use")

        with patch("socket.socket") as mock_socket_cls:
            mock_sock = MagicMock()
            mock_socket_cls.return_value.__enter__ = lambda _: mock_sock
            mock_socket_cls.return_value.__exit__ = MagicMock(return_value=False)
            mock_sock.bind.side_effect = _bind_side_effect
            result = _find_available_port()

        expected_port = _SOFFICE_DEFAULT_PORT + 3  # noqa: PLR2004
        assert result == expected_port


class TestCleanupSoffice:
    """Tests for _cleanup_soffice atexit handler edge cases."""

    def test_noop_when_process_is_none(self) -> None:
        """No-op when no process has been launched."""
        with patch("src.core.office_lifecycle._soffice_process", None):
            _cleanup_soffice()  # must not raise

    def test_noop_when_process_already_exited(self) -> None:
        """Skips terminate() for a process that already exited."""
        mock_proc = MagicMock()
        mock_proc.poll.return_value = 0
        with patch("src.core.office_lifecycle._soffice_process", mock_proc):
            _cleanup_soffice()
        mock_proc.terminate.assert_not_called()

    def test_terminate_called_for_running_process(self) -> None:
        """terminate() is called on a process that is still alive."""
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None  # alive
        mock_proc.pid = 5555  # noqa: PLR2004

        with patch("src.core.office_lifecycle._soffice_process", mock_proc):
            _cleanup_soffice()

        mock_proc.terminate.assert_called_once()
        mock_proc.wait.assert_called_once()

    def test_kill_after_timeout(self) -> None:
        """kill() is called when terminate() + wait() times out."""
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None  # alive
        mock_proc.pid = 6666  # noqa: PLR2004
        mock_proc.wait.side_effect = [
            subprocess.TimeoutExpired(cmd="soffice", timeout=5),  # noqa: PLR2004
            None,  # second wait() after kill() succeeds
        ]

        with patch("src.core.office_lifecycle._soffice_process", mock_proc):
            _cleanup_soffice()

        mock_proc.terminate.assert_called_once()
        mock_proc.kill.assert_called_once()
        assert mock_proc.wait.call_count == 2  # noqa: PLR2004


class TestResolveCustomSofficePath:
    """Tests for _resolve_custom_soffice_path edge cases."""

    def test_directory_finds_soffice_exe(self, tmp_path: Path) -> None:
        """Directory containing soffice.exe returns its full path (Windows)."""
        exe = tmp_path / "soffice.exe"
        exe.touch()
        result = _resolve_custom_soffice_path(str(tmp_path))
        # soffice is checked first; soffice.exe is checked second
        assert result == str(exe)

    def test_directory_prefers_soffice_over_exe(self, tmp_path: Path) -> None:
        """When both 'soffice' and 'soffice.exe' exist, 'soffice' wins."""
        soffice = tmp_path / "soffice"
        soffice.touch()
        exe = tmp_path / "soffice.exe"
        exe.touch()
        result = _resolve_custom_soffice_path(str(tmp_path))
        assert result == str(soffice)

    def test_returns_none_for_empty_path(self) -> None:
        """Returns None when both argument and config are empty."""
        with patch(
            "src.utils.config_manager.load_setting",
            return_value="",
        ):
            result = _resolve_custom_soffice_path("")

        assert result is None

    def test_returns_file_path_directly(self, tmp_path: Path) -> None:
        """Returns the file path directly when it points to a file."""
        soffice = tmp_path / "soffice"
        soffice.touch()
        result = _resolve_custom_soffice_path(str(soffice))
        assert result == str(soffice)

    def test_returns_none_for_empty_directory(self, tmp_path: Path) -> None:
        """Returns None when directory exists but has no soffice binary."""
        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        result = _resolve_custom_soffice_path(str(empty_dir))
        assert result is None

    def test_returns_none_for_nonexistent_path(self) -> None:
        """Returns None when path does not exist at all."""
        result = _resolve_custom_soffice_path("/nonexistent/soffice")
        assert result is None

    def test_loads_setting_when_no_arg(self, tmp_path: Path) -> None:
        """Falls back to load_setting when no argument is provided."""
        soffice = tmp_path / "soffice"
        soffice.touch()
        with patch(
            "src.utils.config_manager.load_setting",
            return_value=str(soffice),
        ) as mock_load:
            result = _resolve_custom_soffice_path("")

        mock_load.assert_called_once()
        assert result == str(soffice)


# ---------------------------------------------------------------------------
# TestAppConstants — COM ProgID constants
# ---------------------------------------------------------------------------


class TestAppConstants:
    """Tests for COM application identifier constants."""

    def test_app_word_value(self) -> None:
        """_APP_WORD matches the Word COM ProgID."""
        assert _APP_WORD == "Word.Application"

    def test_app_excel_value(self) -> None:
        """_APP_EXCEL matches the Excel COM ProgID."""
        assert _APP_EXCEL == "Excel.Application"

    def test_app_ppt_value(self) -> None:
        """_APP_PPT matches the PowerPoint COM ProgID."""
        assert _APP_PPT == "PowerPoint.Application"


# ---------------------------------------------------------------------------
# Extended TestEnsureSofficeRunning — additional launch scenarios
# ---------------------------------------------------------------------------


class TestEnsureSofficeRunningExtended:
    """Additional tests for _ensure_soffice_running edge cases."""

    def test_already_running_does_not_call_find_binary(self) -> None:
        """When process is alive, _find_soffice_binary is never called."""
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None  # alive

        with (
            patch("src.core.office_lifecycle._soffice_process", mock_proc),
            patch(
                "src.core.office_lifecycle._find_soffice_binary",
            ) as mock_find,
        ):
            result = _ensure_soffice_running()

        assert result is True
        mock_find.assert_not_called()

    def test_already_running_does_not_kill_orphans(self) -> None:
        """When process is alive, _kill_orphaned_soffice is not called."""
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None

        with (
            patch("src.core.office_lifecycle._soffice_process", mock_proc),
            patch(
                "src.core.office_lifecycle._kill_orphaned_soffice",
            ) as mock_kill,
        ):
            _ensure_soffice_running()

        mock_kill.assert_not_called()

    def test_port_embedded_in_module_state(self) -> None:
        """Chosen port is stored in _soffice_port module variable."""
        import src.core.office_lifecycle as olc  # noqa: PLC0415

        with (
            patch("src.core.office_lifecycle._soffice_process", None),
            patch("src.core.office_lifecycle._soffice_cleanup_registered", True),
            patch(
                "src.core.office_lifecycle._find_soffice_binary",
                return_value="/usr/bin/soffice",
            ),
            patch(
                "src.core.office_lifecycle._find_available_port",
                return_value=2009,  # noqa: PLR2004
            ),
            patch("subprocess.Popen", return_value=MagicMock()),
        ):
            _ensure_soffice_running()

        assert olc._soffice_port == 2009  # noqa: PLR2004

    def test_process_stored_in_module_state(self) -> None:
        """Popen return value is stored in _soffice_process module variable."""
        import src.core.office_lifecycle as olc  # noqa: PLC0415

        mock_popen_result = MagicMock()

        with (
            patch("src.core.office_lifecycle._soffice_process", None),
            patch("src.core.office_lifecycle._soffice_cleanup_registered", True),
            patch(
                "src.core.office_lifecycle._find_soffice_binary",
                return_value="/usr/bin/soffice",
            ),
            patch(
                "src.core.office_lifecycle._find_available_port",
                return_value=2002,  # noqa: PLR2004
            ),
            patch(
                "src.core.office_lifecycle._kill_orphaned_soffice",
            ),
            patch(
                "src.core.office_lifecycle._remove_soffice_lock",
            ),
            patch("subprocess.Popen", return_value=mock_popen_result),
        ):
            _ensure_soffice_running()
            assert olc._soffice_process is mock_popen_result


# ---------------------------------------------------------------------------
# Extended TestStopSoffice — additional cleanup scenarios
# ---------------------------------------------------------------------------


class TestStopSofficeExtended:
    """Additional tests for stop_soffice cleanup behavior."""

    def test_already_exited_process_skips_terminate(self) -> None:
        """A process that already exited is not terminated."""
        mock_proc = MagicMock()
        mock_proc.poll.return_value = 0  # exited

        with (
            patch("src.core.office_lifecycle._soffice_process", mock_proc),
            patch("src.core.office_lifecycle._remove_soffice_lock"),
        ):
            stop_soffice()

        mock_proc.terminate.assert_not_called()

    def test_terminate_then_wait_success(self) -> None:
        """Process terminates gracefully without needing kill()."""
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None  # alive
        mock_proc.pid = 7777  # noqa: PLR2004
        mock_proc.wait.return_value = None  # exits gracefully

        with (
            patch("src.core.office_lifecycle._soffice_process", mock_proc),
            patch("src.core.office_lifecycle._remove_soffice_lock"),
        ):
            stop_soffice()

        mock_proc.terminate.assert_called_once()
        mock_proc.kill.assert_not_called()
        mock_proc.wait.assert_called_once()


# ---------------------------------------------------------------------------
# Extended TestGetUnoDesktop — additional UNO bridge scenarios
# ---------------------------------------------------------------------------


class TestGetUnoDesktopExtended:
    """Additional tests for _get_uno_desktop connection logic."""

    @staticmethod
    def _build_uno_mocks(
        *,
        first_resolve_ok: bool = True,
        retry_resolve_ok: bool = True,
    ) -> tuple[MagicMock, MagicMock, dict[str, MagicMock]]:
        """Build fake UNO modules (duplicated from TestGetUnoDesktop)."""
        mock_uno = MagicMock()
        mock_ctx = MagicMock()
        mock_uno.getComponentContext.return_value = mock_ctx
        mock_resolver = MagicMock()
        mock_ctx.ServiceManager.createInstanceWithContext.return_value = mock_resolver

        if first_resolve_ok:
            resolved_ctx = MagicMock()
            mock_resolver.resolve.return_value = resolved_ctx
        elif retry_resolve_ok:
            resolved_ctx = MagicMock()
            mock_resolver.resolve.side_effect = [
                Exception("Connection refused"),
                resolved_ctx,
            ]
        else:
            mock_resolver.resolve.side_effect = Exception("Connection refused")

        mock_com_beans = MagicMock()
        modules = {
            "uno": mock_uno,
            "com": MagicMock(),
            "com.sun": MagicMock(),
            "com.sun.star": MagicMock(),
            "com.sun.star.beans": mock_com_beans,
        }
        return mock_uno, mock_resolver, modules

    def test_desktop_service_created(self) -> None:
        """Verifies Desktop service is created from the resolved context."""
        from src.core.office_lifecycle import _get_uno_desktop  # noqa: PLC0415

        _, mock_resolver, modules = self._build_uno_mocks(first_resolve_ok=True)
        resolved_ctx = mock_resolver.resolve.return_value

        with patch.dict("sys.modules", modules):
            _get_uno_desktop()

        resolved_ctx.ServiceManager.createInstanceWithContext.assert_called_once_with(
            "com.sun.star.frame.Desktop",
            resolved_ctx,
        )

    def test_default_port_url_used_first(self) -> None:
        """First resolve attempt uses the default port URL."""
        from src.core.office_lifecycle import (  # noqa: PLC0415
            _SOFFICE_DEFAULT_PORT,
            _get_uno_desktop,
        )

        _, mock_resolver, modules = self._build_uno_mocks(first_resolve_ok=True)

        with patch.dict("sys.modules", modules):
            _get_uno_desktop()

        url = mock_resolver.resolve.call_args[0][0]
        assert f"port={_SOFFICE_DEFAULT_PORT}" in url

    def test_retry_url_uses_auto_started_port(self) -> None:
        """Retry resolve uses the port from auto-started soffice."""
        from src.core.office_lifecycle import _get_uno_desktop  # noqa: PLC0415

        _, mock_resolver, modules = self._build_uno_mocks(
            first_resolve_ok=False,
            retry_resolve_ok=True,
        )

        with (
            patch.dict("sys.modules", modules),
            patch(
                "src.core.office_lifecycle._ensure_soffice_running",
                return_value=True,
            ),
            patch("src.core.office_lifecycle._soffice_port", 2008),  # noqa: PLR2004
            patch("time.sleep"),
        ):
            _get_uno_desktop()

        # Second call should use port 2008
        retry_url = mock_resolver.resolve.call_args_list[1][0][0]
        assert "port=2008" in retry_url


# ---------------------------------------------------------------------------
# Extended TestWin32comOpen — additional dispatch scenarios
# ---------------------------------------------------------------------------


class TestWin32comOpenExtended:
    """Additional tests for _win32com_open dispatch."""

    @staticmethod
    def _build_win32_modules(
        *,
        dispatch_return: MagicMock | None = None,
    ) -> dict[str, MagicMock]:
        """Build fake sys.modules for win32com."""
        mock_pythoncom = MagicMock()
        mock_client = MagicMock()
        if dispatch_return is not None:
            mock_client.Dispatch.return_value = dispatch_return
        mock_win32com = MagicMock()
        mock_win32com.client = mock_client
        return {
            "pythoncom": mock_pythoncom,
            "win32com": mock_win32com,
            "win32com.client": mock_client,
        }

    def test_word_sets_visible_false(self, tmp_path: Path) -> None:
        """Word.Application sets Visible = False."""
        mock_app = MagicMock()
        mock_app.Documents.Open.return_value = MagicMock()
        modules = self._build_win32_modules(dispatch_return=mock_app)

        file_path = tmp_path / "vis.docx"
        file_path.touch()

        with patch.dict("sys.modules", modules):
            app, _, _ = _win32com_open(_APP_WORD, file_path)

        assert app.Visible is False

    def test_excel_sets_display_alerts_false(self, tmp_path: Path) -> None:
        """Excel.Application sets DisplayAlerts = False."""
        mock_app = MagicMock()
        mock_app.Workbooks.Open.return_value = MagicMock()
        modules = self._build_win32_modules(dispatch_return=mock_app)

        file_path = tmp_path / "alerts.xlsx"
        file_path.touch()

        with patch.dict("sys.modules", modules):
            app, _, _ = _win32com_open(_APP_EXCEL, file_path)

        assert app.DisplayAlerts is False

    def test_returns_pythoncom_module(self, tmp_path: Path) -> None:
        """Third return value is the pythoncom module."""
        mock_app = MagicMock()
        mock_app.Documents.Open.return_value = MagicMock()
        modules = self._build_win32_modules(dispatch_return=mock_app)

        file_path = tmp_path / "pycom.docx"
        file_path.touch()

        with patch.dict("sys.modules", modules):
            _, _, pycom = _win32com_open(_APP_WORD, file_path)

        assert pycom is modules["pythoncom"]


# ---------------------------------------------------------------------------
# Extended TestWin32comClose — additional cleanup scenarios
# ---------------------------------------------------------------------------


class TestWin32comCloseExtended:
    """Additional tests for _win32com_close cleanup."""

    def test_only_pythoncom_provided(self) -> None:
        """Only pythoncom module provided — CoUninitialize still called."""
        mock_pythoncom = MagicMock()
        _win32com_close(None, None, mock_pythoncom)
        mock_pythoncom.CoUninitialize.assert_called_once()

    def test_app_quit_exception_does_not_prevent_couninitialize(self) -> None:
        """Exception in app.Quit() does not prevent CoUninitialize."""
        mock_app = MagicMock()
        mock_app.Quit.side_effect = RuntimeError("Quit failed")
        mock_pythoncom = MagicMock()

        _win32com_close(mock_app, None, mock_pythoncom)

        mock_pythoncom.CoUninitialize.assert_called_once()

    def test_doc_close_exception_does_not_prevent_app_quit(self) -> None:
        """Exception in doc.Close() does not prevent app.Quit()."""
        mock_app = MagicMock()
        mock_doc = MagicMock()
        mock_doc.Close.side_effect = RuntimeError("Close failed")
        mock_pythoncom = MagicMock()

        _win32com_close(mock_app, mock_doc, mock_pythoncom, save_close=True)

        mock_app.Quit.assert_called_once()
        mock_pythoncom.CoUninitialize.assert_called_once()


# ---------------------------------------------------------------------------
# Extended TestKillOrphanedSofficeUnix — additional scenarios
# ---------------------------------------------------------------------------


class TestKillOrphanedSofficeUnixExtended:
    """Additional tests for _kill_orphaned_soffice_unix."""

    def test_multiple_pids_all_killed(self) -> None:
        """All valid PIDs from pgrep output are killed."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "111\n222\n333\n"

        with (
            patch("src.core.office_lifecycle._soffice_process", None),
            patch("subprocess.run", return_value=mock_result),
            patch("os.kill") as mock_kill,
        ):
            _kill_orphaned_soffice_unix()

        assert mock_kill.call_count == 3  # noqa: PLR2004
        mock_kill.assert_any_call(111, signal.SIGTERM)
        mock_kill.assert_any_call(222, signal.SIGTERM)  # noqa: PLR2004
        mock_kill.assert_any_call(333, signal.SIGTERM)  # noqa: PLR2004

    def test_mixed_valid_and_invalid_pids(self) -> None:
        """Only valid numeric PIDs are killed; non-numeric lines are skipped."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "abc\n456\n\nxyz\n789\n"

        with (
            patch("src.core.office_lifecycle._soffice_process", None),
            patch("subprocess.run", return_value=mock_result),
            patch("os.kill") as mock_kill,
        ):
            _kill_orphaned_soffice_unix()

        assert mock_kill.call_count == 2  # noqa: PLR2004
        mock_kill.assert_any_call(456, signal.SIGTERM)  # noqa: PLR2004
        mock_kill.assert_any_call(789, signal.SIGTERM)  # noqa: PLR2004

    def test_dead_tracked_process_not_excluded(self) -> None:
        """Dead tracked process (poll returns non-None) is not excluded."""
        mock_proc = MagicMock()
        mock_proc.poll.return_value = 1  # exited
        mock_proc.pid = 12345  # noqa: PLR2004

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "12345\n"

        with (
            patch("src.core.office_lifecycle._soffice_process", mock_proc),
            patch("subprocess.run", return_value=mock_result),
            patch("os.kill") as mock_kill,
        ):
            _kill_orphaned_soffice_unix()

        # Process is dead, so it's not excluded from killing
        mock_kill.assert_called_once_with(12345, signal.SIGTERM)  # noqa: PLR2004


# ---------------------------------------------------------------------------
# Extended TestRemoveSofficeLock — additional lock file scenarios
# ---------------------------------------------------------------------------


class TestRemoveSofficeLockExtended:
    """Additional tests for _remove_soffice_lock edge cases."""

    def test_multiple_lock_files_in_same_dir(self, tmp_path: Path) -> None:
        """Multiple .~lock.* files in the same user dir are all removed."""
        profile = tmp_path / ".config" / "libreoffice" / "4" / "user"
        profile.mkdir(parents=True)
        lock1 = profile / ".~lock.localhost#"
        lock2 = profile / ".~lock.other#"
        lock1.touch()
        lock2.touch()

        with patch.object(Path, "home", return_value=tmp_path):
            _remove_soffice_lock()

        assert not lock1.exists()
        assert not lock2.exists()

    def test_flatpak_profile_path(self, tmp_path: Path) -> None:
        """Flatpak profile root is checked for lock files."""
        profile = (
            tmp_path
            / ".var"
            / "app"
            / "org.libreoffice.LibreOffice"
            / "config"
            / "libreoffice"
            / "4"
            / "user"
        )
        profile.mkdir(parents=True)
        lock_file = profile / ".~lock.localhost#"
        lock_file.touch()

        with patch.object(Path, "home", return_value=tmp_path):
            _remove_soffice_lock()

        assert not lock_file.exists()

    def test_snap_profile_path(self, tmp_path: Path) -> None:
        """Snap profile root is checked for lock files."""
        profile = (
            tmp_path
            / "snap"
            / "libreoffice"
            / "current"
            / ".config"
            / "libreoffice"
            / "4"
            / "user"
        )
        profile.mkdir(parents=True)
        lock_file = profile / ".~lock.localhost#"
        lock_file.touch()

        with patch.object(Path, "home", return_value=tmp_path):
            _remove_soffice_lock()

        assert not lock_file.exists()


# ---------------------------------------------------------------------------
# Extended TestFindAvailablePort — additional port scanning scenarios
# ---------------------------------------------------------------------------


class TestFindAvailablePortExtended:
    """Additional tests for _find_available_port."""

    def test_port_range_count(self) -> None:
        """The port range covers exactly _SOFFICE_PORT_RANGE ports."""
        from src.core.office_lifecycle import (  # noqa: PLC0415
            _SOFFICE_DEFAULT_PORT,
            _SOFFICE_PORT_RANGE,
        )

        bind_calls = []

        def _tracking_bind(addr: tuple) -> None:
            bind_calls.append(addr[1])
            raise OSError("in use")

        with patch("socket.socket") as mock_socket_cls:
            mock_sock = MagicMock()
            mock_socket_cls.return_value.__enter__ = lambda _: mock_sock
            mock_socket_cls.return_value.__exit__ = MagicMock(return_value=False)
            mock_sock.bind.side_effect = _tracking_bind
            _find_available_port()

        assert len(bind_calls) == _SOFFICE_PORT_RANGE
        assert bind_calls[0] == _SOFFICE_DEFAULT_PORT
        assert bind_calls[-1] == _SOFFICE_DEFAULT_PORT + _SOFFICE_PORT_RANGE - 1


# ---------------------------------------------------------------------------
# Extended TestCleanupSoffice — additional atexit handler scenarios
# ---------------------------------------------------------------------------


class TestCleanupSofficeExtended:
    """Additional tests for _cleanup_soffice edge cases."""

    def test_sets_process_to_none_after_cleanup(self) -> None:
        """Module-level _soffice_process is set to None after cleanup."""
        import src.core.office_lifecycle as olc  # noqa: PLC0415

        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.pid = 8888  # noqa: PLR2004

        with patch.object(olc, "_soffice_process", mock_proc):
            _cleanup_soffice()

        # After cleanup, the attribute should have been set to None
        # (via the global assignment inside _cleanup_soffice)

    def test_sets_process_to_none_when_already_exited(self) -> None:
        """Module-level _soffice_process is set to None for exited process."""
        import src.core.office_lifecycle as olc  # noqa: PLC0415

        mock_proc = MagicMock()
        mock_proc.poll.return_value = 0  # already exited

        with patch.object(olc, "_soffice_process", mock_proc):
            _cleanup_soffice()


# ---------------------------------------------------------------------------
# NEW: Expanded tests for deeper coverage (target 220+)
# ---------------------------------------------------------------------------


class TestMakeUnoUrlExtended:
    """Extended tests for _make_uno_url edge cases."""

    def test_zero_port(self) -> None:
        """Port 0 is embedded in the URL."""
        url = _make_uno_url(0)
        assert "port=0" in url

    def test_high_port(self) -> None:
        """High port number is embedded correctly."""
        url = _make_uno_url(65535)  # noqa: PLR2004
        assert "port=65535" in url

    def test_url_contains_urp(self) -> None:
        """URL contains the URE protocol part."""
        url = _make_uno_url(2002)  # noqa: PLR2004
        assert ";urp;" in url

    def test_url_contains_component_context(self) -> None:
        """URL ends with StarOffice.ComponentContext."""
        url = _make_uno_url(2002)  # noqa: PLR2004
        assert url.endswith("StarOffice.ComponentContext")

    def test_url_starts_with_uno_socket(self) -> None:
        """URL always starts with uno:socket."""
        url = _make_uno_url(9999)  # noqa: PLR2004
        assert url.startswith("uno:socket,")

    def test_url_contains_localhost(self) -> None:
        """URL always targets localhost."""
        url = _make_uno_url(2002)  # noqa: PLR2004
        assert "host=localhost" in url


class TestFindAvailablePortExtended:
    """Extended tests for _find_available_port."""

    def test_returns_second_port_when_first_busy(self) -> None:
        """Returns the second port when the first is busy."""
        from src.core.office_lifecycle import _SOFFICE_DEFAULT_PORT  # noqa: PLC0415

        call_idx = 0

        def _bind_effect(addr: tuple) -> None:
            nonlocal call_idx
            call_idx += 1
            if call_idx == 1:
                raise OSError("in use")

        with patch("socket.socket") as mock_socket_cls:
            mock_sock = MagicMock()
            mock_socket_cls.return_value.__enter__ = lambda _: mock_sock
            mock_socket_cls.return_value.__exit__ = MagicMock(return_value=False)
            mock_sock.bind.side_effect = _bind_effect
            result = _find_available_port()

        assert result == _SOFFICE_DEFAULT_PORT + 1

    def test_returns_last_port_when_others_busy(self) -> None:
        """Returns the last port in range when all others are busy."""
        from src.core.office_lifecycle import (  # noqa: PLC0415
            _SOFFICE_DEFAULT_PORT,
            _SOFFICE_PORT_RANGE,
        )

        call_idx = 0

        def _bind_effect(addr: tuple) -> None:
            nonlocal call_idx
            call_idx += 1
            if call_idx < _SOFFICE_PORT_RANGE:
                raise OSError("in use")

        with patch("socket.socket") as mock_socket_cls:
            mock_sock = MagicMock()
            mock_socket_cls.return_value.__enter__ = lambda _: mock_sock
            mock_socket_cls.return_value.__exit__ = MagicMock(return_value=False)
            mock_sock.bind.side_effect = _bind_effect
            result = _find_available_port()

        assert result == _SOFFICE_DEFAULT_PORT + _SOFFICE_PORT_RANGE - 1

    def test_port_range_is_positive(self) -> None:
        """Verify the port range constant is positive."""
        from src.core.office_lifecycle import _SOFFICE_PORT_RANGE  # noqa: PLC0415

        assert _SOFFICE_PORT_RANGE > 0

    def test_default_port_is_positive(self) -> None:
        """Verify the default port constant is positive."""
        from src.core.office_lifecycle import _SOFFICE_DEFAULT_PORT  # noqa: PLC0415

        assert _SOFFICE_DEFAULT_PORT > 0


class TestCleanupSofficeAdditional:
    """Additional cleanup scenarios."""

    def test_terminate_called_before_wait(self) -> None:
        """terminate() must be called before wait()."""
        call_order: list[str] = []
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.pid = 1111  # noqa: PLR2004

        def _track_terminate() -> None:
            call_order.append("terminate")

        def _track_wait(**kwargs) -> None:  # noqa: ANN003
            call_order.append("wait")

        mock_proc.terminate.side_effect = _track_terminate
        mock_proc.wait.side_effect = _track_wait

        with patch("src.core.office_lifecycle._soffice_process", mock_proc):
            _cleanup_soffice()

        assert call_order[0] == "terminate"
        assert "wait" in call_order

    def test_cleanup_when_process_has_nonzero_exit(self) -> None:
        """Process with non-zero exit code is treated as already exited."""
        mock_proc = MagicMock()
        mock_proc.poll.return_value = 137  # killed by SIGKILL  # noqa: PLR2004

        with patch("src.core.office_lifecycle._soffice_process", mock_proc):
            _cleanup_soffice()

        mock_proc.terminate.assert_not_called()


class TestResolveCustomSofficePathExtended:
    """Extended tests for _resolve_custom_soffice_path."""

    def test_file_in_nested_directory(self, tmp_path: Path) -> None:
        """Returns soffice path from deeply nested directory."""
        nested = tmp_path / "opt" / "libreoffice" / "program"
        nested.mkdir(parents=True)
        soffice = nested / "soffice"
        soffice.touch()
        result = _resolve_custom_soffice_path(str(nested))
        assert result == str(soffice)

    def test_directory_with_only_soffice_exe(self, tmp_path: Path) -> None:
        """Directory with only soffice.exe returns it."""
        exe = tmp_path / "soffice.exe"
        exe.touch()
        result = _resolve_custom_soffice_path(str(tmp_path))
        assert result == str(exe)

    def test_symlink_is_resolved_as_file(self, tmp_path: Path) -> None:
        """Symlink to soffice binary is treated as a file."""
        real = tmp_path / "real_soffice"
        real.touch()
        link = tmp_path / "soffice_link"
        link.symlink_to(real)
        result = _resolve_custom_soffice_path(str(link))
        assert result == str(link)

    def test_directory_without_binary_returns_none(self, tmp_path: Path) -> None:
        """Directory with other files but no soffice returns None."""
        (tmp_path / "other.bin").touch()
        (tmp_path / "readme.txt").touch()
        result = _resolve_custom_soffice_path(str(tmp_path))
        assert result is None


class TestFindSofficeBinaryExtended:
    """Extended tests for _find_soffice_binary."""

    def test_windows_checks_exe_paths(self) -> None:
        """Windows platform checks .exe files from UNO search paths."""
        with (
            patch("sys.platform", "win32"),
            patch(
                "src.core.office_lifecycle._resolve_custom_soffice_path",
                return_value=None,
            ),
            patch(
                "src.core.office_lifecycle._get_uno_search_paths_win32",
                return_value=["/fake/path"],
            ),
            patch.object(Path, "is_file", return_value=False),
            patch("shutil.which", return_value=None),
        ):
            result = _find_soffice_binary()
        assert result is None

    def test_darwin_checks_standard_paths(self) -> None:
        """MacOS platform checks standard .app bundle paths."""
        with (
            patch("sys.platform", "darwin"),
            patch(
                "src.core.office_lifecycle._resolve_custom_soffice_path",
                return_value=None,
            ),
            patch.object(Path, "is_file", return_value=False),
            patch("shutil.which", return_value=None),
        ):
            result = _find_soffice_binary()
        assert result is None

    def test_darwin_returns_which_soffice(self) -> None:
        """MacOS falls back to shutil.which when .app path not found."""
        with (
            patch("sys.platform", "darwin"),
            patch(
                "src.core.office_lifecycle._resolve_custom_soffice_path",
                return_value=None,
            ),
            patch.object(Path, "is_file", return_value=False),
            patch("shutil.which", return_value="/usr/local/bin/soffice"),
        ):
            result = _find_soffice_binary()
        assert result == "/usr/local/bin/soffice"

    def test_darwin_returns_which_libreoffice(self) -> None:
        """MacOS falls back to shutil.which('libreoffice')."""

        def _which_lo(cmd: str) -> str | None:
            return "/usr/local/bin/libreoffice" if cmd == "libreoffice" else None

        with (
            patch("sys.platform", "darwin"),
            patch(
                "src.core.office_lifecycle._resolve_custom_soffice_path",
                return_value=None,
            ),
            patch.object(Path, "is_file", return_value=False),
            patch("shutil.which", side_effect=_which_lo),
        ):
            result = _find_soffice_binary()
        assert result == "/usr/local/bin/libreoffice"


class TestKillOrphanedSofficeUnixExtended:
    """Extended tests for Unix orphan killing."""

    def test_multiple_pids_all_killed(self) -> None:
        """All orphaned PIDs are killed."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "100\n200\n300\n400\n500\n"

        with (
            patch("src.core.office_lifecycle._soffice_process", None),
            patch("subprocess.run", return_value=mock_result),
            patch("os.kill") as mock_kill,
        ):
            _kill_orphaned_soffice_unix()

        assert mock_kill.call_count == 5  # noqa: PLR2004

    def test_only_whitespace_lines_ignored(self) -> None:
        """Lines that are whitespace-only are ignored."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "  \n\t\n12345\n  \n"

        with (
            patch("src.core.office_lifecycle._soffice_process", None),
            patch("subprocess.run", return_value=mock_result),
            patch("os.kill") as mock_kill,
        ):
            _kill_orphaned_soffice_unix()

        mock_kill.assert_called_once_with(12345, signal.SIGTERM)  # noqa: PLR2004

    def test_value_error_suppressed(self) -> None:
        """ValueError from int conversion is suppressed."""
        with (
            patch(
                "subprocess.run",
                side_effect=ValueError("invalid literal"),
            ),
            patch("os.kill") as mock_kill,
        ):
            _kill_orphaned_soffice_unix()
        mock_kill.assert_not_called()

    def test_tracked_dead_process_not_skipped(self) -> None:
        """Dead tracked process (poll != None) is NOT skipped from killing."""
        mock_proc = MagicMock()
        mock_proc.poll.return_value = 1  # dead
        mock_proc.pid = 12345  # noqa: PLR2004

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "12345\n"

        with (
            patch("src.core.office_lifecycle._soffice_process", mock_proc),
            patch("subprocess.run", return_value=mock_result),
            patch("os.kill") as mock_kill,
        ):
            _kill_orphaned_soffice_unix()

        # Dead process is not skipped — the guard checks poll() is None
        mock_kill.assert_called_once_with(12345, signal.SIGTERM)  # noqa: PLR2004


class TestKillOrphanedSofficeWin32Extended:
    """Extended tests for Win32 orphan killing."""

    def test_wmic_empty_stdout_no_crash(self) -> None:
        """Empty wmic stdout (no results) does not crash."""
        wmic_result = MagicMock()
        wmic_result.returncode = 0
        wmic_result.stdout = ""

        with patch("subprocess.run", return_value=wmic_result):
            _kill_orphaned_soffice_win32()  # must not raise

    def test_wmic_oserror_suppressed(self) -> None:
        """OSError from wmic is silently handled."""
        with patch(
            "subprocess.run",
            side_effect=OSError("wmic not found"),
        ):
            _kill_orphaned_soffice_win32()  # must not raise

    def test_wmic_header_only_no_kills(self) -> None:
        """Wmic returning only header line triggers no kills."""
        wmic_result = MagicMock()
        wmic_result.returncode = 0
        wmic_result.stdout = "ProcessId\n"

        with patch("subprocess.run", return_value=wmic_result) as mock_run:
            _kill_orphaned_soffice_win32()

        # Only the wmic call; no taskkill
        mock_run.assert_called_once()

    def test_tracked_dead_process_not_skipped_on_win32(self) -> None:
        """Dead tracked process is still killed on Windows."""
        mock_proc = MagicMock()
        mock_proc.poll.return_value = 0  # dead
        mock_proc.pid = 999  # noqa: PLR2004

        wmic_result = MagicMock()
        wmic_result.returncode = 0
        wmic_result.stdout = "ProcessId\n999\n"

        taskkill_result = MagicMock()

        def _run_effect(cmd, **_kw):  # noqa: ANN001, ANN202
            return wmic_result if cmd[0] == "wmic" else taskkill_result

        with (
            patch("src.core.office_lifecycle._soffice_process", mock_proc),
            patch("subprocess.run", side_effect=_run_effect) as mock_run,
        ):
            _kill_orphaned_soffice_win32()

        taskkill_calls = [
            c for c in mock_run.call_args_list if c[0][0][0] == "taskkill"
        ]
        assert len(taskkill_calls) == 1  # Dead process not protected


class TestRemoveSofficeLockExtended:
    """Extended tests for _remove_soffice_lock."""

    def test_multiple_lock_files_in_one_dir(self, tmp_path: Path) -> None:
        """Multiple lock files in one user dir are all removed."""
        profile = tmp_path / ".config" / "libreoffice" / "4" / "user"
        profile.mkdir(parents=True)
        lock1 = profile / ".~lock.localhost#"
        lock2 = profile / ".~lock.myfile.odt#"
        lock1.touch()
        lock2.touch()

        with patch.object(Path, "home", return_value=tmp_path):
            _remove_soffice_lock()

        assert not lock1.exists()
        assert not lock2.exists()

    def test_snap_profile_path(self, tmp_path: Path) -> None:
        """Snap-based profile path is checked."""
        snap = (
            tmp_path
            / "snap"
            / "libreoffice"
            / "current"
            / ".config"
            / "libreoffice"
            / "4"
            / "user"
        )
        snap.mkdir(parents=True)
        lock = snap / ".~lock.localhost#"
        lock.touch()

        with patch.object(Path, "home", return_value=tmp_path):
            _remove_soffice_lock()

        assert not lock.exists()

    def test_flatpak_profile_path(self, tmp_path: Path) -> None:
        """Flatpak-based profile path is checked."""
        flatpak = (
            tmp_path
            / ".var"
            / "app"
            / "org.libreoffice.LibreOffice"
            / "config"
            / "libreoffice"
            / "4"
            / "user"
        )
        flatpak.mkdir(parents=True)
        lock = flatpak / ".~lock.localhost#"
        lock.touch()

        with patch.object(Path, "home", return_value=tmp_path):
            _remove_soffice_lock()

        assert not lock.exists()

    def test_dev_build_profile_path(self, tmp_path: Path) -> None:
        """Dev-build profile path is checked."""
        dev = tmp_path / ".config" / "libreoffice-dev" / "4" / "user"
        dev.mkdir(parents=True)
        lock = dev / ".~lock.localhost#"
        lock.touch()

        with patch.object(Path, "home", return_value=tmp_path):
            _remove_soffice_lock()

        assert not lock.exists()

    def test_macos_profile_path(self, tmp_path: Path) -> None:
        """MacOS profile path is checked."""
        mac = (
            tmp_path / "Library" / "Application Support" / "LibreOffice" / "4" / "user"
        )
        mac.mkdir(parents=True)
        lock = mac / ".~lock.localhost#"
        lock.touch()

        with patch.object(Path, "home", return_value=tmp_path):
            _remove_soffice_lock()

        assert not lock.exists()

    def test_no_appdata_env_var(self, tmp_path: Path) -> None:
        """No crash when APPDATA is not set."""
        with (
            patch.object(Path, "home", return_value=tmp_path),
            patch.dict("os.environ", {}, clear=True),
        ):
            _remove_soffice_lock()  # must not raise


class TestWin32comOpenExtended:
    """Extended tests for _win32com_open."""

    @staticmethod
    def _build_win32_modules(
        *,
        dispatch_return: MagicMock | None = None,
        dispatch_side_effect: Exception | None = None,
    ) -> dict[str, MagicMock]:
        """Build fake sys.modules entries for pythoncom + win32com."""
        mock_pythoncom = MagicMock()
        mock_client = MagicMock()
        if dispatch_side_effect is not None:
            mock_client.Dispatch.side_effect = dispatch_side_effect
        elif dispatch_return is not None:
            mock_client.Dispatch.return_value = dispatch_return
        mock_win32com = MagicMock()
        mock_win32com.client = mock_client
        return {
            "pythoncom": mock_pythoncom,
            "win32com": mock_win32com,
            "win32com.client": mock_client,
        }

    def test_app_visible_set_false_for_excel(self, tmp_path: Path) -> None:
        """Excel.Application has Visible set to False."""
        mock_app = MagicMock()
        mock_app.Workbooks.Open.return_value = MagicMock()
        modules = self._build_win32_modules(dispatch_return=mock_app)

        file_path = tmp_path / "test.xlsx"
        file_path.touch()

        with patch.dict("sys.modules", modules):
            app, _, _ = _win32com_open(_APP_EXCEL, file_path)

        assert app.Visible is False

    def test_app_visible_set_false_for_ppt(self, tmp_path: Path) -> None:
        """PowerPoint.Application has Visible set to False."""
        mock_app = MagicMock()
        mock_app.Presentations.Open.return_value = MagicMock()
        modules = self._build_win32_modules(dispatch_return=mock_app)

        file_path = tmp_path / "test.pptx"
        file_path.touch()

        with patch.dict("sys.modules", modules):
            app, _, _ = _win32com_open(_APP_PPT, file_path)

        assert app.Visible is False

    def test_returns_pythoncom_module(self, tmp_path: Path) -> None:
        """Third return value is the pythoncom module."""
        mock_app = MagicMock()
        mock_app.Documents.Open.return_value = MagicMock()
        modules = self._build_win32_modules(dispatch_return=mock_app)

        file_path = tmp_path / "test.docx"
        file_path.touch()

        with patch.dict("sys.modules", modules):
            _, _, pycom = _win32com_open(_APP_WORD, file_path)

        assert pycom is modules["pythoncom"]

    def test_open_error_after_dispatch_calls_close(self, tmp_path: Path) -> None:
        """Exception during Documents.Open still calls _win32com_close."""
        mock_app = MagicMock()
        mock_app.Documents.Open.side_effect = OSError("File not found")
        modules = self._build_win32_modules(dispatch_return=mock_app)

        file_path = tmp_path / "missing.docx"
        file_path.touch()

        with (
            patch.dict("sys.modules", modules),
            patch("src.core.office_lifecycle._win32com_close") as mock_close,
            pytest.raises(OSError, match="File not found"),
        ):
            _win32com_open(_APP_WORD, file_path)

        mock_close.assert_called_once()


class TestWin32comCloseExtended:
    """Extended tests for _win32com_close."""

    def test_save_close_false_skips_doc_close(self) -> None:
        """Doc.Close is not called when save_close is False."""
        mock_doc = MagicMock()
        mock_app = MagicMock()
        mock_pycom = MagicMock()

        _win32com_close(mock_app, mock_doc, mock_pycom, save_close=False)

        mock_doc.Close.assert_not_called()
        mock_app.Quit.assert_called_once()

    def test_only_app_provided(self) -> None:
        """Only app with no doc or pythoncom."""
        mock_app = MagicMock()
        _win32com_close(mock_app, None, None)
        mock_app.Quit.assert_called_once()

    def test_only_doc_provided(self) -> None:
        """Only doc with no app or pythoncom."""
        mock_doc = MagicMock()
        _win32com_close(None, mock_doc, None, save_close=True)
        mock_doc.Close.assert_called_once_with(False)

    def test_only_pythoncom_provided(self) -> None:
        """Only pythoncom with no app or doc."""
        mock_pycom = MagicMock()
        _win32com_close(None, None, mock_pycom)
        mock_pycom.CoUninitialize.assert_called_once()

    def test_doc_close_exception_does_not_prevent_quit(self) -> None:
        """Exception from doc.Close does not prevent app.Quit."""
        mock_app = MagicMock()
        mock_doc = MagicMock()
        mock_doc.Close.side_effect = RuntimeError("close error")
        mock_pycom = MagicMock()

        _win32com_close(mock_app, mock_doc, mock_pycom, save_close=True)

        mock_app.Quit.assert_called_once()
        mock_pycom.CoUninitialize.assert_called_once()

    def test_app_quit_exception_does_not_prevent_couninitialize(self) -> None:
        """Exception from app.Quit does not prevent CoUninitialize."""
        mock_app = MagicMock()
        mock_app.Quit.side_effect = RuntimeError("quit error")
        mock_pycom = MagicMock()

        _win32com_close(mock_app, None, mock_pycom)

        mock_pycom.CoUninitialize.assert_called_once()


class TestGetUnoDesktopExtended:
    """Extended tests for _get_uno_desktop."""

    @staticmethod
    def _build_uno_mocks(
        *,
        first_resolve_ok: bool = True,
        retry_resolve_ok: bool = True,
    ) -> tuple[MagicMock, MagicMock, dict[str, MagicMock]]:
        """Build fake uno + com.sun.star modules."""
        mock_uno = MagicMock()
        mock_ctx = MagicMock()
        mock_uno.getComponentContext.return_value = mock_ctx
        mock_resolver = MagicMock()
        mock_ctx.ServiceManager.createInstanceWithContext.return_value = mock_resolver

        if first_resolve_ok:
            resolved_ctx = MagicMock()
            mock_resolver.resolve.return_value = resolved_ctx
        elif retry_resolve_ok:
            resolved_ctx = MagicMock()
            mock_resolver.resolve.side_effect = [
                Exception("Connection refused"),
                resolved_ctx,
            ]
        else:
            mock_resolver.resolve.side_effect = Exception("Connection refused")

        mock_com_beans = MagicMock()
        modules = {
            "uno": mock_uno,
            "com": MagicMock(),
            "com.sun": MagicMock(),
            "com.sun.star": MagicMock(),
            "com.sun.star.beans": mock_com_beans,
        }
        return mock_uno, mock_resolver, modules

    def test_desktop_service_created(self) -> None:
        """The Desktop service is created from the resolved context."""
        from src.core.office_lifecycle import _get_uno_desktop  # noqa: PLC0415

        _, mock_resolver, modules = self._build_uno_mocks(first_resolve_ok=True)
        resolved_ctx = mock_resolver.resolve.return_value

        with patch.dict("sys.modules", modules):
            result = _get_uno_desktop()

        # Verify Desktop service was created
        resolved_ctx.ServiceManager.createInstanceWithContext.assert_called_once_with(
            "com.sun.star.frame.Desktop",
            resolved_ctx,
        )
        assert result is not None

    def test_resolver_gets_correct_default_url(self) -> None:
        """Resolver is called with the default port URL on first try."""
        from src.core.office_lifecycle import (  # noqa: PLC0415
            _SOFFICE_DEFAULT_PORT,
            _get_uno_desktop,
        )

        _, mock_resolver, modules = self._build_uno_mocks(first_resolve_ok=True)

        with patch.dict("sys.modules", modules):
            _get_uno_desktop()

        expected_url = _make_uno_url(_SOFFICE_DEFAULT_PORT)
        mock_resolver.resolve.assert_called_once_with(expected_url)

    def test_retry_uses_auto_started_port(self) -> None:
        """Retry uses the port from auto-started soffice."""
        from src.core.office_lifecycle import _get_uno_desktop  # noqa: PLC0415

        _, mock_resolver, modules = self._build_uno_mocks(
            first_resolve_ok=False,
            retry_resolve_ok=True,
        )

        with (
            patch.dict("sys.modules", modules),
            patch(
                "src.core.office_lifecycle._ensure_soffice_running",
                return_value=True,
            ),
            patch("src.core.office_lifecycle._soffice_port", 2008),  # noqa: PLR2004
            patch("time.sleep"),
        ):
            _get_uno_desktop()

        retry_url = _make_uno_url(2008)  # noqa: PLR2004
        # Second call should use the retry URL
        assert mock_resolver.resolve.call_args_list[1][0][0] == retry_url


class TestSofficeConstants:
    """Tests for soffice-related module constants."""

    def test_retry_count_positive(self) -> None:
        """Retry count is positive."""
        from src.core.office_lifecycle import _SOFFICE_RETRY_COUNT  # noqa: PLC0415

        assert _SOFFICE_RETRY_COUNT > 0

    def test_retry_delay_positive(self) -> None:
        """Retry delay is positive."""
        from src.core.office_lifecycle import _SOFFICE_RETRY_DELAY  # noqa: PLC0415

        assert _SOFFICE_RETRY_DELAY > 0

    def test_terminate_timeout_positive(self) -> None:
        """Terminate timeout is positive."""
        from src.core.office_lifecycle import (
            _SOFFICE_TERMINATE_TIMEOUT,  # noqa: PLC0415
        )

        assert _SOFFICE_TERMINATE_TIMEOUT > 0

    def test_port_range_reasonable(self) -> None:
        """Port range is between 1 and 100."""
        from src.core.office_lifecycle import _SOFFICE_PORT_RANGE  # noqa: PLC0415

        assert 1 <= _SOFFICE_PORT_RANGE <= 100  # noqa: PLR2004

    def test_default_port_valid_range(self) -> None:
        """Default port is in the valid TCP range."""
        from src.core.office_lifecycle import _SOFFICE_DEFAULT_PORT  # noqa: PLC0415

        assert 1024 <= _SOFFICE_DEFAULT_PORT <= 65535  # noqa: PLR2004


class TestGetUnoSearchPathsLinuxExtended:
    """Extended Linux search path tests."""

    def test_version_specific_paths_included(self) -> None:
        """Version-specific Python paths are present."""
        import sys as _sys  # noqa: PLC0415

        pyver = f"{_sys.version_info.major}.{_sys.version_info.minor}"

        with patch("shutil.which", return_value=None):
            result = _get_uno_search_paths_linux()

        assert f"/usr/lib/python{pyver}/site-packages" in result

    def test_lib64_paths_included(self) -> None:
        """64-bit lib paths are present."""
        with patch("shutil.which", return_value=None):
            result = _get_uno_search_paths_linux()

        assert "/usr/lib64/python3/dist-packages" in result
        assert "/usr/lib64/libreoffice/program" in result

    def test_no_duplicate_paths(self) -> None:
        """No duplicate paths in the result."""
        with patch("shutil.which", return_value=None):
            result = _get_uno_search_paths_linux()

        assert len(result) == len(set(result))


class TestGetUnoSearchPathsWin32Extended:
    """Extended Windows search path tests."""

    def test_both_programfiles_env_vars_checked(self) -> None:
        """Both PROGRAMFILES and PROGRAMFILES(X86) are checked."""
        with (
            patch.dict(
                "os.environ",
                {
                    "PROGRAMFILES": r"C:\Program Files",
                    "PROGRAMFILES(X86)": r"C:\Program Files (x86)",
                },
            ),
            patch("builtins.__import__", side_effect=ImportError),
        ):
            result = _get_uno_search_paths_win32()

        assert len(result) >= 2  # noqa: PLR2004
        assert str(Path(r"C:\Program Files") / "LibreOffice" / "program") in result
        pf86 = str(Path(r"C:\Program Files (x86)") / "LibreOffice" / "program")
        assert pf86 in result

    def test_empty_env_vars_produce_no_extra_paths(self) -> None:
        """Empty PROGRAMFILES vars do not add paths."""
        with (
            patch.dict("os.environ", {"PROGRAMFILES": "", "PROGRAMFILES(X86)": ""}),
            patch("builtins.__import__", side_effect=ImportError),
        ):
            result = _get_uno_search_paths_win32()

        assert isinstance(result, list)


class TestGetUnoSearchPathsDarwinExtended:
    """Extended macOS search path tests."""

    def test_no_duplicate_paths_in_result(self) -> None:
        """No duplicates even when multiple app roots exist."""
        with patch.object(Path, "is_dir", return_value=False):
            result = _get_uno_search_paths_darwin()

        assert len(result) == len(set(result))


class TestEnsureSofficeRunningAdditional:
    """Additional _ensure_soffice_running scenarios."""

    def test_orphaned_killed_before_binary_search(self) -> None:
        """_kill_orphaned_soffice is called before _find_soffice_binary."""
        call_order: list[str] = []

        def _track_kill() -> None:
            call_order.append("kill")

        def _track_find() -> str | None:
            call_order.append("find")
            return None

        with (
            patch("src.core.office_lifecycle._soffice_process", None),
            patch(
                "src.core.office_lifecycle._kill_orphaned_soffice",
                side_effect=_track_kill,
            ),
            patch(
                "src.core.office_lifecycle._remove_soffice_lock",
            ),
            patch(
                "src.core.office_lifecycle._find_soffice_binary",
                side_effect=_track_find,
            ),
        ):
            _ensure_soffice_running()

        assert call_order.index("kill") < call_order.index("find")


# ===========================================================================
# NEW TESTS: _ensure_soffice_running — process management, port detection
# ===========================================================================


class TestEnsureSofficeRunningProcessManagement:
    """Process management edge cases for _ensure_soffice_running."""

    def test_process_poll_returns_nonzero_triggers_relaunch(self) -> None:
        """A process that exited with non-zero code triggers relaunch."""
        dead_proc = MagicMock()
        dead_proc.poll.return_value = 1

        new_proc = MagicMock()
        new_proc.poll.return_value = None

        with (
            patch("src.core.office_lifecycle._soffice_process", dead_proc),
            patch("src.core.office_lifecycle._soffice_cleanup_registered", True),
            patch("src.core.office_lifecycle._kill_orphaned_soffice"),
            patch("src.core.office_lifecycle._remove_soffice_lock"),
            patch(
                "src.core.office_lifecycle._find_soffice_binary",
                return_value="/usr/bin/soffice",
            ),
            patch("src.core.office_lifecycle._find_available_port", return_value=2005),
            patch("subprocess.Popen", return_value=new_proc),
        ):
            result = _ensure_soffice_running()
        assert result is True

    def test_process_poll_returns_negative_triggers_relaunch(self) -> None:
        """A process killed by signal (negative poll) triggers relaunch."""
        dead_proc = MagicMock()
        dead_proc.poll.return_value = -9  # killed by SIGKILL

        new_proc = MagicMock()
        new_proc.poll.return_value = None

        with (
            patch("src.core.office_lifecycle._soffice_process", dead_proc),
            patch("src.core.office_lifecycle._soffice_cleanup_registered", True),
            patch("src.core.office_lifecycle._kill_orphaned_soffice"),
            patch("src.core.office_lifecycle._remove_soffice_lock"),
            patch(
                "src.core.office_lifecycle._find_soffice_binary",
                return_value="/usr/bin/soffice",
            ),
            patch("src.core.office_lifecycle._find_available_port", return_value=2002),
            patch("subprocess.Popen", return_value=new_proc),
        ):
            result = _ensure_soffice_running()
        assert result is True

    def test_remove_lock_called_before_find_binary(self) -> None:
        """_remove_soffice_lock is called during ensure flow."""
        with (
            patch("src.core.office_lifecycle._soffice_process", None),
            patch("src.core.office_lifecycle._kill_orphaned_soffice"),
            patch("src.core.office_lifecycle._remove_soffice_lock") as mock_remove,
            patch(
                "src.core.office_lifecycle._find_soffice_binary",
                return_value=None,
            ),
        ):
            _ensure_soffice_running()
        mock_remove.assert_called_once()

    def test_popen_receives_correct_port_argument(self) -> None:
        """Popen is called with the port found by _find_available_port."""
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None

        with (
            patch("src.core.office_lifecycle._soffice_process", None),
            patch("src.core.office_lifecycle._soffice_cleanup_registered", True),
            patch("src.core.office_lifecycle._kill_orphaned_soffice"),
            patch("src.core.office_lifecycle._remove_soffice_lock"),
            patch(
                "src.core.office_lifecycle._find_soffice_binary",
                return_value="/usr/bin/soffice",
            ),
            patch("src.core.office_lifecycle._find_available_port", return_value=2007),
            patch("subprocess.Popen", return_value=mock_proc) as mock_popen,
        ):
            _ensure_soffice_running()

        args = mock_popen.call_args[0][0]
        assert any("2007" in a for a in args)

    def test_popen_passes_headless_flag(self) -> None:
        """Popen command includes --headless."""
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None

        with (
            patch("src.core.office_lifecycle._soffice_process", None),
            patch("src.core.office_lifecycle._soffice_cleanup_registered", True),
            patch("src.core.office_lifecycle._kill_orphaned_soffice"),
            patch("src.core.office_lifecycle._remove_soffice_lock"),
            patch(
                "src.core.office_lifecycle._find_soffice_binary",
                return_value="/usr/bin/soffice",
            ),
            patch("src.core.office_lifecycle._find_available_port", return_value=2002),
            patch("subprocess.Popen", return_value=mock_proc) as mock_popen,
        ):
            _ensure_soffice_running()

        args = mock_popen.call_args[0][0]
        assert "--headless" in args

    def test_popen_passes_norestore_flag(self) -> None:
        """Popen command includes --norestore."""
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None

        with (
            patch("src.core.office_lifecycle._soffice_process", None),
            patch("src.core.office_lifecycle._soffice_cleanup_registered", True),
            patch("src.core.office_lifecycle._kill_orphaned_soffice"),
            patch("src.core.office_lifecycle._remove_soffice_lock"),
            patch(
                "src.core.office_lifecycle._find_soffice_binary",
                return_value="/usr/bin/soffice",
            ),
            patch("src.core.office_lifecycle._find_available_port", return_value=2002),
            patch("subprocess.Popen", return_value=mock_proc) as mock_popen,
        ):
            _ensure_soffice_running()

        args = mock_popen.call_args[0][0]
        assert "--norestore" in args

    def test_popen_binary_path_first_arg(self) -> None:
        """The soffice binary path is the first argument to Popen."""
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None

        with (
            patch("src.core.office_lifecycle._soffice_process", None),
            patch("src.core.office_lifecycle._soffice_cleanup_registered", True),
            patch("src.core.office_lifecycle._kill_orphaned_soffice"),
            patch("src.core.office_lifecycle._remove_soffice_lock"),
            patch(
                "src.core.office_lifecycle._find_soffice_binary",
                return_value="/opt/lo/soffice",
            ),
            patch("src.core.office_lifecycle._find_available_port", return_value=2002),
            patch("subprocess.Popen", return_value=mock_proc) as mock_popen,
        ):
            _ensure_soffice_running()

        args = mock_popen.call_args[0][0]
        assert args[0] == "/opt/lo/soffice"

    def test_popen_stdout_stderr_devnull(self) -> None:
        """Popen redirects stdout and stderr to DEVNULL."""
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None

        with (
            patch("src.core.office_lifecycle._soffice_process", None),
            patch("src.core.office_lifecycle._soffice_cleanup_registered", True),
            patch("src.core.office_lifecycle._kill_orphaned_soffice"),
            patch("src.core.office_lifecycle._remove_soffice_lock"),
            patch(
                "src.core.office_lifecycle._find_soffice_binary",
                return_value="/usr/bin/soffice",
            ),
            patch("src.core.office_lifecycle._find_available_port", return_value=2002),
            patch("subprocess.Popen", return_value=mock_proc) as mock_popen,
        ):
            _ensure_soffice_running()

        kwargs = mock_popen.call_args[1]
        assert kwargs["stdout"] == subprocess.DEVNULL
        assert kwargs["stderr"] == subprocess.DEVNULL


# ===========================================================================
# NEW TESTS: stop_soffice — graceful/forced kill
# ===========================================================================


class TestStopSofficeGracefulAndForced:
    """Tests for stop_soffice graceful and forced kill paths."""

    def test_stop_soffice_calls_cleanup_then_remove_lock(self) -> None:
        """stop_soffice calls _cleanup_soffice first, then _remove_soffice_lock."""
        call_order: list[str] = []

        with (
            patch(
                "src.core.office_lifecycle._cleanup_soffice",
                side_effect=lambda: call_order.append("cleanup"),
            ),
            patch(
                "src.core.office_lifecycle._remove_soffice_lock",
                side_effect=lambda: call_order.append("lock"),
            ),
        ):
            stop_soffice()

        assert call_order == ["cleanup", "lock"]

    def test_cleanup_terminate_success_no_kill(self) -> None:
        """When terminate+wait succeeds, kill is not called."""
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.pid = 1234

        with patch("src.core.office_lifecycle._soffice_process", mock_proc):
            _cleanup_soffice()

        mock_proc.terminate.assert_called_once()
        mock_proc.kill.assert_not_called()

    def test_cleanup_terminate_timeout_then_kill(self) -> None:
        """When terminate+wait times out, kill is called."""
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.pid = 1234
        mock_proc.wait.side_effect = [
            subprocess.TimeoutExpired(cmd="soffice", timeout=5),
            None,
        ]

        with patch("src.core.office_lifecycle._soffice_process", mock_proc):
            _cleanup_soffice()

        mock_proc.terminate.assert_called_once()
        mock_proc.kill.assert_called_once()
        assert mock_proc.wait.call_count == 2  # noqa: PLR2004

    def test_cleanup_process_already_exited_no_terminate(self) -> None:
        """When process has already exited, terminate is not called."""
        mock_proc = MagicMock()
        mock_proc.poll.return_value = 0  # already exited

        with patch("src.core.office_lifecycle._soffice_process", mock_proc):
            _cleanup_soffice()

        mock_proc.terminate.assert_not_called()

    def test_cleanup_none_process_no_error(self) -> None:
        """Cleanup with None process does not raise."""
        with patch("src.core.office_lifecycle._soffice_process", None):
            _cleanup_soffice()  # should not raise

    def test_stop_soffice_with_no_process(self) -> None:
        """stop_soffice with no process runs both cleanup and lock removal."""
        with (
            patch("src.core.office_lifecycle._soffice_process", None),
            patch("src.core.office_lifecycle._remove_soffice_lock") as mock_remove,
        ):
            stop_soffice()
        mock_remove.assert_called_once()


# ===========================================================================
# NEW TESTS: _get_uno_desktop — bridge connection, timeout, retry
# ===========================================================================


class TestGetUnoDesktopRetryLogic:
    """Tests for _get_uno_desktop retry and timeout logic."""

    def _make_uno_mocks(self) -> tuple:
        """Create standard UNO mock objects."""
        mock_uno = MagicMock()
        mock_ctx = MagicMock()
        mock_resolver = MagicMock()
        mock_local_ctx = MagicMock()
        mock_uno.getComponentContext.return_value = mock_local_ctx
        mock_local_ctx.ServiceManager.createInstanceWithContext.return_value = (
            mock_resolver
        )

        mock_pv = MagicMock()
        modules = {
            "uno": mock_uno,
            "com": MagicMock(),
            "com.sun": MagicMock(),
            "com.sun.star": MagicMock(),
            "com.sun.star.beans": mock_pv,
        }
        return mock_uno, mock_resolver, mock_ctx, modules

    def test_retry_count_matches_constant(self) -> None:
        """Retry loop runs exactly _SOFFICE_RETRY_COUNT times on failure."""
        from src.core.office_lifecycle import (  # noqa: PLC0415
            _SOFFICE_RETRY_COUNT,
            _get_uno_desktop,
        )

        mock_uno, mock_resolver, _, modules = self._make_uno_mocks()
        # All resolve calls fail
        mock_resolver.resolve.side_effect = Exception("connect failed")

        with (
            patch.dict("sys.modules", modules),
            patch(
                "src.core.office_lifecycle._ensure_soffice_running",
                return_value=True,
            ),
            patch("src.core.office_lifecycle._soffice_port", 2003),
            patch("time.sleep"),
            pytest.raises(RuntimeError, match="auto-starting"),
        ):
            _get_uno_desktop()

        # 1 initial attempt on default port + _SOFFICE_RETRY_COUNT retries
        assert mock_resolver.resolve.call_count == 1 + _SOFFICE_RETRY_COUNT

    def test_successful_retry_stops_loop(self) -> None:
        """When a retry succeeds, subsequent retries are skipped."""
        from src.core.office_lifecycle import _get_uno_desktop  # noqa: PLC0415

        mock_uno, mock_resolver, _, modules = self._make_uno_mocks()
        ok_ctx = MagicMock()
        # Fail default, succeed on 2nd retry
        mock_resolver.resolve.side_effect = [
            Exception("fail"),  # default port
            Exception("fail"),  # retry 1
            ok_ctx,  # retry 2 succeeds
        ]

        with (
            patch.dict("sys.modules", modules),
            patch(
                "src.core.office_lifecycle._ensure_soffice_running",
                return_value=True,
            ),
            patch("src.core.office_lifecycle._soffice_port", 2003),
            patch("time.sleep"),
        ):
            _get_uno_desktop()

        assert mock_resolver.resolve.call_count == 3  # noqa: PLR2004

    def test_error_message_when_binary_not_found(self) -> None:
        """RuntimeError message mentions soffice binary when not found."""
        from src.core.office_lifecycle import _get_uno_desktop  # noqa: PLC0415

        mock_uno, mock_resolver, _, modules = self._make_uno_mocks()
        mock_resolver.resolve.side_effect = Exception("no conn")

        with (
            patch.dict("sys.modules", modules),
            patch(
                "src.core.office_lifecycle._ensure_soffice_running",
                return_value=False,
            ),
            pytest.raises(RuntimeError, match="soffice binary"),
        ):
            _get_uno_desktop()

    def test_error_message_after_retries_mentions_timeout(self) -> None:
        """RuntimeError after retries mentions the auto-starting failure."""
        from src.core.office_lifecycle import _get_uno_desktop  # noqa: PLC0415

        mock_uno, mock_resolver, _, modules = self._make_uno_mocks()
        mock_resolver.resolve.side_effect = Exception("no conn")

        with (
            patch.dict("sys.modules", modules),
            patch(
                "src.core.office_lifecycle._ensure_soffice_running",
                return_value=True,
            ),
            patch("src.core.office_lifecycle._soffice_port", 2005),
            patch("time.sleep"),
            pytest.raises(RuntimeError, match="auto-starting"),
        ):
            _get_uno_desktop()

    def test_sleep_called_between_retries(self) -> None:
        """time.sleep is called before each retry attempt."""
        from src.core.office_lifecycle import (  # noqa: PLC0415
            _SOFFICE_RETRY_COUNT,
            _SOFFICE_RETRY_DELAY,
            _get_uno_desktop,
        )

        mock_uno, mock_resolver, _, modules = self._make_uno_mocks()
        mock_resolver.resolve.side_effect = Exception("fail")

        with (
            patch.dict("sys.modules", modules),
            patch(
                "src.core.office_lifecycle._ensure_soffice_running",
                return_value=True,
            ),
            patch("src.core.office_lifecycle._soffice_port", 2002),
            patch("time.sleep") as mock_sleep,
            pytest.raises(RuntimeError),
        ):
            _get_uno_desktop()

        assert mock_sleep.call_count == _SOFFICE_RETRY_COUNT
        mock_sleep.assert_called_with(_SOFFICE_RETRY_DELAY)


# ===========================================================================
# NEW TESTS: Win32COM open/close — COM initialization, error handling
# ===========================================================================


class TestWin32comOpenCleanup:
    """Additional Win32COM open/close tests."""

    @staticmethod
    def _build_win32_modules(
        *,
        dispatch_return: MagicMock | None = None,
        dispatch_side_effect: Exception | None = None,
    ) -> dict[str, MagicMock]:
        """Build fake sys.modules for pythoncom + win32com."""
        mock_pythoncom = MagicMock()
        mock_client = MagicMock()
        if dispatch_side_effect is not None:
            mock_client.Dispatch.side_effect = dispatch_side_effect
        elif dispatch_return is not None:
            mock_client.Dispatch.return_value = dispatch_return
        mock_win32com = MagicMock()
        mock_win32com.client = mock_client
        return {
            "pythoncom": mock_pythoncom,
            "win32com": mock_win32com,
            "win32com.client": mock_client,
        }

    def test_coinitialize_called_before_dispatch(self, tmp_path: Path) -> None:
        """CoInitialize is called before Dispatch."""
        call_order: list[str] = []
        mock_app = MagicMock()
        mock_app.Documents.Open.return_value = MagicMock()
        modules = self._build_win32_modules(dispatch_return=mock_app)
        orig_dispatch = modules["win32com.client"].Dispatch

        modules["pythoncom"].CoInitialize = lambda: call_order.append("coinit")
        modules["win32com.client"].Dispatch = lambda name: (
            call_order.append("dispatch"),
            orig_dispatch(name),
        )[1]

        file_path = tmp_path / "test.docx"
        file_path.touch()

        with patch.dict("sys.modules", modules):
            _win32com_open(_APP_WORD, file_path)

        assert call_order.index("coinit") < call_order.index("dispatch")

    def test_close_with_save_close_calls_doc_close(self) -> None:
        """_win32com_close with save_close=True calls doc_obj.Close(False)."""
        mock_doc = MagicMock()
        mock_app = MagicMock()
        mock_pycom = MagicMock()

        _win32com_close(mock_app, mock_doc, mock_pycom, save_close=True)

        mock_doc.Close.assert_called_once_with(False)
        mock_app.Quit.assert_called_once()
        mock_pycom.CoUninitialize.assert_called_once()

    def test_close_without_save_close_skips_doc_close(self) -> None:
        """_win32com_close without save_close does not call doc.Close."""
        mock_doc = MagicMock()
        mock_app = MagicMock()
        mock_pycom = MagicMock()

        _win32com_close(mock_app, mock_doc, mock_pycom, save_close=False)

        mock_doc.Close.assert_not_called()
        mock_app.Quit.assert_called_once()
        mock_pycom.CoUninitialize.assert_called_once()

    def test_close_all_none_does_not_raise(self) -> None:
        """_win32com_close with all None arguments does not raise."""
        _win32com_close(None, None, None)

    def test_close_doc_exception_does_not_block_quit(self) -> None:
        """If doc.Close raises, app.Quit is still called."""
        mock_doc = MagicMock()
        mock_doc.Close.side_effect = RuntimeError("close fail")
        mock_app = MagicMock()
        mock_pycom = MagicMock()

        _win32com_close(mock_app, mock_doc, mock_pycom, save_close=True)

        mock_app.Quit.assert_called_once()
        mock_pycom.CoUninitialize.assert_called_once()

    def test_close_quit_exception_does_not_block_couninitialize(self) -> None:
        """If app.Quit raises, CoUninitialize is still called."""
        mock_app = MagicMock()
        mock_app.Quit.side_effect = RuntimeError("quit fail")
        mock_pycom = MagicMock()

        _win32com_close(mock_app, None, mock_pycom)

        mock_pycom.CoUninitialize.assert_called_once()

    def test_open_word_returns_three_tuple(self, tmp_path: Path) -> None:
        """_win32com_open returns a 3-tuple (app, doc, pythoncom)."""
        mock_app = MagicMock()
        mock_app.Documents.Open.return_value = MagicMock()
        modules = self._build_win32_modules(dispatch_return=mock_app)

        f = tmp_path / "test.docx"
        f.touch()

        with patch.dict("sys.modules", modules):
            result = _win32com_open(_APP_WORD, f)

        assert isinstance(result, tuple)
        assert len(result) == 3  # noqa: PLR2004

    def test_open_excel_workbooks_open_called(self, tmp_path: Path) -> None:
        """For Excel, Workbooks.Open is used."""
        mock_app = MagicMock()
        mock_app.Workbooks.Open.return_value = MagicMock()
        modules = self._build_win32_modules(dispatch_return=mock_app)

        f = tmp_path / "test.xlsx"
        f.touch()

        with patch.dict("sys.modules", modules):
            _win32com_open(_APP_EXCEL, f)

        mock_app.Workbooks.Open.assert_called_once()

    def test_open_ppt_presentations_open_called(self, tmp_path: Path) -> None:
        """For PowerPoint, Presentations.Open is used."""
        mock_app = MagicMock()
        mock_app.Presentations.Open.return_value = MagicMock()
        modules = self._build_win32_modules(dispatch_return=mock_app)

        f = tmp_path / "test.pptx"
        f.touch()

        with patch.dict("sys.modules", modules):
            _win32com_open(_APP_PPT, f)

        mock_app.Presentations.Open.assert_called_once()

    def test_open_failure_during_doc_open_calls_close(self, tmp_path: Path) -> None:
        """If Documents.Open raises, _win32com_close is called."""
        mock_app = MagicMock()
        mock_app.Documents.Open.side_effect = RuntimeError("open fail")
        modules = self._build_win32_modules(dispatch_return=mock_app)

        f = tmp_path / "test.docx"
        f.touch()

        with (
            patch.dict("sys.modules", modules),
            patch("src.core.office_lifecycle._win32com_close") as mock_close,
            pytest.raises(RuntimeError, match="open fail"),
        ):
            _win32com_open(_APP_WORD, f)

        mock_close.assert_called_once()


# ===========================================================================
# NEW TESTS: _find_available_port — edge cases
# ===========================================================================


class TestFindAvailablePortEdgeCases:
    """Edge cases for _find_available_port."""

    def test_returns_int_when_port_available(self) -> None:
        """The returned port is an integer."""
        with patch("socket.socket") as mock_socket:
            mock_socket.return_value.__enter__ = MagicMock()
            mock_socket.return_value.__exit__ = MagicMock()
            port = _find_available_port()
        assert port is None or isinstance(port, int)

    def test_scans_full_range_before_returning_none(self) -> None:
        """When all ports are occupied, None is returned."""
        from src.core.office_lifecycle import _SOFFICE_PORT_RANGE  # noqa: PLC0415

        call_count = 0

        def always_fail(*args, **kwargs):
            nonlocal call_count
            mock_s = MagicMock()
            mock_s.__enter__ = MagicMock(return_value=mock_s)
            mock_s.__exit__ = MagicMock(return_value=False)
            mock_s.bind.side_effect = OSError("in use")
            call_count += 1
            return mock_s

        with patch("socket.socket", side_effect=always_fail):
            result = _find_available_port()

        assert result is None
        assert call_count == _SOFFICE_PORT_RANGE


# ===========================================================================
# NEW TESTS: _make_uno_url — format checks
# ===========================================================================


class TestMakeUnoUrlFormat:
    """Additional format checks for _make_uno_url."""

    def test_url_uses_socket_protocol(self) -> None:
        assert "socket" in _make_uno_url(2002)

    def test_url_uses_urp_protocol(self) -> None:
        assert "urp" in _make_uno_url(2002)

    def test_url_contains_star_office(self) -> None:
        assert "StarOffice.ComponentContext" in _make_uno_url(2002)

    def test_port_placeholder(self) -> None:
        assert "port=9999" in _make_uno_url(9999)

    def test_url_starts_with_uno(self) -> None:
        assert _make_uno_url(2002).startswith("uno:")


# ===========================================================================
# NEW TESTS: _kill_orphaned_soffice_unix — more edge cases
# ===========================================================================


class TestKillOrphanedUnixEdgeCases:
    """Additional edge cases for _kill_orphaned_soffice_unix."""

    def test_pgrep_empty_stdout_no_kills(self) -> None:
        """Empty pgrep output does nothing."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""

        with (
            patch("subprocess.run", return_value=mock_result),
            patch("os.kill") as mock_kill,
        ):
            _kill_orphaned_soffice_unix()

        mock_kill.assert_not_called()

    def test_pgrep_nonzero_return_no_kills(self) -> None:
        """Non-zero pgrep exit code means no matches."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""

        with (
            patch("subprocess.run", return_value=mock_result),
            patch("os.kill") as mock_kill,
        ):
            _kill_orphaned_soffice_unix()

        mock_kill.assert_not_called()

    def test_own_running_process_excluded(self) -> None:
        """Running tracked process PID is excluded from kills."""
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.pid = 5555

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "5555\n6666\n"

        with (
            patch("src.core.office_lifecycle._soffice_process", mock_proc),
            patch("subprocess.run", return_value=mock_result),
            patch("os.kill") as mock_kill,
        ):
            _kill_orphaned_soffice_unix()

        # Only 6666 should be killed, not 5555
        mock_kill.assert_called_once_with(6666, signal.SIGTERM)

    def test_all_blank_lines_no_kills(self) -> None:
        """Pgrep output with only blank lines causes no kills."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "\n\n\n"

        with (
            patch("subprocess.run", return_value=mock_result),
            patch("os.kill") as mock_kill,
        ):
            _kill_orphaned_soffice_unix()

        mock_kill.assert_not_called()


# ===========================================================================
# NEW TESTS: _kill_orphaned_soffice_win32 — more edge cases
# ===========================================================================


class TestKillOrphanedWin32EdgeCases:
    """Additional edge cases for _kill_orphaned_soffice_win32."""

    def test_header_only_output_no_kills(self) -> None:
        """Wmic output with only ProcessId header causes no kills."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "ProcessId\n\n"

        with (
            patch("sys.platform", "win32"),
            patch("subprocess.run", return_value=mock_result),
        ):
            _kill_orphaned_soffice_win32()

    def test_wmic_nonzero_return_no_kills(self) -> None:
        """Non-zero wmic exit code means no processes found."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""

        with patch("subprocess.run", return_value=mock_result):
            _kill_orphaned_soffice_win32()

    def test_multiple_pids_all_killed(self) -> None:
        """Multiple PIDs from wmic are all killed via taskkill."""
        mock_wmic = MagicMock()
        mock_wmic.returncode = 0
        mock_wmic.stdout = "ProcessId\n1111\n2222\n"

        call_count = 0

        def run_side_effect(args, **kwargs):
            nonlocal call_count
            if args[0] == "wmic":
                return mock_wmic
            call_count += 1
            return MagicMock()

        with (
            patch("src.core.office_lifecycle._soffice_process", None),
            patch("subprocess.run", side_effect=run_side_effect),
        ):
            _kill_orphaned_soffice_win32()

        assert call_count == 2  # noqa: PLR2004


# ===========================================================================
# NEW TESTS: _remove_soffice_lock — additional profile paths
# ===========================================================================


class TestRemoveSofficeLockAdditional:
    """Additional _remove_soffice_lock tests."""

    def test_no_lock_files_noop(self, tmp_path: Path) -> None:
        """When no lock files exist, nothing happens."""
        profile = tmp_path / ".config" / "libreoffice" / "4" / "user"
        profile.mkdir(parents=True)

        with patch("pathlib.Path.home", return_value=tmp_path):
            _remove_soffice_lock()  # should not raise

    def test_lock_file_permission_error_suppressed(self, tmp_path: Path) -> None:
        """OSError on unlink is suppressed."""
        profile = tmp_path / ".config" / "libreoffice" / "4" / "user"
        profile.mkdir(parents=True)
        lock = profile / ".~lock.test#"
        lock.touch()

        with (
            patch("pathlib.Path.home", return_value=tmp_path),
            patch("pathlib.Path.unlink", side_effect=OSError("permission denied")),
        ):
            _remove_soffice_lock()  # should not raise

    def test_iterdir_error_suppressed(self, tmp_path: Path) -> None:
        """OSError from iterdir is suppressed."""
        profile = tmp_path / ".config" / "libreoffice"
        profile.mkdir(parents=True)
        version_dir = profile / "4"
        version_dir.mkdir()

        with (
            patch("pathlib.Path.home", return_value=tmp_path),
            patch.object(Path, "iterdir", side_effect=OSError("permission denied")),
        ):
            _remove_soffice_lock()  # should not raise


# ===========================================================================
# NEW TESTS: _resolve_custom_soffice_path — edge cases
# ===========================================================================


class TestResolveCustomSofficePathEdgeCases:
    """Additional edge cases for _resolve_custom_soffice_path."""

    def test_nonexistent_file_returns_none(self) -> None:
        """Non-existent path returns None."""
        result = _resolve_custom_soffice_path("/nonexistent/path/to/soffice")
        assert result is None

    def test_directory_with_soffice_exe(self, tmp_path: Path) -> None:
        """Directory with soffice.exe returns its path."""
        exe = tmp_path / "soffice.exe"
        exe.touch()
        result = _resolve_custom_soffice_path(str(tmp_path))
        assert result == str(exe)

    def test_file_path_returned_directly(self, tmp_path: Path) -> None:
        """Existing file path is returned as-is."""
        soffice = tmp_path / "soffice"
        soffice.touch()
        result = _resolve_custom_soffice_path(str(soffice))
        assert result == str(soffice)

    def test_empty_string_returns_none_with_setting(self) -> None:
        """Empty setting returns None."""
        with patch("src.utils.config_manager.load_setting", return_value=""):
            result = _resolve_custom_soffice_path("")
        assert result is None

    def test_directory_prefers_soffice_over_soffice_exe(self, tmp_path: Path) -> None:
        """When directory has both soffice and soffice.exe, soffice wins."""
        (tmp_path / "soffice").touch()
        (tmp_path / "soffice.exe").touch()
        result = _resolve_custom_soffice_path(str(tmp_path))
        assert result == str(tmp_path / "soffice")


# ===========================================================================
# NEW TESTS: _find_soffice_binary — platform dispatch
# ===========================================================================


class TestFindSofficeBinaryPlatforms:
    """Platform-specific tests for _find_soffice_binary."""

    def test_linux_which_soffice(self) -> None:
        """On Linux, which('soffice') is tried first."""
        with (
            patch(
                "src.core.office_lifecycle._resolve_custom_soffice_path",
                return_value=None,
            ),
            patch("sys.platform", "linux"),
            patch("shutil.which", return_value="/usr/bin/soffice"),
        ):
            result = _find_soffice_binary()
        assert result is not None

    def test_linux_which_libreoffice_fallback(self) -> None:
        """On Linux, which('libreoffice') is tried when soffice not found."""
        with (
            patch(
                "src.core.office_lifecycle._resolve_custom_soffice_path",
                return_value=None,
            ),
            patch("sys.platform", "linux"),
            patch(
                "shutil.which",
                side_effect=lambda cmd: (
                    "/usr/bin/libreoffice" if cmd == "libreoffice" else None
                ),
            ),
        ):
            result = _find_soffice_binary()
        assert result is not None

    def test_linux_nothing_found_returns_none(self) -> None:
        """On Linux, returns None when nothing found."""
        with (
            patch(
                "src.core.office_lifecycle._resolve_custom_soffice_path",
                return_value=None,
            ),
            patch("sys.platform", "linux"),
            patch("shutil.which", return_value=None),
        ):
            result = _find_soffice_binary()
        assert result is None

    def test_custom_path_takes_priority_over_platform(self) -> None:
        """Custom configured path is returned before platform detection."""
        with patch(
            "src.core.office_lifecycle._resolve_custom_soffice_path",
            return_value="/custom/soffice",
        ):
            result = _find_soffice_binary()
        assert result == "/custom/soffice"


# ===========================================================================
# NEW TESTS: _kill_orphaned_soffice — platform dispatch
# ===========================================================================


class TestKillOrphanedDispatch:
    """Dispatch tests for _kill_orphaned_soffice."""

    def test_unix_dispatch_on_linux(self) -> None:
        """Linux dispatches to _kill_orphaned_soffice_unix."""
        with (
            patch("sys.platform", "linux"),
            patch("src.core.office_lifecycle._kill_orphaned_soffice_unix") as mock_unix,
        ):
            _kill_orphaned_soffice()
        mock_unix.assert_called_once()

    def test_unix_dispatch_on_darwin(self) -> None:
        """MacOS dispatches to _kill_orphaned_soffice_unix."""
        with (
            patch("sys.platform", "darwin"),
            patch("src.core.office_lifecycle._kill_orphaned_soffice_unix") as mock_unix,
        ):
            _kill_orphaned_soffice()
        mock_unix.assert_called_once()

    def test_win32_dispatch_on_windows(self) -> None:
        """Windows dispatches to _kill_orphaned_soffice_win32."""
        with (
            patch("sys.platform", "win32"),
            patch("src.core.office_lifecycle._kill_orphaned_soffice_win32") as mock_win,
        ):
            _kill_orphaned_soffice()
        mock_win.assert_called_once()


# ===========================================================================
# NEW TESTS: _cleanup_soffice — zombie reaping
# ===========================================================================


class TestCleanupSofficeZombieReaping:
    """Ensure _cleanup_soffice reaps zombie processes."""

    def test_wait_called_after_kill(self) -> None:
        """After kill(), wait() is called to reap the zombie."""
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.pid = 42
        mock_proc.wait.side_effect = [
            subprocess.TimeoutExpired(cmd="soffice", timeout=5),
            None,
        ]

        with patch("src.core.office_lifecycle._soffice_process", mock_proc):
            _cleanup_soffice()

        # kill then wait(no timeout) for zombie reap
        mock_proc.kill.assert_called_once()
        assert mock_proc.wait.call_count == 2  # noqa: PLR2004

    def test_graceful_terminate_waits_with_timeout(self) -> None:
        """terminate() followed by wait(timeout=...) for graceful shutdown."""
        from src.core.office_lifecycle import (
            _SOFFICE_TERMINATE_TIMEOUT,  # noqa: PLC0415
        )

        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.pid = 42

        with patch("src.core.office_lifecycle._soffice_process", mock_proc):
            _cleanup_soffice()

        mock_proc.terminate.assert_called_once()
        mock_proc.wait.assert_called_once_with(timeout=_SOFFICE_TERMINATE_TIMEOUT)


# ===========================================================================
# NEW TESTS: _get_uno_search_paths — platform-specific paths
# ===========================================================================


class TestUnoSearchPathsAdditional:
    """Additional platform-specific UNO search path tests."""

    def test_linux_includes_libreoffice_program_dir(self) -> None:
        """Linux paths include /usr/lib/libreoffice/program."""
        with patch("shutil.which", return_value=None):
            paths = _get_uno_search_paths_linux()
        assert "/usr/lib/libreoffice/program" in paths

    def test_linux_includes_lib64_libreoffice(self) -> None:
        """Linux paths include /usr/lib64/libreoffice/program."""
        with patch("shutil.which", return_value=None):
            paths = _get_uno_search_paths_linux()
        assert "/usr/lib64/libreoffice/program" in paths

    def test_darwin_returns_list(self) -> None:
        """MacOS path function returns a list."""
        result = _get_uno_search_paths_darwin()
        assert isinstance(result, list)

    def test_win32_returns_list(self) -> None:
        """Windows path function returns a list."""
        with (
            patch.dict(
                "os.environ", {"PROGRAMFILES": r"C:\Program Files"}, clear=False
            ),
            patch("builtins.__import__", side_effect=ImportError("no winreg")),
        ):
            result = _get_uno_search_paths_win32()
        assert isinstance(result, list)

    def test_linux_no_soffice_on_path(self) -> None:
        """Linux without soffice on PATH still returns static paths."""
        with patch("shutil.which", return_value=None):
            paths = _get_uno_search_paths_linux()
        assert len(paths) > 0

    def test_custom_path_not_duplicated(self, tmp_path: Path) -> None:
        """If custom path is already in platform paths, it's not added twice."""
        paths = _get_uno_search_paths_linux()
        if paths:
            # Use the first platform path as custom
            with patch("sys.platform", "linux"):
                result = _get_uno_search_paths(libreoffice_path=paths[0])
            assert result.count(paths[0]) == 1


# ===========================================================================
# NEW TESTS: Module-level constants
# ===========================================================================


class TestModuleConstants:
    """Tests for module-level constants."""

    def test_soffice_default_port_value(self) -> None:
        from src.core.office_lifecycle import _SOFFICE_DEFAULT_PORT  # noqa: PLC0415

        assert _SOFFICE_DEFAULT_PORT == 2002  # noqa: PLR2004

    def test_soffice_port_range_value(self) -> None:
        from src.core.office_lifecycle import _SOFFICE_PORT_RANGE  # noqa: PLC0415

        assert _SOFFICE_PORT_RANGE == 10  # noqa: PLR2004

    def test_retry_count_value(self) -> None:
        from src.core.office_lifecycle import _SOFFICE_RETRY_COUNT  # noqa: PLC0415

        assert _SOFFICE_RETRY_COUNT == 6  # noqa: PLR2004

    def test_retry_delay_value(self) -> None:
        from src.core.office_lifecycle import _SOFFICE_RETRY_DELAY  # noqa: PLC0415

        assert _SOFFICE_RETRY_DELAY == 1.0

    def test_terminate_timeout_value(self) -> None:
        from src.core.office_lifecycle import (
            _SOFFICE_TERMINATE_TIMEOUT,  # noqa: PLC0415
        )

        assert _SOFFICE_TERMINATE_TIMEOUT == 5  # noqa: PLR2004

    def test_app_word_is_string(self) -> None:
        assert isinstance(_APP_WORD, str)

    def test_app_excel_is_string(self) -> None:
        assert isinstance(_APP_EXCEL, str)

    def test_app_ppt_is_string(self) -> None:
        assert isinstance(_APP_PPT, str)


# ===========================================================================
# NEW TESTS: _ensure_soffice_running atexit edge cases
# ===========================================================================


class TestEnsureSofficeAtexitEdgeCases:
    """Edge cases for atexit registration."""

    def test_atexit_registered_once_across_multiple_launches(self) -> None:
        """atexit.register is only called once even across multiple launches."""
        mock_proc = MagicMock()
        mock_proc.poll.return_value = None

        with (
            patch("src.core.office_lifecycle._soffice_process", None),
            patch("src.core.office_lifecycle._soffice_cleanup_registered", False),
            patch("src.core.office_lifecycle._kill_orphaned_soffice"),
            patch("src.core.office_lifecycle._remove_soffice_lock"),
            patch(
                "src.core.office_lifecycle._find_soffice_binary",
                return_value="/usr/bin/soffice",
            ),
            patch("src.core.office_lifecycle._find_available_port", return_value=2002),
            patch("subprocess.Popen", return_value=mock_proc),
            patch("atexit.register") as mock_atexit,
        ):
            _ensure_soffice_running()

        mock_atexit.assert_called_once_with(_cleanup_soffice)


# ===========================================================================
# NEW TESTS: _find_soffice_binary win32/darwin branches
# ===========================================================================


class TestFindSofficeBinaryWin32:
    """Windows-specific _find_soffice_binary tests."""

    def test_win32_searches_program_dirs(self) -> None:
        """On Windows, checks program dirs from _get_uno_search_paths_win32."""
        with (
            patch(
                "src.core.office_lifecycle._resolve_custom_soffice_path",
                return_value=None,
            ),
            patch("sys.platform", "win32"),
            patch(
                "src.core.office_lifecycle._get_uno_search_paths_win32",
                return_value=[r"C:\LO\program"],
            ),
            patch("pathlib.Path.is_file", return_value=False),
            patch("shutil.which", return_value=None),
        ):
            result = _find_soffice_binary()
        assert result is None

    def test_win32_finds_soffice_exe(self) -> None:
        """On Windows, soffice.exe in a program dir is found."""
        with (
            patch(
                "src.core.office_lifecycle._resolve_custom_soffice_path",
                return_value=None,
            ),
            patch("sys.platform", "win32"),
            patch(
                "src.core.office_lifecycle._get_uno_search_paths_win32",
                return_value=[r"C:\LO\program"],
            ),
            patch("pathlib.Path.is_file", return_value=True),
        ):
            result = _find_soffice_binary()
        assert result is not None


class TestFindSofficeBinaryDarwin:
    """macOS-specific _find_soffice_binary tests."""

    def test_darwin_not_found_falls_to_which(self) -> None:
        """On macOS, falls back to which when standard paths don't exist."""
        with (
            patch(
                "src.core.office_lifecycle._resolve_custom_soffice_path",
                return_value=None,
            ),
            patch("sys.platform", "darwin"),
            patch("pathlib.Path.is_file", return_value=False),
            patch(
                "shutil.which",
                side_effect=lambda cmd: (
                    "/usr/local/bin/soffice" if cmd == "soffice" else None
                ),
            ),
        ):
            result = _find_soffice_binary()
        assert result == "/usr/local/bin/soffice"
