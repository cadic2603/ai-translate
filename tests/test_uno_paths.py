"""Unit tests for the UNO path discovery helpers in office_lifecycle."""

import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.core.office_lifecycle import (
    _cleanup_soffice,
    _ensure_soffice_running,
    _find_available_port,
    _find_soffice_binary,
    _get_uno_desktop,
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
    stop_soffice,
)
from src.core.office_processor import (
    _detect_backend,
)

# ---------------------------------------------------------------------------
# _get_uno_search_paths — dispatcher
# ---------------------------------------------------------------------------


def test_get_uno_search_paths_returns_list_of_strings() -> None:
    """_get_uno_search_paths() always returns a list of strings."""
    result = _get_uno_search_paths()
    assert isinstance(result, list)
    assert all(isinstance(p, str) for p in result)


def test_get_uno_search_paths_dispatches_by_platform() -> None:
    """_get_uno_search_paths() calls the correct platform helper."""
    with (
        patch("sys.platform", "win32"),
        patch(
            "src.core.office_lifecycle._get_uno_search_paths_win32",
            return_value=["WIN_PATH"],
        ) as mock_win,
    ):
        result = _get_uno_search_paths()
    mock_win.assert_called_once()
    assert result == ["WIN_PATH"]

    with (
        patch("sys.platform", "darwin"),
        patch(
            "src.core.office_lifecycle._get_uno_search_paths_darwin",
            return_value=["MAC_PATH"],
        ) as mock_mac,
    ):
        result = _get_uno_search_paths()
    mock_mac.assert_called_once()
    assert result == ["MAC_PATH"]

    with (
        patch("sys.platform", "linux"),
        patch(
            "src.core.office_lifecycle._get_uno_search_paths_linux",
            return_value=["LINUX_PATH"],
        ) as mock_linux,
    ):
        result = _get_uno_search_paths()
    mock_linux.assert_called_once()
    assert result == ["LINUX_PATH"]


# ---------------------------------------------------------------------------
# _get_uno_search_paths_linux
# ---------------------------------------------------------------------------


def test_get_uno_search_paths_linux_contains_expected_paths() -> None:
    """Linux paths include non-versioned, versioned, and program-dir entries."""
    result = _get_uno_search_paths_linux()
    pyver = f"{sys.version_info.major}.{sys.version_info.minor}"

    # Non-versioned Debian path
    assert "/usr/lib/python3/dist-packages" in result
    # Versioned site-packages path (Fedora / Arch / Alpine)
    assert f"/usr/lib/python{pyver}/site-packages" in result
    assert f"/usr/lib64/python{pyver}/site-packages" in result
    # LibreOffice program directory (Arch / Alpine / Gentoo)
    assert "/usr/lib/libreoffice/program" in result
    assert "/usr/lib64/libreoffice/program" in result


def test_get_uno_search_paths_linux_soffice_binary_appended() -> None:
    """Custom soffice program dir is appended when not already in candidates."""
    custom_program = "/opt/libreoffice/program"
    fake_soffice = f"{custom_program}/soffice"

    with (
        patch("shutil.which", return_value=fake_soffice),
        patch(
            "src.core.office_lifecycle.Path.resolve",
            return_value=Path(fake_soffice),
        ),
    ):
        result = _get_uno_search_paths_linux()

    assert custom_program in result


def test_get_uno_search_paths_linux_no_duplicate_from_soffice() -> None:
    """Program dir already in the static list is not duplicated by soffice."""
    # /usr/lib/libreoffice/program is already in the static list
    with (
        patch("shutil.which", return_value="/usr/bin/soffice"),
        patch(
            "src.core.office_lifecycle.Path.resolve",
            return_value=Path("/usr/lib/libreoffice/program/soffice"),
        ),
    ):
        result = _get_uno_search_paths_linux()

    assert result.count("/usr/lib/libreoffice/program") == 1  # noqa: PLR2004


def test_get_uno_search_paths_linux_no_soffice_on_path() -> None:
    """Missing soffice binary is handled gracefully — no crash."""
    with patch("shutil.which", return_value=None):
        result = _get_uno_search_paths_linux()

    assert isinstance(result, list)
    assert len(result) > 0


# ---------------------------------------------------------------------------
# _get_uno_search_paths_win32
# ---------------------------------------------------------------------------


def test_get_uno_search_paths_win32_contains_programfiles() -> None:
    """Windows paths include entries derived from PROGRAMFILES env vars."""
    env = {
        "PROGRAMFILES": r"C:\Program Files",
        "PROGRAMFILES(X86)": r"C:\Program Files (x86)",
    }
    with patch.dict("os.environ", env, clear=False):
        result = _get_uno_search_paths_win32()

    # Path separators differ by OS, so check component names independently
    assert any("LibreOffice" in p and "program" in p for p in result)
    assert any("Program Files" in p for p in result)


def test_get_uno_search_paths_win32_returns_list_of_strings() -> None:
    """Windows helper always returns a list of strings."""
    result = _get_uno_search_paths_win32()
    assert isinstance(result, list)
    assert all(isinstance(p, str) for p in result)


# ---------------------------------------------------------------------------
# _get_uno_search_paths_darwin
# ---------------------------------------------------------------------------


def test_get_uno_search_paths_darwin_no_app_bundle() -> None:
    """Returns empty list when LibreOffice.app is not installed."""
    with patch("src.core.office_lifecycle.Path.is_dir", return_value=False):
        result = _get_uno_search_paths_darwin()

    assert result == []


def test_get_uno_search_paths_darwin_with_app_bundle() -> None:
    """Returns Contents sub-dirs when LibreOffice.app exists."""
    app_contents = Path("/Applications/LibreOffice.app/Contents")

    def fake_is_dir(self: Path) -> bool:
        return str(self).startswith(str(app_contents))

    with (
        patch.object(Path, "is_dir", fake_is_dir),
        patch.object(Path, "glob", return_value=iter([])),
    ):
        result = _get_uno_search_paths_darwin()

    assert any("MacOS" in p for p in result)
    assert any("Frameworks" in p for p in result)
    assert any("Resources" in p for p in result)


def test_get_uno_search_paths_darwin_framework_glob_included() -> None:
    """Framework site-packages found via glob are included in candidates."""
    app_contents = Path("/Applications/LibreOffice.app/Contents")
    fw_ver = "Frameworks/LibreOfficePython.framework/Versions/3.10"
    fake_sp = app_contents / fw_ver / "lib/python3.10/site-packages"

    def fake_is_dir(self: Path) -> bool:
        return str(self).startswith(str(app_contents))

    with (
        patch.object(Path, "is_dir", fake_is_dir),
        patch.object(Path, "glob", return_value=iter([fake_sp])),
    ):
        result = _get_uno_search_paths_darwin()

    assert str(fake_sp) in result


def test_get_uno_search_paths_darwin_homebrew_intel() -> None:
    """Homebrew Intel path is included when present."""
    intel_root = Path("/usr/local/opt/libreoffice/LibreOffice.app/Contents")

    def fake_is_dir(self: Path) -> bool:
        return str(self).startswith(str(intel_root))

    with (
        patch.object(Path, "is_dir", fake_is_dir),
        patch.object(Path, "glob", return_value=iter([])),
    ):
        result = _get_uno_search_paths_darwin()

    assert any("/usr/local/opt/libreoffice/" in p for p in result)
    assert any("MacOS" in p for p in result)


def test_get_uno_search_paths_darwin_homebrew_apple_silicon() -> None:
    """Homebrew Apple Silicon path is included when present."""
    arm_root = Path("/opt/homebrew/opt/libreoffice/LibreOffice.app/Contents")

    def fake_is_dir(self: Path) -> bool:
        return str(self).startswith(str(arm_root))

    with (
        patch.object(Path, "is_dir", fake_is_dir),
        patch.object(Path, "glob", return_value=iter([])),
    ):
        result = _get_uno_search_paths_darwin()

    assert any("/opt/homebrew/opt/libreoffice/" in p for p in result)
    assert any("MacOS" in p for p in result)


def test_get_uno_search_paths_darwin_no_duplicates_across_roots() -> None:
    """When multiple roots exist, paths are not duplicated."""

    # Pretend all three roots exist
    def fake_is_dir(self: Path) -> bool:
        s = str(self)
        return (
            s.startswith("/Applications/LibreOffice.app/Contents")
            or s.startswith("/usr/local/opt/libreoffice/LibreOffice.app/Contents")
            or s.startswith("/opt/homebrew/opt/libreoffice/LibreOffice.app/Contents")
        )

    with (
        patch.object(Path, "is_dir", fake_is_dir),
        patch.object(Path, "glob", return_value=iter([])),
    ):
        result = _get_uno_search_paths_darwin()

    # All three MacOS paths should be present
    macos_paths = [p for p in result if "MacOS" in p]
    assert len(macos_paths) == 3  # noqa: PLR2004
    assert len(macos_paths) == len(set(macos_paths))


# ---------------------------------------------------------------------------
# _get_uno_search_paths_win32 — Registry lookup
# ---------------------------------------------------------------------------


def test_get_uno_search_paths_win32_registry_path_included() -> None:
    """Registry install path is included in candidates when winreg succeeds."""
    fake_winreg = MagicMock()
    fake_key = MagicMock()
    fake_key.__enter__ = lambda self: self
    fake_key.__exit__ = MagicMock(return_value=False)
    fake_winreg.OpenKey.return_value = fake_key
    fake_winreg.QueryValueEx.return_value = (r"C:\LibreOffice\program", 1)
    fake_winreg.HKEY_LOCAL_MACHINE = 0x80000002
    fake_winreg.HKEY_CURRENT_USER = 0x80000001

    with patch.dict("sys.modules", {"winreg": fake_winreg}):
        result = _get_uno_search_paths_win32()

    assert any("LibreOffice" in p for p in result)


def test_get_uno_search_paths_win32_registry_oserror_falls_through() -> None:
    """Registry OSError is caught — function still returns PROGRAMFILES paths."""
    fake_winreg = MagicMock()
    fake_winreg.OpenKey.side_effect = OSError("no key")
    fake_winreg.HKEY_LOCAL_MACHINE = 0x80000002
    fake_winreg.HKEY_CURRENT_USER = 0x80000001

    env = {"PROGRAMFILES": r"C:\Program Files"}
    with (
        patch.dict("sys.modules", {"winreg": fake_winreg}),
        patch.dict("os.environ", env, clear=False),
    ):
        result = _get_uno_search_paths_win32()

    assert any("Program Files" in p for p in result)


def test_get_uno_search_paths_win32_no_env_vars() -> None:
    """Returns a list (possibly empty) when PROGRAMFILES is unset."""
    fake_winreg = MagicMock()
    fake_winreg.OpenKey.side_effect = OSError("no key")
    fake_winreg.HKEY_LOCAL_MACHINE = 0x80000002
    fake_winreg.HKEY_CURRENT_USER = 0x80000001

    env_clear = {"PROGRAMFILES": "", "PROGRAMFILES(X86)": ""}
    with (
        patch.dict("sys.modules", {"winreg": fake_winreg}),
        patch.dict("os.environ", env_clear),
    ):
        result = _get_uno_search_paths_win32()

    assert isinstance(result, list)


# ---------------------------------------------------------------------------
# _detect_backend() — sys.path integration with _get_uno_search_paths()
# ---------------------------------------------------------------------------


def test_detect_backend_calls_get_uno_search_paths() -> None:
    """_detect_backend() calls _get_uno_search_paths() for UNO fallback.

    Uses an ODF format (.odt) because OOXML formats (.docx) return
    python_lib immediately without probing external backends.
    """
    # Disable win32com so we reach the UNO branch
    mods_to_remove = [k for k in sys.modules if k.startswith("win32com")]
    saved = {k: sys.modules.pop(k) for k in mods_to_remove}
    try:
        with (
            patch.dict(
                "sys.modules",
                {"win32com": None, "win32com.client": None, "uno": MagicMock()},
            ),
            patch(
                "src.core.office_processor._get_uno_search_paths",
                return_value=[],
            ) as mock_paths,
        ):
            _detect_backend(".odt")
        mock_paths.assert_called_once()
    finally:
        sys.modules.update(saved)


def test_detect_backend_appends_valid_paths_to_sys_path(tmp_path: Path) -> None:
    """_detect_backend() appends only existing directories from path list.

    Uses ODF format (.odt) because OOXML formats return python_lib
    immediately without probing UNO search paths.
    """
    # Create a real temporary directory to pass the is_dir() check
    real_dir = str(tmp_path / "uno_dir")
    Path(real_dir).mkdir()
    fake_dir = "/nonexistent_test_path_xyz_123"

    original_sys_path = sys.path.copy()
    mods_to_remove = [k for k in sys.modules if k.startswith("win32com")]
    saved = {k: sys.modules.pop(k) for k in mods_to_remove}
    try:
        with (
            patch.dict(
                "sys.modules",
                {"win32com": None, "win32com.client": None, "uno": MagicMock()},
            ),
            patch(
                "src.core.office_processor._get_uno_search_paths",
                return_value=[real_dir, fake_dir],
            ),
        ):
            _detect_backend(".odt")

        # Real dir should have been added
        assert real_dir in sys.path
        # Nonexistent dir should NOT have been added
        assert fake_dir not in sys.path
    finally:
        sys.modules.update(saved)
        # Restore sys.path to avoid test pollution
        sys.path[:] = original_sys_path


def test_detect_backend_skips_duplicate_sys_path_entries(
    tmp_path: Path,
) -> None:
    """_detect_backend() does not add a path that is already in sys.path.

    Uses ODF format (.odt) because OOXML formats return python_lib
    immediately without probing UNO search paths.
    """
    real_dir = str(tmp_path / "uno_dup")
    Path(real_dir).mkdir()

    original_sys_path = sys.path.copy()
    # Pre-add the path
    sys.path.append(real_dir)
    mods_to_remove = [k for k in sys.modules if k.startswith("win32com")]
    saved = {k: sys.modules.pop(k) for k in mods_to_remove}
    try:
        with (
            patch.dict(
                "sys.modules",
                {"win32com": None, "win32com.client": None, "uno": MagicMock()},
            ),
            patch(
                "src.core.office_processor._get_uno_search_paths",
                return_value=[real_dir],
            ),
        ):
            _detect_backend(".odt")

        # Should appear exactly once (no duplicate)
        assert sys.path.count(real_dir) == 1  # noqa: PLR2004
    finally:
        sys.modules.update(saved)
        sys.path[:] = original_sys_path


# ---------------------------------------------------------------------------
# _find_soffice_binary — cross-platform binary discovery
# ---------------------------------------------------------------------------


def test_find_soffice_binary_linux_finds_soffice() -> None:
    """Linux: resolves soffice via shutil.which and returns real path."""
    fake_bin = "/usr/bin/soffice"

    def _which_soffice(cmd: str) -> str | None:
        return fake_bin if cmd == "soffice" else None

    with (
        patch("sys.platform", "linux"),
        patch("shutil.which", side_effect=_which_soffice),
        patch.object(Path, "resolve", return_value=Path(fake_bin)),
    ):
        result = _find_soffice_binary()
    assert result == fake_bin


def test_find_soffice_binary_linux_falls_back_to_libreoffice() -> None:
    """Linux: uses libreoffice binary when soffice is absent from PATH."""
    fake_bin = "/usr/bin/libreoffice"

    def _which_libreoffice(cmd: str) -> str | None:
        return fake_bin if cmd == "libreoffice" else None

    with (
        patch("sys.platform", "linux"),
        patch("shutil.which", side_effect=_which_libreoffice),
        patch.object(Path, "resolve", return_value=Path(fake_bin)),
    ):
        result = _find_soffice_binary()
    assert result == fake_bin


def test_find_soffice_binary_linux_returns_none_when_not_found() -> None:
    """Linux: returns None when neither soffice nor libreoffice is on PATH."""
    with (
        patch("sys.platform", "linux"),
        patch("shutil.which", return_value=None),
    ):
        result = _find_soffice_binary()
    assert result is None


def test_find_soffice_binary_darwin_uses_app_bundle() -> None:
    """macOS: returns bundle binary path when LibreOffice.app is installed."""
    expected = "/Applications/LibreOffice.app/Contents/MacOS/soffice"
    with (
        patch("sys.platform", "darwin"),
        patch.object(Path, "is_file", return_value=True),
    ):
        result = _find_soffice_binary()
    assert result == expected


def test_find_soffice_binary_darwin_homebrew_intel() -> None:
    """macOS: returns Homebrew Intel path when standard bundle is absent."""
    intel_bin = "/usr/local/opt/libreoffice/LibreOffice.app/Contents/MacOS/soffice"

    def fake_is_file(self: Path) -> bool:
        return str(self) == intel_bin

    with (
        patch("sys.platform", "darwin"),
        patch.object(Path, "is_file", fake_is_file),
    ):
        result = _find_soffice_binary()
    assert result == intel_bin


def test_find_soffice_binary_darwin_homebrew_arm() -> None:
    """macOS: returns Homebrew Apple Silicon path when others are absent."""
    arm_bin = "/opt/homebrew/opt/libreoffice/LibreOffice.app/Contents/MacOS/soffice"

    def fake_is_file(self: Path) -> bool:
        return str(self) == arm_bin

    with (
        patch("sys.platform", "darwin"),
        patch.object(Path, "is_file", fake_is_file),
    ):
        result = _find_soffice_binary()
    assert result == arm_bin


def test_find_soffice_binary_darwin_falls_back_to_which() -> None:
    """macOS: shutil.which is used when all app bundles are absent."""
    fake_bin = "/usr/local/bin/soffice"
    with (
        patch("sys.platform", "darwin"),
        patch.object(Path, "is_file", return_value=False),
        patch("shutil.which", return_value=fake_bin),
    ):
        result = _find_soffice_binary()
    assert result == fake_bin


def test_find_soffice_binary_darwin_libreoffice_fallback() -> None:
    """macOS: libreoffice binary used when soffice is also absent."""
    fake_bin = "/opt/homebrew/bin/libreoffice"

    def _which_lo_only(cmd: str) -> str | None:
        return fake_bin if cmd == "libreoffice" else None

    with (
        patch("sys.platform", "darwin"),
        patch.object(Path, "is_file", return_value=False),
        patch("shutil.which", side_effect=_which_lo_only),
    ):
        result = _find_soffice_binary()
    assert result == fake_bin


def test_find_soffice_binary_darwin_returns_none_when_not_found() -> None:
    """macOS: returns None when bundle absent and PATH has no matching binary."""
    with (
        patch("sys.platform", "darwin"),
        patch.object(Path, "is_file", return_value=False),
        patch("shutil.which", return_value=None),
    ):
        result = _find_soffice_binary()
    assert result is None


def test_find_soffice_binary_win32_finds_exe_in_search_paths(tmp_path: Path) -> None:
    """Windows: returns soffice.exe path when found in a known program dir."""
    program_dir = tmp_path / "LibreOffice" / "program"
    program_dir.mkdir(parents=True)
    exe = program_dir / "soffice.exe"
    exe.touch()
    with (
        patch("sys.platform", "win32"),
        patch(
            "src.core.office_lifecycle._get_uno_search_paths_win32",
            return_value=[str(program_dir)],
        ),
    ):
        result = _find_soffice_binary()
    assert result == str(exe)


def test_find_soffice_binary_win32_falls_back_to_which() -> None:
    """Windows: shutil.which used when exe is not in any known program dir."""
    fake_bin = r"C:\Program Files\LibreOffice\program\soffice.exe"
    with (
        patch("sys.platform", "win32"),
        patch(
            "src.core.office_lifecycle._get_uno_search_paths_win32",
            return_value=[],
        ),
        patch("shutil.which", return_value=fake_bin),
    ):
        result = _find_soffice_binary()
    assert result == fake_bin


def test_find_soffice_binary_win32_returns_none_when_not_found() -> None:
    """Windows: returns None when exe not in search paths and not on PATH."""
    with (
        patch("sys.platform", "win32"),
        patch(
            "src.core.office_lifecycle._get_uno_search_paths_win32",
            return_value=[],
        ),
        patch("shutil.which", return_value=None),
    ):
        result = _find_soffice_binary()
    assert result is None


# ---------------------------------------------------------------------------
# _find_available_port — port scanning
# ---------------------------------------------------------------------------


def test_find_available_port_returns_first_free_port() -> None:
    """Returns the default port when it is available."""
    with patch("socket.socket") as mock_socket_cls:
        mock_sock = MagicMock()
        mock_socket_cls.return_value.__enter__ = lambda _: mock_sock
        mock_socket_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_sock.bind.return_value = None  # bind succeeds
        result = _find_available_port()
    from src.core.office_lifecycle import _SOFFICE_DEFAULT_PORT  # noqa: PLC0415

    assert result == _SOFFICE_DEFAULT_PORT


def test_find_available_port_skips_occupied_ports() -> None:
    """Skips ports that raise OSError and returns the next free one."""
    from src.core.office_lifecycle import _SOFFICE_DEFAULT_PORT  # noqa: PLC0415

    call_count = 0

    def _bind_side_effect(addr: tuple) -> None:
        nonlocal call_count
        call_count += 1
        # First two ports occupied, third is free
        if call_count <= 2:  # noqa: PLR2004
            raise OSError("Address already in use")

    with patch("socket.socket") as mock_socket_cls:
        mock_sock = MagicMock()
        mock_socket_cls.return_value.__enter__ = lambda _: mock_sock
        mock_socket_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_sock.bind.side_effect = _bind_side_effect
        result = _find_available_port()

    assert result == _SOFFICE_DEFAULT_PORT + 2  # noqa: PLR2004


def test_find_available_port_returns_none_when_all_occupied() -> None:
    """Returns None when every port in the range is occupied."""
    with patch("socket.socket") as mock_socket_cls:
        mock_sock = MagicMock()
        mock_socket_cls.return_value.__enter__ = lambda _: mock_sock
        mock_socket_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_sock.bind.side_effect = OSError("Address already in use")
        result = _find_available_port()
    assert result is None


# ---------------------------------------------------------------------------
# _make_uno_url — URL builder
# ---------------------------------------------------------------------------


def test_make_uno_url_contains_port() -> None:
    """_make_uno_url embeds the given port in the UNO resolver URL."""
    url = _make_uno_url(3456)  # noqa: PLR2004
    assert "port=3456" in url
    assert "StarOffice.ComponentContext" in url


# ---------------------------------------------------------------------------
# _cleanup_soffice — atexit handler
# ---------------------------------------------------------------------------


def test_cleanup_soffice_noop_when_process_is_none() -> None:
    """_cleanup_soffice is a no-op when no process has been launched."""
    with patch("src.core.office_lifecycle._soffice_process", None):
        _cleanup_soffice()  # must not raise


def test_cleanup_soffice_noop_when_process_already_exited() -> None:
    """_cleanup_soffice skips terminate() for a process that already exited."""
    mock_proc = MagicMock()
    mock_proc.poll.return_value = 0  # already exited
    with patch("src.core.office_lifecycle._soffice_process", mock_proc):
        _cleanup_soffice()
    mock_proc.terminate.assert_not_called()


def test_cleanup_soffice_terminates_running_process() -> None:
    """_cleanup_soffice gracefully terminates a live soffice process."""
    mock_proc = MagicMock()
    mock_proc.poll.return_value = None  # still running
    mock_proc.pid = 42
    with patch("src.core.office_lifecycle._soffice_process", mock_proc):
        _cleanup_soffice()
    mock_proc.terminate.assert_called_once()
    mock_proc.wait.assert_called_once_with(timeout=5)  # noqa: PLR2004


def test_cleanup_soffice_kills_on_timeout() -> None:
    """_cleanup_soffice escalates to kill() when graceful shutdown times out."""
    mock_proc = MagicMock()
    mock_proc.poll.return_value = None  # still running
    mock_proc.pid = 42
    # First .wait(timeout=5) raises TimeoutExpired; second .wait() after kill succeeds
    mock_proc.wait.side_effect = [
        subprocess.TimeoutExpired(cmd="soffice", timeout=5),
        None,
    ]
    with patch("src.core.office_lifecycle._soffice_process", mock_proc):
        _cleanup_soffice()
    mock_proc.kill.assert_called_once()
    # .wait() called after .kill() to reap the zombie process
    assert mock_proc.wait.call_count == 2  # noqa: PLR2004


# ---------------------------------------------------------------------------
# _ensure_soffice_running — lazy launcher
# ---------------------------------------------------------------------------


def test_ensure_soffice_running_returns_true_when_already_running() -> None:
    """Returns True immediately when a tracked soffice process is alive."""
    mock_proc = MagicMock()
    mock_proc.poll.return_value = None  # alive
    with patch("src.core.office_lifecycle._soffice_process", mock_proc):
        result = _ensure_soffice_running()
    assert result is True


def test_ensure_soffice_running_returns_false_when_binary_not_found() -> None:
    """Returns False when the soffice binary cannot be located."""
    with (
        patch("src.core.office_lifecycle._soffice_process", None),
        patch("src.core.office_lifecycle._find_soffice_binary", return_value=None),
    ):
        result = _ensure_soffice_running()
    assert result is False


def test_ensure_soffice_running_launches_process_and_returns_true() -> None:
    """Spawns soffice with the expected flags and returns True."""
    mock_proc = MagicMock()
    with (
        patch("src.core.office_lifecycle._soffice_process", None),
        patch("src.core.office_lifecycle._soffice_cleanup_registered", False),
        patch(
            "src.core.office_lifecycle._find_soffice_binary",
            return_value="/usr/bin/soffice",
        ),
        patch(
            "src.core.office_lifecycle._find_available_port",
            return_value=2005,  # noqa: PLR2004
        ),
        patch("subprocess.Popen", return_value=mock_proc) as mock_popen,
        patch("atexit.register") as mock_atexit,
    ):
        result = _ensure_soffice_running()

    assert result is True
    cmd = mock_popen.call_args[0][0]
    assert "--headless" in cmd
    assert "--norestore" in cmd
    # Port from _find_available_port appears in the accept string
    assert any("port=2005" in arg for arg in cmd)
    kwargs = mock_popen.call_args[1]
    assert kwargs["stdout"] == subprocess.DEVNULL
    assert kwargs["stderr"] == subprocess.DEVNULL
    mock_atexit.assert_called_once()


def test_ensure_soffice_running_returns_false_on_popen_failure() -> None:
    """Returns False when subprocess.Popen raises OSError."""
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
        patch("subprocess.Popen", side_effect=OSError("Permission denied")),
    ):
        result = _ensure_soffice_running()
    assert result is False


def test_ensure_soffice_running_returns_false_when_no_port() -> None:
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


def test_ensure_soffice_running_skips_atexit_when_already_registered() -> None:
    """Cleanup handler is not re-registered when atexit was already set up."""
    mock_proc = MagicMock()
    mock_proc.poll.return_value = 0  # exited, so re-launch is attempted
    with (
        patch("src.core.office_lifecycle._soffice_process", mock_proc),
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


# ---------------------------------------------------------------------------
# _get_uno_desktop — auto-start retry behaviour
# ---------------------------------------------------------------------------


def _build_uno_mocks(
    resolve_side_effect: list | None = None,
    resolve_return: object = None,
) -> tuple[MagicMock, MagicMock, dict]:
    """Return (mock_desktop, mock_resolver, fake_sys_modules) for UNO tests."""
    mock_desktop = MagicMock()
    mock_ctx = MagicMock()
    mock_smgr = MagicMock()
    mock_smgr.createInstanceWithContext.return_value = mock_desktop
    mock_ctx.ServiceManager = mock_smgr

    mock_resolver = MagicMock()
    if resolve_side_effect is not None:
        mock_resolver.resolve.side_effect = resolve_side_effect
    else:
        default = resolve_return if resolve_return is not None else mock_ctx
        mock_resolver.resolve.return_value = default

    mock_local_ctx = MagicMock()
    mock_local_ctx.ServiceManager.createInstanceWithContext.return_value = mock_resolver

    mock_uno = MagicMock()
    mock_uno.getComponentContext.return_value = mock_local_ctx

    fake_modules = {
        "uno": mock_uno,
        "com": MagicMock(),
        "com.sun": MagicMock(),
        "com.sun.star": MagicMock(),
        "com.sun.star.beans": MagicMock(),
    }
    return mock_desktop, mock_resolver, fake_modules


def test_get_uno_desktop_returns_desktop_on_first_connect() -> None:
    """Returns the Desktop service when the first resolver.resolve() succeeds."""
    mock_desktop, _, fake_modules = _build_uno_mocks()
    with patch.dict("sys.modules", fake_modules):
        result = _get_uno_desktop()
    assert result is mock_desktop


def test_get_uno_desktop_raises_when_binary_not_found() -> None:
    """Raises RuntimeError with install hint when soffice binary is absent."""
    _, _, fake_modules = _build_uno_mocks(
        resolve_side_effect=[Exception("connection refused")],
    )
    with (
        patch.dict("sys.modules", fake_modules),
        patch(
            "src.core.office_lifecycle._ensure_soffice_running",
            return_value=False,
        ),
        pytest.raises(RuntimeError, match="binary was not found"),
    ):
        _get_uno_desktop()


def test_get_uno_desktop_retries_and_succeeds_after_autostart() -> None:
    """Succeeds on a retry after soffice is auto-started."""
    # Build the ctx that will be returned on the successful retry
    mock_desktop = MagicMock()
    mock_ctx = MagicMock()
    mock_smgr = MagicMock()
    mock_smgr.createInstanceWithContext.return_value = mock_desktop
    mock_ctx.ServiceManager = mock_smgr

    _, _, fake_modules = _build_uno_mocks(
        resolve_side_effect=[
            Exception("not running"),  # initial attempt
            Exception("not yet"),  # retry 1
            mock_ctx,  # retry 2 — succeeds
        ],
    )
    with (
        patch.dict("sys.modules", fake_modules),
        patch("src.core.office_lifecycle._ensure_soffice_running", return_value=True),
        patch("src.core.office_lifecycle._soffice_port", 2005),
        patch("time.sleep"),
    ):
        result = _get_uno_desktop()
    assert result is mock_desktop


def test_get_uno_desktop_raises_after_all_retries_exhausted() -> None:
    """Raises RuntimeError after all retry attempts are exhausted."""
    from src.core.office_lifecycle import _SOFFICE_RETRY_COUNT  # noqa: PLC0415

    _, _, fake_modules = _build_uno_mocks(
        resolve_side_effect=Exception("connection refused"),
    )
    with (
        patch.dict("sys.modules", fake_modules),
        patch("src.core.office_lifecycle._ensure_soffice_running", return_value=True),
        patch("src.core.office_lifecycle._soffice_port", 2005),
        patch("time.sleep") as mock_sleep,
        pytest.raises(RuntimeError, match="auto-starting"),
    ):
        _get_uno_desktop()

    # Verify every retry was attempted (1 sleep per retry)
    assert mock_sleep.call_count == _SOFFICE_RETRY_COUNT


# ---------------------------------------------------------------------------
# process_office_file — RuntimeError → OFFICE_CONVERTER_NOT_FOUND
# ---------------------------------------------------------------------------


def test_process_office_file_maps_runtime_error_to_converter_not_found(
    tmp_path: Path,
) -> None:
    """RuntimeError from UNO extract raises OFFICE_CONVERTER_NOT_FOUND."""
    from src.core.office_processor import process_office_file  # noqa: PLC0415

    src_file = tmp_path / "test.docx"
    src_file.touch()
    out_file = tmp_path / "out.docx"

    with (
        patch(
            "src.core.office_processor._detect_backend",
            return_value="uno",
        ),
        patch(
            "src.core.office_processor._EXTRACTORS",
            {"uno": {"word": MagicMock(side_effect=RuntimeError("UNO failed"))}},
        ),
        pytest.raises(ValueError, match="OFFICE_CONVERTER_NOT_FOUND"),
    ):
        process_office_file(src_file, out_file, "English")


def test_process_office_file_inject_runtime_error_maps_to_converter_not_found(
    tmp_path: Path,
) -> None:
    """RuntimeError from UNO inject raises OFFICE_CONVERTER_NOT_FOUND, not TEXT_WRITE_ERROR."""  # noqa: E501
    from src.core.office_processor import process_office_file  # noqa: PLC0415

    src_file = tmp_path / "test.docx"
    src_file.touch()
    out_file = tmp_path / "out.docx"

    with (
        patch(
            "src.core.office_processor._detect_backend",
            return_value="uno",
        ),
        patch(
            "src.core.office_processor._EXTRACTORS",
            {"uno": {"word": MagicMock(return_value=[("k1", "Hello")])}},
        ),
        patch(
            "src.core.office_processor.translate_batch",
            return_value=["Hola"],
        ),
        patch(
            "src.core.office_processor._INJECTORS",
            {"uno": {"word": MagicMock(side_effect=RuntimeError("UNO inject failed"))}},
        ),
        pytest.raises(ValueError, match="OFFICE_CONVERTER_NOT_FOUND"),
    ):
        process_office_file(src_file, out_file, "English")


# ── _resolve_custom_soffice_path ──────────────────────────────────────


class TestResolveCustomSofficePath:
    """Tests for _resolve_custom_soffice_path."""

    def test_empty_string_loads_setting(self) -> None:
        """Empty path falls back to load_setting → returns None."""
        with patch(
            "src.utils.config_manager.load_setting",
            return_value="",
        ):
            assert _resolve_custom_soffice_path("") is None

    def test_file_path_returned(self, tmp_path: Path) -> None:
        """Existing file path is returned as-is."""
        soffice = tmp_path / "soffice"
        soffice.touch()
        assert _resolve_custom_soffice_path(str(soffice)) == str(soffice)

    def test_directory_finds_soffice(self, tmp_path: Path) -> None:
        """Directory containing soffice returns its full path."""
        soffice = tmp_path / "soffice"
        soffice.touch()
        result = _resolve_custom_soffice_path(str(tmp_path))
        assert result == str(soffice)

    def test_directory_without_soffice(self, tmp_path: Path) -> None:
        """Directory without soffice returns None."""
        assert _resolve_custom_soffice_path(str(tmp_path)) is None

    def test_nonexistent_path(self) -> None:
        """Non-existent path returns None."""
        assert _resolve_custom_soffice_path("/no/such/path") is None


# ── _remove_soffice_lock ──────────────────────────────────────────────


class TestRemoveSofficeLock:
    """Tests for _remove_soffice_lock."""

    def test_removes_lock_file(self, tmp_path: Path) -> None:
        """Lock file inside a libreoffice profile dir is removed."""
        profile = tmp_path / ".config" / "libreoffice" / "4" / "user"
        profile.mkdir(parents=True)
        lock = profile / ".~lock.localhost#"
        lock.touch()

        with patch(
            "src.core.office_lifecycle.Path.home",
            return_value=tmp_path,
        ):
            _remove_soffice_lock()

        assert not lock.exists()

    def test_no_profile_dir_no_crash(self, tmp_path: Path) -> None:
        """Missing profile directory doesn't crash."""
        with patch(
            "src.core.office_lifecycle.Path.home",
            return_value=tmp_path,
        ):
            _remove_soffice_lock()  # should not raise

    def test_unlink_oserror_suppressed(self, tmp_path: Path) -> None:
        """OSError on unlink is logged, not raised."""
        profile = tmp_path / ".config" / "libreoffice" / "4" / "user"
        profile.mkdir(parents=True)
        lock = profile / ".~lock.localhost#"
        lock.touch()

        with (
            patch(
                "src.core.office_lifecycle.Path.home",
                return_value=tmp_path,
            ),
            patch.object(
                Path,
                "unlink",
                side_effect=OSError("perm denied"),
            ),
        ):
            _remove_soffice_lock()  # should not raise

    def test_removes_macos_lock_file(self, tmp_path: Path) -> None:
        """Lock file in macOS Library/Application Support dir is removed."""
        profile = (
            tmp_path / "Library" / "Application Support" / "LibreOffice" / "4" / "user"
        )
        profile.mkdir(parents=True)
        lock = profile / ".~lock.localhost#"
        lock.touch()

        with patch(
            "src.core.office_lifecycle.Path.home",
            return_value=tmp_path,
        ):
            _remove_soffice_lock()

        assert not lock.exists()

    def test_removes_windows_appdata_lock_file(self, tmp_path: Path) -> None:
        """Lock file in Windows %APPDATA% dir is removed."""
        appdata = tmp_path / "AppData" / "Roaming"
        profile = appdata / "LibreOffice" / "4" / "user"
        profile.mkdir(parents=True)
        lock = profile / ".~lock.localhost#"
        lock.touch()

        with (
            patch(
                "src.core.office_lifecycle.Path.home",
                return_value=tmp_path,
            ),
            patch.dict(
                "os.environ",
                {"APPDATA": str(appdata)},
            ),
        ):
            _remove_soffice_lock()

        assert not lock.exists()

    def test_removes_flatpak_lock_file(self, tmp_path: Path) -> None:
        """Lock file in Flatpak config dir is removed."""
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
        lock = profile / ".~lock.localhost#"
        lock.touch()

        with patch(
            "src.core.office_lifecycle.Path.home",
            return_value=tmp_path,
        ):
            _remove_soffice_lock()

        assert not lock.exists()

    def test_removes_snap_lock_file(self, tmp_path: Path) -> None:
        """Lock file in Snap sandbox config dir is removed."""
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
        lock = profile / ".~lock.localhost#"
        lock.touch()

        with patch(
            "src.core.office_lifecycle.Path.home",
            return_value=tmp_path,
        ):
            _remove_soffice_lock()

        assert not lock.exists()

    def test_removes_dev_build_lock_file(self, tmp_path: Path) -> None:
        """Lock file in libreoffice-dev profile dir is removed."""
        profile = tmp_path / ".config" / "libreoffice-dev" / "4" / "user"
        profile.mkdir(parents=True)
        lock = profile / ".~lock.localhost#"
        lock.touch()

        with patch(
            "src.core.office_lifecycle.Path.home",
            return_value=tmp_path,
        ):
            _remove_soffice_lock()

        assert not lock.exists()

    def test_iterdir_oserror_suppressed(self, tmp_path: Path) -> None:
        """OSError from iterdir (race condition) is suppressed."""
        profile_root = tmp_path / ".config" / "libreoffice"
        profile_root.mkdir(parents=True)

        # Simulate race: directory exists at is_dir() but iterdir() fails
        orig_iterdir = Path.iterdir

        def _broken_iterdir(self: Path) -> list:
            if self == profile_root:
                raise OSError("directory vanished")
            return orig_iterdir(self)

        with (
            patch(
                "src.core.office_lifecycle.Path.home",
                return_value=tmp_path,
            ),
            patch.object(Path, "iterdir", _broken_iterdir),
        ):
            _remove_soffice_lock()  # should not raise


# ── _kill_orphaned_soffice ────────────────────────────────────────────


class TestKillOrphanedSoffice:
    """Tests for _kill_orphaned_soffice dispatcher and platform helpers."""

    def test_dispatches_to_unix_on_non_win32(self) -> None:
        """Non-Windows platforms use the unix helper."""
        with (
            patch("src.core.office_lifecycle.sys") as mock_sys,
            patch(
                "src.core.office_lifecycle._kill_orphaned_soffice_unix",
            ) as mock_unix,
            patch(
                "src.core.office_lifecycle._kill_orphaned_soffice_win32",
            ) as mock_win32,
        ):
            mock_sys.platform = "linux"
            _kill_orphaned_soffice()
            mock_unix.assert_called_once()
            mock_win32.assert_not_called()

    def test_dispatches_to_win32_on_windows(self) -> None:
        """Windows uses the win32 helper."""
        with (
            patch("src.core.office_lifecycle.sys") as mock_sys,
            patch(
                "src.core.office_lifecycle._kill_orphaned_soffice_unix",
            ) as mock_unix,
            patch(
                "src.core.office_lifecycle._kill_orphaned_soffice_win32",
            ) as mock_win32,
        ):
            mock_sys.platform = "win32"
            _kill_orphaned_soffice()
            mock_win32.assert_called_once()
            mock_unix.assert_not_called()


class TestKillOrphanedSofficeUnix:
    """Tests for _kill_orphaned_soffice_unix."""

    def test_no_orphans(self) -> None:
        """Pgrep returns empty → no kills."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""

        with patch(
            "src.core.office_lifecycle.subprocess.run",
            return_value=mock_result,
        ):
            _kill_orphaned_soffice_unix()  # should not raise

    def test_kills_orphan_pid(self) -> None:
        """Orphan PID is killed with SIGTERM."""
        import signal  # noqa: PLC0415

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "12345\n"

        with (
            patch(
                "src.core.office_lifecycle.subprocess.run",
                return_value=mock_result,
            ),
            patch("src.core.office_lifecycle.os.kill") as mock_kill,
            patch(
                "src.core.office_lifecycle._soffice_process",
                None,
            ),
        ):
            _kill_orphaned_soffice_unix()
            mock_kill.assert_called_once_with(
                12345,
                signal.SIGTERM,  # noqa: PLR2004
            )

    def test_skips_own_tracked_process(self) -> None:
        """Our own tracked soffice PID is not killed."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "99999\n"

        mock_proc = MagicMock()
        mock_proc.poll.return_value = None  # still running
        mock_proc.pid = 99999  # noqa: PLR2004

        with (
            patch(
                "src.core.office_lifecycle.subprocess.run",
                return_value=mock_result,
            ),
            patch("src.core.office_lifecycle.os.kill") as mock_kill,
            patch(
                "src.core.office_lifecycle._soffice_process",
                mock_proc,
            ),
        ):
            _kill_orphaned_soffice_unix()
            mock_kill.assert_not_called()

    def test_oserror_on_kill_suppressed(self) -> None:
        """OSError when killing a PID is suppressed."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "12345\n"

        with (
            patch(
                "src.core.office_lifecycle.subprocess.run",
                return_value=mock_result,
            ),
            patch(
                "src.core.office_lifecycle.os.kill",
                side_effect=OSError("no such process"),
            ),
            patch("src.core.office_lifecycle._soffice_process", None),
        ):
            _kill_orphaned_soffice_unix()  # should not raise

    def test_pgrep_timeout_suppressed(self) -> None:
        """Subprocess.TimeoutExpired is suppressed."""
        with patch(
            "src.core.office_lifecycle.subprocess.run",
            side_effect=subprocess.TimeoutExpired("pgrep", 5),
        ):
            _kill_orphaned_soffice_unix()  # should not raise

    def test_non_numeric_pgrep_lines_skipped(self) -> None:
        """Non-numeric lines in pgrep output are silently skipped."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "WARNING: something\n12345\n\n"

        with (
            patch(
                "src.core.office_lifecycle.subprocess.run",
                return_value=mock_result,
            ),
            patch("src.core.office_lifecycle.os.kill") as mock_kill,
            patch("src.core.office_lifecycle._soffice_process", None),
        ):
            _kill_orphaned_soffice_unix()
            # Only the valid PID is killed, non-numeric lines skipped
            mock_kill.assert_called_once()


class TestKillOrphanedSofficeWin32:
    """Tests for _kill_orphaned_soffice_win32."""

    def test_no_orphans(self) -> None:
        """Wmic returns empty → no kills."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""

        with patch(
            "src.core.office_lifecycle.subprocess.run",
            return_value=mock_result,
        ):
            _kill_orphaned_soffice_win32()  # should not raise

    def test_kills_orphan_pid(self) -> None:
        """Orphan PID is killed via taskkill."""
        # wmic output: header line then PID values
        wmic_result = MagicMock()
        wmic_result.returncode = 0
        wmic_result.stdout = "ProcessId  \n12345      \n\n"

        call_count = 0

        def fake_run(cmd: list, **_kwargs: object) -> MagicMock:
            nonlocal call_count
            call_count += 1
            if cmd[0] == "wmic":
                return wmic_result
            return MagicMock(returncode=0)

        with (
            patch(
                "src.core.office_lifecycle.subprocess.run",
                side_effect=fake_run,
            ),
            patch("src.core.office_lifecycle._soffice_process", None),
        ):
            _kill_orphaned_soffice_win32()

        # wmic + taskkill = 2 calls
        assert call_count == 2  # noqa: PLR2004

    def test_skips_own_tracked_process(self) -> None:
        """Our own tracked soffice PID is not killed."""
        wmic_result = MagicMock()
        wmic_result.returncode = 0
        wmic_result.stdout = "ProcessId  \n99999      \n\n"

        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.pid = 99999  # noqa: PLR2004

        calls: list[list] = []

        def fake_run(cmd: list, **_kwargs: object) -> MagicMock:
            calls.append(cmd)
            if cmd[0] == "wmic":
                return wmic_result
            return MagicMock(returncode=0)

        with (
            patch(
                "src.core.office_lifecycle.subprocess.run",
                side_effect=fake_run,
            ),
            patch("src.core.office_lifecycle._soffice_process", mock_proc),
        ):
            _kill_orphaned_soffice_win32()

        # Only wmic should be called (no taskkill for own process)
        assert all(c[0] == "wmic" for c in calls)

    def test_wmic_timeout_suppressed(self) -> None:
        """Subprocess.TimeoutExpired is suppressed."""
        with patch(
            "src.core.office_lifecycle.subprocess.run",
            side_effect=subprocess.TimeoutExpired("wmic", 10),
        ):
            _kill_orphaned_soffice_win32()  # should not raise

    def test_wmic_not_found_suppressed(self) -> None:
        """FileNotFoundError (wmic removed on newer Windows 11) is suppressed."""
        with patch(
            "src.core.office_lifecycle.subprocess.run",
            side_effect=FileNotFoundError("wmic not found"),
        ):
            _kill_orphaned_soffice_win32()  # should not raise

    def test_kills_multiple_orphan_pids(self) -> None:
        """Multiple orphaned PIDs are all killed."""
        wmic_result = MagicMock()
        wmic_result.returncode = 0
        wmic_result.stdout = "ProcessId  \n12345      \n54321      \n\n"

        killed_pids: list[int] = []

        def fake_run(cmd: list, **_kwargs: object) -> MagicMock:
            if cmd[0] == "wmic":
                return wmic_result
            if cmd[0] == "taskkill":
                killed_pids.append(int(cmd[2]))
            return MagicMock(returncode=0)

        with (
            patch(
                "src.core.office_lifecycle.subprocess.run",
                side_effect=fake_run,
            ),
            patch("src.core.office_lifecycle._soffice_process", None),
        ):
            _kill_orphaned_soffice_win32()

        assert sorted(killed_pids) == [12345, 54321]  # noqa: PLR2004

    def test_non_numeric_lines_skipped(self) -> None:
        """Header and blank lines in wmic output are skipped."""
        wmic_result = MagicMock()
        wmic_result.returncode = 0
        wmic_result.stdout = "ProcessId  \n\n"

        with (
            patch(
                "src.core.office_lifecycle.subprocess.run",
                return_value=wmic_result,
            ),
            patch("src.core.office_lifecycle._soffice_process", None),
        ):
            _kill_orphaned_soffice_win32()  # should not raise, no taskkill


# ── stop_soffice ──────────────────────────────────────────────────────


class TestStopSoffice:
    """Tests for stop_soffice public API."""

    def test_calls_cleanup_and_remove_lock(self) -> None:
        """Delegates to _cleanup_soffice and _remove_soffice_lock."""
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

    def test_idempotent(self) -> None:
        """Can be called multiple times without error."""
        with (
            patch("src.core.office_lifecycle._cleanup_soffice"),
            patch("src.core.office_lifecycle._remove_soffice_lock"),
        ):
            stop_soffice()
            stop_soffice()  # second call should not raise
