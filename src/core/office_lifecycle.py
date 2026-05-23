"""LibreOffice soffice process management, UNO bridge setup, and Win32COM lifecycle.

Extracted from ``office_processor.py`` to keep the main module focused on
document-level extract/translate/inject logic.

Dependency rule: this module only imports stdlib, lazy win32com/uno, and
``config_manager`` — it does NOT import ``office_processor``.
"""

import atexit
import logging
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

logger = logging.getLogger("office_lifecycle")

# Application identifiers used by win32com.client.Dispatch
_APP_WORD = "Word.Application"
_APP_EXCEL = "Excel.Application"
_APP_PPT = "PowerPoint.Application"

# Auto-started soffice process (lazy-launched by _ensure_soffice_running)
_soffice_process: subprocess.Popen | None = None
_soffice_cleanup_registered: bool = False
_soffice_port: int = 0  # actual port used by the auto-started instance

# Retry settings for waiting on soffice listener startup
_SOFFICE_RETRY_COUNT = 6
_SOFFICE_RETRY_DELAY = 1.0  # seconds between retries
_SOFFICE_TERMINATE_TIMEOUT = 5  # seconds to wait for graceful shutdown

# Port range for soffice listener
_SOFFICE_DEFAULT_PORT = 2002
_SOFFICE_PORT_RANGE = 10  # try ports 2002–2011


# ---------------------------------------------------------------------------
# UNO path discovery
# ---------------------------------------------------------------------------


def _get_uno_search_paths(libreoffice_path: str = "") -> list[str]:
    """Returns platform-specific candidate paths for the LibreOffice UNO module.

    pyenv / virtualenv isolate from system site-packages, so the ``uno``
    module installed by LibreOffice (or python3-uno) is invisible.  This
    function returns the directories that should be appended to
    ``sys.path`` before attempting ``import uno``.

    Args:
        libreoffice_path: User-configured LibreOffice directory; when
            empty, falls back to load_setting().

    Platform notes
    --------------
    * **Windows** (8.1+, required by Python 3.12): queries the Windows
      Registry first (``SOFTWARE/LibreOffice/UNO/InstallPath``), then
      falls back to standard ``PROGRAMFILES`` env-var paths.
    * **macOS**: scans ``/Applications/LibreOffice.app/Contents/`` —
      ``MacOS`` (program dir), ``Frameworks`` (``pyuno.so``),
      ``Resources``, and the version-varying
      ``LibreOfficePython.framework`` site-packages.
    * **Linux**: covers Debian/Ubuntu ``dist-packages``,
      Fedora/openSUSE ``site-packages``, and Arch/Snap/Flatpak
      ``libreoffice/program`` directories for both lib and lib64.
    """
    if sys.platform == "win32":
        paths = _get_uno_search_paths_win32()
    elif sys.platform == "darwin":
        paths = _get_uno_search_paths_darwin()
    else:
        paths = _get_uno_search_paths_linux()

    # Prepend user-configured LibreOffice directory for priority discovery
    if not libreoffice_path:
        from src.constants.settings import SETTING_LIBREOFFICE_PATH  # noqa: PLC0415
        from src.utils.config_manager import load_setting  # noqa: PLC0415

        libreoffice_path = load_setting(SETTING_LIBREOFFICE_PATH, "")

    if libreoffice_path:
        custom_dir = Path(libreoffice_path)
        if custom_dir.is_file():
            custom_dir = custom_dir.parent
        custom_str = str(custom_dir)
        if custom_dir.is_dir() and custom_str not in paths:
            paths.insert(0, custom_str)

    return paths


def _get_uno_search_paths_win32() -> list[str]:
    """Windows-specific UNO path discovery.

    1. Queries the Windows Registry for the LibreOffice install path
       (handles custom install locations and all Windows locales).
    2. Falls back to standard ``PROGRAMFILES`` env-var based paths.
    """
    candidates: list[str] = []

    # --- Registry lookup (most reliable) ---
    try:
        import winreg  # noqa: PLC0415

        for reg_key in (
            r"SOFTWARE\LibreOffice\UNO\InstallPath",
            r"SOFTWARE\OpenOffice.org\UNO\InstallPath",
        ):
            for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
                try:
                    with winreg.OpenKey(hive, reg_key) as key:
                        install_path, _ = winreg.QueryValueEx(key, "")
                        if install_path:
                            candidates.append(install_path)
                except OSError:
                    pass
    except ImportError:
        pass  # Should never happen on Windows, but stay defensive

    # --- Env-var fallback ---
    for env_var in ("PROGRAMFILES", "PROGRAMFILES(X86)"):
        pf = os.environ.get(env_var)
        if pf:
            candidates.append(str(Path(pf) / "LibreOffice" / "program"))

    return candidates


def _get_uno_search_paths_darwin() -> list[str]:
    """macOS-specific UNO path discovery.

    LibreOffice bundles its own Python + UNO inside the ``.app`` bundle.
    ``pyuno.so`` is in ``Contents/Frameworks``, ``uno.py`` may live in
    ``Contents/MacOS``, ``Contents/Resources``, or the embedded
    ``LibreOfficePython.framework`` site-packages (version varies).

    Also checks Homebrew ``Cellar`` paths for both Intel
    (``/usr/local/opt/libreoffice``) and Apple Silicon
    (``/opt/homebrew/opt/libreoffice``).
    """
    candidates: list[str] = []

    # Standard .app bundle location + Homebrew Cellar symlinks
    app_roots = [
        Path("/Applications/LibreOffice.app/Contents"),
        Path("/usr/local/opt/libreoffice/LibreOffice.app/Contents"),  # Intel
        Path("/opt/homebrew/opt/libreoffice/LibreOffice.app/Contents"),  # Apple Silicon
    ]

    for app in app_roots:
        if not app.is_dir():
            continue

        # Fixed sub-directories that may contain uno.py or pyuno.so
        for sub in ("MacOS", "Frameworks", "Resources"):
            d = app / sub
            if d.is_dir() and str(d) not in candidates:
                candidates.append(str(d))

        # uno.py may be in the framework's version-specific site-packages
        fw = app / "Frameworks"
        for sp in fw.glob(
            "LibreOfficePython.framework/Versions/*/lib/python*/site-packages"
        ):
            if str(sp) not in candidates:
                candidates.append(str(sp))

    return candidates


def _get_uno_search_paths_linux() -> list[str]:
    """Linux-specific UNO path discovery.

    Covers the major distro families with a combination of:

    * **Static well-known paths** — both non-versioned (Debian/Ubuntu)
      and version-specific (Fedora, Arch, Alpine, openSUSE).  Distros
      install ``uno.py`` either in Python ``site-packages`` /
      ``dist-packages`` or in the LibreOffice ``program/`` directory.
    * **Dynamic ``soffice`` binary resolution** — ``/usr/bin/soffice``
      is almost always a symlink into the LibreOffice ``program/``
      directory.  Resolving it catches custom installs, NixOS (when
      ``soffice`` is on ``PATH``), and any distro not covered by the
      static list.
    """
    pyver = f"{sys.version_info.major}.{sys.version_info.minor}"
    candidates = [
        # Non-versioned paths
        "/usr/lib/python3/dist-packages",  # Debian / Ubuntu
        "/usr/lib/python3/site-packages",  # openSUSE / Arch
        "/usr/lib64/python3/dist-packages",  # (64-bit variants)
        "/usr/lib64/python3/site-packages",
        # Version-specific paths (Fedora, Arch, Alpine, Docker)
        f"/usr/lib/python{pyver}/site-packages",
        f"/usr/lib64/python{pyver}/site-packages",
        f"/usr/lib/python{pyver}/dist-packages",
        f"/usr/lib64/python{pyver}/dist-packages",
        # LibreOffice program directory (Gentoo, Alpine, Snap, Flatpak)
        "/usr/lib/libreoffice/program",
        "/usr/lib64/libreoffice/program",
    ]

    # Dynamic: resolve the soffice binary to find the program directory.
    # /usr/bin/soffice → ../lib[64]/libreoffice/program/soffice (symlink)
    for cmd in ("soffice", "libreoffice"):
        bin_path = shutil.which(cmd)
        if bin_path:
            program_dir = str(Path(bin_path).resolve().parent)
            if program_dir not in candidates:
                candidates.append(program_dir)
            break

    return candidates


# ---------------------------------------------------------------------------
# Auto-start soffice headless server
# ---------------------------------------------------------------------------


def _resolve_custom_soffice_path(libreoffice_path: str = "") -> str | None:
    """Resolves the user-configured LibreOffice path from Settings.

    Handles both file and directory paths. If the user pointed to a
    directory, searches for ``soffice`` / ``soffice.exe`` inside it.

    Args:
        libreoffice_path: User-configured LibreOffice path; when empty,
            falls back to load_setting().

    Returns:
        Absolute path to the soffice binary, or None if not configured
        or the configured path is invalid.
    """
    if not libreoffice_path:
        from src.constants.settings import SETTING_LIBREOFFICE_PATH  # noqa: PLC0415
        from src.utils.config_manager import load_setting  # noqa: PLC0415

        libreoffice_path = load_setting(SETTING_LIBREOFFICE_PATH, "")

    custom = libreoffice_path
    if not custom:
        return None

    p = Path(custom)
    if p.is_file():
        return str(p)
    # User may have pointed to a directory — try finding soffice inside
    if p.is_dir():
        for name in ("soffice", "soffice.exe"):
            candidate = p / name
            if candidate.is_file():
                return str(candidate)
    return None


def _find_soffice_binary() -> str | None:  # noqa: PLR0911
    """Discovers the soffice executable path on the current platform.

    Checks the user-configured LibreOffice path first (from Settings),
    then falls back to platform-specific auto-detection.

    Returns:
        Absolute path to the soffice binary, or None if not found.
    """
    # Check user-configured custom path first
    result = _resolve_custom_soffice_path()
    if result:
        return result

    if sys.platform == "win32":
        # Check known Windows install paths from UNO search
        for program_dir in _get_uno_search_paths_win32():
            exe = Path(program_dir) / "soffice.exe"
            if exe.is_file():
                return str(exe)
        return shutil.which("soffice")

    if sys.platform == "darwin":
        # Standard macOS bundle + Homebrew (Intel & Apple Silicon)
        for mac_bin in (
            Path("/Applications/LibreOffice.app/Contents/MacOS/soffice"),
            Path("/usr/local/opt/libreoffice/LibreOffice.app/Contents/MacOS/soffice"),
            Path(
                "/opt/homebrew/opt/libreoffice/LibreOffice.app/Contents/MacOS/soffice"
            ),
        ):
            if mac_bin.is_file():
                return str(mac_bin)
        return shutil.which("soffice") or shutil.which("libreoffice")

    # Linux — same strategy as _get_uno_search_paths_linux
    for cmd in ("soffice", "libreoffice"):
        bin_path = shutil.which(cmd)
        if bin_path:
            return str(Path(bin_path).resolve())

    return None


def _find_available_port() -> int | None:
    """Finds the first available TCP port in the soffice port range.

    Scans ``_SOFFICE_DEFAULT_PORT`` through
    ``_SOFFICE_DEFAULT_PORT + _SOFFICE_PORT_RANGE - 1`` and returns
    the first port that can be bound.

    Returns:
        An available port number, or None if every port is occupied.
    """
    end = _SOFFICE_DEFAULT_PORT + _SOFFICE_PORT_RANGE
    for port in range(_SOFFICE_DEFAULT_PORT, end):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("localhost", port))
                return port
        except OSError:
            continue
    return None


def _cleanup_soffice() -> None:
    """Terminates the auto-started soffice process (atexit handler)."""
    global _soffice_process  # noqa: PLW0603
    if _soffice_process is None or _soffice_process.poll() is not None:
        _soffice_process = None
        return

    logger.debug("Terminating auto-started soffice (pid=%d)", _soffice_process.pid)
    _soffice_process.terminate()
    try:
        _soffice_process.wait(timeout=_SOFFICE_TERMINATE_TIMEOUT)
    except subprocess.TimeoutExpired:
        logger.warning("soffice did not exit gracefully; killing")
        _soffice_process.kill()
        _soffice_process.wait()  # Reap zombie to release lock files
    _soffice_process = None


def _remove_soffice_lock() -> None:
    """Removes stale LibreOffice user-profile lock files left by SIGKILL.

    LibreOffice writes a ``.~lock.localhost#`` file in its user profile
    directory.  When soffice is forcefully killed the lock is not deleted,
    which prevents the GUI from opening.
    """
    home = Path.home()
    # Common LibreOffice profile directories across distros / versions / OSes
    profile_roots = [
        home / ".config" / "libreoffice",  # Linux (most distros)
        home / ".config" / "libreoffice-dev",  # Dev builds
        home / "snap" / "libreoffice" / "current" / ".config" / "libreoffice",
        home
        / ".var"
        / "app"
        / "org.libreoffice.LibreOffice"
        / "config"
        / "libreoffice",  # Flatpak
        home / "Library" / "Application Support" / "LibreOffice",  # macOS
    ]
    # Windows: profile is in %APPDATA%\LibreOffice (not under home)
    appdata = os.environ.get("APPDATA")
    if appdata:
        profile_roots.append(Path(appdata) / "LibreOffice")
    for root in profile_roots:
        if not root.is_dir():
            continue
        # Profile version dirs: "4", "24.2", etc.
        try:
            children = list(root.iterdir())
        except OSError:
            continue
        for version_dir in children:
            user_dir = version_dir / "user"
            if not user_dir.is_dir():
                continue
            for lock_file in user_dir.glob(".~lock.*"):
                try:
                    lock_file.unlink()
                    logger.debug("Removed stale LibreOffice lock: %s", lock_file)
                except OSError as e:
                    logger.debug("Could not remove lock %s: %s", lock_file, e)


def stop_soffice() -> None:
    """Stops the auto-started soffice process if it is running.

    Call this after all UNO operations are complete so the user can open
    files with the LibreOffice GUI (LibreOffice only allows one instance
    per user profile).
    """
    _cleanup_soffice()
    _remove_soffice_lock()


def _kill_orphaned_soffice() -> None:
    """Kills orphaned soffice headless processes from previous sessions.

    When the app crashes or exits without calling ``stop_soffice()``,
    the headless soffice process keeps running and blocks the LibreOffice
    GUI (only one instance per user profile is allowed).

    Uses ``pgrep`` on Unix (Linux / macOS) and ``tasklist`` on Windows.
    """
    if sys.platform == "win32":
        _kill_orphaned_soffice_win32()
    else:
        _kill_orphaned_soffice_unix()


def _kill_orphaned_soffice_unix() -> None:
    """Kills orphaned soffice headless processes on Linux / macOS."""
    import signal  # noqa: PLC0415

    try:
        # Find all soffice processes with --headless flag
        result = subprocess.run(
            ["pgrep", "-f", "soffice.*--headless"],
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return

        for line in result.stdout.strip().splitlines():
            token = line.strip()
            if not token or not token.isdigit():
                continue
            pid = int(token)
            # Don't kill our own tracked process
            if (
                _soffice_process is not None
                and _soffice_process.poll() is None
                and pid == _soffice_process.pid
            ):
                continue
            try:
                os.kill(pid, signal.SIGTERM)
                logger.info(
                    "Killed orphaned soffice headless process (pid=%d)",
                    pid,
                )
            except OSError:
                pass
    except (OSError, ValueError, subprocess.TimeoutExpired):
        pass


def _kill_orphaned_soffice_win32() -> None:
    """Kills orphaned soffice headless processes on Windows.

    Uses ``wmic`` to query process command lines so only ``--headless``
    instances are killed (not the LibreOffice GUI).  Falls back
    gracefully on systems where ``wmic`` is unavailable (newer Windows 11
    builds where it was fully removed).
    """
    try:
        # wmic filters by command line — only matches headless instances
        result = subprocess.run(
            [
                "wmic",
                "process",
                "where",
                "name='soffice.bin' and commandline like '%--headless%'",
                "get",
                "processid",
            ],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return

        for raw_line in result.stdout.strip().splitlines():
            token = raw_line.strip()
            # wmic output: header "ProcessId" then numeric PIDs
            if not token or not token.isdigit():
                continue
            pid = int(token)
            # Don't kill our own tracked process
            if (
                _soffice_process is not None
                and _soffice_process.poll() is None
                and pid == _soffice_process.pid
            ):
                continue
            try:
                subprocess.run(
                    ["taskkill", "/PID", str(pid), "/F"],
                    capture_output=True,
                    check=False,
                    timeout=5,
                )
                logger.info(
                    "Killed orphaned soffice headless process (pid=%d)",
                    pid,
                )
            except OSError:
                pass
    except (OSError, ValueError, subprocess.TimeoutExpired):
        pass


def _ensure_soffice_running() -> bool:
    """Launches soffice --headless if it is not already running.

    Finds the first available port in the configured range, stores the
    process handle and chosen port in module-level state, and registers
    an ``atexit`` handler for cleanup.

    Returns:
        True if soffice is (now) running, False if the binary was not
        found or no port was available.
    """
    global _soffice_process, _soffice_cleanup_registered, _soffice_port  # noqa: PLW0603

    # Already running?
    if _soffice_process is not None and _soffice_process.poll() is None:
        return True

    # Kill orphaned soffice processes from previous sessions
    _kill_orphaned_soffice()
    _remove_soffice_lock()

    binary = _find_soffice_binary()
    if binary is None:
        logger.warning("Could not find soffice binary; UNO auto-start unavailable")
        return False

    port = _find_available_port()
    if port is None:
        logger.error(
            "No available port in range %d–%d for soffice",
            _SOFFICE_DEFAULT_PORT,
            _SOFFICE_DEFAULT_PORT + _SOFFICE_PORT_RANGE - 1,
        )
        return False

    logger.info(
        "Auto-starting soffice --headless from %s on port %d",
        binary,
        port,
    )
    try:
        _soffice_process = subprocess.Popen(
            [
                binary,
                "--headless",
                "--norestore",
                f"--accept=socket,host=localhost,port={port};urp;",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError as e:
        logger.error("Failed to launch soffice: %s", e)
        return False

    _soffice_port = port

    # Register the cleanup handler exactly once
    if not _soffice_cleanup_registered:
        atexit.register(_cleanup_soffice)
        _soffice_cleanup_registered = True

    return True


# ---------------------------------------------------------------------------
# UNO connection helpers
# ---------------------------------------------------------------------------


def _make_uno_url(port: int) -> str:
    """Builds a UNO resolver URL for the given port.

    Args:
        port: TCP port number of the soffice listener.

    Returns:
        str: Full UNO resolver URL string.
    """
    return f"uno:socket,host=localhost,port={port};urp;StarOffice.ComponentContext"


def _get_uno_desktop() -> object:
    """Connects to a running LibreOffice instance via UNO.

    First tries the default port (``_SOFFICE_DEFAULT_PORT``).  If that
    fails, auto-starts soffice on the first available port and retries
    up to ``_SOFFICE_RETRY_COUNT`` times.

    Returns:
        The com.sun.star.frame.Desktop service.

    Raises:
        RuntimeError: If connection fails after all retries.
    """
    import uno  # noqa: PLC0415
    from com.sun.star.beans import PropertyValue  # noqa: PLC0415, F401

    local_context = uno.getComponentContext()
    resolver = local_context.ServiceManager.createInstanceWithContext(
        "com.sun.star.bridge.UnoUrlResolver",
        local_context,
    )

    # First attempt — default port, catches manually-started soffice
    try:
        ctx = resolver.resolve(_make_uno_url(_SOFFICE_DEFAULT_PORT))
    except Exception:
        # Connection failed — try to auto-start soffice and retry
        if not _ensure_soffice_running():
            raise RuntimeError(
                "Could not connect to LibreOffice UNO and soffice binary"
                " was not found. Please install LibreOffice or start it"
                " manually with: soffice --headless --accept="
                '"socket,host=localhost,port=2002;urp;"',
            ) from None

        # Retry on the port that auto-started soffice is listening on
        retry_url = _make_uno_url(_soffice_port)
        ctx = None
        for attempt in range(_SOFFICE_RETRY_COUNT):
            time.sleep(_SOFFICE_RETRY_DELAY)
            try:
                ctx = resolver.resolve(retry_url)
                logger.debug(
                    "UNO connection succeeded on retry %d (port %d)",
                    attempt + 1,
                    _soffice_port,
                )
                break
            except Exception:
                logger.debug(
                    "UNO connection retry %d/%d failed",
                    attempt + 1,
                    _SOFFICE_RETRY_COUNT,
                )

        if ctx is None:
            raise RuntimeError(
                "Could not connect to LibreOffice UNO after auto-starting"
                " soffice. The listener did not become available within"
                f" {_SOFFICE_RETRY_COUNT * _SOFFICE_RETRY_DELAY:.0f}s.",
            ) from None

    smgr = ctx.ServiceManager
    return smgr.createInstanceWithContext(
        "com.sun.star.frame.Desktop",
        ctx,
    )


# ---------------------------------------------------------------------------
# Win32COM lifecycle helpers
# ---------------------------------------------------------------------------


def _win32com_open(  # noqa: PLR0912
    app_name: str,
    file_path: Path,
) -> tuple[object, object, object]:
    """Opens an office document via win32com.

    Initialises COM, launches the application, and opens the file.
    Returns (app, doc, pythoncom_module) — caller MUST call
    ``_win32com_close`` in a ``finally`` block.

    Args:
        app_name: COM ProgID (e.g. "Word.Application").
        file_path: Path to the document.

    Returns:
        tuple: (app, doc_obj, pythoncom_module).
    """
    import pythoncom  # noqa: PLC0415
    import win32com.client  # noqa: PLC0415

    pythoncom.CoInitialize()
    app = None
    try:
        app = win32com.client.Dispatch(app_name)
        app.Visible = False
        if app_name == _APP_EXCEL:
            app.DisplayAlerts = False

        if app_name == _APP_WORD:
            doc_obj = app.Documents.Open(str(file_path.resolve()))
        elif app_name == _APP_EXCEL:
            doc_obj = app.Workbooks.Open(str(file_path.resolve()))
        else:  # PowerPoint
            doc_obj = app.Presentations.Open(
                str(file_path.resolve()),
                WithWindow=False,
            )
    except Exception:
        _win32com_close(app, None, pythoncom)
        raise

    return app, doc_obj, pythoncom


def _win32com_close(
    app: object | None,
    doc_obj: object | None,
    pythoncom_mod: object | None,
    *,
    save_close: bool = False,
) -> None:
    """Closes a win32com document and application, uninitialises COM.

    Args:
        app: The COM application object.
        doc_obj: The COM document object.
        pythoncom_mod: The pythoncom module (for CoUninitialize).
        save_close: If True, call Close(False) on doc_obj. Some callers
                    already closed the document via Save/SaveAs.
    """
    import contextlib  # noqa: PLC0415

    if doc_obj and save_close:
        with contextlib.suppress(Exception):
            doc_obj.Close(False)
    if app:
        with contextlib.suppress(Exception):
            app.Quit()
    if pythoncom_mod:
        pythoncom_mod.CoUninitialize()
