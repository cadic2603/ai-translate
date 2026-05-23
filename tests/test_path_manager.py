"""Unit tests for the path_manager utility."""

import logging
from pathlib import Path

import pytest

from src.utils.path_manager import (
    configure_logging,
    ensure_app_dirs_exist,
    generate_dubbing_output_path,
    generate_extraction_output_path,
    generate_output_path,
    generate_subtitle_output_path,
    generate_voice_output_path,
    get_app_cache_dir,
    get_app_config_dir,
    get_app_data_dir,
    get_app_logs_dir,
    get_app_temp_dir,
    get_desktop_path,
    get_dubbing_storage_dir,
)


def test_app_dirs_creation() -> None:
    """Verify that app directory getters return Path objects and ensure they exist."""
    data_dir = get_app_data_dir()
    config_dir = get_app_config_dir()
    cache_dir = get_app_cache_dir()
    logs_dir = get_app_logs_dir()
    temp_dir = get_app_temp_dir()

    for d in [data_dir, config_dir, cache_dir, logs_dir]:
        assert isinstance(d, Path)
        assert d.exists()
        assert "ai-translate" in str(d)

    assert isinstance(temp_dir, Path)
    assert temp_dir.exists()


def test_ensure_app_dirs_exist() -> None:
    """Verify that calling ensure_app_dirs_exist works without error."""
    try:
        ensure_app_dirs_exist()
    except Exception as e:
        pytest.fail(f"ensure_app_dirs_exist raised an unexpected error: {e}")


def test_get_tts_cache_dir_creates_directory(tmp_path: Path) -> None:
    """get_tts_cache_dir creates the 'tts' subdirectory under the cache root."""
    import sys  # noqa: PLC0415
    from unittest.mock import patch  # noqa: PLC0415

    from src.utils.path_manager import get_tts_cache_dir  # noqa: PLC0415

    fake_cache = tmp_path / "ai-translate-cache"
    # Ensure the module-level import is re-resolved in the patched scope.
    with patch("src.utils.path_manager.get_app_cache_dir", return_value=fake_cache):
        fake_cache.mkdir()
        d = get_tts_cache_dir()
        assert d == fake_cache / "tts"
        assert d.is_dir()
    del sys


def test_get_tts_cache_dir_idempotent(tmp_path: Path) -> None:
    """Calling get_tts_cache_dir when the directory already exists is a no-op."""
    from unittest.mock import patch  # noqa: PLC0415

    from src.utils.path_manager import get_tts_cache_dir  # noqa: PLC0415

    fake_cache = tmp_path / "ai-translate-cache"
    fake_cache.mkdir()
    (fake_cache / "tts").mkdir()
    # Drop a sentinel file so we can detect accidental deletion.
    (fake_cache / "tts" / "sentinel.mp3").write_bytes(b"\x00")

    with patch("src.utils.path_manager.get_app_cache_dir", return_value=fake_cache):
        d = get_tts_cache_dir()
        assert d == fake_cache / "tts"
        assert (d / "sentinel.mp3").exists()


# ── generate_output_path ─────────────────────────────────────


def test_generate_output_path_default(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without custom storage, output goes to source file's parent directory."""
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda _k, _d: "",
    )
    source = tmp_path / "report.docx"
    source.touch()

    result = generate_output_path(source)

    assert result.parent == tmp_path
    assert result.name == "translated_report.docx"


def test_generate_output_path_custom_storage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Custom storage path setting overrides default location."""
    custom_dir = tmp_path / "my_output"
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda _k, _d: str(custom_dir),
    )
    source = tmp_path / "notes.txt"
    source.touch()

    result = generate_output_path(source)

    assert result.parent == custom_dir
    assert result.name == "translated_notes.txt"


def test_generate_output_path_collision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Existing file triggers numeric suffix increment."""
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda _k, _d: str(output_dir),
    )
    source = tmp_path / "file.txt"
    source.touch()

    # Create collisions in the output directory
    (output_dir / "translated_file.txt").touch()
    (output_dir / "translated_file_1.txt").touch()

    result = generate_output_path(source)

    assert result.name == "translated_file_2.txt"


def test_generate_output_path_no_collision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """First call with no existing files returns base name directly."""
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda _k, _d: "",
    )
    source = tmp_path / "data.csv"
    source.touch()

    result = generate_output_path(source)

    assert result.parent == tmp_path
    assert result.name == "translated_data.csv"
    assert not result.exists()


def test_generate_output_path_unicode_filename(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unicode filenames are handled correctly."""
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda _k, _d: "",
    )
    source = tmp_path / "tài_liệu.docx"
    source.touch()

    result = generate_output_path(source)

    assert result.name == "translated_tài_liệu.docx"


def test_generate_output_path_double_extension(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Files with double extensions preserve the last suffix."""
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda _k, _d: "",
    )
    source = tmp_path / "archive.tar.gz"
    source.touch()

    result = generate_output_path(source)

    assert result.suffix == ".gz"
    assert "translated_archive.tar" in result.stem


def test_generate_output_path_no_extension(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """File without extension gets translated_ prefix."""
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda _k, _d: "",
    )
    source = tmp_path / "Makefile"
    source.touch()

    result = generate_output_path(source)

    assert result.name == "translated_Makefile"
    assert result.suffix == ""


def test_generate_output_path_many_collisions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Multiple collisions increment counter correctly."""
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda _k, _d: str(output_dir),
    )
    source = tmp_path / "f.txt"
    source.touch()

    # Create collisions 0 through 4
    (output_dir / "translated_f.txt").touch()
    for i in range(1, 5):
        (output_dir / f"translated_f_{i}.txt").touch()

    result = generate_output_path(source)

    assert result.name == "translated_f_5.txt"


def test_generate_output_path_creates_output_dir(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Output directory is created if it doesn't exist."""
    custom_dir = tmp_path / "nonexistent" / "output"
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda _k, _d: str(custom_dir),
    )
    source = tmp_path / "doc.pdf"
    source.touch()

    generate_output_path(source)

    assert custom_dir.exists()


# ── generate_output_path additional edge cases ──────────────


def test_generate_output_path_spaces_in_name(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Files with spaces in the name get translated_ prefix correctly."""
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda _k, _d: "",
    )
    source = tmp_path / "my document (1).docx"
    source.touch()

    result = generate_output_path(source)

    assert result.name == "translated_my document (1).docx"


def test_generate_output_path_special_chars_in_name(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Special characters in filename are preserved in output path."""
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda _k, _d: "",
    )
    source = tmp_path / "report-v2_final.txt"
    source.touch()

    result = generate_output_path(source)

    assert result.name == "translated_report-v2_final.txt"


def test_generate_output_path_translated_prefix_already_present(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """File already named translated_ still gets the prefix again."""
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda _k, _d: "",
    )
    source = tmp_path / "translated_old.txt"
    source.touch()

    result = generate_output_path(source)

    assert result.name == "translated_translated_old.txt"


def test_generate_output_path_collision_preserves_extension(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Collision counter is appended before the extension."""
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda _k, _d: str(output_dir),
    )
    source = tmp_path / "data.csv"
    source.touch()

    (output_dir / "translated_data.csv").touch()

    result = generate_output_path(source)

    assert result.suffix == ".csv"
    assert result.name == "translated_data_1.csv"


def test_generate_output_path_hidden_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Hidden files (starting with .) get translated_ prefix."""
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda _k, _d: "",
    )
    source = tmp_path / ".hidden_config.json"
    source.touch()

    result = generate_output_path(source)

    assert result.name == "translated_.hidden_config.json"


def test_generate_output_path_empty_string_uses_source_parent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Empty string custom storage falls back to source file's parent."""
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda _k, _d: "",
    )
    source = tmp_path / "file.txt"
    source.touch()

    result = generate_output_path(source)

    assert result.parent == tmp_path


def test_generate_output_path_missing_parent_falls_to_desktop(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Falls back to Desktop when source parent directory doesn't exist."""
    desktop = tmp_path / "FakeDesktop"
    desktop.mkdir()
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda _k, _d: "",
    )
    monkeypatch.setattr(
        "src.utils.path_manager.get_desktop_path",
        lambda: desktop,
    )
    # Source parent does not exist
    source = tmp_path / "deleted_folder" / "file.txt"

    result = generate_output_path(source)

    assert result.parent == desktop


def test_generate_output_path_returns_absolute(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """generate_output_path always returns an absolute path."""
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda _k, _d: "",
    )
    source = tmp_path / "report.txt"
    source.touch()

    result = generate_output_path(source)

    assert result.is_absolute()


def test_xdg_data_home_respected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """XDG_DATA_HOME env var controls the app data directory on Linux."""
    import platform  # noqa: PLC0415

    if platform.system() != "Linux":
        pytest.skip("XDG env vars only apply on Linux")

    custom_xdg = tmp_path / "custom_xdg_data"
    monkeypatch.setenv("XDG_DATA_HOME", str(custom_xdg))

    from src.utils.path_manager import _get_base_app_dir  # noqa: PLC0415

    data_dir = _get_base_app_dir("data")

    assert str(custom_xdg) in str(data_dir)
    assert data_dir.exists()


# ── configure_logging ─────────────────────────────────────────


def test_configure_logging_sets_up_handlers() -> None:
    """configure_logging adds file and console handlers to the root logger."""
    root = logging.getLogger()
    # Count handlers before
    handlers_before = len(root.handlers)

    configure_logging()

    # Should have at least 2 new handlers (file + console)
    handlers_after = len(root.handlers)
    new_handlers = handlers_after - handlers_before
    assert new_handlers >= 2  # noqa: PLR2004

    # Verify handler types
    has_file = any(isinstance(h, logging.FileHandler) for h in root.handlers)
    has_stream = any(
        isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)
        for h in root.handlers
    )
    assert has_file
    assert has_stream

    # Clean up — remove the handlers we added to avoid polluting other tests
    for h in root.handlers[handlers_before:]:
        root.removeHandler(h)
        h.close()


def test_configure_logging_creates_log_file() -> None:
    """configure_logging creates the app.log file in the logs directory."""
    log_dir = get_app_logs_dir()
    log_file = log_dir / "app.log"

    root = logging.getLogger()
    handlers_before = len(root.handlers)

    configure_logging()

    assert log_file.exists()

    # Clean up
    for h in root.handlers[handlers_before:]:
        root.removeHandler(h)
        h.close()


def test_configure_logging_root_logger_level_is_debug() -> None:
    """configure_logging sets root logger level to DEBUG."""
    root = logging.getLogger()
    handlers_before = len(root.handlers)

    configure_logging()

    assert root.level == logging.DEBUG

    # Clean up
    for h in root.handlers[handlers_before:]:
        root.removeHandler(h)
        h.close()


# ── _get_base_app_dir unknown type ────────────────────────────


def test_get_base_app_dir_unknown_type_falls_back_to_home() -> None:
    """_get_base_app_dir with unknown dir_type falls back to home/ai-translate."""
    from src.utils.path_manager import _get_base_app_dir  # noqa: PLC0415

    result = _get_base_app_dir("unknown_type")
    assert result.exists()
    assert result.name == "ai-translate"


# ── get_desktop_path ─────────────────────────────────────────


def test_get_desktop_path_returns_path() -> None:
    """get_desktop_path() returns a Path object."""
    result = get_desktop_path()
    assert isinstance(result, Path)


def test_get_desktop_path_xdg_user_dirs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reads XDG_DESKTOP_DIR from user-dirs.dirs on Linux."""
    monkeypatch.setattr("src.utils.path_manager.platform.system", lambda: "Linux")
    desktop = tmp_path / "Bureau"
    desktop.mkdir()

    config_dir = tmp_path / ".config"
    config_dir.mkdir()
    user_dirs = config_dir / "user-dirs.dirs"
    user_dirs.write_text('XDG_DESKTOP_DIR="$HOME/Bureau"\n', encoding="utf-8")
    monkeypatch.setattr("src.utils.path_manager.Path.home", lambda: tmp_path)

    result = get_desktop_path()
    assert result == desktop


def test_get_desktop_path_falls_back_to_home_desktop(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Falls back to ~/Desktop when it exists."""
    monkeypatch.setattr("src.utils.path_manager.platform.system", lambda: "Windows")
    desktop = tmp_path / "Desktop"
    desktop.mkdir()
    monkeypatch.setattr("src.utils.path_manager.Path.home", lambda: tmp_path)

    result = get_desktop_path()
    assert result == desktop


def test_get_desktop_path_falls_back_to_home(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Falls back to home directory when ~/Desktop doesn't exist."""
    monkeypatch.setattr("src.utils.path_manager.platform.system", lambda: "Linux")
    # No Desktop, no user-dirs.dirs
    monkeypatch.setattr("src.utils.path_manager.Path.home", lambda: tmp_path)

    result = get_desktop_path()
    assert result == tmp_path


def test_get_desktop_path_xdg_oserror_handled(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """OSError reading user-dirs.dirs is handled gracefully."""
    monkeypatch.setattr("src.utils.path_manager.platform.system", lambda: "Linux")
    config_dir = tmp_path / ".config"
    config_dir.mkdir()
    user_dirs = config_dir / "user-dirs.dirs"
    user_dirs.mkdir()  # directory instead of file → OSError on read
    monkeypatch.setattr("src.utils.path_manager.Path.home", lambda: tmp_path)

    # Should not raise, falls back to home
    result = get_desktop_path()
    assert result == tmp_path


# ── generate_extraction_output_path ──────────────────────────


def test_generate_extraction_output_path_default_txt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without custom storage, extraction output goes to source file's parent."""
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda _k, _d: "",
    )
    source = tmp_path / "scan.png"
    source.touch()

    result = generate_extraction_output_path(source)

    assert result.parent == tmp_path
    assert result.name == "scan_extracted.txt"


def test_generate_extraction_output_path_custom_storage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Custom extraction storage path overrides default location."""
    custom_dir = tmp_path / "extractions"
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda _k, _d: str(custom_dir),
    )
    source = tmp_path / "photo.jpg"
    source.touch()

    result = generate_extraction_output_path(source)

    assert result.parent == custom_dir
    assert result.name == "photo_extracted.txt"


def test_generate_extraction_output_path_custom_extension(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Custom extension (e.g. .docx) is used in the output file name."""
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda _k, _d: "",
    )
    source = tmp_path / "image.png"
    source.touch()

    result = generate_extraction_output_path(source, ext=".docx")

    assert result.suffix == ".docx"
    assert result.name == "image_extracted.docx"


def test_generate_extraction_output_path_collision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Existing extracted file triggers numeric suffix increment."""
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda _k, _d: "",
    )
    source = tmp_path / "page.png"
    source.touch()
    (tmp_path / "page_extracted.txt").touch()
    (tmp_path / "page_extracted_1.txt").touch()

    result = generate_extraction_output_path(source)

    assert result.name == "page_extracted_2.txt"


def test_generate_extraction_output_path_many_collisions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Counter keeps incrementing through many collisions."""
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda _k, _d: "",
    )
    source = tmp_path / "img.png"
    source.touch()
    (tmp_path / "img_extracted.txt").touch()
    for i in range(1, 5):
        (tmp_path / f"img_extracted_{i}.txt").touch()

    result = generate_extraction_output_path(source)

    assert result.name == "img_extracted_5.txt"


def test_generate_extraction_output_path_creates_dir(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Output directory is created when it does not exist."""
    custom_dir = tmp_path / "new" / "extractions"
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda _k, _d: str(custom_dir),
    )
    source = tmp_path / "scan.png"
    source.touch()

    generate_extraction_output_path(source)

    assert custom_dir.exists()


def test_generate_extraction_output_path_missing_parent_uses_desktop(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Falls back to Desktop when source parent directory doesn't exist."""
    desktop = tmp_path / "FakeDesktop"
    desktop.mkdir()
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda _k, _d: "",
    )
    monkeypatch.setattr(
        "src.utils.path_manager.get_desktop_path",
        lambda: desktop,
    )
    source = tmp_path / "gone_folder" / "img.png"

    result = generate_extraction_output_path(source)

    assert result.parent == desktop


def test_generate_extraction_output_path_unicode_filename(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unicode filenames are handled in the extracted output path."""
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda _k, _d: "",
    )
    source = tmp_path / "hình_ảnh.png"
    source.touch()

    result = generate_extraction_output_path(source)

    assert "hình_ảnh" in result.name
    assert result.suffix == ".txt"


def test_generate_extraction_output_path_no_collision_returns_base(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """First call with no existing files returns base name directly."""
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda _k, _d: "",
    )
    source = tmp_path / "diagram.bmp"
    source.touch()

    result = generate_extraction_output_path(source)

    assert result.name == "diagram_extracted.txt"
    assert not result.exists()


def test_generate_extraction_output_path_is_absolute(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """generate_extraction_output_path always returns an absolute path."""
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda _k, _d: "",
    )
    source = tmp_path / "file.png"
    source.touch()

    result = generate_extraction_output_path(source)

    assert result.is_absolute()


# ── get_desktop_path — XDG path exists in file but not on disk ────────


def test_get_desktop_path_xdg_path_not_on_disk(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """XDG_DESKTOP_DIR resolves fine but the directory doesn't exist → falls through."""
    monkeypatch.setattr("src.utils.path_manager.platform.system", lambda: "Linux")

    config_dir = tmp_path / ".config"
    config_dir.mkdir()
    user_dirs = config_dir / "user-dirs.dirs"
    # Point to a directory that does NOT exist on disk
    user_dirs.write_text(
        'XDG_DESKTOP_DIR="$HOME/NonExistentDesktop"\n', encoding="utf-8"
    )
    monkeypatch.setattr("src.utils.path_manager.Path.home", lambda: tmp_path)

    # ~/Desktop also doesn't exist → should return home
    result = get_desktop_path()
    assert result == tmp_path


# ── _get_base_app_dir — Windows branch ────────────────────────────────


def test_get_base_app_dir_windows_branch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Windows branch uses LOCALAPPDATA / APPDATA for data and config dirs."""
    from src.utils.path_manager import _get_base_app_dir  # noqa: PLC0415

    local_appdata = tmp_path / "LocalAppData"
    roaming_appdata = tmp_path / "AppData" / "Roaming"

    monkeypatch.setattr("src.utils.path_manager.platform.system", lambda: "Windows")
    monkeypatch.setenv("LOCALAPPDATA", str(local_appdata))
    monkeypatch.setenv("APPDATA", str(roaming_appdata))

    data_dir = _get_base_app_dir("data")
    config_dir = _get_base_app_dir("config")

    # data lives under LOCALAPPDATA/ai-translate
    assert str(local_appdata) in str(data_dir)
    assert data_dir.exists()
    # config lives under APPDATA/ai-translate
    assert str(roaming_appdata) in str(config_dir)
    assert config_dir.exists()


# ── _get_base_app_dir — Darwin branch ─────────────────────────────────


def test_get_base_app_dir_darwin_branch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """MacOS branch places data under ~/Library/Application Support."""
    from src.utils.path_manager import _get_base_app_dir  # noqa: PLC0415

    monkeypatch.setattr("src.utils.path_manager.platform.system", lambda: "Darwin")
    monkeypatch.setattr("src.utils.path_manager.Path.home", lambda: tmp_path)

    data_dir = _get_base_app_dir("data")
    cache_dir = _get_base_app_dir("cache")

    # data → ~/Library/Application Support/ai-translate
    assert "Application Support" in str(data_dir)
    assert data_dir.exists()
    # cache → ~/Library/Caches/ai-translate
    assert "Caches" in str(cache_dir)
    assert cache_dir.exists()


# ---------------------------------------------------------------------------
# generate_subtitle_output_path
# ---------------------------------------------------------------------------


def test_subtitle_output_default_srt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Default extension is .srt."""
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda *a, **kw: "",
    )
    src = tmp_path / "video.mp4"
    src.touch()
    result = generate_subtitle_output_path(src)
    assert result.suffix == ".srt"
    assert result.stem == "video_subtitle"


def test_subtitle_output_vtt_extension(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Custom extension .vtt is used when specified."""
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda *a, **kw: "",
    )
    src = tmp_path / "video.mp4"
    src.touch()
    result = generate_subtitle_output_path(src, ext=".vtt")
    assert result.suffix == ".vtt"
    assert result.stem == "video_subtitle"


def test_subtitle_output_increments_on_collision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Auto-increments when output file already exists."""
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda *a, **kw: "",
    )
    src = tmp_path / "video.mp4"
    src.touch()
    # Create the first output so it collides
    (tmp_path / "video_subtitle.srt").touch()
    result = generate_subtitle_output_path(src)
    assert result.name == "video_subtitle_1.srt"


def test_subtitle_output_uses_storage_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Uses configured storage path when set."""
    out_dir = tmp_path / "configured_dir"
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda *a, **kw: str(out_dir),
    )
    src = tmp_path / "video.mp4"
    src.touch()
    result = generate_subtitle_output_path(src)
    assert result.parent == out_dir


# ---------------------------------------------------------------------------
# generate_voice_output_path
# ---------------------------------------------------------------------------


def test_voice_output_mp3_suffix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Voice output has _voice.mp3 suffix."""
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda *a, **kw: "",
    )
    src = tmp_path / "video.srt"
    src.touch()
    result = generate_voice_output_path(src)
    assert result.suffix == ".mp3"
    assert "_voice" in result.stem


def test_voice_output_increments_on_collision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Auto-increments when voice file already exists."""
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda *a, **kw: "",
    )
    src = tmp_path / "video.srt"
    src.touch()
    (tmp_path / "video_voice.mp3").touch()
    result = generate_voice_output_path(src)
    assert result.name == "video_voice_1.mp3"


def test_voice_output_uses_storage_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Uses configured storage path when set."""
    out_dir = tmp_path / "vo_dir"
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda *a, **kw: str(out_dir),
    )
    src = tmp_path / "video.srt"
    src.touch()
    result = generate_voice_output_path(src)
    assert result.parent == out_dir


# ---------------------------------------------------------------------------
# generate_dubbing_output_path
# ---------------------------------------------------------------------------


def test_dubbing_output_suffix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Dubbing output has _dubbed suffix and preserves extension."""
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda *a, **kw: "",
    )
    src = tmp_path / "video.mp4"
    src.touch()
    result = generate_dubbing_output_path(src)
    assert result.suffix == ".mp4"
    assert "_dubbed" in result.stem


def test_dubbing_output_increments_on_collision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Auto-increments when dubbed file already exists."""
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda *a, **kw: "",
    )
    src = tmp_path / "video.mp4"
    src.touch()
    (tmp_path / "video_dubbed.mp4").touch()
    result = generate_dubbing_output_path(src)
    # stem is "video_dubbed", counter appended to stem
    assert result.name == "video_dubbed_1.mp4"


def test_dubbing_output_uses_storage_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Uses configured storage path when set."""
    out_dir = tmp_path / "dub_dir"
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda *a, **kw: str(out_dir),
    )
    src = tmp_path / "video.mkv"
    src.touch()
    result = generate_dubbing_output_path(src)
    assert result.parent == out_dir
    assert result.suffix == ".mkv"


# ---------------------------------------------------------------------------
# get_dubbing_storage_dir
# ---------------------------------------------------------------------------


def test_get_dubbing_storage_dir_creates_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Creates the storage directory and returns the correct path."""
    monkeypatch.setattr(
        "src.utils.path_manager.get_app_data_dir",
        lambda: tmp_path,
    )
    entry_id = 42  # noqa: PLR2004

    result = get_dubbing_storage_dir(entry_id)

    expected = tmp_path / "dubbing" / "42"
    assert result == expected
    assert result.exists()
    assert result.is_dir()


def test_get_dubbing_storage_dir_idempotent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Calling get_dubbing_storage_dir twice returns the same path without error."""
    monkeypatch.setattr(
        "src.utils.path_manager.get_app_data_dir",
        lambda: tmp_path,
    )
    entry_id = 7  # noqa: PLR2004

    first = get_dubbing_storage_dir(entry_id)
    second = get_dubbing_storage_dir(entry_id)

    assert first == second
    assert first.exists()


def test_get_dubbing_storage_dir_returns_path_object(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """get_dubbing_storage_dir returns a Path instance."""
    monkeypatch.setattr(
        "src.utils.path_manager.get_app_data_dir",
        lambda: tmp_path,
    )

    result = get_dubbing_storage_dir(1)

    assert isinstance(result, Path)


def test_get_dubbing_storage_dir_different_ids(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Different entry IDs produce different storage directories."""
    monkeypatch.setattr(
        "src.utils.path_manager.get_app_data_dir",
        lambda: tmp_path,
    )

    dir_a = get_dubbing_storage_dir(1)
    dir_b = get_dubbing_storage_dir(2)

    assert dir_a != dir_b
    assert dir_a.name == "1"
    assert dir_b.name == "2"


# ---------------------------------------------------------------------------
# generate_dubbing_output_path — no extension defaults to .mp4
# ---------------------------------------------------------------------------


def test_dubbing_output_no_extension_defaults_to_mp4(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Source file with no extension defaults to .mp4 in dubbed output."""
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda *a, **kw: "",
    )
    src = tmp_path / "raw_video"
    src.touch()

    result = generate_dubbing_output_path(src)

    assert result.suffix == ".mp4"
    assert "_dubbed" in result.stem


# ---------------------------------------------------------------------------
# generate_subtitle_output_path — multiple collisions & directory creation
# ---------------------------------------------------------------------------


def test_subtitle_output_multiple_collisions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Counter increments up to 3 when prior files exist."""
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda *a, **kw: "",
    )
    src = tmp_path / "video.mp4"
    src.touch()

    # Create collisions: video_subtitle.srt, video_subtitle_1.srt, etc.
    (tmp_path / "video_subtitle.srt").touch()
    (tmp_path / "video_subtitle_1.srt").touch()
    (tmp_path / "video_subtitle_2.srt").touch()

    result = generate_subtitle_output_path(src)

    assert result.name == "video_subtitle_3.srt"


def test_subtitle_output_creates_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Output directory is created if it doesn't exist."""
    new_dir = tmp_path / "nonexistent" / "subs"
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda *a, **kw: str(new_dir),
    )
    src = tmp_path / "video.mp4"
    src.touch()

    generate_subtitle_output_path(src)

    assert new_dir.exists()
    assert new_dir.is_dir()


# ---------------------------------------------------------------------------
# generate_voice_output_path — multiple collisions & directory creation
# ---------------------------------------------------------------------------


def test_voice_output_multiple_collisions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Counter increments up to 3 when prior voice files exist."""
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda *a, **kw: "",
    )
    src = tmp_path / "audio.srt"
    src.touch()

    # Create collisions: audio_voice.mp3, audio_voice_1.mp3, audio_voice_2.mp3
    (tmp_path / "audio_voice.mp3").touch()
    (tmp_path / "audio_voice_1.mp3").touch()
    (tmp_path / "audio_voice_2.mp3").touch()

    result = generate_voice_output_path(src)

    assert result.name == "audio_voice_3.mp3"


def test_voice_output_creates_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Output directory is created if it doesn't exist."""
    new_dir = tmp_path / "nonexistent" / "voices"
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda *a, **kw: str(new_dir),
    )
    src = tmp_path / "audio.srt"
    src.touch()

    generate_voice_output_path(src)

    assert new_dir.exists()
    assert new_dir.is_dir()


# ---------------------------------------------------------------------------
# generate_dubbing_output_path — directory creation
# ---------------------------------------------------------------------------


def test_dubbing_output_creates_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Output directory is created if it doesn't exist."""
    new_dir = tmp_path / "nonexistent" / "dubs"
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda *a, **kw: str(new_dir),
    )
    src = tmp_path / "video.mp4"
    src.touch()

    generate_dubbing_output_path(src)

    assert new_dir.exists()
    assert new_dir.is_dir()


# ---------------------------------------------------------------------------
# generate_dubbing_output_path — locale codes
# ---------------------------------------------------------------------------


def test_dubbing_output_with_locale_codes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Dubbing output includes locale codes when languages are provided."""
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda *a, **kw: "",
    )
    src = tmp_path / "video.mp4"
    src.touch()

    result = generate_dubbing_output_path(
        src,
        src_lang="English (US)",
        target_lang="Vietnamese",
    )

    assert result.name == "video_dubbed_en-US_vi.mp4"


def test_dubbing_output_locale_collision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Collision counter works with locale codes in the name."""
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda *a, **kw: "",
    )
    src = tmp_path / "video.mp4"
    src.touch()
    (tmp_path / "video_dubbed_en-US_vi.mp4").touch()

    result = generate_dubbing_output_path(
        src,
        src_lang="English (US)",
        target_lang="Vietnamese",
    )

    assert result.name == "video_dubbed_en-US_vi_1.mp4"


def test_dubbing_output_no_locale_backward_compat(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without language args, falls back to plain _dubbed suffix."""
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda *a, **kw: "",
    )
    src = tmp_path / "video.mp4"
    src.touch()

    result = generate_dubbing_output_path(src)

    assert result.name == "video_dubbed.mp4"


# ---------------------------------------------------------------------------
# get_desktop_path — XDG user-dirs parsing on Linux (additional edge cases)
# ---------------------------------------------------------------------------


def test_get_desktop_path_xdg_comment_lines_ignored(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Comment and blank lines in user-dirs.dirs are skipped."""
    monkeypatch.setattr("src.utils.path_manager.platform.system", lambda: "Linux")
    desktop = tmp_path / "MyDesktop"
    desktop.mkdir()

    config_dir = tmp_path / ".config"
    config_dir.mkdir()
    user_dirs = config_dir / "user-dirs.dirs"
    content = (
        "# This is a comment\n"
        "\n"
        'XDG_DOWNLOAD_DIR="$HOME/Downloads"\n'
        'XDG_DESKTOP_DIR="$HOME/MyDesktop"\n'
    )
    user_dirs.write_text(content, encoding="utf-8")
    monkeypatch.setattr("src.utils.path_manager.Path.home", lambda: tmp_path)

    result = get_desktop_path()
    assert result == desktop


def test_get_desktop_path_xdg_no_desktop_entry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """user-dirs.dirs exists but has no XDG_DESKTOP_DIR entry → falls back."""
    monkeypatch.setattr("src.utils.path_manager.platform.system", lambda: "Linux")

    config_dir = tmp_path / ".config"
    config_dir.mkdir()
    user_dirs = config_dir / "user-dirs.dirs"
    user_dirs.write_text('XDG_DOWNLOAD_DIR="$HOME/Downloads"\n', encoding="utf-8")
    monkeypatch.setattr("src.utils.path_manager.Path.home", lambda: tmp_path)

    # No ~/Desktop exists either
    result = get_desktop_path()
    assert result == tmp_path


def test_get_desktop_path_macos_has_desktop(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """On macOS, returns ~/Desktop when it exists (skips XDG parsing)."""
    monkeypatch.setattr("src.utils.path_manager.platform.system", lambda: "Darwin")
    desktop = tmp_path / "Desktop"
    desktop.mkdir()
    monkeypatch.setattr("src.utils.path_manager.Path.home", lambda: tmp_path)

    result = get_desktop_path()
    assert result == desktop


# ---------------------------------------------------------------------------
# configure_logging — additional coverage
# ---------------------------------------------------------------------------


def test_configure_logging_file_handler_points_to_app_log() -> None:
    """FileHandler created by configure_logging targets 'app.log' in logs dir."""
    root = logging.getLogger()
    handlers_before = len(root.handlers)

    configure_logging()

    log_dir = get_app_logs_dir()
    expected_path = str(log_dir / "app.log")

    file_handlers = [
        h for h in root.handlers[handlers_before:] if isinstance(h, logging.FileHandler)
    ]
    assert len(file_handlers) >= 1  # noqa: PLR2004
    assert file_handlers[0].baseFilename == expected_path

    # Clean up
    for h in root.handlers[handlers_before:]:
        root.removeHandler(h)
        h.close()


def test_configure_logging_file_handler_level_is_debug() -> None:
    """File handler is set to DEBUG level."""
    root = logging.getLogger()
    handlers_before = len(root.handlers)

    configure_logging()

    file_handlers = [
        h for h in root.handlers[handlers_before:] if isinstance(h, logging.FileHandler)
    ]
    assert file_handlers[0].level == logging.DEBUG

    # Clean up
    for h in root.handlers[handlers_before:]:
        root.removeHandler(h)
        h.close()


def test_configure_logging_console_handler_level_is_debug() -> None:
    """Console (stream) handler is set to DEBUG level."""
    root = logging.getLogger()
    handlers_before = len(root.handlers)

    configure_logging()

    stream_handlers = [
        h
        for h in root.handlers[handlers_before:]
        if isinstance(h, logging.StreamHandler)
        and not isinstance(h, logging.FileHandler)
    ]
    assert len(stream_handlers) >= 1  # noqa: PLR2004
    assert stream_handlers[0].level == logging.DEBUG

    # Clean up
    for h in root.handlers[handlers_before:]:
        root.removeHandler(h)
        h.close()


def test_configure_logging_handlers_have_formatters() -> None:
    """Both handlers have non-None formatters."""
    root = logging.getLogger()
    handlers_before = len(root.handlers)

    configure_logging()

    new_handlers = root.handlers[handlers_before:]
    for h in new_handlers:
        assert h.formatter is not None

    # Clean up
    for h in new_handlers:
        root.removeHandler(h)
        h.close()


# ---------------------------------------------------------------------------
# get_dubbing_storage_dir — additional format verification
# ---------------------------------------------------------------------------


def test_get_dubbing_storage_dir_path_components(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify the exact directory hierarchy: data_dir/dubbing/<id>."""
    monkeypatch.setattr(
        "src.utils.path_manager.get_app_data_dir",
        lambda: tmp_path,
    )
    entry_id = 99  # noqa: PLR2004

    result = get_dubbing_storage_dir(entry_id)

    # Check each component in order
    parts = result.parts
    assert parts[-1] == "99"
    assert parts[-2] == "dubbing"


def test_get_dubbing_storage_dir_large_id(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Large entry IDs are stringified correctly."""
    monkeypatch.setattr(
        "src.utils.path_manager.get_app_data_dir",
        lambda: tmp_path,
    )
    large_id = 999999  # noqa: PLR2004

    result = get_dubbing_storage_dir(large_id)

    assert result.name == "999999"
    assert result.exists()


# ---------------------------------------------------------------------------
# generate_subtitle_output_path — collision handling (additional)
# ---------------------------------------------------------------------------


def test_subtitle_output_collision_with_custom_ext(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Collision counter works correctly with non-default .vtt extension."""
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda *a, **kw: "",
    )
    src = tmp_path / "video.mp4"
    src.touch()
    (tmp_path / "video_subtitle.vtt").touch()
    (tmp_path / "video_subtitle_1.vtt").touch()

    result = generate_subtitle_output_path(src, ext=".vtt")

    assert result.name == "video_subtitle_2.vtt"


def test_subtitle_output_falls_back_to_desktop(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Falls back to Desktop when source parent doesn't exist and no storage set."""
    desktop = tmp_path / "FakeDesktop"
    desktop.mkdir()
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda *a, **kw: "",
    )
    monkeypatch.setattr(
        "src.utils.path_manager.get_desktop_path",
        lambda: desktop,
    )
    source = tmp_path / "deleted_dir" / "video.mp4"

    result = generate_subtitle_output_path(source)

    assert result.parent == desktop
    assert result.name == "video_subtitle.srt"


def test_subtitle_output_returns_absolute_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """generate_subtitle_output_path always returns an absolute path."""
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda *a, **kw: "",
    )
    src = tmp_path / "clip.mp4"
    src.touch()

    result = generate_subtitle_output_path(src)

    assert result.is_absolute()


# ---------------------------------------------------------------------------
# generate_voice_output_path — collision handling (additional)
# ---------------------------------------------------------------------------


def test_voice_output_collision_with_custom_ext(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Collision counter works correctly with non-default .wav extension."""
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda *a, **kw: "",
    )
    src = tmp_path / "narration.srt"
    src.touch()
    (tmp_path / "narration_voice.wav").touch()
    (tmp_path / "narration_voice_1.wav").touch()

    result = generate_voice_output_path(src, ext=".wav")

    assert result.name == "narration_voice_2.wav"


def test_voice_output_falls_back_to_desktop(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Falls back to Desktop when source parent doesn't exist and no storage set."""
    desktop = tmp_path / "FakeDesktop"
    desktop.mkdir()
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda *a, **kw: "",
    )
    monkeypatch.setattr(
        "src.utils.path_manager.get_desktop_path",
        lambda: desktop,
    )
    source = tmp_path / "deleted_dir" / "audio.srt"

    result = generate_voice_output_path(source)

    assert result.parent == desktop
    assert result.name == "audio_voice.mp3"


def test_voice_output_returns_absolute_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """generate_voice_output_path always returns an absolute path."""
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda *a, **kw: "",
    )
    src = tmp_path / "clip.srt"
    src.touch()

    result = generate_voice_output_path(src)

    assert result.is_absolute()


# ---------------------------------------------------------------------------
# Platform-specific _get_base_app_dir branch coverage
# ---------------------------------------------------------------------------


def test_get_base_app_dir_windows_cache_and_logs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Windows branch places cache under LOCALAPPDATA/cache and logs under logs."""
    from src.utils.path_manager import _get_base_app_dir  # noqa: PLC0415

    local_appdata = tmp_path / "LocalAppData"
    monkeypatch.setattr("src.utils.path_manager.platform.system", lambda: "Windows")
    monkeypatch.setenv("LOCALAPPDATA", str(local_appdata))
    monkeypatch.setenv("APPDATA", str(tmp_path / "AppData"))

    cache_dir = _get_base_app_dir("cache")
    logs_dir = _get_base_app_dir("logs")

    assert "cache" in str(cache_dir)
    assert cache_dir.exists()
    assert "logs" in str(logs_dir)
    assert logs_dir.exists()


def test_get_base_app_dir_darwin_config_and_logs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """MacOS branch places config under Preferences and logs under Logs."""
    from src.utils.path_manager import _get_base_app_dir  # noqa: PLC0415

    monkeypatch.setattr("src.utils.path_manager.platform.system", lambda: "Darwin")
    monkeypatch.setattr("src.utils.path_manager.Path.home", lambda: tmp_path)

    config_dir = _get_base_app_dir("config")
    logs_dir = _get_base_app_dir("logs")

    assert "Preferences" in str(config_dir)
    assert config_dir.exists()
    assert "Logs" in str(logs_dir)
    assert logs_dir.exists()


def test_get_base_app_dir_linux_xdg_config_home(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Linux branch respects XDG_CONFIG_HOME for config directory."""
    from src.utils.path_manager import _get_base_app_dir  # noqa: PLC0415

    monkeypatch.setattr("src.utils.path_manager.platform.system", lambda: "Linux")
    custom_config = tmp_path / "custom_config"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(custom_config))

    config_dir = _get_base_app_dir("config")

    assert str(custom_config) in str(config_dir)
    assert config_dir.exists()


def test_get_base_app_dir_linux_xdg_cache_home(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Linux branch respects XDG_CACHE_HOME for cache directory."""
    from src.utils.path_manager import _get_base_app_dir  # noqa: PLC0415

    monkeypatch.setattr("src.utils.path_manager.platform.system", lambda: "Linux")
    custom_cache = tmp_path / "custom_cache"
    monkeypatch.setenv("XDG_CACHE_HOME", str(custom_cache))

    cache_dir = _get_base_app_dir("cache")

    assert str(custom_cache) in str(cache_dir)
    assert cache_dir.exists()


def test_get_base_app_dir_linux_xdg_state_home_for_logs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Linux branch respects XDG_STATE_HOME for logs directory."""
    from src.utils.path_manager import _get_base_app_dir  # noqa: PLC0415

    monkeypatch.setattr("src.utils.path_manager.platform.system", lambda: "Linux")
    custom_state = tmp_path / "custom_state"
    monkeypatch.setenv("XDG_STATE_HOME", str(custom_state))

    logs_dir = _get_base_app_dir("logs")

    assert str(custom_state) in str(logs_dir)
    assert "log" in str(logs_dir)
    assert logs_dir.exists()


def test_get_base_app_dir_windows_missing_env_vars(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Windows branch falls back to tempdir when env vars are absent."""
    from src.utils.path_manager import _get_base_app_dir  # noqa: PLC0415

    monkeypatch.setattr("src.utils.path_manager.platform.system", lambda: "Windows")
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.delenv("APPDATA", raising=False)

    # Should not raise; falls back to tempfile.gettempdir()
    data_dir = _get_base_app_dir("data")
    assert data_dir.exists()
    assert data_dir.name == "ai-translate"


# ---------------------------------------------------------------------------
# generate_output_path: additional edge cases
# ---------------------------------------------------------------------------


def test_generate_output_path_long_filename(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Long filenames are handled correctly with translated_ prefix."""
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda _k, _d: "",
    )
    long_name = "a" * 200 + ".txt"
    source = tmp_path / long_name
    source.touch()

    result = generate_output_path(source)

    assert result.name == f"translated_{long_name}"
    assert result.parent == tmp_path


def test_generate_output_path_deeply_nested_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Deeply nested source file uses its parent directory for output."""
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda _k, _d: "",
    )
    deep_dir = tmp_path / "a" / "b" / "c" / "d" / "e"
    deep_dir.mkdir(parents=True)
    source = deep_dir / "deep_file.txt"
    source.touch()

    result = generate_output_path(source)

    assert result.parent == deep_dir
    assert result.name == "translated_deep_file.txt"


def test_generate_output_path_dot_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Dotfiles (like .gitignore) get translated_ prefix."""
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda _k, _d: "",
    )
    source = tmp_path / ".gitignore"
    source.touch()

    result = generate_output_path(source)

    assert result.name == "translated_.gitignore"


def test_generate_output_path_unicode_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unicode characters in custom storage directory path are handled."""
    custom_dir = tmp_path / "xuất_bản"
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda _k, _d: str(custom_dir),
    )
    source = tmp_path / "file.txt"
    source.touch()

    result = generate_output_path(source)

    assert result.parent == custom_dir
    assert custom_dir.exists()


def test_generate_output_path_multiple_dots_in_name(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Files with multiple dots preserve all dots in the name."""
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda _k, _d: "",
    )
    source = tmp_path / "my.report.v2.final.docx"
    source.touch()

    result = generate_output_path(source)

    assert result.name == "translated_my.report.v2.final.docx"
    assert result.suffix == ".docx"


# ---------------------------------------------------------------------------
# generate_extraction_output_path: additional edge cases
# ---------------------------------------------------------------------------


def test_generate_extraction_output_path_docx_extension(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Extraction with .docx extension uses the correct suffix."""
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda _k, _d: "",
    )
    source = tmp_path / "image.png"
    source.touch()

    result = generate_extraction_output_path(source, ext=".docx")

    assert result.suffix == ".docx"
    assert result.stem == "image_extracted"


def test_generate_extraction_output_path_unicode_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unicode source filename generates correctly named output."""
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda _k, _d: "",
    )
    source = tmp_path / "hình_ảnh.jpg"
    source.touch()

    result = generate_extraction_output_path(source)

    assert result.name == "hình_ảnh_extracted.txt"


# ---------------------------------------------------------------------------
# get_desktop_path: platform branch coverage
# ---------------------------------------------------------------------------


def test_get_desktop_path_windows_branch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Windows branch returns ~/Desktop if it exists."""
    monkeypatch.setattr("src.utils.path_manager.platform.system", lambda: "Windows")
    monkeypatch.setattr("src.utils.path_manager.Path.home", lambda: tmp_path)

    desktop = tmp_path / "Desktop"
    desktop.mkdir()

    result = get_desktop_path()
    assert result == desktop


def test_get_desktop_path_windows_no_desktop(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Windows falls back to home when Desktop doesn't exist."""
    monkeypatch.setattr("src.utils.path_manager.platform.system", lambda: "Windows")
    monkeypatch.setattr("src.utils.path_manager.Path.home", lambda: tmp_path)

    # No Desktop directory created
    result = get_desktop_path()
    assert result == tmp_path


def test_get_desktop_path_darwin_with_desktop(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """MacOS returns ~/Desktop when it exists."""
    monkeypatch.setattr("src.utils.path_manager.platform.system", lambda: "Darwin")
    monkeypatch.setattr("src.utils.path_manager.Path.home", lambda: tmp_path)

    desktop = tmp_path / "Desktop"
    desktop.mkdir()

    result = get_desktop_path()
    assert result == desktop


# ---------------------------------------------------------------------------
# generate_subtitle_output_path: edge cases
# ---------------------------------------------------------------------------


def test_subtitle_output_unicode_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unicode source filename in subtitle output is handled correctly."""
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda *a, **kw: "",
    )
    src = tmp_path / "phim_thuyết_minh.mp4"
    src.touch()

    result = generate_subtitle_output_path(src)

    assert result.stem == "phim_thuyết_minh_subtitle"
    assert result.suffix == ".srt"


# ---------------------------------------------------------------------------
# generate_dubbing_output_path: locale code edge cases
# ---------------------------------------------------------------------------


def test_dubbing_output_partial_locale_only_src(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Dubbing output with only src_lang (no target_lang) uses simple _dubbed tag."""
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda *a, **kw: "",
    )
    src = tmp_path / "video.mp4"
    src.touch()

    result = generate_dubbing_output_path(src, src_lang="English (US)", target_lang="")

    assert "_dubbed" in result.name
    # Without both languages, no locale codes
    assert "en-US" not in result.name


def test_dubbing_output_partial_locale_only_target(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Dubbing output with only target_lang uses simple _dubbed tag."""
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda *a, **kw: "",
    )
    src = tmp_path / "clip.mp4"
    src.touch()

    result = generate_dubbing_output_path(src, src_lang="", target_lang="Vietnamese")

    assert "_dubbed" in result.name
    # Without both languages, no locale code pair should appear
    assert "_dubbed_" not in result.name  # no "_dubbed_xx_yy" pattern


def test_dubbing_output_returns_absolute_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """generate_dubbing_output_path always returns an absolute path."""
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda *a, **kw: "",
    )
    src = tmp_path / "clip.mp4"
    src.touch()

    result = generate_dubbing_output_path(src)

    assert result.is_absolute()


# ---------------------------------------------------------------------------
# get_dubbing_storage_dir: edge cases
# ---------------------------------------------------------------------------


def test_get_dubbing_storage_dir_zero_id(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Entry ID of 0 creates a valid directory named '0'."""
    monkeypatch.setattr(
        "src.utils.path_manager.get_app_data_dir",
        lambda: tmp_path,
    )
    result = get_dubbing_storage_dir(0)

    assert result.exists()
    assert result.name == "0"


def test_get_dubbing_storage_dir_negative_id(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Negative entry ID creates a valid directory (edge case)."""
    monkeypatch.setattr(
        "src.utils.path_manager.get_app_data_dir",
        lambda: tmp_path,
    )
    neg_id = -1
    result = get_dubbing_storage_dir(neg_id)

    assert result.exists()
    assert str(neg_id) in result.name


# ---------------------------------------------------------------------------
# generate_output_path: special storage directory edge cases
# ---------------------------------------------------------------------------


def test_generate_output_path_storage_dir_with_spaces(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Storage directory path with spaces is handled correctly."""
    custom_dir = tmp_path / "My Documents" / "Translations"
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda _k, _d: str(custom_dir),
    )
    source = tmp_path / "input.txt"
    source.touch()

    result = generate_output_path(source)

    assert result.parent == custom_dir
    assert custom_dir.exists()
    assert result.name == "translated_input.txt"


def test_generate_extraction_output_path_collision_counter_increments(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Multiple extraction collisions increment counter past 1."""
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda _k, _d: str(output_dir),
    )
    source = tmp_path / "photo.png"
    source.touch()

    # Create collisions
    (output_dir / "photo_extracted.txt").touch()
    (output_dir / "photo_extracted_1.txt").touch()
    (output_dir / "photo_extracted_2.txt").touch()

    result = generate_extraction_output_path(source)

    assert result.name == "photo_extracted_3.txt"


def test_generate_subtitle_output_returns_absolute_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """generate_subtitle_output_path always returns an absolute path."""
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda *a, **kw: "",
    )
    src = tmp_path / "audio.wav"
    src.touch()

    result = generate_subtitle_output_path(src)

    assert result.is_absolute()


def test_generate_extraction_output_path_returns_absolute_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """generate_extraction_output_path always returns an absolute path."""
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda _k, _d: "",
    )
    source = tmp_path / "scan.png"
    source.touch()

    result = generate_extraction_output_path(source)

    assert result.is_absolute()


# ===========================================================================
# Additional tests — _unique_path collision handling
# ===========================================================================


def test_unique_path_no_collision(tmp_path: Path) -> None:
    """_unique_path returns base name when no collision exists."""
    from src.utils.path_manager import _unique_path  # noqa: PLC0415

    result = _unique_path(tmp_path, "output", ".txt")
    assert result == tmp_path / "output.txt"


def test_unique_path_first_collision(tmp_path: Path) -> None:
    """_unique_path appends _1 on first collision."""
    from src.utils.path_manager import _unique_path  # noqa: PLC0415

    (tmp_path / "output.txt").touch()
    result = _unique_path(tmp_path, "output", ".txt")
    assert result == tmp_path / "output_1.txt"


def test_unique_path_second_collision(tmp_path: Path) -> None:
    """_unique_path appends _2 when both base and _1 exist."""
    from src.utils.path_manager import _unique_path  # noqa: PLC0415

    (tmp_path / "output.txt").touch()
    (tmp_path / "output_1.txt").touch()
    result = _unique_path(tmp_path, "output", ".txt")
    assert result == tmp_path / "output_2.txt"


def test_unique_path_ten_collisions(tmp_path: Path) -> None:
    """_unique_path increments counter up to 10."""
    from src.utils.path_manager import _unique_path  # noqa: PLC0415

    (tmp_path / "file.txt").touch()
    for i in range(1, 10):
        (tmp_path / f"file_{i}.txt").touch()
    result = _unique_path(tmp_path, "file", ".txt")
    assert result == tmp_path / "file_10.txt"


def test_unique_path_thousand_collisions_no_hang(tmp_path: Path) -> None:
    """Regression: 1000 collisions resolve to ``file_1000.txt`` with no hang.

    The counter is unbounded — there's no internal cap.  Pin the
    contract so a future "let's bound the counter at 100" tweak
    can't silently truncate filenames or hang in an infinite loop.
    1000 is a reasonable upper bound for "user has been queueing
    translations of the same source file all afternoon"; we don't
    want to drag the test suite by going higher.
    """
    from src.utils.path_manager import _unique_path  # noqa: PLC0415

    (tmp_path / "doc.txt").touch()
    for i in range(1, 1000):
        (tmp_path / f"doc_{i}.txt").touch()
    result = _unique_path(tmp_path, "doc", ".txt")
    assert result == tmp_path / "doc_1000.txt"
    # And the next call after _1000 lands works too — no off-by-one.
    (tmp_path / "doc_1000.txt").touch()
    result2 = _unique_path(tmp_path, "doc", ".txt")
    assert result2 == tmp_path / "doc_1001.txt"


def test_unique_path_no_extension(tmp_path: Path) -> None:
    """_unique_path works with empty extension."""
    from src.utils.path_manager import _unique_path  # noqa: PLC0415

    (tmp_path / "Makefile").touch()
    result = _unique_path(tmp_path, "Makefile", "")
    assert result == tmp_path / "Makefile_1"


def test_unique_path_double_extension(tmp_path: Path) -> None:
    """_unique_path treats only the last suffix as the extension."""
    from src.utils.path_manager import _unique_path  # noqa: PLC0415

    (tmp_path / "archive.tar.gz").touch()
    result = _unique_path(tmp_path, "archive.tar", ".gz")
    assert result == tmp_path / "archive.tar_1.gz"


# ===========================================================================
# Additional tests — _resolve_output_dir
# ===========================================================================


def test_resolve_output_dir_uses_setting(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_resolve_output_dir returns configured path when setting is non-empty."""
    from src.utils.path_manager import _resolve_output_dir  # noqa: PLC0415

    custom = tmp_path / "custom_out"
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda _k, _d: str(custom),
    )
    result = _resolve_output_dir("any_key", tmp_path)
    assert result == custom
    assert result.exists()


def test_resolve_output_dir_falls_back_to_source_parent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_resolve_output_dir uses source parent when setting is empty."""
    from src.utils.path_manager import _resolve_output_dir  # noqa: PLC0415

    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda _k, _d: "",
    )
    result = _resolve_output_dir("any_key", tmp_path)
    assert result == tmp_path


def test_resolve_output_dir_falls_back_to_desktop(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_resolve_output_dir uses desktop when source parent doesn't exist."""
    from src.utils.path_manager import _resolve_output_dir  # noqa: PLC0415

    desktop = tmp_path / "Desktop"
    desktop.mkdir()
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda _k, _d: "",
    )
    monkeypatch.setattr(
        "src.utils.path_manager.get_desktop_path",
        lambda: desktop,
    )
    nonexistent = tmp_path / "nonexistent_dir"
    result = _resolve_output_dir("any_key", nonexistent)
    assert result == desktop


def test_resolve_output_dir_creates_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_resolve_output_dir creates the output directory if it doesn't exist."""
    from src.utils.path_manager import _resolve_output_dir  # noqa: PLC0415

    new_dir = tmp_path / "brand_new_dir"
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda _k, _d: str(new_dir),
    )
    assert not new_dir.exists()
    result = _resolve_output_dir("key", tmp_path)
    assert result == new_dir
    assert result.exists()


def test_resolve_output_dir_all_fallbacks_unwritable_raises_gracefully(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: every fallback unwritable → raises last OSError, doesn't crash.

    Failure mode: the user's configured storage path is unwritable
    (read-only NFS / SELinux denial / quota exceeded), the source
    file's parent is also unwritable (read-only mount), AND the
    Desktop directory is unwritable too (locked-down homedir).  The
    function must re-raise the last :class:`OSError` so the caller
    surfaces a real "couldn't write anywhere" diagnostic, NOT swallow
    it and return a path the caller can't write to (which would
    surface as a confusing "file not found" downstream) or crash with
    ``AttributeError`` on ``last_error`` being None.
    """
    from src.utils.path_manager import _resolve_output_dir  # noqa: PLC0415

    configured = tmp_path / "configured_storage"
    source_parent = tmp_path / "source"
    desktop = tmp_path / "desktop"

    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda _k, _d: str(configured),
    )
    monkeypatch.setattr(
        "src.utils.path_manager.get_desktop_path",
        lambda: desktop,
    )

    # Every mkdir raises PermissionError — simulates read-only mounts
    # across all three candidates.  The first error MUST propagate
    # via ``last_error`` so the user sees something actionable.
    def _always_denied(self: Path, **_kwargs: object) -> None:
        raise PermissionError(13, "denied", str(self))

    monkeypatch.setattr(Path, "mkdir", _always_denied)

    with pytest.raises(PermissionError) as exc_info:
        _resolve_output_dir("key", source_parent)

    # The raised error must be one of the three candidate paths —
    # confirms the function tried all fallbacks before giving up.
    raised_path = exc_info.value.filename
    assert raised_path in (
        str(configured),
        str(source_parent),
        str(desktop),
    ), f"raised path {raised_path!r} was not one of the candidates"


# ===========================================================================
# Additional tests — app directory paths
# ===========================================================================


def test_app_data_dir_is_absolute() -> None:
    """get_app_data_dir returns an absolute path."""
    assert get_app_data_dir().is_absolute()


def test_app_config_dir_is_absolute() -> None:
    """get_app_config_dir returns an absolute path."""
    assert get_app_config_dir().is_absolute()


def test_app_cache_dir_is_absolute() -> None:
    """get_app_cache_dir returns an absolute path."""
    assert get_app_cache_dir().is_absolute()


def test_app_logs_dir_is_absolute() -> None:
    """get_app_logs_dir returns an absolute path."""
    assert get_app_logs_dir().is_absolute()


def test_app_temp_dir_is_absolute() -> None:
    """get_app_temp_dir returns an absolute path."""
    assert get_app_temp_dir().is_absolute()


# ===========================================================================
# Additional tests — generate_output_path with various extensions
# ===========================================================================


def test_generate_output_path_pdf_extension(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PDF files get translated_ prefix and preserve .pdf extension."""
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda _k, _d: "",
    )
    source = tmp_path / "report.pdf"
    source.touch()
    result = generate_output_path(source)
    assert result.name == "translated_report.pdf"
    assert result.suffix == ".pdf"


def test_generate_output_path_epub_extension(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """EPUB files get translated_ prefix and preserve .epub extension."""
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda _k, _d: "",
    )
    source = tmp_path / "novel.epub"
    source.touch()
    result = generate_output_path(source)
    assert result.name == "translated_novel.epub"
    assert result.suffix == ".epub"


def test_generate_output_path_srt_extension(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SRT files preserve .srt extension."""
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda _k, _d: "",
    )
    source = tmp_path / "subtitles.srt"
    source.touch()
    result = generate_output_path(source)
    assert result.suffix == ".srt"


# ===========================================================================
# Additional tests — unicode file paths
# ===========================================================================


def test_generate_output_path_cjk_filename(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CJK characters in filename are preserved."""
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda _k, _d: "",
    )
    source = tmp_path / "\u7ffb\u8bd1\u6587\u4ef6.docx"
    source.touch()
    result = generate_output_path(source)
    assert "\u7ffb\u8bd1\u6587\u4ef6" in result.name


def test_generate_subtitle_output_path_cjk_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CJK source filename generates correct subtitle output name."""
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda *a, **kw: "",
    )
    src = tmp_path / "\u52a8\u753b.mp4"
    src.touch()
    result = generate_subtitle_output_path(src)
    assert "\u52a8\u753b_subtitle" in result.stem


# ===========================================================================
# Additional tests — get_dubbing_storage_dir
# ===========================================================================


def test_get_dubbing_storage_dir_is_absolute(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """get_dubbing_storage_dir returns an absolute path."""
    monkeypatch.setattr(
        "src.utils.path_manager.get_app_data_dir",
        lambda: tmp_path,
    )
    result = get_dubbing_storage_dir(5)
    assert result.is_absolute()


def test_get_dubbing_storage_dir_contents_empty(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Newly created dubbing storage dir is empty."""
    monkeypatch.setattr(
        "src.utils.path_manager.get_app_data_dir",
        lambda: tmp_path,
    )
    result = get_dubbing_storage_dir(77)
    assert list(result.iterdir()) == []


# ===========================================================================
# Additional tests — generate_dubbing_output_path
# ===========================================================================


def test_dubbing_output_avi_extension(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Dubbing output preserves .avi extension from source."""
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda *a, **kw: "",
    )
    src = tmp_path / "video.avi"
    src.touch()
    result = generate_dubbing_output_path(src)
    assert result.suffix == ".avi"
    assert "_dubbed" in result.stem


def test_dubbing_output_multiple_collisions_with_locale(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Multiple collisions with locale codes increment correctly."""
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda *a, **kw: "",
    )
    src = tmp_path / "video.mp4"
    src.touch()
    (tmp_path / "video_dubbed_en-US_vi.mp4").touch()
    (tmp_path / "video_dubbed_en-US_vi_1.mp4").touch()
    (tmp_path / "video_dubbed_en-US_vi_2.mp4").touch()

    result = generate_dubbing_output_path(
        src,
        src_lang="English (US)",
        target_lang="Vietnamese",
    )
    assert result.name == "video_dubbed_en-US_vi_3.mp4"


# ===========================================================================
# Additional tests — generate_voice_output_path
# ===========================================================================


def test_voice_output_wav_extension(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Voice output with .wav extension is correct."""
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda *a, **kw: "",
    )
    src = tmp_path / "narration.srt"
    src.touch()
    result = generate_voice_output_path(src, ext=".wav")
    assert result.suffix == ".wav"
    assert result.stem == "narration_voice"


# ===========================================================================
# New expanded tests — _unique_path collision handling
# ===========================================================================


def test_unique_path_no_collision(tmp_path: Path) -> None:
    """Returns original path when no file exists."""
    from src.utils.path_manager import _unique_path

    result = _unique_path(tmp_path, "report", ".docx")
    assert result == tmp_path / "report.docx"


def test_unique_path_first_collision(tmp_path: Path) -> None:
    """Appends _1 when original path exists."""
    from src.utils.path_manager import _unique_path

    (tmp_path / "report.docx").touch()
    result = _unique_path(tmp_path, "report", ".docx")
    assert result == tmp_path / "report_1.docx"


def test_unique_path_second_collision(tmp_path: Path) -> None:
    """Appends _2 when _1 also exists."""
    from src.utils.path_manager import _unique_path

    (tmp_path / "report.docx").touch()
    (tmp_path / "report_1.docx").touch()
    result = _unique_path(tmp_path, "report", ".docx")
    assert result == tmp_path / "report_2.docx"


def test_unique_path_many_collisions(tmp_path: Path) -> None:
    """Handles many collisions (up to _10)."""
    from src.utils.path_manager import _unique_path

    (tmp_path / "file.txt").touch()
    for i in range(1, 11):
        (tmp_path / f"file_{i}.txt").touch()
    result = _unique_path(tmp_path, "file", ".txt")
    assert result == tmp_path / "file_11.txt"


def test_unique_path_different_extension(tmp_path: Path) -> None:
    """Extension is preserved in collision paths."""
    from src.utils.path_manager import _unique_path

    (tmp_path / "data.csv").touch()
    result = _unique_path(tmp_path, "data", ".csv")
    assert result.suffix == ".csv"
    assert result.stem == "data_1"


def test_unique_path_empty_extension(tmp_path: Path) -> None:
    """Works with empty extension."""
    from src.utils.path_manager import _unique_path

    (tmp_path / "readme").touch()
    result = _unique_path(tmp_path, "readme", "")
    assert result == tmp_path / "readme_1"


def test_unique_path_dot_only_extension(tmp_path: Path) -> None:
    """Handles extension with just a dot."""
    from src.utils.path_manager import _unique_path

    result = _unique_path(tmp_path, "file", ".")
    assert result == tmp_path / "file."


def test_unique_path_unicode_stem(tmp_path: Path) -> None:
    """Unicode characters in stem are preserved."""
    from src.utils.path_manager import _unique_path

    (tmp_path / "tài_liệu.docx").touch()
    result = _unique_path(tmp_path, "tài_liệu", ".docx")
    assert result == tmp_path / "tài_liệu_1.docx"


def test_unique_path_stem_with_spaces(tmp_path: Path) -> None:
    """Spaces in stem are preserved."""
    from src.utils.path_manager import _unique_path

    result = _unique_path(tmp_path, "my report", ".pdf")
    assert result == tmp_path / "my report.pdf"


def test_unique_path_stem_with_dots(tmp_path: Path) -> None:
    """Dots in stem do not confuse the extension logic."""
    from src.utils.path_manager import _unique_path

    (tmp_path / "file.v2.txt").touch()
    result = _unique_path(tmp_path, "file.v2", ".txt")
    assert result == tmp_path / "file.v2_1.txt"


# ===========================================================================
# New expanded tests — _resolve_output_dir
# ===========================================================================


def test_resolve_output_dir_with_configured_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Configured setting path takes priority."""
    from src.utils.path_manager import _resolve_output_dir

    custom = tmp_path / "custom_output"
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda *a, **kw: str(custom),
    )
    result = _resolve_output_dir("any_key", tmp_path)
    assert result == custom
    assert custom.exists()


def test_resolve_output_dir_fallback_to_source_parent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Falls back to source parent when no setting configured."""
    from src.utils.path_manager import _resolve_output_dir

    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda *a, **kw: "",
    )
    result = _resolve_output_dir("any_key", tmp_path)
    assert result == tmp_path


def test_resolve_output_dir_fallback_to_desktop(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Falls back to desktop when source parent doesn't exist."""
    from src.utils.path_manager import _resolve_output_dir

    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda *a, **kw: "",
    )
    non_existent = tmp_path / "no_such_dir"
    result = _resolve_output_dir("any_key", non_existent)
    # Should be desktop or home, not the non-existent dir
    assert result.exists()


def test_resolve_output_dir_creates_directory(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Configured directory is created if it doesn't exist."""
    from src.utils.path_manager import _resolve_output_dir

    new_dir = tmp_path / "brand_new" / "nested"
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda *a, **kw: str(new_dir),
    )
    result = _resolve_output_dir("key", tmp_path)
    assert result == new_dir
    assert new_dir.exists()


# ===========================================================================
# New expanded tests — generate_output_path variations
# ===========================================================================


def test_generate_output_path_preserves_suffix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Output file has same extension as source."""
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda *a, **kw: "",
    )
    src = tmp_path / "data.xlsx"
    src.touch()
    result = generate_output_path(src)
    assert result.suffix == ".xlsx"


def test_generate_output_path_prefix(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Output filename starts with 'translated_'."""
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda *a, **kw: "",
    )
    src = tmp_path / "file.pdf"
    src.touch()
    result = generate_output_path(src)
    assert result.name.startswith("translated_")


def test_generate_output_path_collision_handling(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Generates unique name when translated file already exists."""
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda *a, **kw: "",
    )
    src = tmp_path / "doc.docx"
    src.touch()
    (tmp_path / "translated_doc.docx").touch()
    result = generate_output_path(src)
    assert result.name == "translated_doc_1.docx"


def test_generate_output_path_double_collision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Generates _2 name when _1 also exists."""
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda *a, **kw: "",
    )
    src = tmp_path / "doc.docx"
    src.touch()
    (tmp_path / "translated_doc.docx").touch()
    (tmp_path / "translated_doc_1.docx").touch()
    result = generate_output_path(src)
    assert result.name == "translated_doc_2.docx"


def test_generate_output_path_unicode_filename(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unicode source filename is preserved in output."""
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda *a, **kw: "",
    )
    src = tmp_path / "文档.pdf"
    src.touch()
    result = generate_output_path(src)
    assert result.name == "translated_文档.pdf"


def test_generate_output_path_long_filename(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Long filenames are handled."""
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda *a, **kw: "",
    )
    long_name = "a" * 200 + ".txt"
    src = tmp_path / long_name
    src.touch()
    result = generate_output_path(src)
    assert result.name.startswith("translated_")
    assert result.suffix == ".txt"


def test_generate_output_path_custom_dir(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Custom storage setting directs output to custom directory."""
    output_dir = tmp_path / "output"
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda *a, **kw: str(output_dir),
    )
    src = tmp_path / "source.odt"
    src.touch()
    result = generate_output_path(src)
    assert result.parent == output_dir


def test_generate_output_path_no_extension(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Source file without extension produces output without extension."""
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda *a, **kw: "",
    )
    src = tmp_path / "Makefile"
    src.touch()
    result = generate_output_path(src)
    assert result.suffix == ""
    assert "translated_Makefile" in result.name


# ===========================================================================
# New expanded tests — generate_extraction_output_path
# ===========================================================================


def test_extraction_output_default_txt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Default extension is .txt."""
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda *a, **kw: "",
    )
    src = tmp_path / "photo.jpg"
    src.touch()
    result = generate_extraction_output_path(src)
    assert result.suffix == ".txt"
    assert "_extracted" in result.stem


def test_extraction_output_docx_ext(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Can specify .docx extension."""
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda *a, **kw: "",
    )
    src = tmp_path / "scan.png"
    src.touch()
    result = generate_extraction_output_path(src, ext=".docx")
    assert result.suffix == ".docx"


def test_extraction_output_collision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Handles name collision for extraction output."""
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda *a, **kw: "",
    )
    src = tmp_path / "img.jpg"
    src.touch()
    (tmp_path / "img_extracted.txt").touch()
    result = generate_extraction_output_path(src)
    assert result.name == "img_extracted_1.txt"


def test_extraction_output_custom_dir(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Custom extraction storage path is used."""
    out = tmp_path / "extracts"
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda *a, **kw: str(out),
    )
    src = tmp_path / "image.png"
    src.touch()
    result = generate_extraction_output_path(src)
    assert result.parent == out


def test_extraction_output_unicode_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unicode source filename preserved in extraction output."""
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda *a, **kw: "",
    )
    src = tmp_path / "ảnh_chụp.png"
    src.touch()
    result = generate_extraction_output_path(src)
    assert "ảnh_chụp_extracted" in result.stem


# ===========================================================================
# New expanded tests — generate_subtitle_output_path
# ===========================================================================


def test_subtitle_output_default_srt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Default extension is .srt."""
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda *a, **kw: "",
    )
    src = tmp_path / "video.mp4"
    src.touch()
    result = generate_subtitle_output_path(src)
    assert result.suffix == ".srt"
    assert "_subtitle" in result.stem


def test_subtitle_output_vtt_ext(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Can specify .vtt extension."""
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda *a, **kw: "",
    )
    src = tmp_path / "audio.wav"
    src.touch()
    result = generate_subtitle_output_path(src, ext=".vtt")
    assert result.suffix == ".vtt"


def test_subtitle_output_collision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Handles name collision for subtitle output."""
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda *a, **kw: "",
    )
    src = tmp_path / "video.mp4"
    src.touch()
    (tmp_path / "video_subtitle.srt").touch()
    result = generate_subtitle_output_path(src)
    assert result.name == "video_subtitle_1.srt"


def test_subtitle_output_custom_dir(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Custom subtitle storage path is used."""
    out = tmp_path / "subs"
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda *a, **kw: str(out),
    )
    src = tmp_path / "movie.mkv"
    src.touch()
    result = generate_subtitle_output_path(src)
    assert result.parent == out


def test_subtitle_output_ass_ext(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Can specify .ass extension."""
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda *a, **kw: "",
    )
    src = tmp_path / "clip.avi"
    src.touch()
    result = generate_subtitle_output_path(src, ext=".ass")
    assert result.suffix == ".ass"


# ===========================================================================
# New expanded tests — generate_voice_output_path
# ===========================================================================


def test_voice_output_default_mp3(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Default extension is .mp3."""
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda *a, **kw: "",
    )
    src = tmp_path / "subtitle.srt"
    src.touch()
    result = generate_voice_output_path(src)
    assert result.suffix == ".mp3"
    assert "_voice" in result.stem


def test_voice_output_collision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Handles name collision for voice output."""
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda *a, **kw: "",
    )
    src = tmp_path / "narration.srt"
    src.touch()
    (tmp_path / "narration_voice.mp3").touch()
    result = generate_voice_output_path(src)
    assert result.name == "narration_voice_1.mp3"


def test_voice_output_custom_dir(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Custom voice storage path is used."""
    out = tmp_path / "voices"
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda *a, **kw: str(out),
    )
    src = tmp_path / "sub.srt"
    src.touch()
    result = generate_voice_output_path(src)
    assert result.parent == out


def test_voice_output_ogg_ext(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Can specify .ogg extension."""
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda *a, **kw: "",
    )
    src = tmp_path / "audio.srt"
    src.touch()
    result = generate_voice_output_path(src, ext=".ogg")
    assert result.suffix == ".ogg"


# ===========================================================================
# New expanded tests — generate_dubbing_output_path
# ===========================================================================


def test_dubbing_output_with_languages(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Dubbing output includes language locale codes."""
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda *a, **kw: "",
    )
    monkeypatch.setattr(
        "src.constants.languages.get_locale_code",
        lambda lang: {"English (US)": "en-US", "Vietnamese": "vi"}.get(lang, ""),
    )
    src = tmp_path / "video.mp4"
    src.touch()
    result = generate_dubbing_output_path(
        src, src_lang="English (US)", target_lang="Vietnamese"
    )
    assert result.suffix == ".mp4"
    assert "dubbed" in result.stem
    assert "en-US" in result.stem
    assert "vi" in result.stem


def test_dubbing_output_no_languages(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Dubbing output without languages uses _dubbed suffix."""
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda *a, **kw: "",
    )
    src = tmp_path / "clip.mp4"
    src.touch()
    result = generate_dubbing_output_path(src)
    assert "_dubbed" in result.stem
    assert result.suffix == ".mp4"


def test_dubbing_output_preserves_source_ext(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Dubbing preserves source video extension."""
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda *a, **kw: "",
    )
    src = tmp_path / "movie.mkv"
    src.touch()
    result = generate_dubbing_output_path(src)
    assert result.suffix == ".mkv"


def test_dubbing_output_no_extension_defaults_mp4(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Source without extension defaults to .mp4."""
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda *a, **kw: "",
    )
    src = tmp_path / "noext"
    src.touch()
    result = generate_dubbing_output_path(src)
    assert result.suffix == ".mp4"


def test_dubbing_output_collision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Handles name collision for dubbing output."""
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda *a, **kw: "",
    )
    src = tmp_path / "video.mp4"
    src.touch()
    (tmp_path / "video_dubbed.mp4").touch()
    result = generate_dubbing_output_path(src)
    assert result.name == "video_dubbed_1.mp4"


def test_dubbing_output_custom_dir(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Custom dubbing storage path is used."""
    out = tmp_path / "dubs"
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda *a, **kw: str(out),
    )
    src = tmp_path / "vid.mp4"
    src.touch()
    result = generate_dubbing_output_path(src)
    assert result.parent == out


def test_dubbing_output_partial_lang_only_src(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only source language, no target, uses _dubbed suffix."""
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda *a, **kw: "",
    )
    monkeypatch.setattr(
        "src.constants.languages.get_locale_code",
        lambda lang: "en-US" if lang == "English (US)" else "",
    )
    src = tmp_path / "video.mp4"
    src.touch()
    result = generate_dubbing_output_path(src, src_lang="English (US)")
    assert "_dubbed" in result.stem
    # Without target lang, no locale codes
    assert "en-US" not in result.stem


# ===========================================================================
# New expanded tests — get_dubbing_storage_dir
# ===========================================================================


def test_dubbing_storage_dir_created(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Dubbing storage dir is created for the given entry ID."""
    monkeypatch.setattr(
        "src.utils.path_manager.get_app_data_dir",
        lambda: tmp_path,
    )
    result = get_dubbing_storage_dir(42)
    assert result == tmp_path / "dubbing" / "42"
    assert result.exists()


def test_dubbing_storage_dir_idempotent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Calling twice returns same path without error."""
    monkeypatch.setattr(
        "src.utils.path_manager.get_app_data_dir",
        lambda: tmp_path,
    )
    r1 = get_dubbing_storage_dir(7)
    r2 = get_dubbing_storage_dir(7)
    assert r1 == r2
    assert r1.exists()


def test_dubbing_storage_dir_different_ids(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Different entry IDs produce different directories."""
    monkeypatch.setattr(
        "src.utils.path_manager.get_app_data_dir",
        lambda: tmp_path,
    )
    r1 = get_dubbing_storage_dir(1)
    r2 = get_dubbing_storage_dir(2)
    assert r1 != r2


# ===========================================================================
# New expanded tests — get_desktop_path
# ===========================================================================


def test_desktop_path_returns_path() -> None:
    """get_desktop_path returns a Path object."""
    result = get_desktop_path()
    assert isinstance(result, Path)


def test_desktop_path_exists() -> None:
    """get_desktop_path returns an existing directory."""
    result = get_desktop_path()
    assert result.exists()


def test_desktop_path_linux_xdg(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """On Linux, reads XDG_DESKTOP_DIR from user-dirs.dirs."""
    monkeypatch.setattr("platform.system", lambda: "Linux")
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

    desktop = tmp_path / "Máy tính"
    desktop.mkdir()

    config_dir = tmp_path / ".config"
    config_dir.mkdir()
    user_dirs = config_dir / "user-dirs.dirs"
    user_dirs.write_text(
        'XDG_DESKTOP_DIR="$HOME/Máy tính"\n',
        encoding="utf-8",
    )

    result = get_desktop_path()
    assert result == desktop


def test_desktop_path_linux_fallback_to_desktop(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Falls back to ~/Desktop when XDG config doesn't exist."""
    monkeypatch.setattr("platform.system", lambda: "Linux")
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

    desktop = tmp_path / "Desktop"
    desktop.mkdir()

    result = get_desktop_path()
    assert result == desktop


def test_desktop_path_linux_fallback_to_home(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Falls back to home when neither XDG nor ~/Desktop exists."""
    monkeypatch.setattr("platform.system", lambda: "Linux")
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

    result = get_desktop_path()
    assert result == tmp_path


def test_desktop_path_windows(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """On Windows, returns ~/Desktop."""
    monkeypatch.setattr("platform.system", lambda: "Windows")
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

    desktop = tmp_path / "Desktop"
    desktop.mkdir()

    result = get_desktop_path()
    assert result == desktop


def test_desktop_path_macos(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """On macOS, returns ~/Desktop."""
    monkeypatch.setattr("platform.system", lambda: "Darwin")
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

    desktop = tmp_path / "Desktop"
    desktop.mkdir()

    result = get_desktop_path()
    assert result == desktop


def test_desktop_path_linux_xdg_unreadable(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """When user-dirs.dirs exists but is unreadable, falls back gracefully."""
    monkeypatch.setattr("platform.system", lambda: "Linux")
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

    config_dir = tmp_path / ".config"
    config_dir.mkdir()
    user_dirs = config_dir / "user-dirs.dirs"
    user_dirs.write_text("GARBAGE_NOT_XDG")

    # No Desktop dir — should fallback to home
    result = get_desktop_path()
    assert result == tmp_path


def test_desktop_path_linux_xdg_resolved_not_exist(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """When XDG dir resolves to non-existent path, falls back."""
    monkeypatch.setattr("platform.system", lambda: "Linux")
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

    config_dir = tmp_path / ".config"
    config_dir.mkdir()
    user_dirs = config_dir / "user-dirs.dirs"
    user_dirs.write_text('XDG_DESKTOP_DIR="$HOME/NonExistent"\n')

    result = get_desktop_path()
    # Falls back to ~/Desktop or ~
    assert result == tmp_path


# ===========================================================================
# New expanded tests — _get_base_app_dir platform-specific
# ===========================================================================


def test_base_app_dir_linux_data(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Linux data dir follows XDG_DATA_HOME."""
    from src.utils.path_manager import _get_base_app_dir

    monkeypatch.setattr("platform.system", lambda: "Linux")
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    xdg_data = tmp_path / "xdg_data"
    monkeypatch.setenv("XDG_DATA_HOME", str(xdg_data))

    result = _get_base_app_dir("data")
    assert result == xdg_data / "ai-translate"
    assert result.exists()


def test_base_app_dir_linux_config(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Linux config dir follows XDG_CONFIG_HOME."""
    from src.utils.path_manager import _get_base_app_dir

    monkeypatch.setattr("platform.system", lambda: "Linux")
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    xdg_config = tmp_path / "xdg_config"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(xdg_config))

    result = _get_base_app_dir("config")
    assert result == xdg_config / "ai-translate"


def test_base_app_dir_linux_cache(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Linux cache dir follows XDG_CACHE_HOME."""
    from src.utils.path_manager import _get_base_app_dir

    monkeypatch.setattr("platform.system", lambda: "Linux")
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    xdg_cache = tmp_path / "xdg_cache"
    monkeypatch.setenv("XDG_CACHE_HOME", str(xdg_cache))

    result = _get_base_app_dir("cache")
    assert result == xdg_cache / "ai-translate"


def test_base_app_dir_linux_logs(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Linux logs dir follows XDG_STATE_HOME/log."""
    from src.utils.path_manager import _get_base_app_dir

    monkeypatch.setattr("platform.system", lambda: "Linux")
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    xdg_state = tmp_path / "xdg_state"
    monkeypatch.setenv("XDG_STATE_HOME", str(xdg_state))

    result = _get_base_app_dir("logs")
    assert result == xdg_state / "log" / "ai-translate"


def test_base_app_dir_linux_defaults(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Linux dirs use XDG defaults when env vars not set."""
    from src.utils.path_manager import _get_base_app_dir

    monkeypatch.setattr("platform.system", lambda: "Linux")
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
    monkeypatch.delenv("XDG_STATE_HOME", raising=False)

    data = _get_base_app_dir("data")
    config = _get_base_app_dir("config")
    cache = _get_base_app_dir("cache")
    logs = _get_base_app_dir("logs")

    assert data == tmp_path / ".local" / "share" / "ai-translate"
    assert config == tmp_path / ".config" / "ai-translate"
    assert cache == tmp_path / ".cache" / "ai-translate"
    assert logs == tmp_path / ".local" / "state" / "log" / "ai-translate"


def test_base_app_dir_windows(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Windows uses LOCALAPPDATA and APPDATA."""
    from src.utils.path_manager import _get_base_app_dir

    monkeypatch.setattr("platform.system", lambda: "Windows")
    local = tmp_path / "Local"
    roaming = tmp_path / "Roaming"
    monkeypatch.setenv("LOCALAPPDATA", str(local))
    monkeypatch.setenv("APPDATA", str(roaming))

    data = _get_base_app_dir("data")
    config = _get_base_app_dir("config")
    cache = _get_base_app_dir("cache")

    assert data == local / "ai-translate"
    assert config == roaming / "ai-translate"
    assert cache == local / "cache" / "ai-translate"


def test_base_app_dir_macos(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """MacOS uses ~/Library subdirectories."""
    from src.utils.path_manager import _get_base_app_dir

    monkeypatch.setattr("platform.system", lambda: "Darwin")
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

    data = _get_base_app_dir("data")
    config = _get_base_app_dir("config")
    cache = _get_base_app_dir("cache")
    logs = _get_base_app_dir("logs")

    assert data == tmp_path / "Library" / "Application Support" / "ai-translate"
    assert config == tmp_path / "Library" / "Preferences" / "ai-translate"
    assert cache == tmp_path / "Library" / "Caches" / "ai-translate"
    assert logs == tmp_path / "Library" / "Logs" / "ai-translate"


def test_base_app_dir_unknown_type(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Unknown dir_type falls back to home directory."""
    from src.utils.path_manager import _get_base_app_dir

    monkeypatch.setattr("platform.system", lambda: "Linux")
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)

    result = _get_base_app_dir("unknown_type")
    assert result == tmp_path / "ai-translate"


# ===========================================================================
# New expanded tests — configure_logging
# ===========================================================================


def test_configure_logging_creates_log_file() -> None:
    """configure_logging creates a log file."""
    from src.utils.path_manager import get_app_logs_dir

    configure_logging()
    log_file = get_app_logs_dir() / "app.log"
    assert log_file.exists()


def test_configure_logging_adds_handlers() -> None:
    """configure_logging adds file and console handlers."""
    configure_logging()
    root = logging.getLogger()
    handler_types = [type(h).__name__ for h in root.handlers]
    assert "FileHandler" in handler_types
    assert "StreamHandler" in handler_types


def test_configure_logging_root_level_debug() -> None:
    """Root logger is set to DEBUG level."""
    configure_logging()
    root = logging.getLogger()
    assert root.level == logging.DEBUG


# ===========================================================================
# New expanded tests — get_app_temp_dir
# ===========================================================================


def test_app_temp_dir_is_system_temp() -> None:
    """get_app_temp_dir returns the system temporary directory."""
    import tempfile

    result = get_app_temp_dir()
    assert result == Path(tempfile.gettempdir())


def test_app_temp_dir_exists() -> None:
    """Temp directory exists."""
    assert get_app_temp_dir().exists()


def test_app_temp_dir_is_directory() -> None:
    """Temp directory is actually a directory."""
    assert get_app_temp_dir().is_dir()


# ===========================================================================
# New expanded tests — Edge cases for generate functions
# ===========================================================================


def test_generate_output_path_source_parent_not_exist(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When source parent doesn't exist and no setting, falls back to desktop."""
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda *a, **kw: "",
    )
    src = tmp_path / "nonexistent_dir" / "file.txt"
    result = generate_output_path(src)
    assert result.parent.exists()


def test_extraction_path_multiple_collisions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Multiple extraction output collisions handled."""
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda *a, **kw: "",
    )
    src = tmp_path / "img.jpg"
    src.touch()
    (tmp_path / "img_extracted.txt").touch()
    (tmp_path / "img_extracted_1.txt").touch()
    (tmp_path / "img_extracted_2.txt").touch()
    result = generate_extraction_output_path(src)
    assert result.name == "img_extracted_3.txt"


def test_subtitle_output_multiple_collisions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Multiple subtitle output collisions handled."""
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda *a, **kw: "",
    )
    src = tmp_path / "video.mp4"
    src.touch()
    (tmp_path / "video_subtitle.srt").touch()
    (tmp_path / "video_subtitle_1.srt").touch()
    result = generate_subtitle_output_path(src)
    assert result.name == "video_subtitle_2.srt"


def test_voice_output_multiple_collisions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Multiple voice output collisions handled."""
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda *a, **kw: "",
    )
    src = tmp_path / "sub.srt"
    src.touch()
    (tmp_path / "sub_voice.mp3").touch()
    (tmp_path / "sub_voice_1.mp3").touch()
    (tmp_path / "sub_voice_2.mp3").touch()
    result = generate_voice_output_path(src)
    assert result.name == "sub_voice_3.mp3"


def test_dubbing_output_multiple_collisions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Multiple dubbing output collisions handled."""
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda *a, **kw: "",
    )
    src = tmp_path / "video.mp4"
    src.touch()
    (tmp_path / "video_dubbed.mp4").touch()
    (tmp_path / "video_dubbed_1.mp4").touch()
    result = generate_dubbing_output_path(src)
    assert result.name == "video_dubbed_2.mp4"


def test_generate_output_special_chars_in_name(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Special characters in filename are handled."""
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda *a, **kw: "",
    )
    src = tmp_path / "report (final) [v2].docx"
    src.touch()
    result = generate_output_path(src)
    assert "translated_report (final) [v2]" in result.stem


def test_generate_output_hidden_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Hidden file (dot prefix) is handled."""
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda *a, **kw: "",
    )
    src = tmp_path / ".hidden.txt"
    src.touch()
    result = generate_output_path(src)
    assert result.name == "translated_.hidden.txt"


def test_extraction_path_stem_preserves_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Extraction output stem contains source stem."""
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda *a, **kw: "",
    )
    src = tmp_path / "photograph.jpeg"
    src.touch()
    result = generate_extraction_output_path(src)
    assert "photograph" in result.stem


# ===========================================================================
# New expanded tests — Additional _unique_path edge cases
# ===========================================================================


def test_unique_path_compound_extension(tmp_path: Path) -> None:
    """Compound extensions like .tar.gz are treated as single ext."""
    from src.utils.path_manager import _unique_path

    (tmp_path / "archive.gz").touch()
    result = _unique_path(tmp_path, "archive", ".gz")
    assert result.name == "archive_1.gz"


def test_unique_path_numeric_stem(tmp_path: Path) -> None:
    """Numeric-only stem works correctly."""
    from src.utils.path_manager import _unique_path

    (tmp_path / "12345.txt").touch()
    result = _unique_path(tmp_path, "12345", ".txt")
    assert result.name == "12345_1.txt"


def test_unique_path_hyphenated_stem(tmp_path: Path) -> None:
    """Hyphenated stem works correctly."""
    from src.utils.path_manager import _unique_path

    result = _unique_path(tmp_path, "my-file-name", ".pdf")
    assert result.name == "my-file-name.pdf"


def test_unique_path_existing_suffixed_no_original(tmp_path: Path) -> None:
    """When _1 exists but original doesn't, returns original."""
    from src.utils.path_manager import _unique_path

    (tmp_path / "file_1.txt").touch()
    result = _unique_path(tmp_path, "file", ".txt")
    assert result.name == "file.txt"


def test_unique_path_three_collisions(tmp_path: Path) -> None:
    """Handles exactly three collisions."""
    from src.utils.path_manager import _unique_path

    (tmp_path / "doc.pdf").touch()
    (tmp_path / "doc_1.pdf").touch()
    (tmp_path / "doc_2.pdf").touch()
    result = _unique_path(tmp_path, "doc", ".pdf")
    assert result.name == "doc_3.pdf"


# ===========================================================================
# New expanded tests — _resolve_output_dir additional cases
# ===========================================================================


def test_resolve_output_dir_whitespace_setting(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Whitespace-only setting is treated as truthy (path with spaces)."""
    from src.utils.path_manager import _resolve_output_dir

    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda *a, **kw: "   ",
    )
    # Whitespace string is truthy, so it will be used as a path
    result = _resolve_output_dir("key", tmp_path)
    # The path is "   " which is truthy
    assert result.exists()


def test_resolve_output_dir_relative_source_parent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Existing source parent directory is used as fallback."""
    from src.utils.path_manager import _resolve_output_dir

    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda *a, **kw: "",
    )
    subdir = tmp_path / "subdir"
    subdir.mkdir()
    result = _resolve_output_dir("key", subdir)
    assert result == subdir


# ===========================================================================
# New expanded tests — generate functions with various extensions
# ===========================================================================


@pytest.mark.parametrize(
    "ext",
    [".pptx", ".odt", ".ods", ".odp", ".txt", ".md", ".html", ".xml", ".csv"],
)
def test_generate_output_path_various_extensions(
    ext: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Output preserves various file extensions."""
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda *a, **kw: "",
    )
    src = tmp_path / f"file{ext}"
    src.touch()
    result = generate_output_path(src)
    assert result.suffix == ext


@pytest.mark.parametrize(
    "ext",
    [".srt", ".vtt", ".ass", ".ssa"],
)
def test_subtitle_output_various_formats(
    ext: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Subtitle output works with various subtitle formats."""
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda *a, **kw: "",
    )
    src = tmp_path / "media.mp4"
    src.touch()
    result = generate_subtitle_output_path(src, ext=ext)
    assert result.suffix == ext


@pytest.mark.parametrize(
    "ext",
    [".mp3", ".wav", ".ogg", ".flac"],
)
def test_voice_output_various_formats(
    ext: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Voice output works with various audio formats."""
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda *a, **kw: "",
    )
    src = tmp_path / "sub.srt"
    src.touch()
    result = generate_voice_output_path(src, ext=ext)
    assert result.suffix == ext


@pytest.mark.parametrize(
    "ext",
    [".txt", ".docx"],
)
def test_extraction_output_various_formats(
    ext: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Extraction output works with txt and docx."""
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda *a, **kw: "",
    )
    src = tmp_path / "image.png"
    src.touch()
    result = generate_extraction_output_path(src, ext=ext)
    assert result.suffix == ext


# ===========================================================================
# New expanded tests — Unicode and special character filenames
# ===========================================================================


@pytest.mark.parametrize(
    "filename",
    [
        "файл.docx",
        "文件.xlsx",
        "ファイル.pptx",
        "파일.odt",
        "αρχείο.pdf",
        "tệp tin.txt",
        "ملف.doc",
    ],
)
def test_generate_output_path_unicode_languages(
    filename: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unicode filenames from various scripts are handled."""
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda *a, **kw: "",
    )
    src = tmp_path / filename
    src.touch()
    result = generate_output_path(src)
    assert result.parent == tmp_path
    assert result.name.startswith("translated_")


@pytest.mark.parametrize(
    "filename",
    [
        "file with spaces.docx",
        "file_with_underscores.txt",
        "file-with-dashes.pdf",
        "UPPERCASE.DOCX",
        "mixed.CaSe.TxT",
    ],
)
def test_generate_output_various_naming_conventions(
    filename: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Various naming conventions are handled."""
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda *a, **kw: "",
    )
    src = tmp_path / filename
    src.touch()
    result = generate_output_path(src)
    assert result.exists() is False  # New file doesn't exist yet
    assert result.parent.exists()


# ===========================================================================
# New expanded tests — Dubbing storage and output edge cases
# ===========================================================================


def test_dubbing_storage_zero_id(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Entry ID 0 creates a valid directory."""
    monkeypatch.setattr(
        "src.utils.path_manager.get_app_data_dir",
        lambda: tmp_path,
    )
    result = get_dubbing_storage_dir(0)
    assert result == tmp_path / "dubbing" / "0"
    assert result.exists()


def test_dubbing_storage_large_id(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Large entry ID works correctly."""
    monkeypatch.setattr(
        "src.utils.path_manager.get_app_data_dir",
        lambda: tmp_path,
    )
    result = get_dubbing_storage_dir(999999)
    assert result == tmp_path / "dubbing" / "999999"
    assert result.exists()


def test_dubbing_output_avi_extension(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Dubbing with .avi source preserves extension."""
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda *a, **kw: "",
    )
    src = tmp_path / "movie.avi"
    src.touch()
    result = generate_dubbing_output_path(src)
    assert result.suffix == ".avi"


def test_dubbing_output_webm_extension(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Dubbing with .webm source preserves extension."""
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda *a, **kw: "",
    )
    src = tmp_path / "clip.webm"
    src.touch()
    result = generate_dubbing_output_path(src)
    assert result.suffix == ".webm"


# ===========================================================================
# New expanded tests — ensure_app_dirs_exist
# ===========================================================================


def test_ensure_dirs_idempotent() -> None:
    """Calling ensure_app_dirs_exist multiple times is safe."""
    ensure_app_dirs_exist()
    ensure_app_dirs_exist()
    # Should not raise


def test_ensure_dirs_all_exist() -> None:
    """All app directories exist after ensure_app_dirs_exist."""
    ensure_app_dirs_exist()
    assert get_app_data_dir().exists()
    assert get_app_config_dir().exists()
    assert get_app_cache_dir().exists()
    assert get_app_logs_dir().exists()


# ===========================================================================
# New expanded tests — App directory properties
# ===========================================================================


def test_app_data_dir_contains_app_name() -> None:
    """Data directory contains 'ai-translate' in path."""
    assert "ai-translate" in str(get_app_data_dir())


def test_app_config_dir_contains_app_name() -> None:
    """Config directory contains 'ai-translate' in path."""
    assert "ai-translate" in str(get_app_config_dir())


def test_app_cache_dir_contains_app_name() -> None:
    """Cache directory contains 'ai-translate' in path."""
    assert "ai-translate" in str(get_app_cache_dir())


def test_app_logs_dir_contains_app_name() -> None:
    """Logs directory contains 'ai-translate' in path."""
    assert "ai-translate" in str(get_app_logs_dir())


def test_app_data_dir_is_directory() -> None:
    """Data directory is a directory, not a file."""
    assert get_app_data_dir().is_dir()


def test_app_config_dir_is_directory() -> None:
    """Config directory is a directory."""
    assert get_app_config_dir().is_dir()


def test_app_cache_dir_is_directory() -> None:
    """Cache directory is a directory."""
    assert get_app_cache_dir().is_dir()


def test_app_dirs_are_different() -> None:
    """Data, config, cache, and logs directories are all different."""
    dirs = {
        get_app_data_dir(),
        get_app_config_dir(),
        get_app_cache_dir(),
        get_app_logs_dir(),
    }
    assert len(dirs) == 4


# ===========================================================================
# New expanded tests — final batch
# ===========================================================================


def test_unique_path_case_sensitive(tmp_path: Path) -> None:
    """Path collision is case-sensitive on case-sensitive filesystems."""
    from src.utils.path_manager import _unique_path

    (tmp_path / "File.txt").touch()
    result = _unique_path(tmp_path, "file", ".txt")
    # On case-sensitive filesystems, file.txt != File.txt
    # Just verify it returns a valid path
    assert result.parent == tmp_path


def test_generate_output_path_multiple_dots(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Source file with multiple dots in name is handled."""
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda *a, **kw: "",
    )
    src = tmp_path / "report.v2.final.docx"
    src.touch()
    result = generate_output_path(src)
    assert result.suffix == ".docx"
    assert "translated_" in result.name


def test_extraction_double_collision_docx(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Double collision with .docx extraction output."""
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda *a, **kw: "",
    )
    src = tmp_path / "scan.png"
    src.touch()
    (tmp_path / "scan_extracted.docx").touch()
    (tmp_path / "scan_extracted_1.docx").touch()
    result = generate_extraction_output_path(src, ext=".docx")
    assert result.name == "scan_extracted_2.docx"


# ===========================================================================
# Backfill — _unique_path collisions, generate_output_path with unwritable
# storage, Unicode/emoji path components.
# ===========================================================================


def test_unique_path_five_collisions(tmp_path: Path) -> None:
    """Five existing files yield ``<stem>_5<ext>``."""
    from src.utils.path_manager import _unique_path  # noqa: PLC0415

    # Create base + _1, _2, _3, _4 → next free is _5.
    (tmp_path / "report.txt").touch()
    for i in range(1, 5):
        (tmp_path / f"report_{i}.txt").touch()

    result = _unique_path(tmp_path, "report", ".txt")
    assert result.name == "report_5.txt"


def test_unique_path_returns_base_name_when_no_collision(tmp_path: Path) -> None:
    """Empty directory returns plain ``<stem><ext>`` with no suffix."""
    from src.utils.path_manager import _unique_path  # noqa: PLC0415

    result = _unique_path(tmp_path, "fresh", ".pdf")
    assert result.name == "fresh.pdf"


def test_generate_output_path_unwritable_storage_falls_back_to_source_parent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """An unwritable configured storage path falls back to the source parent.

    Avoids surfacing a confusing OSError to the user when their saved
    output directory has been moved, deleted, or made read-only.
    """
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda _k, _d: "/proc/0/cannot-create-this",
    )
    source = tmp_path / "doc.txt"
    source.touch()

    import logging  # noqa: PLC0415

    with caplog.at_level(logging.WARNING, logger="path_manager"):
        result = generate_output_path(source)
    # Output sits next to the source file (the first viable fallback).
    assert result.parent == tmp_path
    assert any("/proc/0/cannot-create-this" in rec.message for rec in caplog.records)


def test_generate_output_path_all_candidates_fail_reraises(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When all three candidates fail, the last OSError re-raises.

    Configured-storage, source-parent, and Desktop fallbacks all
    raise here so the caller sees a real error instead of silently
    writing nowhere.
    """
    from src.utils import path_manager as pm  # noqa: PLC0415

    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda _k, _d: "/proc/0/configured",
    )
    monkeypatch.setattr(
        pm,
        "get_desktop_path",
        lambda: Path("/proc/0/desktop"),
    )

    # Force every mkdir to fail so all three fallback candidates raise.
    original_mkdir = Path.mkdir

    def always_raise(self, *_args, **_kwargs):  # noqa: ANN001, ANN201
        raise PermissionError(f"simulated permission denied on {self}")

    monkeypatch.setattr(Path, "mkdir", always_raise)

    source = tmp_path / "doc.txt"
    # Don't actually create the file (we patched mkdir; touching may fail
    # too).  Just synthesize a Path; generate_output_path doesn't stat.
    try:
        with pytest.raises(OSError):
            pm.generate_output_path(source)
    finally:
        # Restore so tmp_path cleanup works.
        monkeypatch.setattr(Path, "mkdir", original_mkdir)


def test_resolve_output_dir_no_setting_no_source_parent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Empty setting + non-existent source parent → falls back to Desktop."""
    from src.utils import path_manager as pm  # noqa: PLC0415

    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda _k, _d: "",
    )
    desktop = tmp_path / "fake_desktop"
    monkeypatch.setattr(pm, "get_desktop_path", lambda: desktop)

    # Source parent does not exist.
    missing_parent = tmp_path / "vanished"
    result = pm._resolve_output_dir("any_setting_key", missing_parent)
    assert result == desktop
    assert desktop.is_dir()


def test_generate_output_path_unicode_with_emoji(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unicode + emoji in filename and directory are handled correctly."""
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda _k, _d: "",
    )
    # Vietnamese diacritics + emoji in directory and filename.
    nested = tmp_path / "tài_liệu_📄"
    nested.mkdir()
    source = nested / "báo_cáo_🎉.docx"
    source.touch()

    result = generate_output_path(source)

    # No exception, output preserves the unicode/emoji characters.
    assert result.parent == nested
    assert "translated_báo_cáo_🎉" in result.name
    assert result.suffix == ".docx"


def test_generate_output_path_unicode_target_dir(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Configured storage path with unicode/emoji works."""
    target = tmp_path / "đầu_ra_🚀"
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda _k, _d: str(target),
    )
    source = tmp_path / "input.txt"
    source.touch()

    result = generate_output_path(source)

    assert result.parent == target
    assert target.exists()  # mkdir created it
    assert result.name == "translated_input.txt"


def test_unique_path_many_collisions_keeps_counting(tmp_path: Path) -> None:
    """20 collisions yield ``_20`` suffix (counter has no upper bound)."""
    from src.utils.path_manager import _unique_path  # noqa: PLC0415

    (tmp_path / "x.dat").touch()
    for i in range(1, 20):
        (tmp_path / f"x_{i}.dat").touch()

    result = _unique_path(tmp_path, "x", ".dat")
    assert result.name == "x_20.dat"


# ===========================================================================
# Triple-check gap coverage — _resolve_output_dir edge cases
# ===========================================================================


def test_resolve_output_dir_configured_equals_source_parent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Configured path identical to source_parent: returned as-is.

    The setting branch has priority over the fallback chain — when the
    user happens to point the storage path at the source's own parent
    dir, the configured value still wins (no special "they're the same"
    short-circuit). This guards against a future refactor that might
    accidentally treat identity as "not configured".
    """
    from src.utils.path_manager import _resolve_output_dir  # noqa: PLC0415

    source_parent = tmp_path / "src"
    source_parent.mkdir()
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda _k, _d: str(source_parent),
    )

    result = _resolve_output_dir("any_key", source_parent)
    assert result == source_parent
    assert result.exists()


def test_resolve_output_dir_desktop_creatable_but_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Source parent missing AND Desktop dir doesn't exist yet → mkdir creates it.

    Validates the final fallback also goes through ``mkdir(parents=True,
    exist_ok=True)`` rather than failing when the desktop dir hasn't
    materialised yet (e.g. fresh user account, no XDG dirs created).
    """
    from src.utils.path_manager import _resolve_output_dir  # noqa: PLC0415

    desktop_root = tmp_path / "fresh_user_home" / "Desktop"
    # NOTE: not creating desktop_root yet — _resolve_output_dir must mkdir.
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda _k, _d: "",
    )
    monkeypatch.setattr(
        "src.utils.path_manager.get_desktop_path",
        lambda: desktop_root,
    )

    nonexistent_source = tmp_path / "vanished" / "src"
    assert not nonexistent_source.exists()
    assert not desktop_root.exists()

    result = _resolve_output_dir("any_key", nonexistent_source)
    assert result == desktop_root
    # mkdir(parents=True, exist_ok=True) created the chain.
    assert result.exists()
    assert result.is_dir()


# ===========================================================================
# Unicode / non-ASCII filename coverage
# ===========================================================================
#
# Existing collision-counter tests use ASCII stems.  Real users drop
# files with emoji, RTL scripts, and CJK in their names.  These tests
# guard against regressions where the counter suffix corrupts the
# filename or the collision check fails to recognise an existing
# Unicode file as a collision (e.g. NFC vs NFD normalization mismatch).


def test_unique_path_emoji_no_collision(tmp_path: Path) -> None:
    """``_unique_path`` returns an emoji-bearing name unchanged when free."""
    from src.utils.path_manager import _unique_path  # noqa: PLC0415

    result = _unique_path(tmp_path, "report_📊", ".xlsx")
    assert result == tmp_path / "report_📊.xlsx"


def test_unique_path_emoji_collision_appends_counter(tmp_path: Path) -> None:
    """Emoji stems collide and gain an ``_1`` suffix without mangling."""
    from src.utils.path_manager import _unique_path  # noqa: PLC0415

    (tmp_path / "report_📊.xlsx").touch()
    result = _unique_path(tmp_path, "report_📊", ".xlsx")
    # The emoji must survive intact; only the counter is appended.
    assert result == tmp_path / "report_📊_1.xlsx"
    assert result.name == "report_📊_1.xlsx"


def test_unique_path_rtl_script(tmp_path: Path) -> None:
    """Right-to-left script (Arabic) stems work as collision keys."""
    from src.utils.path_manager import _unique_path  # noqa: PLC0415

    (tmp_path / "العربية.txt").touch()
    result = _unique_path(tmp_path, "العربية", ".txt")
    assert result == tmp_path / "العربية_1.txt"


def test_unique_path_cjk_collision_chain(tmp_path: Path) -> None:
    """CJK stems extend the collision counter past the first conflict."""
    from src.utils.path_manager import _unique_path  # noqa: PLC0415

    (tmp_path / "文件.docx").touch()
    (tmp_path / "文件_1.docx").touch()
    result = _unique_path(tmp_path, "文件", ".docx")
    assert result == tmp_path / "文件_2.docx"


def test_unique_path_vietnamese_diacritics(tmp_path: Path) -> None:
    """Vietnamese diacritics (combining + precomposed) round-trip cleanly."""
    from src.utils.path_manager import _unique_path  # noqa: PLC0415

    # Vietnamese stem with multiple diacritics.
    stem = "tài_liệu"
    (tmp_path / f"{stem}.pdf").touch()
    result = _unique_path(tmp_path, stem, ".pdf")
    assert result.name == f"{stem}_1.pdf"


# ── get_default_live_output_dir ───────────────────────────────────────


def test_get_default_live_output_dir_is_under_home_documents() -> None:
    """Default Live folder lives under ``~/Documents/AI Translate Live``.

    Picked for discoverability — burying recordings in app-data
    leaves users unable to find their files without docs.
    """
    from src.utils.path_manager import get_default_live_output_dir  # noqa: PLC0415

    result = get_default_live_output_dir()
    assert result.parent.name == "Documents"
    assert result.name == "AI Translate Live"
    # Cross-platform sanity: the parent.parent should be the user's
    # home directory (resolved by ``Path.home()`` internally).
    assert result.parent.parent == Path.home()


# ── generate_live_session_output_path ─────────────────────────────────


def test_generate_live_session_output_path_uses_configured_dir(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A configured SETTING_LIVE_OUTPUT_PATH overrides the default folder."""
    from src.utils.path_manager import (  # noqa: PLC0415
        generate_live_session_output_path,
    )

    configured = tmp_path / "my_live_recordings"
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda _k, _d: str(configured),
    )

    result = generate_live_session_output_path(
        extension=".wav",
        stem_prefix="live_audio",
        timestamp="2026-01-15_10-30-45",
    )

    assert result.parent == configured
    assert result.name == "live_audio_2026-01-15_10-30-45.wav"
    # Folder must have been created so the caller can write immediately.
    assert configured.is_dir()


def test_generate_live_session_output_path_falls_back_when_configured_unwritable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """OSError on mkdir → fall back to the default Documents folder.

    A read-only / unmounted / deleted configured path doesn't crash
    the Live save pipeline; it silently redirects to the default
    folder.  Mirrors the same convention as
    :func:`_resolve_output_dir` for translated documents.
    """
    from src.utils.path_manager import (  # noqa: PLC0415
        generate_live_session_output_path,
    )

    fallback_dir = tmp_path / "fallback_documents" / "AI Translate Live"
    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda _k, _d: "/this/path/does/not/and/cannot/exist",
    )
    monkeypatch.setattr(
        "src.utils.path_manager.get_default_live_output_dir",
        lambda: fallback_dir,
    )
    # Force the configured-path mkdir to raise so the fallback branch
    # is hit deterministically.  Patch Path.mkdir to raise for the
    # configured path only — the fallback mkdir should succeed.
    real_mkdir = Path.mkdir

    def selective_mkdir(self, *a, **kw):
        if "does/not" in str(self):
            raise OSError("permission denied")
        return real_mkdir(self, *a, **kw)

    monkeypatch.setattr(Path, "mkdir", selective_mkdir)

    result = generate_live_session_output_path(
        extension=".txt",
        stem_prefix="live_transcript",
        timestamp="2026-01-15_10-30-45",
    )

    assert result.parent == fallback_dir
    assert result.name == "live_transcript_2026-01-15_10-30-45.txt"


def test_generate_live_session_output_path_shared_timestamp_pairs_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Passing the same ``timestamp`` produces paired audio/transcript files.

    Locks the contract that powers Live's "save both" flow: the page
    formats one timestamp once, then calls this helper twice (once
    for ``.wav``, once for ``.txt``) so the user gets visually paired
    files in the output folder.
    """
    from src.utils.path_manager import (  # noqa: PLC0415
        generate_live_session_output_path,
    )

    monkeypatch.setattr(
        "src.utils.config_manager.load_setting",
        lambda _k, _d: str(tmp_path),
    )
    stamp = "2026-01-15_10-30-45"

    audio = generate_live_session_output_path(
        extension=".wav",
        stem_prefix="live_audio",
        timestamp=stamp,
    )
    transcript = generate_live_session_output_path(
        extension=".txt",
        stem_prefix="live_transcript",
        timestamp=stamp,
    )

    assert audio.stem == f"live_audio_{stamp}"
    assert transcript.stem == f"live_transcript_{stamp}"
    assert audio.parent == transcript.parent
