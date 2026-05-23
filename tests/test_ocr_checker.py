"""Unit tests for the ocr_checker utility."""

from unittest.mock import MagicMock, patch

from src.constants import (
    OCR_METHOD_EASYOCR,
    OCR_METHOD_GOOGLE_CLOUD,
    OCR_METHOD_TESSERACT,
)
from src.utils.ocr_checker import check_ocr_availability


def test_google_cloud_always_available() -> None:
    """Google Cloud OCR is cloud-based, so it is always available."""
    is_ready, message = check_ocr_availability(OCR_METHOD_GOOGLE_CLOUD)
    assert is_ready is True
    assert "Cloud-based" in message


def test_unknown_method() -> None:
    """Verify behavior when an unknown OCR method is checked."""
    is_ready, message = check_ocr_availability("Unknown Method")
    assert is_ready is False
    assert "Unknown OCR method" in message


def test_local_methods_return_tuple() -> None:
    """Basic check that local method checks return expected data types."""
    for method in [OCR_METHOD_TESSERACT, OCR_METHOD_EASYOCR]:
        is_ready, message = check_ocr_availability(method)
        assert isinstance(is_ready, bool)
        assert isinstance(message, str)


# ---------------------------------------------------------------------------
# Tesseract — PATH-based availability
# ---------------------------------------------------------------------------


def test_tesseract_available_when_found_in_path() -> None:
    """Returns (True, ready message) when tesseract executable is in PATH."""
    with patch("shutil.which", return_value="/usr/bin/tesseract"):
        is_ready, message = check_ocr_availability(OCR_METHOD_TESSERACT)
    assert is_ready is True
    assert "ready" in message.lower()


def test_tesseract_unavailable_when_not_in_path() -> None:
    """Returns (False, not-found message) when tesseract is absent from PATH."""
    with patch("shutil.which", return_value=None):
        is_ready, message = check_ocr_availability(OCR_METHOD_TESSERACT)
    assert is_ready is False
    assert "not found" in message.lower()


# ---------------------------------------------------------------------------
# EasyOCR — package-based availability
# ---------------------------------------------------------------------------


def test_easyocr_available_when_package_installed() -> None:
    """Returns (True, ready message) when the easyocr package is installed."""
    fake_spec = MagicMock()
    with patch("importlib.util.find_spec", return_value=fake_spec):
        is_ready, message = check_ocr_availability(OCR_METHOD_EASYOCR)
    assert is_ready is True
    assert "ready" in message.lower()


def test_easyocr_unavailable_when_package_not_installed() -> None:
    """Returns (False, not-installed message) when easyocr is absent."""
    with patch("importlib.util.find_spec", return_value=None):
        is_ready, message = check_ocr_availability(OCR_METHOD_EASYOCR)
    assert is_ready is False
    assert "not installed" in message.lower()


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_empty_string_method() -> None:
    """Empty string method falls through to the unknown-method branch."""
    is_ready, message = check_ocr_availability("")
    assert is_ready is False
    assert "Unknown OCR method" in message


# ---------------------------------------------------------------------------
# detect_tesseract_languages — subprocess output parsing
# ---------------------------------------------------------------------------


def test_detect_languages_normal_output() -> None:
    """Normal tesseract output with 2 languages returns correct set."""
    from subprocess import CompletedProcess  # noqa: PLC0415

    from src.utils.ocr_checker import detect_tesseract_languages  # noqa: PLC0415

    output = "List of available languages (2):\neng\nfra\n"
    fake = CompletedProcess(args=[], returncode=0, stdout=output, stderr="")
    with patch("subprocess.run", return_value=fake):
        langs = detect_tesseract_languages()
    assert langs == {"eng", "fra"}


def test_detect_languages_header_only() -> None:
    """Only the header line → no language packs → empty set."""
    from subprocess import CompletedProcess  # noqa: PLC0415

    from src.utils.ocr_checker import detect_tesseract_languages  # noqa: PLC0415

    output = "List of available languages (0):\n"
    fake = CompletedProcess(args=[], returncode=0, stdout=output, stderr="")
    with patch("subprocess.run", return_value=fake):
        langs = detect_tesseract_languages()
    assert langs == set()


def test_detect_languages_empty_output() -> None:
    """Empty stdout → empty set (no lines at all)."""
    from subprocess import CompletedProcess  # noqa: PLC0415

    from src.utils.ocr_checker import detect_tesseract_languages  # noqa: PLC0415

    fake = CompletedProcess(args=[], returncode=0, stdout="", stderr="")
    with patch("subprocess.run", return_value=fake):
        langs = detect_tesseract_languages()
    assert langs == set()


def test_detect_languages_whitespace_entries_filtered() -> None:
    """Whitespace-only language entries are excluded from the result."""
    from subprocess import CompletedProcess  # noqa: PLC0415

    from src.utils.ocr_checker import detect_tesseract_languages  # noqa: PLC0415

    output = "List of available languages:\neng\n   \ndeu\n\n"
    fake = CompletedProcess(args=[], returncode=0, stdout=output, stderr="")
    with patch("subprocess.run", return_value=fake):
        langs = detect_tesseract_languages()
    assert langs == {"eng", "deu"}


def test_detect_languages_file_not_found() -> None:
    """FileNotFoundError (tesseract not in PATH) → empty set."""
    from src.utils.ocr_checker import detect_tesseract_languages  # noqa: PLC0415

    with patch("subprocess.run", side_effect=FileNotFoundError):
        langs = detect_tesseract_languages()
    assert langs == set()


def test_detect_languages_timeout() -> None:
    """TimeoutExpired → empty set (graceful degradation)."""
    import subprocess  # noqa: PLC0415

    from src.utils.ocr_checker import detect_tesseract_languages  # noqa: PLC0415

    with patch(
        "subprocess.run",
        side_effect=subprocess.TimeoutExpired(cmd="tesseract", timeout=5),
    ):
        langs = detect_tesseract_languages()
    assert langs == set()


def test_detect_languages_oserror() -> None:
    """OSError (permission denied, etc.) → empty set."""
    from src.utils.ocr_checker import detect_tesseract_languages  # noqa: PLC0415

    with patch("subprocess.run", side_effect=OSError("Permission denied")):
        langs = detect_tesseract_languages()
    assert langs == set()


def test_detect_languages_many_langs() -> None:
    """Output with many language codes is fully parsed."""
    from subprocess import CompletedProcess  # noqa: PLC0415

    from src.utils.ocr_checker import detect_tesseract_languages  # noqa: PLC0415

    codes = ["eng", "fra", "deu", "spa", "chi_sim", "jpn", "kor", "ara"]
    output = "List of available languages (8):\n" + "\n".join(codes) + "\n"
    fake = CompletedProcess(args=[], returncode=0, stdout=output, stderr="")
    with patch("subprocess.run", return_value=fake):
        langs = detect_tesseract_languages()
    assert langs == set(codes)


# ──────────────────────────────────────────────────────────────────────
# get_tesseract_install_hint / get_tesseract_langpack_install_hint
# ──────────────────────────────────────────────────────────────────────


class TestGetTesseractInstallHint:
    """Distro-specific install command for the Tesseract binary.

    Used by the Settings → OCR no-langs banner (and the legacy
    "Tesseract missing" install dialog) to substitute the right
    ``sudo apt-get install`` / ``sudo dnf install`` etc. into the
    localized message template.
    """

    def test_returns_empty_on_non_linux(self) -> None:
        """Non-Linux callers (macOS / Windows) get '' so the message renders without it."""
        from src.utils.ocr_checker import get_tesseract_install_hint  # noqa: PLC0415

        with patch("src.utils.ocr_checker.platform.system", return_value="Darwin"):
            assert get_tesseract_install_hint() == ""
        with patch("src.utils.ocr_checker.platform.system", return_value="Windows"):
            assert get_tesseract_install_hint() == ""

    def test_returns_apt_command_when_apt_get_on_path(self) -> None:
        """Debian/Ubuntu: apt-get → ``sudo apt-get install tesseract-ocr``."""
        from src.utils.ocr_checker import get_tesseract_install_hint  # noqa: PLC0415

        with (
            patch("src.utils.ocr_checker.platform.system", return_value="Linux"),
            patch(
                "src.utils.ocr_checker.shutil.which",
                side_effect=lambda b: "/usr/bin/apt-get" if b == "apt-get" else None,
            ),
        ):
            assert get_tesseract_install_hint() == (
                "sudo apt-get install tesseract-ocr"
            )

    def test_returns_dnf_command_when_dnf_on_path(self) -> None:
        """Fedora/RHEL: dnf → ``sudo dnf install tesseract``."""
        from src.utils.ocr_checker import get_tesseract_install_hint  # noqa: PLC0415

        with (
            patch("src.utils.ocr_checker.platform.system", return_value="Linux"),
            patch(
                "src.utils.ocr_checker.shutil.which",
                side_effect=lambda b: "/usr/bin/dnf" if b == "dnf" else None,
            ),
        ):
            assert get_tesseract_install_hint() == "sudo dnf install tesseract"

    def test_returns_empty_on_unrecognised_linux(self) -> None:
        """Exotic distros with no recognised pkg manager get ''."""
        from src.utils.ocr_checker import get_tesseract_install_hint  # noqa: PLC0415

        with (
            patch("src.utils.ocr_checker.platform.system", return_value="Linux"),
            patch("src.utils.ocr_checker.shutil.which", return_value=None),
        ):
            assert get_tesseract_install_hint() == ""


class TestGetTesseractLangpackInstallHint:
    """Distro-specific install command for the Tesseract English language pack.

    Pairs with the no-langs banner.  English-only by design — adding
    every locale would balloon the banner; users following the
    ``tesseract-ocr-fra`` / ``tesseract-ocr-deu`` pattern can adapt.
    """

    def test_returns_empty_on_non_linux(self) -> None:
        """Non-Linux callers (macOS / Windows) get '' so the message renders without it."""
        from src.utils.ocr_checker import (  # noqa: PLC0415
            get_tesseract_langpack_install_hint,
        )

        with patch("src.utils.ocr_checker.platform.system", return_value="Darwin"):
            assert get_tesseract_langpack_install_hint() == ""
        with patch("src.utils.ocr_checker.platform.system", return_value="Windows"):
            assert get_tesseract_langpack_install_hint() == ""

    def test_returns_apt_langpack_command(self) -> None:
        """Debian/Ubuntu: ``sudo apt-get install tesseract-ocr-eng``."""
        from src.utils.ocr_checker import (  # noqa: PLC0415
            get_tesseract_langpack_install_hint,
        )

        with (
            patch("src.utils.ocr_checker.platform.system", return_value="Linux"),
            patch(
                "src.utils.ocr_checker.shutil.which",
                side_effect=lambda b: "/usr/bin/apt-get" if b == "apt-get" else None,
            ),
        ):
            assert get_tesseract_langpack_install_hint() == (
                "sudo apt-get install tesseract-ocr-eng"
            )

    def test_returns_pacman_langpack_command(self) -> None:
        """Arch: ``sudo pacman -S tesseract-data-eng``."""
        from src.utils.ocr_checker import (  # noqa: PLC0415
            get_tesseract_langpack_install_hint,
        )

        with (
            patch("src.utils.ocr_checker.platform.system", return_value="Linux"),
            patch(
                "src.utils.ocr_checker.shutil.which",
                side_effect=lambda b: "/usr/bin/pacman" if b == "pacman" else None,
            ),
        ):
            assert get_tesseract_langpack_install_hint() == (
                "sudo pacman -S tesseract-data-eng"
            )

    def test_returns_empty_on_unrecognised_linux(self) -> None:
        """No package manager match → empty string (caller-friendly)."""
        from src.utils.ocr_checker import (  # noqa: PLC0415
            get_tesseract_langpack_install_hint,
        )

        with (
            patch("src.utils.ocr_checker.platform.system", return_value="Linux"),
            patch("src.utils.ocr_checker.shutil.which", return_value=None),
        ):
            assert get_tesseract_langpack_install_hint() == ""
