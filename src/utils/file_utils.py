"""Utility functions for file handling."""

import logging
import math
import shutil
import zipfile
from pathlib import Path

logger = logging.getLogger("file_utils")

# ── Password / encryption detection ──────────────────────────────────

# OLE2 Compound Binary File magic bytes (first 8 bytes)
_OLE2_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"

# EncryptionInfo stream name encoded as UTF-16LE (OLE2 directory format)
_ENCRYPTION_INFO_UTF16 = "EncryptionInfo".encode("utf-16-le")

# Bytes to scan in the OLE2 header area for the EncryptionInfo stream name
_OLE2_SCAN_BYTES = 8192


def is_file_encrypted(file_path: Path) -> bool:
    """Checks whether a file is password-protected or DRM-encrypted.

    Detection strategies by format:

    - Modern Office (.docx/.xlsx/.pptx): encrypted files are wrapped in
      an OLE2 container instead of being a plain ZIP archive.
    - Legacy Office (.doc/.xls/.ppt): always OLE2; scan for the
      UTF-16LE ``EncryptionInfo`` stream name in the directory.
    - ODF (.odt/.ods/.odp): check ``META-INF/manifest.xml`` for
      ``encryption-data`` elements.
    - EPUB (.epub): check for ``META-INF/rights.xml`` (Adobe ADEPT DRM)
      or AES algorithms in ``META-INF/encryption.xml``.

    Args:
        file_path: Path to the file to check.

    Returns:
        True if the file appears to be encrypted/protected.
    """
    suffix = file_path.suffix.lower()

    try:
        # Modern Office: encrypted → OLE2 wrapper instead of ZIP
        if suffix in {".docx", ".xlsx", ".pptx"}:
            with file_path.open("rb") as f:
                return f.read(8) == _OLE2_MAGIC

        # Legacy Office: scan OLE2 directory for EncryptionInfo stream
        if suffix in {".doc", ".xls", ".ppt"}:
            return _is_legacy_ole2_encrypted(file_path)

        # ODF: check manifest.xml for encryption-data elements
        if suffix in {".odt", ".ods", ".odp"}:
            return _check_odf_encryption(file_path)

        # EPUB: check for DRM markers
        if suffix == ".epub":
            return _check_epub_drm(file_path)

        # PDF: check if password-protected
        if suffix == ".pdf":
            return _check_pdf_encryption(file_path)
    except Exception:
        logger.debug(
            "Encryption check failed for %s, assuming not encrypted",
            file_path.name,
        )

    return False


def _is_legacy_ole2_encrypted(file_path: Path) -> bool:
    """Checks if a legacy OLE2 Office file (.doc/.xls/.ppt) is encrypted.

    Scans the first 8 KB for the UTF-16LE encoded ``EncryptionInfo``
    stream name in the OLE2 directory entries.  Covers Office 2002+
    encryption (RC4 and AES).

    Args:
        file_path: Path to the legacy Office file.

    Returns:
        True if the file contains an EncryptionInfo stream.
    """
    with file_path.open("rb") as f:
        header = f.read(_OLE2_SCAN_BYTES)

    # Verify it's actually OLE2
    if header[:8] != _OLE2_MAGIC:
        return False

    return _ENCRYPTION_INFO_UTF16 in header


def _check_odf_encryption(file_path: Path) -> bool:
    """Checks if an ODF file (.odt/.ods/.odp) is encrypted.

    ODF encryption is application-level: content files are encrypted
    individually and key derivation parameters are stored in
    ``META-INF/manifest.xml`` as ``encryption-data`` elements.

    Args:
        file_path: Path to the ODF file.

    Returns:
        True if the manifest contains encryption-data elements.
    """
    try:
        with zipfile.ZipFile(file_path, "r") as zf:
            manifest = zf.read("META-INF/manifest.xml")
        return b"encryption-data" in manifest
    except (zipfile.BadZipFile, KeyError):
        return False


def _check_epub_drm(file_path: Path) -> bool:
    """Checks if an EPUB file has DRM protection.

    Detects Adobe ADEPT DRM (``META-INF/rights.xml``) and W3C XML
    Encryption with AES algorithms.  Font obfuscation (IDPF/Adobe
    URIs) is **not** flagged as DRM since content remains readable.

    Args:
        file_path: Path to the EPUB file.

    Returns:
        True if the EPUB appears to be DRM-protected.
    """
    try:
        with zipfile.ZipFile(file_path, "r") as zf:
            names = zf.namelist()

            # Adobe ADEPT DRM
            if "META-INF/rights.xml" in names:
                return True

            # W3C XML Encryption — check for AES (real DRM, not font obfuscation)
            if "META-INF/encryption.xml" not in names:
                return False

            enc_data = zf.read("META-INF/encryption.xml")
            return b"http://www.w3.org/2001/04/xmlenc#aes" in enc_data
    except (zipfile.BadZipFile, KeyError):
        return False


def _check_pdf_encryption(file_path: Path) -> bool:
    """Checks if a PDF file is password-protected.

    Uses PyMuPDF to open the file and check the ``needs_pass`` flag.
    Returns False if PyMuPDF is not installed.

    Args:
        file_path: Path to the PDF file.

    Returns:
        True if the PDF requires a user password to open.
    """
    try:
        import pymupdf  # noqa: PLC0415
    except ImportError:
        return False
    doc = pymupdf.open(str(file_path))
    try:
        return bool(doc.needs_pass)
    finally:
        doc.close()


def format_file_size(size_bytes: int) -> str:
    """Formats bytes into human-readable string.

    Args:
        size_bytes (int): Size in bytes.

    Returns:
        str: Human readable size (e.g. 1.2 KB).
    """
    if size_bytes == 0:
        return "0B"
    size_name = ("B", "KB", "MB", "GB", "TB")
    i = min(int(math.log(size_bytes, 1024)), len(size_name) - 1)
    p = 1024**i
    s = round(size_bytes / p, 2)

    # Remove .0 if it's an integer
    if s == int(s):
        s = int(s)

    return f"{s} {size_name[i]}"


def clone_file_to_storage(src_path: str, storage_dir: Path) -> str:
    """Clones a file to a specific storage directory.

    Copies *src_path* into *storage_dir*, creating the directory tree if
    needed.  Metadata (timestamps, permissions) are preserved via
    :func:`shutil.copy2`.

    Args:
        src_path: Absolute path of the source file.
        storage_dir: Target directory (created if absent).

    Returns:
        Absolute path of the cloned file inside *storage_dir*.
    """
    storage_dir.mkdir(parents=True, exist_ok=True)
    src = Path(src_path)
    dest = storage_dir / src.name
    shutil.copy2(src, dest)
    return str(dest.absolute())


def wipe_history_directory(file_path: str) -> None:
    """Removes the parent directory of a storage file.

    Used to clean up the per-task storage folder when a history entry
    is deleted.  No-op if *file_path* is empty or the parent directory
    does not exist.

    Args:
        file_path: Path to any file inside the task storage directory.
    """
    if not file_path:
        return
    path = Path(file_path)
    storage_dir = path.parent
    if storage_dir.exists() and storage_dir.is_dir():
        shutil.rmtree(storage_dir, ignore_errors=True)
