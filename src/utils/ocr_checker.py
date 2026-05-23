"""Utility functions for checking OCR engine availability."""

import importlib.util
import logging
import platform
import shutil
import subprocess

from src.constants import (
    OCR_METHOD_EASYOCR,
    OCR_METHOD_GOOGLE_CLOUD,
    OCR_METHOD_TESSERACT,
)

logger = logging.getLogger("ocr_checker")


# Per-package-manager install commands for the Tesseract binary.  Mirrors
# the ``_PULSEAUDIO_PACKAGES`` style in ``src/core/live_engine.py`` so the
# OCR settings tab can surface a distro-specific copy-paste command when
# the user is missing the binary.
_TESSERACT_PACKAGES: dict[str, str] = {
    "apt-get": "sudo apt-get install tesseract-ocr",
    "dnf": "sudo dnf install tesseract",
    "pacman": "sudo pacman -S tesseract",
    "zypper": "sudo zypper install tesseract-ocr",
    "apk": "sudo apk add tesseract-ocr",
}

# Per-package-manager install commands for the Tesseract English language
# pack.  Each distro has its own naming convention — pinning to English
# only because additional languages follow the same pattern (e.g.
# ``tesseract-ocr-fra``) and listing every locale would balloon the banner.
_TESSERACT_LANGPACK_PACKAGES: dict[str, str] = {
    "apt-get": "sudo apt-get install tesseract-ocr-eng",
    "dnf": "sudo dnf install tesseract-langpack-eng",
    "pacman": "sudo pacman -S tesseract-data-eng",
    "zypper": "sudo zypper install tesseract-ocr-traineddata-english",
    "apk": "sudo apk add tesseract-ocr-data-eng",
}


def get_tesseract_install_hint() -> str:
    """Returns a distro-specific Tesseract install command, or empty string.

    Empty string on non-Linux platforms or unrecognised package managers —
    the caller substitutes locale-specific link text instead.
    """
    if platform.system() != "Linux":
        return ""
    for binary, cmd in _TESSERACT_PACKAGES.items():
        if shutil.which(binary):
            return cmd
    return ""


def get_tesseract_langpack_install_hint() -> str:
    """Returns a distro-specific Tesseract English language-pack install command.

    Empty string on non-Linux platforms or unrecognised package managers.
    """
    if platform.system() != "Linux":
        return ""
    for binary, cmd in _TESSERACT_LANGPACK_PACKAGES.items():
        if shutil.which(binary):
            return cmd
    return ""


def check_ocr_availability(method: str) -> tuple[bool, str]:
    """Checks if the selected OCR method is available on the system.

    Args:
        method (str): The name of the OCR method to check.

    Returns:
        tuple[bool, str]: A tuple containing (is_available, status_message).
    """
    if method == OCR_METHOD_GOOGLE_CLOUD:
        return True, "Cloud-based: Ensure API credentials are configured."

    if method == OCR_METHOD_TESSERACT:
        is_ready = shutil.which("tesseract") is not None
        message = (
            "TesseractOCR executable not found in PATH."
            if not is_ready
            else "TesseractOCR is ready."
        )
        return is_ready, message

    if method == OCR_METHOD_EASYOCR:
        is_ready = importlib.util.find_spec("easyocr") is not None
        message = (
            "EasyOCR package is not installed." if not is_ready else "EasyOCR is ready."
        )
        return is_ready, message

    return False, "Unknown OCR method selected."


def detect_tesseract_languages() -> set[str]:
    """Detects installed Tesseract language packs via ``tesseract --list-langs``.

    Returns:
        set[str]: Language codes available (e.g. ``{"eng", "fra"}``).
            Empty set if Tesseract is not in PATH or the command fails.
    """
    try:
        result = subprocess.run(
            ["tesseract", "--list-langs"],  # noqa: S603, S607
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        # First line is a header like "List of available languages (N):"
        lines = result.stdout.strip().splitlines()
        if len(lines) <= 1:
            return set()
        return {lang.strip() for lang in lines[1:] if lang.strip()}
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as exc:
        logger.debug("Failed to detect Tesseract languages: %s", exc)
        return set()
