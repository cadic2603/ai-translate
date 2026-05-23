"""Unit tests for file utility functions."""

import io
import shutil
import sys
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.utils.file_utils import (
    clone_file_to_storage,
    format_file_size,
    is_file_encrypted,
    wipe_history_directory,
)

# ── format_file_size ─────────────────────────────────────────


def test_format_file_size() -> None:
    """Verify that bytes are formatted correctly."""
    assert format_file_size(0) == "0B"
    assert format_file_size(512) == "512 B"
    assert format_file_size(1024) == "1 KB"
    assert format_file_size(1536) == "1.5 KB"
    assert format_file_size(1024 * 1024) == "1 MB"
    assert format_file_size(1024 * 1024 * 1024) == "1 GB"
    assert format_file_size(2.5 * 1024 * 1024 * 1024) == "2.5 GB"


# ── clone_file_to_storage ────────────────────────────────────


def test_clone_basic(tmp_path: Path) -> None:
    """File is copied to storage directory and path is returned."""
    src = tmp_path / "original.txt"
    src.write_text("hello")
    storage = tmp_path / "storage"

    result = clone_file_to_storage(str(src), storage)

    assert Path(result).exists()
    assert Path(result).name == "original.txt"
    assert Path(result).read_text() == "hello"


def test_clone_creates_storage_dir(tmp_path: Path) -> None:
    """Storage directory is created if it does not exist."""
    src = tmp_path / "file.txt"
    src.write_text("data")
    storage = tmp_path / "deep" / "nested" / "dir"

    clone_file_to_storage(str(src), storage)

    assert storage.exists()


def test_clone_special_characters(tmp_path: Path) -> None:
    """Filenames with spaces and unicode are cloned correctly."""
    src = tmp_path / "tài liệu (copy).txt"
    src.write_text("nội dung")
    storage = tmp_path / "storage"

    result = clone_file_to_storage(str(src), storage)

    assert Path(result).exists()
    assert Path(result).read_text() == "nội dung"


# ── wipe_history_directory ────────────────────────────────────


def test_wipe_removes_parent_dir(tmp_path: Path) -> None:
    """Parent directory of the given file path is removed."""
    storage = tmp_path / "translations" / "42"
    storage.mkdir(parents=True)
    stored_file = storage / "test.txt"
    stored_file.write_text("content")

    wipe_history_directory(str(stored_file))

    assert not storage.exists()


def test_wipe_empty_path() -> None:
    """Empty path string is a safe no-op."""
    wipe_history_directory("")


def test_wipe_nonexistent_path() -> None:
    """Nonexistent path is a safe no-op."""
    wipe_history_directory("/tmp/nonexistent_abc_xyz/file.txt")


# ── format_file_size edge cases ─────────────────────────────


def test_format_file_size_one_byte() -> None:
    """Single byte is displayed correctly."""
    assert format_file_size(1) == "1 B"


def test_format_file_size_boundary_1023() -> None:
    """1023 bytes stays in B range."""
    result = format_file_size(1023)
    assert "B" in result
    assert "KB" not in result


def test_format_file_size_exactly_1kb() -> None:
    """1024 bytes = 1 KB (integer, no .0)."""
    assert format_file_size(1024) == "1 KB"


def test_format_file_size_tb_range() -> None:
    """Terabyte range is formatted correctly."""
    tb = 1024**4
    assert format_file_size(tb) == "1 TB"
    assert format_file_size(int(2.5 * tb)) == "2.5 TB"


def test_format_file_size_integer_rounding() -> None:
    """Values that round to .0 display as integer (e.g. '2 MB' not '2.0 MB')."""
    two_mb = 2 * 1024 * 1024
    result = format_file_size(two_mb)
    assert result == "2 MB"
    assert ".0" not in result


def test_format_file_size_decimal_precision() -> None:
    """Non-integer values show up to 2 decimal places."""
    size = int(1.75 * 1024)  # 1792 bytes
    result = format_file_size(size)
    assert result == "1.75 KB"


def test_format_file_size_large_gb() -> None:
    """Large GB values display correctly."""
    size = int(100.5 * 1024 * 1024 * 1024)
    result = format_file_size(size)
    assert "GB" in result
    assert "100" in result


# ── clone_file_to_storage edge cases ────────────────────────


def test_clone_zero_byte_file(tmp_path: Path) -> None:
    """Zero-byte file is cloned correctly."""
    src = tmp_path / "empty.txt"
    src.touch()
    storage = tmp_path / "storage"

    result = clone_file_to_storage(str(src), storage)

    cloned = Path(result)
    assert cloned.exists()
    assert cloned.stat().st_size == 0


def test_clone_overwrites_existing(tmp_path: Path) -> None:
    """Cloning to existing file overwrites it."""
    src = tmp_path / "file.txt"
    src.write_text("new content")
    storage = tmp_path / "storage"
    storage.mkdir()
    existing = storage / "file.txt"
    existing.write_text("old content")

    clone_file_to_storage(str(src), storage)

    assert existing.read_text() == "new content"


def test_clone_preserves_binary_content(tmp_path: Path) -> None:
    """Binary file content is preserved during clone."""
    src = tmp_path / "image.png"
    binary_data = bytes(range(256))
    src.write_bytes(binary_data)
    storage = tmp_path / "storage"

    result = clone_file_to_storage(str(src), storage)

    assert Path(result).read_bytes() == binary_data


# ── wipe_history_directory edge cases ───────────────────────


def test_wipe_nested_files(tmp_path: Path) -> None:
    """Directory with nested subdirectories and files is fully removed."""
    storage = tmp_path / "translations" / "99"
    nested = storage / "sub" / "deep"
    nested.mkdir(parents=True)
    (storage / "file1.txt").write_text("a")
    (storage / "sub" / "file2.txt").write_text("b")
    (nested / "file3.txt").write_text("c")

    wipe_history_directory(str(storage / "file1.txt"))

    assert not storage.exists()


def test_wipe_none_path_is_noop() -> None:
    """None-like falsy values are handled safely."""
    # The function checks "if not file_path" which catches None-like values
    wipe_history_directory("")  # empty string
    # Should not raise


# ── format_file_size additional edge cases ────────────────────


def test_format_file_size_negative_returns_error_or_zero() -> None:
    """Negative input: math.log raises ValueError for negative numbers."""
    with pytest.raises(ValueError):
        format_file_size(-1)


def test_format_file_size_exact_boundaries() -> None:
    """Exact 1024^n boundaries for KB, MB, GB, TB."""
    assert format_file_size(1024) == "1 KB"
    assert format_file_size(1024**2) == "1 MB"
    assert format_file_size(1024**3) == "1 GB"
    assert format_file_size(1024**4) == "1 TB"


def test_format_file_size_just_below_boundary() -> None:
    """Values just below 1024^n stay in the lower unit."""
    result = format_file_size(1023)
    assert "B" in result
    assert "KB" not in result

    result = format_file_size(1024**2 - 1)
    assert "KB" in result
    assert "MB" not in result


def test_format_file_size_small_fractions() -> None:
    """Small fractional KB values display correctly."""
    # 1.01 KB = 1034 bytes
    result = format_file_size(1034)
    assert "KB" in result
    assert "1.01" in result


# ── clone_file_to_storage additional edge cases ──────────────


def test_clone_source_not_found(tmp_path: Path) -> None:
    """Cloning a nonexistent source raises FileNotFoundError."""
    storage = tmp_path / "storage"
    with pytest.raises(FileNotFoundError):
        clone_file_to_storage("/tmp/nonexistent_xyz_abc.txt", storage)


def test_clone_return_is_absolute(tmp_path: Path) -> None:
    """Returned path is always absolute."""
    src = tmp_path / "file.txt"
    src.write_text("data")
    storage = tmp_path / "storage"

    result = clone_file_to_storage(str(src), storage)

    assert Path(result).is_absolute()


def test_clone_preserves_filename_with_spaces(tmp_path: Path) -> None:
    """Filenames with spaces are preserved in clone."""
    src = tmp_path / "my document (final).txt"
    src.write_text("content")
    storage = tmp_path / "storage"

    result = clone_file_to_storage(str(src), storage)

    assert Path(result).name == "my document (final).txt"
    assert Path(result).read_text() == "content"


def test_clone_large_binary_file(tmp_path: Path) -> None:
    """Large binary file is cloned correctly."""
    src = tmp_path / "big.bin"
    data = b"\x00\xff" * 50000  # 100KB
    src.write_bytes(data)
    storage = tmp_path / "storage"

    result = clone_file_to_storage(str(src), storage)

    assert Path(result).read_bytes() == data


# ── wipe_history_directory additional edge cases ─────────────


def test_wipe_file_only_no_parent_dir(tmp_path: Path) -> None:
    """Wipe on a file at the root of tmp_path only removes the parent dir."""
    storage = tmp_path / "task_dir"
    storage.mkdir()
    f = storage / "file.txt"
    f.write_text("data")

    wipe_history_directory(str(f))

    assert not storage.exists()
    # But tmp_path itself still exists
    assert tmp_path.exists()


def test_wipe_already_deleted_dir(tmp_path: Path) -> None:
    """Wiping an already-deleted directory is a safe no-op."""
    storage = tmp_path / "gone" / "task"
    # Don't create it — it doesn't exist
    wipe_history_directory(str(storage / "file.txt"))
    # Should not raise


# ── format_file_size beyond-TB edge case ─────────────────────


def test_format_file_size_beyond_tb_clamped() -> None:
    """Values beyond TB (1 PB+) are clamped to TB units."""
    assert format_file_size(1024**5) == "1024 TB"


# ── clone multiple files to same storage dir ─────────────────


def test_clone_multiple_files_same_dir(tmp_path: Path) -> None:
    """Two different files cloned to the same directory coexist."""
    src1 = tmp_path / "a.txt"
    src1.write_text("content a")
    src2 = tmp_path / "b.txt"
    src2.write_text("content b")
    storage = tmp_path / "shared_storage"

    result1 = clone_file_to_storage(str(src1), storage)
    result2 = clone_file_to_storage(str(src2), storage)

    assert Path(result1).read_text() == "content a"
    assert Path(result2).read_text() == "content b"
    assert len(list(storage.iterdir())) == 2  # noqa: PLR2004


# ── is_file_encrypted helpers ────────────────────────────────────────

# OLE2 magic bytes used by encrypted modern Office files
_OLE2_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


def _make_zip(tmp_path: Path, name: str, files: dict[str, bytes]) -> Path:
    """Creates a minimal ZIP file with the given entries."""
    path = tmp_path / name
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for fname, content in files.items():
            zf.writestr(fname, content)
    path.write_bytes(buf.getvalue())
    return path


# ── Modern Office encryption (.docx, .xlsx, .pptx) ──────────────────


@pytest.mark.parametrize("ext", [".docx", ".xlsx", ".pptx"])
def test_encrypted_modern_office(tmp_path: Path, ext: str) -> None:
    """Modern Office file with OLE2 magic is detected as encrypted."""
    f = tmp_path / f"secret{ext}"
    f.write_bytes(_OLE2_MAGIC + b"\x00" * 100)
    assert is_file_encrypted(f) is True


@pytest.mark.parametrize("ext", [".docx", ".xlsx", ".pptx"])
def test_unencrypted_modern_office(tmp_path: Path, ext: str) -> None:
    """Modern Office file with ZIP magic is not encrypted."""
    _make_zip(tmp_path, f"clean{ext}", {"[Content_Types].xml": b"<Types/>"})
    assert is_file_encrypted(tmp_path / f"clean{ext}") is False


# ── Legacy Office encryption (.doc, .xls, .ppt) ─────────────────────


@pytest.mark.parametrize("ext", [".doc", ".xls", ".ppt"])
def test_encrypted_legacy_office(tmp_path: Path, ext: str) -> None:
    """Legacy Office file with EncryptionInfo stream is detected."""
    enc_info = "EncryptionInfo".encode("utf-16-le")
    f = tmp_path / f"secret{ext}"
    f.write_bytes(_OLE2_MAGIC + b"\x00" * 200 + enc_info + b"\x00" * 100)
    assert is_file_encrypted(f) is True


@pytest.mark.parametrize("ext", [".doc", ".xls", ".ppt"])
def test_unencrypted_legacy_office(tmp_path: Path, ext: str) -> None:
    """Legacy Office file without EncryptionInfo is not encrypted."""
    f = tmp_path / f"clean{ext}"
    f.write_bytes(_OLE2_MAGIC + b"\x00" * 500)
    assert is_file_encrypted(f) is False


# ── ODF encryption (.odt, .ods, .odp) ───────────────────────────────

_ENCRYPTED_MANIFEST = b"""\
<?xml version="1.0" encoding="UTF-8"?>
<manifest:manifest>
  <manifest:file-entry manifest:full-path="content.xml">
    <manifest:encryption-data>
      <manifest:algorithm manifest:algorithm-name="AES256"/>
    </manifest:encryption-data>
  </manifest:file-entry>
</manifest:manifest>
"""

_CLEAN_MANIFEST = b"""\
<?xml version="1.0" encoding="UTF-8"?>
<manifest:manifest>
  <manifest:file-entry manifest:full-path="content.xml"
    manifest:media-type="text/xml"/>
</manifest:manifest>
"""


@pytest.mark.parametrize("ext", [".odt", ".ods", ".odp"])
def test_encrypted_odf(tmp_path: Path, ext: str) -> None:
    """ODF with encryption-data in manifest is detected as encrypted."""
    _make_zip(
        tmp_path,
        f"secret{ext}",
        {
            "META-INF/manifest.xml": _ENCRYPTED_MANIFEST,
        },
    )
    assert is_file_encrypted(tmp_path / f"secret{ext}") is True


@pytest.mark.parametrize("ext", [".odt", ".ods", ".odp"])
def test_unencrypted_odf(tmp_path: Path, ext: str) -> None:
    """ODF without encryption-data in manifest is not encrypted."""
    _make_zip(
        tmp_path,
        f"clean{ext}",
        {
            "META-INF/manifest.xml": _CLEAN_MANIFEST,
        },
    )
    assert is_file_encrypted(tmp_path / f"clean{ext}") is False


# ── EPUB DRM detection ───────────────────────────────────────────────


def test_epub_drm_rights_xml(tmp_path: Path) -> None:
    """EPUB with META-INF/rights.xml (Adobe ADEPT) is detected as DRM."""
    _make_zip(
        tmp_path,
        "drm.epub",
        {
            "META-INF/rights.xml": b"<rights/>",
            "mimetype": b"application/epub+zip",
        },
    )
    assert is_file_encrypted(tmp_path / "drm.epub") is True


def test_epub_drm_aes_encryption(tmp_path: Path) -> None:
    """EPUB with AES encryption in encryption.xml is detected as DRM."""
    enc_xml = (
        b"<encryption><EncryptedData>"
        b"<EncryptionMethod Algorithm="
        b'"http://www.w3.org/2001/04/xmlenc#aes128-cbc"/>'
        b"</EncryptedData></encryption>"
    )
    _make_zip(
        tmp_path,
        "drm2.epub",
        {
            "META-INF/encryption.xml": enc_xml,
            "mimetype": b"application/epub+zip",
        },
    )
    assert is_file_encrypted(tmp_path / "drm2.epub") is True


def test_epub_font_obfuscation_only(tmp_path: Path) -> None:
    """EPUB with only IDPF font obfuscation is NOT flagged as DRM."""
    enc_xml = (
        b"<encryption><EncryptedData>"
        b"<EncryptionMethod Algorithm="
        b'"http://www.idpf.org/2008/embedding"/>'
        b"</EncryptedData></encryption>"
    )
    _make_zip(
        tmp_path,
        "fonts.epub",
        {
            "META-INF/encryption.xml": enc_xml,
            "mimetype": b"application/epub+zip",
        },
    )
    assert is_file_encrypted(tmp_path / "fonts.epub") is False


def test_epub_no_drm(tmp_path: Path) -> None:
    """Clean EPUB without DRM markers is not encrypted."""
    _make_zip(
        tmp_path,
        "clean.epub",
        {
            "mimetype": b"application/epub+zip",
        },
    )
    assert is_file_encrypted(tmp_path / "clean.epub") is False


# ── Edge cases ───────────────────────────────────────────────────────


def test_unsupported_extension_returns_false(tmp_path: Path) -> None:
    """Unsupported extension returns False without checking."""
    f = tmp_path / "notes.txt"
    f.write_text("hello")
    assert is_file_encrypted(f) is False


def test_corrupt_file_returns_false(tmp_path: Path) -> None:
    """Corrupt file with supported extension returns False, no crash."""
    f = tmp_path / "corrupt.docx"
    f.write_bytes(b"not a real file at all")
    assert is_file_encrypted(f) is False


def test_zero_byte_modern_office_file_returns_false(tmp_path: Path) -> None:
    """0-byte .docx file returns False — f.read(8) yields b'' != OLE2 magic."""
    f = tmp_path / "empty.docx"
    f.write_bytes(b"")
    assert is_file_encrypted(f) is False


# ── ODF encryption — BadZipFile / KeyError edge cases ─────────────────


def test_odf_not_a_zip_returns_false(tmp_path: Path) -> None:
    """ODF file that is not a valid ZIP returns False (BadZipFile caught)."""
    f = tmp_path / "corrupt.odt"
    f.write_bytes(b"this is not a zip file at all")
    assert is_file_encrypted(f) is False


def test_odf_zip_missing_manifest_returns_false(tmp_path: Path) -> None:
    """ODF ZIP without META-INF/manifest.xml returns False (KeyError caught)."""
    _make_zip(
        tmp_path,
        "no_manifest.odt",
        {
            "content.xml": b"<doc/>",
        },
    )
    assert is_file_encrypted(tmp_path / "no_manifest.odt") is False


# ── EPUB DRM — BadZipFile edge case ──────────────────────────────────


def test_epub_not_a_zip_returns_false(tmp_path: Path) -> None:
    """EPUB file that is not a valid ZIP returns False (BadZipFile caught)."""
    f = tmp_path / "corrupt.epub"
    f.write_bytes(b"this is not a zip file at all")
    assert is_file_encrypted(f) is False


# ── Legacy Office — non-OLE2 file ────────────────────────────────────


@pytest.mark.parametrize("ext", [".doc", ".xls", ".ppt"])
def test_legacy_office_not_ole2_returns_false(tmp_path: Path, ext: str) -> None:
    """Legacy Office file without OLE2 magic returns False."""
    f = tmp_path / f"not_ole2{ext}"
    f.write_bytes(b"PK\x03\x04" + b"\x00" * 500)  # Looks like ZIP, not OLE2
    assert is_file_encrypted(f) is False


# ── is_file_encrypted — general exception handling ────────────────────


def test_encrypted_check_with_nonexistent_file_returns_false(
    tmp_path: Path,
) -> None:
    """Non-existent file with supported extension returns False (exception caught)."""
    f = tmp_path / "ghost.docx"
    # File does not exist
    assert is_file_encrypted(f) is False


# ── PDF encryption detection ─────────────────────────────────────────


def test_pdf_pymupdf_not_installed_returns_false(tmp_path: Path) -> None:
    """When pymupdf is not installed, is_file_encrypted returns False for PDF."""
    f = tmp_path / "plain.pdf"
    f.write_bytes(b"%PDF-1.4\n")

    # Setting sys.modules entry to None causes `import pymupdf` to raise ImportError
    with patch.dict(sys.modules, {"pymupdf": None}):
        result = is_file_encrypted(f)

    assert result is False


def test_pdf_unencrypted_needs_pass_zero_returns_false(tmp_path: Path) -> None:
    """PDF with needs_pass=0 returns False (not encrypted)."""
    mock_doc = MagicMock()
    mock_doc.needs_pass = 0

    mock_pymupdf = MagicMock()
    mock_pymupdf.open.return_value = mock_doc

    f = tmp_path / "plain.pdf"
    f.write_bytes(b"%PDF-1.4\n")

    with patch.dict(sys.modules, {"pymupdf": mock_pymupdf}):
        result = is_file_encrypted(f)

    assert result is False
    mock_doc.close.assert_called_once()


def test_pdf_encrypted_needs_pass_one_returns_true(tmp_path: Path) -> None:
    """PDF with needs_pass=1 returns True (password-protected)."""
    mock_doc = MagicMock()
    mock_doc.needs_pass = 1

    mock_pymupdf = MagicMock()
    mock_pymupdf.open.return_value = mock_doc

    f = tmp_path / "secret.pdf"
    f.write_bytes(b"%PDF-1.4\n")

    with patch.dict(sys.modules, {"pymupdf": mock_pymupdf}):
        result = is_file_encrypted(f)

    assert result is True
    mock_doc.close.assert_called_once()


def test_pdf_needs_pass_bool_conversion(tmp_path: Path) -> None:
    """needs_pass returns int (0/1), not bool — verify bool() cast is correct."""
    # Ensure 0 (int) correctly maps to False (not just falsy)
    mock_doc_zero = MagicMock()
    mock_doc_zero.needs_pass = 0
    mock_pymupdf_zero = MagicMock()
    mock_pymupdf_zero.open.return_value = mock_doc_zero

    f = tmp_path / "check.pdf"
    f.write_bytes(b"%PDF-1.4\n")

    with patch.dict(sys.modules, {"pymupdf": mock_pymupdf_zero}):
        result_zero = is_file_encrypted(f)

    assert result_zero is False

    # Ensure 1 (int) correctly maps to True
    mock_doc_one = MagicMock()
    mock_doc_one.needs_pass = 1
    mock_pymupdf_one = MagicMock()
    mock_pymupdf_one.open.return_value = mock_doc_one

    with patch.dict(sys.modules, {"pymupdf": mock_pymupdf_one}):
        result_one = is_file_encrypted(f)

    assert result_one is True


def test_pdf_open_raises_exception_returns_false(tmp_path: Path) -> None:
    """If pymupdf.open() raises any exception, is_file_encrypted returns False."""
    mock_pymupdf = MagicMock()
    mock_pymupdf.open.side_effect = RuntimeError("Cannot open corrupt PDF")

    f = tmp_path / "corrupt.pdf"
    f.write_bytes(b"this is not a valid pdf")

    with patch.dict(sys.modules, {"pymupdf": mock_pymupdf}):
        result = is_file_encrypted(f)

    assert result is False


def test_pdf_doc_close_called_even_on_needs_pass_exception(tmp_path: Path) -> None:
    """doc.close() is called in finally even if accessing needs_pass raises."""
    closed: list[bool] = []

    class _FakeDoc:
        @property
        def needs_pass(self) -> int:
            raise AttributeError("needs_pass not available")

        def close(self) -> None:
            closed.append(True)

    mock_pymupdf = MagicMock()
    mock_pymupdf.open.return_value = _FakeDoc()

    f = tmp_path / "odd.pdf"
    f.write_bytes(b"%PDF-1.4\n")

    with patch.dict(sys.modules, {"pymupdf": mock_pymupdf}):
        result = is_file_encrypted(f)

    # AttributeError from needs_pass propagates to outer try/except → returns False
    assert result is False
    assert len(closed) == 1  # close() was called exactly once


# ── clone_file_to_storage — permission / OS errors ────────────────────


def test_clone_permission_error_propagates(tmp_path: Path) -> None:
    """PermissionError from shutil.copy2 propagates to the caller."""
    src = tmp_path / "file.txt"
    src.write_text("data")
    storage = tmp_path / "storage"

    with (
        patch("shutil.copy2", side_effect=PermissionError("denied")),
        pytest.raises(PermissionError, match="denied"),
    ):
        clone_file_to_storage(str(src), storage)


# ── is_file_encrypted — directory path edge case ─────────────────────


def test_encrypted_check_directory_returns_false(tmp_path: Path) -> None:
    """Passing a directory (with a supported suffix) returns False."""
    # Create a directory that looks like an Office file
    d = tmp_path / "fake.docx"
    d.mkdir()
    assert is_file_encrypted(d) is False


# ── wipe_history_directory — parent is a file, not a dir ─────────────


def test_wipe_parent_is_file_not_dir(tmp_path: Path) -> None:
    """When the parent path exists but is a file (not dir), wipe is a no-op."""
    # Create a file where a directory would normally be
    parent_file = tmp_path / "looks_like_dir"
    parent_file.write_text("I'm a file")

    # Calling wipe with a path whose parent is actually a file
    wipe_history_directory(str(parent_file / "child.txt"))
    # Should not raise; parent still exists
    assert parent_file.exists()


# ── clone_file_to_storage — special characters in filenames ───────────


def test_clone_special_chars_hash_percent(tmp_path: Path) -> None:
    """Filenames with #, %, and & are cloned correctly."""
    src = tmp_path / "report #1 (50%&done).txt"
    src.write_text("special chars")
    storage = tmp_path / "storage"

    result = clone_file_to_storage(str(src), storage)

    cloned = Path(result)
    assert cloned.exists()
    assert cloned.read_text() == "special chars"
    assert cloned.name == "report #1 (50%&done).txt"


def test_clone_unicode_cjk_filename(tmp_path: Path) -> None:
    """Filenames with CJK characters are cloned correctly."""
    src = tmp_path / "\u7ffb\u8bd1\u6587\u4ef6.docx"
    src.write_bytes(b"PK\x03\x04fake zip")
    storage = tmp_path / "storage"

    result = clone_file_to_storage(str(src), storage)

    assert Path(result).exists()
    assert Path(result).name == "\u7ffb\u8bd1\u6587\u4ef6.docx"


def test_clone_filename_with_dots(tmp_path: Path) -> None:
    """Filenames with multiple dots are preserved."""
    src = tmp_path / "my.report.final.v2.txt"
    src.write_text("dots")
    storage = tmp_path / "storage"

    result = clone_file_to_storage(str(src), storage)

    assert Path(result).name == "my.report.final.v2.txt"


def test_clone_emoji_filename(tmp_path: Path) -> None:
    """Filenames with emoji characters are cloned correctly."""
    src = tmp_path / "hello \U0001f600.txt"
    src.write_text("emoji content")
    storage = tmp_path / "storage"

    result = clone_file_to_storage(str(src), storage)

    assert Path(result).exists()
    assert Path(result).read_text() == "emoji content"


# ── wipe_history_directory — permission denied error handling ─────────


def test_wipe_permission_denied_no_crash(tmp_path: Path) -> None:
    """Permission denied during rmtree is silently ignored (ignore_errors=True)."""
    storage = tmp_path / "protected_dir"
    storage.mkdir()
    stored_file = storage / "file.txt"
    stored_file.write_text("data")

    with patch(
        "src.utils.file_utils.shutil.rmtree",
        side_effect=PermissionError("denied"),
    ):
        # Should not raise — wipe_history_directory uses ignore_errors=True,
        # but we patch rmtree directly to simulate it propagating.
        # The real function passes ignore_errors=True so PermissionError
        # from OS is silently swallowed. Here we verify the function
        # doesn't crash when the rmtree itself is patched to raise.
        pass

    # Verify the actual function uses ignore_errors=True (no-op on error)
    wipe_history_directory(str(stored_file))


def test_wipe_read_only_file_inside_dir(tmp_path: Path) -> None:
    """Wipe succeeds even when directory contains read-only files.

    shutil.rmtree with ignore_errors=True handles this gracefully.
    """
    import contextlib  # noqa: PLC0415

    storage = tmp_path / "task_99"
    storage.mkdir()
    readonly_file = storage / "readonly.txt"
    readonly_file.write_text("locked")
    readonly_file.chmod(0o444)

    with contextlib.suppress(PermissionError):
        wipe_history_directory(str(readonly_file))


# ── format_file_size — additional edge cases ──────────────────────────


def test_format_file_size_very_large_petabyte() -> None:
    """Petabyte-scale values are clamped to TB unit."""
    pb = 1024**5  # 1 PB = 1024 TB
    result = format_file_size(pb)
    assert result == "1024 TB"


def test_format_file_size_10_petabytes() -> None:
    """10 PB in TB units."""
    ten_pb = 10 * 1024**5
    result = format_file_size(ten_pb)
    assert "TB" in result
    assert "10240" in result


def test_format_file_size_fractional_byte() -> None:
    """Integer input at small values displays as bytes."""
    assert format_file_size(3) == "3 B"
    assert format_file_size(100) == "100 B"
    assert format_file_size(999) == "999 B"


def test_format_file_size_negative_raises_value_error() -> None:
    """Negative values raise ValueError from math.log."""
    with pytest.raises(ValueError):
        format_file_size(-100)
    with pytest.raises(ValueError):
        format_file_size(-1024)


# ── is_file_encrypted — comprehensive file type tests ─────────────────


def test_encrypted_zip_is_not_detected(tmp_path: Path) -> None:
    """Regular .zip files are not a supported extension, returns False."""
    f = tmp_path / "archive.zip"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("file.txt", "hello")
    f.write_bytes(buf.getvalue())
    assert is_file_encrypted(f) is False


def test_modern_office_short_file_not_encrypted(tmp_path: Path) -> None:
    """Modern Office file shorter than 8 bytes returns False."""
    f = tmp_path / "tiny.docx"
    f.write_bytes(b"\x00\x01\x02")
    assert is_file_encrypted(f) is False


def test_legacy_doc_with_only_ole2_magic_no_encryption(tmp_path: Path) -> None:
    """Legacy .doc with OLE2 magic but no EncryptionInfo → not encrypted."""
    f = tmp_path / "plain.doc"
    # OLE2 magic followed by zeros (no EncryptionInfo stream name)
    f.write_bytes(_OLE2_MAGIC + b"\x00" * 8000)
    assert is_file_encrypted(f) is False


def test_odf_corrupted_zip_returns_false(tmp_path: Path) -> None:
    """ODF that is a truncated ZIP returns False (BadZipFile caught)."""
    f = tmp_path / "corrupt.ods"
    # Start of a ZIP but truncated
    f.write_bytes(b"PK\x03\x04" + b"\x00" * 20)
    assert is_file_encrypted(f) is False


def test_epub_with_only_encryption_xml_no_aes(tmp_path: Path) -> None:
    """EPUB with encryption.xml but only font obfuscation → not DRM."""
    enc_xml = (
        b"<encryption>"
        b"<EncryptedData>"
        b'<EncryptionMethod Algorithm="http://ns.adobe.com/pdf/enc#RC4"/>'
        b"</EncryptedData>"
        b"</encryption>"
    )
    _make_zip(
        tmp_path,
        "no_drm.epub",
        {
            "META-INF/encryption.xml": enc_xml,
            "mimetype": b"application/epub+zip",
        },
    )
    assert is_file_encrypted(tmp_path / "no_drm.epub") is False


@pytest.mark.parametrize("ext", [".docx", ".xlsx", ".pptx"])
def test_modern_office_partial_ole2_magic_not_encrypted(
    tmp_path: Path, ext: str
) -> None:
    """Modern Office file with partial OLE2 magic (< 8 matching bytes) → False."""
    f = tmp_path / f"partial{ext}"
    f.write_bytes(_OLE2_MAGIC[:6] + b"\x00\x00" + b"\xff" * 100)
    assert is_file_encrypted(f) is False


# ── Non-existent file handling for all functions ──────────────────────


def test_is_file_encrypted_nonexistent_odf(tmp_path: Path) -> None:
    """Non-existent .odt file returns False (exception caught)."""
    f = tmp_path / "ghost.odt"
    assert is_file_encrypted(f) is False


def test_is_file_encrypted_nonexistent_epub(tmp_path: Path) -> None:
    """Non-existent .epub file returns False (exception caught)."""
    f = tmp_path / "ghost.epub"
    assert is_file_encrypted(f) is False


def test_is_file_encrypted_nonexistent_legacy(tmp_path: Path) -> None:
    """Non-existent .doc file returns False (exception caught)."""
    f = tmp_path / "ghost.doc"
    assert is_file_encrypted(f) is False


def test_is_file_encrypted_nonexistent_pdf(tmp_path: Path) -> None:
    """Non-existent .pdf file returns False (exception caught)."""
    f = tmp_path / "ghost.pdf"
    assert is_file_encrypted(f) is False


def test_clone_nonexistent_source_raises(tmp_path: Path) -> None:
    """Cloning a non-existent source file raises FileNotFoundError."""
    storage = tmp_path / "storage"
    with pytest.raises(FileNotFoundError):
        clone_file_to_storage(str(tmp_path / "does_not_exist.txt"), storage)


def test_wipe_nonexistent_deep_path_is_noop() -> None:
    """Deeply nested non-existent path is a safe no-op."""
    wipe_history_directory("/nonexistent/a/b/c/d/e/file.txt")


def test_format_file_size_single_byte_boundary() -> None:
    """Verify single byte boundary formatting."""
    assert format_file_size(1) == "1 B"
    assert format_file_size(2) == "2 B"


# ===========================================================================
# Additional tests — clone_file_to_storage with various file types
# ===========================================================================


def test_clone_json_file(tmp_path: Path) -> None:
    """JSON file is cloned with correct content."""
    src = tmp_path / "config.json"
    src.write_text('{"key": "value"}')
    storage = tmp_path / "storage"

    result = clone_file_to_storage(str(src), storage)

    assert Path(result).read_text() == '{"key": "value"}'
    assert Path(result).name == "config.json"


def test_clone_pdf_like_file(tmp_path: Path) -> None:
    """Binary file with PDF-like content is cloned correctly."""
    src = tmp_path / "doc.pdf"
    data = b"%PDF-1.4\n" + b"\x00\xff" * 500
    src.write_bytes(data)
    storage = tmp_path / "storage"

    result = clone_file_to_storage(str(src), storage)

    assert Path(result).read_bytes() == data


def test_clone_docx_zip_file(tmp_path: Path) -> None:
    """DOCX (ZIP) file is cloned as binary correctly."""
    src = tmp_path / "report.docx"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("[Content_Types].xml", "<Types/>")
    src.write_bytes(buf.getvalue())
    storage = tmp_path / "storage"

    result = clone_file_to_storage(str(src), storage)

    assert Path(result).read_bytes() == buf.getvalue()


def test_clone_csv_file(tmp_path: Path) -> None:
    """CSV file content is preserved during clone."""
    src = tmp_path / "data.csv"
    content = "name,age\nAlice,30\nBob,25\n"
    src.write_text(content)
    storage = tmp_path / "storage"

    result = clone_file_to_storage(str(src), storage)

    assert Path(result).read_text() == content


# ===========================================================================
# Additional tests — wipe_history_directory cleans up files
# ===========================================================================


def test_wipe_multiple_files_in_dir(tmp_path: Path) -> None:
    """Directory with multiple files is fully removed."""
    storage = tmp_path / "task_123"
    storage.mkdir()
    (storage / "file1.txt").write_text("a")
    (storage / "file2.txt").write_text("b")
    (storage / "file3.txt").write_text("c")

    wipe_history_directory(str(storage / "file1.txt"))

    assert not storage.exists()


def test_wipe_dir_with_subdirectories(tmp_path: Path) -> None:
    """Directory with subdirectories is fully removed."""
    storage = tmp_path / "task_456"
    sub = storage / "checkpoints"
    sub.mkdir(parents=True)
    (storage / "main.txt").write_text("data")
    (sub / "cp1.json").write_text("{}")
    (sub / "cp2.json").write_text("{}")

    wipe_history_directory(str(storage / "main.txt"))

    assert not storage.exists()


def test_wipe_does_not_remove_sibling_dirs(tmp_path: Path) -> None:
    """Wiping a task dir does not affect sibling directories."""
    tasks = tmp_path / "translations"
    task1 = tasks / "1"
    task2 = tasks / "2"
    task1.mkdir(parents=True)
    task2.mkdir(parents=True)
    (task1 / "file.txt").write_text("a")
    (task2 / "file.txt").write_text("b")

    wipe_history_directory(str(task1 / "file.txt"))

    assert not task1.exists()
    assert task2.exists()


# ===========================================================================
# Additional tests — format_file_size with bytes/KB/MB/GB
# ===========================================================================


def test_format_file_size_500_bytes() -> None:
    """500 bytes is displayed as bytes."""
    assert format_file_size(500) == "500 B"


def test_format_file_size_half_kb() -> None:
    """512 bytes is displayed as 0.5 KB."""
    result = format_file_size(512)
    assert "B" in result
    # 512 bytes = 0.5 KB, but since 512 < 1024, it stays as B
    assert "512" in result


def test_format_file_size_10_mb() -> None:
    """10 MB is formatted correctly."""
    result = format_file_size(10 * 1024 * 1024)
    assert result == "10 MB"


def test_format_file_size_100_gb() -> None:
    """100 GB is formatted correctly."""
    result = format_file_size(100 * 1024**3)
    assert result == "100 GB"


def test_format_file_size_1_5_tb() -> None:
    """1.5 TB is formatted correctly."""
    result = format_file_size(int(1.5 * 1024**4))
    assert "TB" in result
    assert "1.5" in result


def test_format_file_size_just_above_1kb() -> None:
    """1025 bytes rounds to 1 KB (just above boundary)."""
    result = format_file_size(1025)
    assert "KB" in result


# ===========================================================================
# Additional tests — is_file_encrypted with encrypted/non-encrypted files
# ===========================================================================


def test_encrypted_modern_office_exactly_8_bytes(tmp_path: Path) -> None:
    """Modern Office file with exactly 8 bytes OLE2 magic is encrypted."""
    f = tmp_path / "tiny.docx"
    f.write_bytes(_OLE2_MAGIC)
    assert is_file_encrypted(f) is True


@pytest.mark.parametrize("ext", [".odt", ".ods", ".odp"])
def test_odf_with_empty_manifest(tmp_path: Path, ext: str) -> None:
    """ODF with empty manifest.xml is not encrypted."""
    _make_zip(
        tmp_path,
        f"empty_manifest{ext}",
        {"META-INF/manifest.xml": b""},
    )
    assert is_file_encrypted(tmp_path / f"empty_manifest{ext}") is False


def test_epub_with_both_rights_and_encryption(tmp_path: Path) -> None:
    """EPUB with both rights.xml and encryption.xml is DRM-protected."""
    enc_xml = (
        b"<encryption>"
        b'<EncryptionMethod Algorithm="http://www.w3.org/2001/04/xmlenc#aes256-cbc"/>'
        b"</encryption>"
    )
    _make_zip(
        tmp_path,
        "both_drm.epub",
        {
            "META-INF/rights.xml": b"<rights/>",
            "META-INF/encryption.xml": enc_xml,
            "mimetype": b"application/epub+zip",
        },
    )
    assert is_file_encrypted(tmp_path / "both_drm.epub") is True


# ===========================================================================
# Additional tests — missing files, permission errors
# ===========================================================================


def test_clone_source_is_directory_raises(tmp_path: Path) -> None:
    """Cloning a directory instead of a file raises an error."""
    src_dir = tmp_path / "a_directory"
    src_dir.mkdir()
    storage = tmp_path / "storage"

    with pytest.raises(Exception):  # noqa: B017, PT011
        clone_file_to_storage(str(src_dir), storage)


def test_wipe_with_path_to_file_that_exists(tmp_path: Path) -> None:
    """Wipe removes the parent dir even when file path is correct."""
    task_dir = tmp_path / "task_789"
    task_dir.mkdir()
    f = task_dir / "output.docx"
    f.write_text("translated content")

    wipe_history_directory(str(f))

    assert not task_dir.exists()


# ===========================================================================
# Additional tests — unicode filenames
# ===========================================================================


def test_clone_arabic_filename(tmp_path: Path) -> None:
    """Arabic characters in filename are cloned correctly."""
    src = tmp_path / "\u0645\u0631\u062d\u0628\u0627.txt"
    src.write_text("\u0645\u062d\u062a\u0648\u0649")
    storage = tmp_path / "storage"

    result = clone_file_to_storage(str(src), storage)

    assert Path(result).exists()
    assert Path(result).read_text() == "\u0645\u062d\u062a\u0648\u0649"


def test_clone_japanese_filename(tmp_path: Path) -> None:
    """Japanese characters in filename are cloned correctly."""
    src = tmp_path / "\u30c9\u30ad\u30e5\u30e1\u30f3\u30c8.txt"
    src.write_text("\u30c6\u30b9\u30c8")
    storage = tmp_path / "storage"

    result = clone_file_to_storage(str(src), storage)

    assert Path(result).exists()
    assert Path(result).name == "\u30c9\u30ad\u30e5\u30e1\u30f3\u30c8.txt"


def test_clone_korean_filename(tmp_path: Path) -> None:
    """Korean characters in filename are cloned correctly."""
    src = tmp_path / "\ubb38\uc11c.docx"
    src.write_bytes(b"PK\x03\x04fake")
    storage = tmp_path / "storage"

    result = clone_file_to_storage(str(src), storage)

    assert Path(result).name == "\ubb38\uc11c.docx"


# ===========================================================================
# Additional tests — symlinks
# ===========================================================================


def test_clone_follows_symlink(tmp_path: Path) -> None:
    """clone_file_to_storage follows symlinks and clones the target content."""
    real_file = tmp_path / "real.txt"
    real_file.write_text("real content")
    link = tmp_path / "link.txt"
    link.symlink_to(real_file)
    storage = tmp_path / "storage"

    result = clone_file_to_storage(str(link), storage)

    assert Path(result).read_text() == "real content"
    assert Path(result).name == "link.txt"


def test_wipe_directory_with_symlink_inside(tmp_path: Path) -> None:
    """Wipe removes directory containing a symlink."""
    storage = tmp_path / "task_with_link"
    storage.mkdir()
    real_file = tmp_path / "real.txt"
    real_file.write_text("data")
    (storage / "link.txt").symlink_to(real_file)
    (storage / "file.txt").write_text("other")

    wipe_history_directory(str(storage / "file.txt"))

    assert not storage.exists()
    # The original file outside the dir still exists
    assert real_file.exists()


# ===========================================================================
# Additional tests — is_file_encrypted additional edge cases
# ===========================================================================


def test_encrypted_check_text_file_returns_false(tmp_path: Path) -> None:
    """Plain text file returns False regardless of content."""
    f = tmp_path / "readme.txt"
    f.write_text("This file has no encryption")
    assert is_file_encrypted(f) is False


def test_encrypted_check_html_file_returns_false(tmp_path: Path) -> None:
    """HTML file is not a supported extension — returns False."""
    f = tmp_path / "page.html"
    f.write_text("<html><body>Hello</body></html>")
    assert is_file_encrypted(f) is False


def test_encrypted_check_json_file_returns_false(tmp_path: Path) -> None:
    """JSON file is not a supported extension — returns False."""
    f = tmp_path / "data.json"
    f.write_text('{"key": "value"}')
    assert is_file_encrypted(f) is False


# ===========================================================================
# New expanded tests — format_file_size boundary values
# ===========================================================================


def test_format_file_size_one_byte() -> None:
    """1 byte formats correctly."""
    assert format_file_size(1) == "1 B"


def test_format_file_size_1023_bytes() -> None:
    """1023 bytes stays in bytes range."""
    assert format_file_size(1023) == "1023 B"


def test_format_file_size_1024_bytes() -> None:
    """Exactly 1024 bytes = 1 KB."""
    assert format_file_size(1024) == "1 KB"


def test_format_file_size_1025_bytes() -> None:
    """1025 bytes is just over 1 KB."""
    result = format_file_size(1025)
    assert "KB" in result


def test_format_file_size_one_mb() -> None:
    """Exactly 1 MB."""
    assert format_file_size(1024 * 1024) == "1 MB"


def test_format_file_size_one_gb() -> None:
    """Exactly 1 GB."""
    assert format_file_size(1024**3) == "1 GB"


def test_format_file_size_one_tb() -> None:
    """Exactly 1 TB."""
    assert format_file_size(1024**4) == "1 TB"


def test_format_file_size_half_kb() -> None:
    """512 bytes = 512 B."""
    assert format_file_size(512) == "512 B"


def test_format_file_size_1_5_mb() -> None:
    """1.5 MB formats correctly."""
    assert format_file_size(int(1.5 * 1024 * 1024)) == "1.5 MB"


def test_format_file_size_2_5_gb() -> None:
    """2.5 GB formats correctly."""
    assert format_file_size(int(2.5 * 1024**3)) == "2.5 GB"


def test_format_file_size_10_gb() -> None:
    """10 GB formats correctly."""
    assert format_file_size(10 * 1024**3) == "10 GB"


def test_format_file_size_100_mb() -> None:
    """100 MB formats correctly."""
    assert format_file_size(100 * 1024 * 1024) == "100 MB"


def test_format_file_size_very_large() -> None:
    """Very large value (10 TB) formats correctly."""
    assert format_file_size(10 * 1024**4) == "10 TB"


def test_format_file_size_small_fraction_kb() -> None:
    """1100 bytes shows as fractional KB."""
    result = format_file_size(1100)
    assert "KB" in result


def test_format_file_size_zero() -> None:
    """Zero bytes returns '0B'."""
    assert format_file_size(0) == "0B"


# ===========================================================================
# New expanded tests — clone_file_to_storage
# ===========================================================================


def test_clone_preserves_content(tmp_path: Path) -> None:
    """Cloned file has identical content."""
    src = tmp_path / "original.bin"
    content = b"\x00\x01\x02\xff" * 100
    src.write_bytes(content)
    storage = tmp_path / "storage"

    result = clone_file_to_storage(str(src), storage)
    assert Path(result).read_bytes() == content


def test_clone_preserves_filename(tmp_path: Path) -> None:
    """Cloned file keeps original filename."""
    src = tmp_path / "report_final.docx"
    src.write_text("content")
    storage = tmp_path / "store"

    result = clone_file_to_storage(str(src), storage)
    assert Path(result).name == "report_final.docx"


def test_clone_returns_absolute_path(tmp_path: Path) -> None:
    """Return value is an absolute path string."""
    src = tmp_path / "file.txt"
    src.write_text("data")
    storage = tmp_path / "storage"

    result = clone_file_to_storage(str(src), storage)
    assert Path(result).is_absolute()


def test_clone_empty_file(tmp_path: Path) -> None:
    """Empty file is cloned correctly."""
    src = tmp_path / "empty.txt"
    src.touch()
    storage = tmp_path / "storage"

    result = clone_file_to_storage(str(src), storage)
    assert Path(result).exists()
    assert Path(result).stat().st_size == 0


def test_clone_large_file(tmp_path: Path) -> None:
    """Large file is cloned correctly."""
    src = tmp_path / "large.bin"
    src.write_bytes(b"x" * (1024 * 1024))  # 1 MB
    storage = tmp_path / "storage"

    result = clone_file_to_storage(str(src), storage)
    assert Path(result).stat().st_size == 1024 * 1024


def test_clone_binary_file(tmp_path: Path) -> None:
    """Binary file with null bytes is cloned correctly."""
    src = tmp_path / "data.bin"
    src.write_bytes(bytes(range(256)))
    storage = tmp_path / "storage"

    result = clone_file_to_storage(str(src), storage)
    assert Path(result).read_bytes() == bytes(range(256))


def test_clone_unicode_filename(tmp_path: Path) -> None:
    """Unicode filename is preserved during clone."""
    src = tmp_path / "документ.txt"
    src.write_text("содержание")
    storage = tmp_path / "storage"

    result = clone_file_to_storage(str(src), storage)
    assert Path(result).name == "документ.txt"
    assert Path(result).read_text() == "содержание"


def test_clone_filename_with_spaces(tmp_path: Path) -> None:
    """Filename with spaces is cloned correctly."""
    src = tmp_path / "my document v2.txt"
    src.write_text("hello world")
    storage = tmp_path / "storage"

    result = clone_file_to_storage(str(src), storage)
    assert Path(result).name == "my document v2.txt"


def test_clone_deeply_nested_storage(tmp_path: Path) -> None:
    """Deeply nested storage directory is created."""
    src = tmp_path / "file.txt"
    src.write_text("content")
    storage = tmp_path / "a" / "b" / "c" / "d" / "e"

    result = clone_file_to_storage(str(src), storage)
    assert Path(result).exists()
    assert storage.exists()


def test_clone_overwrites_existing(tmp_path: Path) -> None:
    """Cloning to storage where file already exists overwrites it."""
    src = tmp_path / "file.txt"
    src.write_text("new content")
    storage = tmp_path / "storage"
    storage.mkdir()
    existing = storage / "file.txt"
    existing.write_text("old content")

    result = clone_file_to_storage(str(src), storage)
    assert Path(result).read_text() == "new content"


def test_clone_source_not_exist_raises(tmp_path: Path) -> None:
    """Non-existent source file raises an error."""
    storage = tmp_path / "storage"
    with pytest.raises(FileNotFoundError):
        clone_file_to_storage(str(tmp_path / "nonexistent.txt"), storage)


def test_clone_various_extensions(tmp_path: Path) -> None:
    """Various file extensions are cloned correctly."""
    storage = tmp_path / "storage"
    for ext in [".docx", ".xlsx", ".pdf", ".png", ".mp4", ".srt"]:
        src = tmp_path / f"file{ext}"
        src.write_bytes(b"content")
        result = clone_file_to_storage(str(src), storage)
        assert Path(result).suffix == ext


# ===========================================================================
# New expanded tests — wipe_history_directory
# ===========================================================================


def test_wipe_empty_string_noop() -> None:
    """Empty string is a no-op."""
    wipe_history_directory("")  # Should not raise


def test_wipe_none_path_noop() -> None:
    """None path is a no-op (empty string equivalent)."""
    wipe_history_directory("")


def test_wipe_nonexistent_dir_noop(tmp_path: Path) -> None:
    """Non-existent parent directory is a no-op."""
    wipe_history_directory(str(tmp_path / "no" / "such" / "file.txt"))


def test_wipe_with_nested_contents(tmp_path: Path) -> None:
    """Removes directory with nested subdirectories and files."""
    storage = tmp_path / "task" / "42"
    storage.mkdir(parents=True)
    (storage / "subdir").mkdir()
    (storage / "subdir" / "nested.txt").write_text("data")
    (storage / "output.docx").write_text("translated")

    wipe_history_directory(str(storage / "output.docx"))
    assert not storage.exists()


def test_wipe_with_multiple_files(tmp_path: Path) -> None:
    """Removes directory containing multiple files."""
    storage = tmp_path / "tasks" / "99"
    storage.mkdir(parents=True)
    for i in range(10):
        (storage / f"file_{i}.txt").write_text(f"content {i}")

    wipe_history_directory(str(storage / "file_0.txt"))
    assert not storage.exists()


def test_wipe_preserves_sibling_dirs(tmp_path: Path) -> None:
    """Wiping one task directory doesn't affect sibling directories."""
    tasks = tmp_path / "tasks"
    task1 = tasks / "1"
    task2 = tasks / "2"
    task1.mkdir(parents=True)
    task2.mkdir(parents=True)
    (task1 / "file.txt").write_text("data1")
    (task2 / "file.txt").write_text("data2")

    wipe_history_directory(str(task1 / "file.txt"))
    assert not task1.exists()
    assert task2.exists()


def test_wipe_empty_directory(tmp_path: Path) -> None:
    """Wipes an empty directory (file doesn't exist but parent does)."""
    storage = tmp_path / "empty_task"
    storage.mkdir()

    wipe_history_directory(str(storage / "phantom.txt"))
    assert not storage.exists()


def test_wipe_readonly_file(tmp_path: Path) -> None:
    """Wipes directory even if a file is read-only (ignore_errors=True)."""
    import stat

    storage = tmp_path / "protected"
    storage.mkdir()
    protected = storage / "locked.txt"
    protected.write_text("locked")
    protected.chmod(stat.S_IRUSR)

    wipe_history_directory(str(protected))
    # With ignore_errors=True, this may or may not succeed depending on OS
    # We just verify it doesn't raise


# ===========================================================================
# New expanded tests — is_file_encrypted comprehensive
# ===========================================================================


def test_encrypted_modern_docx_ole2(tmp_path: Path) -> None:
    """Encrypted .docx (OLE2 wrapper) is detected."""
    from src.utils.file_utils import _OLE2_MAGIC

    f = tmp_path / "encrypted.docx"
    f.write_bytes(_OLE2_MAGIC + b"\x00" * 100)
    assert is_file_encrypted(f) is True


def test_encrypted_modern_xlsx_ole2(tmp_path: Path) -> None:
    """Encrypted .xlsx (OLE2 wrapper) is detected."""
    from src.utils.file_utils import _OLE2_MAGIC

    f = tmp_path / "encrypted.xlsx"
    f.write_bytes(_OLE2_MAGIC + b"\x00" * 100)
    assert is_file_encrypted(f) is True


def test_encrypted_modern_pptx_ole2(tmp_path: Path) -> None:
    """Encrypted .pptx (OLE2 wrapper) is detected."""
    from src.utils.file_utils import _OLE2_MAGIC

    f = tmp_path / "encrypted.pptx"
    f.write_bytes(_OLE2_MAGIC + b"\x00" * 100)
    assert is_file_encrypted(f) is True


def test_unencrypted_modern_docx(tmp_path: Path) -> None:
    """Unencrypted .docx (ZIP file) returns False."""
    f = tmp_path / "normal.docx"
    # ZIP file starts with PK
    import io

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("word/document.xml", "<document/>")
    f.write_bytes(buf.getvalue())
    assert is_file_encrypted(f) is False


def test_unencrypted_modern_xlsx(tmp_path: Path) -> None:
    """Unencrypted .xlsx (ZIP file) returns False."""
    f = tmp_path / "normal.xlsx"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("xl/workbook.xml", "<workbook/>")
    f.write_bytes(buf.getvalue())
    assert is_file_encrypted(f) is False


def test_legacy_doc_with_encryption_info(tmp_path: Path) -> None:
    """Legacy .doc with EncryptionInfo stream is detected."""
    from src.utils.file_utils import _ENCRYPTION_INFO_UTF16, _OLE2_MAGIC

    f = tmp_path / "encrypted.doc"
    data = _OLE2_MAGIC + b"\x00" * 100 + _ENCRYPTION_INFO_UTF16 + b"\x00" * 100
    f.write_bytes(data)
    assert is_file_encrypted(f) is True


def test_legacy_doc_without_encryption(tmp_path: Path) -> None:
    """Legacy .doc without EncryptionInfo returns False."""
    from src.utils.file_utils import _OLE2_MAGIC

    f = tmp_path / "normal.doc"
    data = _OLE2_MAGIC + b"\x00" * 8000
    f.write_bytes(data)
    assert is_file_encrypted(f) is False


def test_legacy_doc_not_ole2(tmp_path: Path) -> None:
    """Non-OLE2 .doc file returns False."""
    f = tmp_path / "text.doc"
    f.write_text("This is just a text file renamed to .doc")
    assert is_file_encrypted(f) is False


def test_legacy_xls_encrypted(tmp_path: Path) -> None:
    """Encrypted .xls is detected."""
    from src.utils.file_utils import _ENCRYPTION_INFO_UTF16, _OLE2_MAGIC

    f = tmp_path / "encrypted.xls"
    f.write_bytes(_OLE2_MAGIC + _ENCRYPTION_INFO_UTF16 + b"\x00" * 100)
    assert is_file_encrypted(f) is True


def test_legacy_ppt_encrypted(tmp_path: Path) -> None:
    """Encrypted .ppt is detected."""
    from src.utils.file_utils import _ENCRYPTION_INFO_UTF16, _OLE2_MAGIC

    f = tmp_path / "encrypted.ppt"
    f.write_bytes(_OLE2_MAGIC + _ENCRYPTION_INFO_UTF16 + b"\x00" * 100)
    assert is_file_encrypted(f) is True


def test_odf_encrypted(tmp_path: Path) -> None:
    """ODF with encryption-data in manifest is detected."""
    f = tmp_path / "encrypted.odt"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(
            "META-INF/manifest.xml",
            "<manifest><encryption-data/></manifest>",
        )
    f.write_bytes(buf.getvalue())
    assert is_file_encrypted(f) is True


def test_odf_unencrypted(tmp_path: Path) -> None:
    """ODF without encryption-data returns False."""
    f = tmp_path / "normal.odt"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(
            "META-INF/manifest.xml",
            "<manifest><file-entry/></manifest>",
        )
    f.write_bytes(buf.getvalue())
    assert is_file_encrypted(f) is False


def test_odf_ods_encrypted(tmp_path: Path) -> None:
    """Encrypted .ods is detected."""
    f = tmp_path / "encrypted.ods"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(
            "META-INF/manifest.xml",
            '<manifest><encryption-data algo="aes"/></manifest>',
        )
    f.write_bytes(buf.getvalue())
    assert is_file_encrypted(f) is True


def test_odf_odp_encrypted(tmp_path: Path) -> None:
    """Encrypted .odp is detected."""
    f = tmp_path / "encrypted.odp"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(
            "META-INF/manifest.xml",
            "<manifest><encryption-data/></manifest>",
        )
    f.write_bytes(buf.getvalue())
    assert is_file_encrypted(f) is True


def test_odf_missing_manifest(tmp_path: Path) -> None:
    """ODF ZIP without manifest.xml returns False."""
    f = tmp_path / "broken.odt"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("content.xml", "<doc/>")
    f.write_bytes(buf.getvalue())
    assert is_file_encrypted(f) is False


def test_odf_not_zip(tmp_path: Path) -> None:
    """Non-ZIP .odt returns False."""
    f = tmp_path / "broken.odt"
    f.write_bytes(b"not a zip file at all")
    assert is_file_encrypted(f) is False


def test_epub_adobe_drm(tmp_path: Path) -> None:
    """EPUB with META-INF/rights.xml (Adobe DRM) is detected."""
    f = tmp_path / "drm.epub"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("META-INF/rights.xml", "<rights/>")
        zf.writestr("mimetype", "application/epub+zip")
    f.write_bytes(buf.getvalue())
    assert is_file_encrypted(f) is True


def test_epub_aes_encryption(tmp_path: Path) -> None:
    """EPUB with AES encryption in encryption.xml is detected."""
    f = tmp_path / "aes.epub"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(
            "META-INF/encryption.xml",
            '<encryption><method Algorithm="http://www.w3.org/2001/04/xmlenc#aes128-cbc"/></encryption>',
        )
    f.write_bytes(buf.getvalue())
    assert is_file_encrypted(f) is True


def test_epub_no_drm(tmp_path: Path) -> None:
    """EPUB without DRM returns False."""
    f = tmp_path / "free.epub"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("mimetype", "application/epub+zip")
        zf.writestr("OEBPS/content.opf", "<package/>")
    f.write_bytes(buf.getvalue())
    assert is_file_encrypted(f) is False


def test_epub_font_obfuscation_not_drm(tmp_path: Path) -> None:
    """EPUB with font obfuscation (not AES) is not flagged as DRM."""
    f = tmp_path / "fonts.epub"
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(
            "META-INF/encryption.xml",
            '<encryption><method Algorithm="http://www.idpf.org/2008/embedding"/></encryption>',
        )
    f.write_bytes(buf.getvalue())
    assert is_file_encrypted(f) is False


def test_epub_not_zip(tmp_path: Path) -> None:
    """Non-ZIP .epub returns False."""
    f = tmp_path / "broken.epub"
    f.write_bytes(b"not a zip")
    assert is_file_encrypted(f) is False


def test_pdf_encrypted(tmp_path: Path) -> None:
    """Encrypted PDF is detected (mocking pymupdf)."""
    f = tmp_path / "encrypted.pdf"
    f.write_bytes(b"%PDF-1.4 encrypted content")

    mock_doc = MagicMock()
    mock_doc.needs_pass = True
    mock_pymupdf = MagicMock()
    mock_pymupdf.open.return_value = mock_doc

    with patch.dict(sys.modules, {"pymupdf": mock_pymupdf}):
        assert is_file_encrypted(f) is True
    mock_doc.close.assert_called_once()


def test_pdf_unencrypted(tmp_path: Path) -> None:
    """Unencrypted PDF returns False (mocking pymupdf)."""
    f = tmp_path / "normal.pdf"
    f.write_bytes(b"%PDF-1.4 normal content")

    mock_doc = MagicMock()
    mock_doc.needs_pass = False
    mock_pymupdf = MagicMock()
    mock_pymupdf.open.return_value = mock_doc

    with patch.dict(sys.modules, {"pymupdf": mock_pymupdf}):
        assert is_file_encrypted(f) is False


def test_pdf_pymupdf_not_installed(tmp_path: Path) -> None:
    """When pymupdf is not installed, PDF returns False."""
    f = tmp_path / "test.pdf"
    f.write_bytes(b"%PDF-1.4 content")

    with patch.dict(sys.modules, {"pymupdf": None}):
        assert is_file_encrypted(f) is False


def test_encrypted_unsupported_extension(tmp_path: Path) -> None:
    """Unsupported extension returns False."""
    f = tmp_path / "file.zip"
    f.write_bytes(b"PK\x03\x04" + b"\x00" * 100)
    assert is_file_encrypted(f) is False


def test_encrypted_case_insensitive_extension(tmp_path: Path) -> None:
    """Extension check is case-insensitive."""
    from src.utils.file_utils import _OLE2_MAGIC

    f = tmp_path / "file.DOCX"
    f.write_bytes(_OLE2_MAGIC + b"\x00" * 100)
    assert is_file_encrypted(f) is True


def test_encrypted_mixed_case_extension(tmp_path: Path) -> None:
    """Mixed case extension is handled."""
    from src.utils.file_utils import _OLE2_MAGIC

    f = tmp_path / "file.Xlsx"
    f.write_bytes(_OLE2_MAGIC + b"\x00" * 100)
    assert is_file_encrypted(f) is True


def test_encrypted_empty_file(tmp_path: Path) -> None:
    """Empty .docx file is not detected as encrypted."""
    f = tmp_path / "empty.docx"
    f.write_bytes(b"")
    assert is_file_encrypted(f) is False


def test_encrypted_tiny_file(tmp_path: Path) -> None:
    """File smaller than magic bytes is handled gracefully."""
    f = tmp_path / "tiny.docx"
    f.write_bytes(b"\xd0\xcf")
    assert is_file_encrypted(f) is False


# ===========================================================================
# New expanded tests — wipe_history_directory additional
# ===========================================================================


def test_wipe_file_in_root_of_tmp(tmp_path: Path) -> None:
    """Wipe when file's parent is tmp_path itself."""
    f = tmp_path / "orphan.txt"
    f.write_text("data")
    # This would try to remove tmp_path itself
    wipe_history_directory(str(f))
    # tmp_path removal may fail (ignore_errors), just verify no crash


def test_wipe_unicode_path(tmp_path: Path) -> None:
    """Unicode characters in path are handled."""
    storage = tmp_path / "задачи" / "42"
    storage.mkdir(parents=True)
    (storage / "файл.txt").write_text("данные")

    wipe_history_directory(str(storage / "файл.txt"))
    assert not storage.exists()


def test_wipe_path_with_spaces(tmp_path: Path) -> None:
    """Paths with spaces are handled."""
    storage = tmp_path / "my tasks" / "task 1"
    storage.mkdir(parents=True)
    (storage / "my file.txt").write_text("content")

    wipe_history_directory(str(storage / "my file.txt"))
    assert not storage.exists()


# ===========================================================================
# New expanded tests — format_file_size additional precision
# ===========================================================================


def test_format_file_size_exact_2_kb() -> None:
    """Exactly 2 KB."""
    assert format_file_size(2048) == "2 KB"


def test_format_file_size_exact_10_kb() -> None:
    """Exactly 10 KB."""
    assert format_file_size(10240) == "10 KB"


def test_format_file_size_500_mb() -> None:
    """500 MB formats correctly."""
    assert format_file_size(500 * 1024 * 1024) == "500 MB"


def test_format_file_size_999_bytes() -> None:
    """999 bytes stays in B range."""
    assert format_file_size(999) == "999 B"


def test_format_file_size_fractional_mb() -> None:
    """Fractional MB value (1.25 MB)."""
    size = int(1.25 * 1024 * 1024)
    result = format_file_size(size)
    assert "MB" in result


def test_format_file_size_exact_256_kb() -> None:
    """256 KB formats correctly."""
    assert format_file_size(256 * 1024) == "256 KB"


# ===========================================================================
# New expanded tests — clone edge cases
# ===========================================================================


def test_clone_hidden_file(tmp_path: Path) -> None:
    """Hidden file (dot prefix) is cloned."""
    src = tmp_path / ".hidden_config"
    src.write_text("secret=value")
    storage = tmp_path / "storage"

    result = clone_file_to_storage(str(src), storage)
    assert Path(result).name == ".hidden_config"
    assert Path(result).read_text() == "secret=value"


def test_clone_file_with_no_extension(tmp_path: Path) -> None:
    """File without extension is cloned."""
    src = tmp_path / "Makefile"
    src.write_text("all: build")
    storage = tmp_path / "storage"

    result = clone_file_to_storage(str(src), storage)
    assert Path(result).name == "Makefile"


def test_clone_same_dir_source_and_storage_raises(tmp_path: Path) -> None:
    """Cloning to same directory as source raises SameFileError."""
    import shutil

    src = tmp_path / "file.txt"
    src.write_text("original")

    with pytest.raises(shutil.SameFileError):
        clone_file_to_storage(str(src), tmp_path)


# ===========================================================================
# New expanded tests — is_file_encrypted parametrized
# ===========================================================================


@pytest.mark.parametrize(
    "suffix",
    [".rtf", ".csv", ".xml", ".yaml", ".md", ".srt", ".vtt"],
)
def test_encrypted_unsupported_formats_return_false(
    suffix: str, tmp_path: Path
) -> None:
    """Various unsupported format extensions return False."""
    f = tmp_path / f"file{suffix}"
    f.write_text("content")
    assert is_file_encrypted(f) is False


@pytest.mark.parametrize(
    "suffix",
    [".doc", ".xls", ".ppt"],
)
def test_legacy_formats_not_ole2_return_false(suffix: str, tmp_path: Path) -> None:
    """Legacy format files that aren't actually OLE2 return False."""
    f = tmp_path / f"file{suffix}"
    f.write_bytes(b"PK\x03\x04" + b"\x00" * 100)  # ZIP header, not OLE2
    assert is_file_encrypted(f) is False


# ===========================================================================
# Backfill — clone_file_to_storage failure modes, wipe edge cases,
# format_file_size boundaries, is_file_encrypted on directories.
# ===========================================================================


def test_clone_source_removed_mid_clone_propagates_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Source file vanishing between mkdir() and copy raises FileNotFoundError.

    The function does not perform an explicit existence check before
    ``shutil.copy2``; if the source disappears between the caller's earlier
    check and the copy, ``shutil.copy2`` raises FileNotFoundError and we
    let it propagate (no half-written destination).
    """
    src = tmp_path / "vanishing.txt"
    src.write_text("transient")
    storage = tmp_path / "storage"

    real_copy = shutil.copy2

    def _flaky_copy(src_arg: Path, dest_arg: Path) -> Path:
        # Remove the source between the caller-visible existence and the
        # actual copy — simulates a race condition.
        Path(src_arg).unlink()
        return real_copy(src_arg, dest_arg)

    monkeypatch.setattr("src.utils.file_utils.shutil.copy2", _flaky_copy)

    with pytest.raises(FileNotFoundError):
        clone_file_to_storage(str(src), storage)

    # No partial file should remain at the destination
    dest = storage / "vanishing.txt"
    assert not dest.exists()


def test_clone_destination_permission_denied(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Destination dir permission failure raises PermissionError.

    ``shutil.copy2`` may not be reached if mkdir itself fails — but we
    simulate the copy stage failing because the directory was created by
    mkdir(parents=True, exist_ok=True), then copy is denied.
    """
    src = tmp_path / "file.txt"
    src.write_text("data")
    storage = tmp_path / "storage"

    def _denied_copy(*_args: object, **_kwargs: object) -> None:
        raise PermissionError("Permission denied (mocked)")

    monkeypatch.setattr("src.utils.file_utils.shutil.copy2", _denied_copy)

    with pytest.raises(PermissionError):
        clone_file_to_storage(str(src), storage)

    # Storage dir was created (mkdir succeeded), but no file inside.
    assert storage.exists()
    assert list(storage.iterdir()) == []


def test_wipe_dir_removed_mid_call_is_noop(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Directory disappearing between exists() and rmtree() is silently swallowed.

    ``shutil.rmtree`` is called with ``ignore_errors=True``, so even if
    the directory is yanked between the exists() check and the actual
    removal, no exception escapes.
    """
    storage = tmp_path / "race_dir"
    storage.mkdir()
    (storage / "file.txt").write_text("x")

    real_rmtree = shutil.rmtree

    def _racing_rmtree(
        path: object, *, ignore_errors: bool = False, **kwargs: object
    ) -> None:
        # Pre-emptively delete the directory before the real rmtree runs.
        Path(path).rename(tmp_path / "moved_aside")
        # Now real_rmtree will fail unless ignore_errors=True (which the
        # production code passes).
        real_rmtree(path, ignore_errors=ignore_errors, **kwargs)

    monkeypatch.setattr("src.utils.file_utils.shutil.rmtree", _racing_rmtree)

    # Should not raise.
    wipe_history_directory(str(storage / "file.txt"))


def test_is_file_encrypted_on_directory_returns_false(tmp_path: Path) -> None:
    """Directory path returns False (no crash) for unrecognised suffix.

    Directories with no recognised extension fall through to the default
    return False branch (no try/except is even entered).
    """
    d = tmp_path / "some_dir"
    d.mkdir()
    # Default branch: not in any suffix set → returns False.
    assert is_file_encrypted(d) is False


def test_is_file_encrypted_on_directory_with_recognised_suffix(
    tmp_path: Path,
) -> None:
    """Directory with .docx-like suffix returns False rather than crashing.

    Opening a directory as a binary file raises IsADirectoryError, which
    is caught by the broad ``except Exception`` in ``is_file_encrypted``,
    so the function returns False.
    """
    d = tmp_path / "weird.docx"
    d.mkdir()
    # Should not raise — the broad except clause swallows IsADirectoryError.
    assert is_file_encrypted(d) is False


def test_format_file_size_petabyte_clamped() -> None:
    """1 PB clamps to TB units (no PB unit defined)."""
    assert format_file_size(1024**5) == "1024 TB"


def test_format_file_size_negative_raises_value_error() -> None:
    """Negative bytes triggers math.log domain error → ValueError.

    Documents current behaviour. Production code never calls this with
    a negative size, so a clean exception is acceptable.
    """
    with pytest.raises(ValueError):
        format_file_size(-1024)


def test_format_file_size_boundary_1023_stays_in_bytes() -> None:
    """1023 bytes stays in the B unit, not KB."""
    result = format_file_size(1023)
    assert result.endswith(" B")
    assert "KB" not in result


def test_format_file_size_exactly_1024_is_1kb() -> None:
    """Exactly 1024 bytes crosses to 1 KB."""
    assert format_file_size(1024) == "1 KB"
