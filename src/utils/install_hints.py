"""Distro-aware install command hints for optional system binaries.

Mirrors the ``_get_install_hint`` helper in ``src/core/live_engine.py`` but
lives in a dependency-light module so the settings page can import these
without dragging in faster-whisper / sounddevice / etc.

Each ``get_*_install_hint()`` returns a copy-paste-ready install command for
the user's current Linux distro, or empty string on non-Linux platforms
(callers substitute a download link in that case).
"""

import platform
import shutil


def _get_install_hint(packages: dict[str, str]) -> str:
    """Returns a distro-specific install command, or empty string.

    Args:
        packages: Mapping of package-manager binary (apt-get / dnf / …) to the
            full install command to surface when that binary is detected.
    """
    if platform.system() != "Linux":
        return ""
    for binary, cmd in packages.items():
        if shutil.which(binary):
            return cmd
    return ""


# Per-package-manager install commands for FFmpeg.
_FFMPEG_PACKAGES: dict[str, str] = {
    "apt-get": "sudo apt-get install ffmpeg",
    "dnf": "sudo dnf install ffmpeg",
    "pacman": "sudo pacman -S ffmpeg",
    "zypper": "sudo zypper install ffmpeg",
    "apk": "sudo apk add ffmpeg",
}


def get_ffmpeg_install_hint() -> str:
    """Returns a distro-specific FFmpeg install command, or empty string."""
    return _get_install_hint(_FFMPEG_PACKAGES)


def format_install_clause(cmd: str) -> str:
    """Wraps a bare install command into the localized inline template.

    The wrapping comes from the ``live.install_command_inline`` i18n
    key (``" Install with:<br><b>{cmd}</b>"`` in en-US — note the
    ``<br>`` that puts the command on its own line so narrow contexts
    like the install dialog don't wrap it mid-word) and gets appended
    after a Linux base banner.  Returns empty string when ``cmd`` is
    empty so the base banner reads cleanly on unrecognised distros —
    avoids the empty ``<b></b>`` artefact that callers would otherwise
    emit.

    Import is lazy to keep this module free of PySide6/i18n imports
    at module load (so it can be imported from places that don't
    have the i18n catalogue initialised yet).
    """
    if not cmd:
        return ""
    from src.constants.i18n import tr  # noqa: PLC0415

    # The i18n template puts the command on its own line via ``<br>``
    # so a narrow context (especially the install dialog) doesn't try
    # to wrap the command mid-word.  An earlier attempt to use
    # ``<nobr>`` (Qt's "don't break inside" tag) didn't reliably
    # prevent the break — Qt's QLabel rich-text subset apparently
    # parses but doesn't honour it across all nesting cases.  Putting
    # the command on a dedicated line is the robust fix.
    return tr("live.install_command_inline").format(cmd=cmd)


def build_ffmpeg_install_message() -> str:
    """Returns the per-OS FFmpeg install message used by the install dialog.

    Reuses the same ``settings.ffmpeg_install_{linux,macos,windows,
    unsupported}`` i18n keys as the top-of-page banners in Voice /
    Dubbing / Live — single source of truth for "how to install
    FFmpeg" messaging across the app.  On Linux, the
    ``{linux_install}`` placeholder is filled by the auto-detected
    package-manager command via :func:`format_install_clause` — so a
    Debian user gets "Install with: sudo apt-get install ffmpeg" inline
    instead of a generic listing.

    Returns rich-text (HTML); callers feeding this into
    :class:`QLabel` (e.g. ``CustomMessageDialog``'s message label)
    must enable rich-text auto-detection and ``setOpenExternalLinks
    (True)`` so the ``<a href>`` download links resolve to the
    user's browser.

    Lazy i18n / platform import so the module loads without PySide6
    / catalogue side effects.
    """
    import platform  # noqa: PLC0415

    from src.constants.i18n import tr  # noqa: PLC0415

    system = platform.system()
    if system == "Linux":
        return tr(
            "settings.ffmpeg_install_linux",
            linux_install=format_install_clause(get_ffmpeg_install_hint()),
        )
    if system == "Darwin":
        return tr("settings.ffmpeg_install_macos")
    if system == "Windows":
        return tr("settings.ffmpeg_install_windows")
    return tr("settings.ffmpeg_install_unsupported")
