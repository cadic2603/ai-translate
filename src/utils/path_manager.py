"""Utility for managing cross-platform application paths and temporary files.

Supports Windows, macOS, and Linux following platform-specific standards.
"""

import logging
import os
import platform
import tempfile
from pathlib import Path

logger = logging.getLogger("path_manager")


def _get_base_app_dir(dir_type: str) -> Path:
    """Internal helper to determine base directories across platforms.

    dir_type: 'data', 'config', 'cache', 'logs'.
    """
    system = platform.system()
    home = Path.home()

    if system == "Windows":
        local_app_data = Path(os.getenv("LOCALAPPDATA", tempfile.gettempdir()))
        roaming_app_data = Path(os.getenv("APPDATA", tempfile.gettempdir()))

        paths = {
            "data": local_app_data,
            "config": roaming_app_data,
            "cache": local_app_data / "cache",
            "logs": local_app_data / "logs",
        }
    elif system == "Darwin":  # macOS
        library = home / "Library"
        paths = {
            "data": library / "Application Support",
            "config": library / "Preferences",
            "cache": library / "Caches",
            "logs": library / "Logs",
        }
    else:  # Linux and other POSIX
        # Follow XDG Base Directory Specification
        xdg_data = Path(os.getenv("XDG_DATA_HOME", home / ".local" / "share"))
        xdg_config = Path(os.getenv("XDG_CONFIG_HOME", home / ".config"))
        xdg_cache = Path(os.getenv("XDG_CACHE_HOME", home / ".cache"))
        xdg_state = Path(os.getenv("XDG_STATE_HOME", home / ".local" / "state"))

        paths = {
            "data": xdg_data,
            "config": xdg_config,
            "cache": xdg_cache,
            "logs": xdg_state / "log",
        }

    app_dir = paths.get(dir_type, home) / "ai-translate"
    app_dir.mkdir(parents=True, exist_ok=True)
    return app_dir


def get_app_data_dir() -> Path:
    """Persistent application data (e.g., databases)."""
    return _get_base_app_dir("data")


def get_app_config_dir() -> Path:
    """Application configuration and settings."""
    return _get_base_app_dir("config")


def get_app_cache_dir() -> Path:
    """Non-essential cached data (e.g., translation models)."""
    return _get_base_app_dir("cache")


def get_piper_voice_dir() -> Path:
    """Returns the directory holding downloaded Piper TTS voice models.

    Each voice is one ``<voice_id>.onnx`` + ``<voice_id>.onnx.json``
    pair, downloaded on demand from HuggingFace via Settings → Voice
    → Piper.  Files persist across sessions (unlike the TTS cache,
    which is wiped on app start) — voice models are slow to fetch
    (25–60 MB each) and the user explicitly opted in to install them.
    Lives under ``app_data_dir`` rather than ``cache_dir`` so a cache
    wipe doesn't blow away the user's downloaded voices.
    """
    d = get_app_data_dir() / "piper_voices"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_tts_cache_dir() -> Path:
    """Returns the directory holding cached Listen-button TTS audio."""
    d = get_app_cache_dir() / "tts"
    d.mkdir(parents=True, exist_ok=True)
    return d


def wipe_tts_cache() -> None:
    """Removes all cached Listen-button TTS audio files.

    Called at app start so each session begins with a clean TTS cache.
    Missing directory or individual permission errors are ignored — the
    cache is best-effort and rebuilds on demand.
    """
    import shutil  # noqa: PLC0415

    d = get_app_cache_dir() / "tts"
    if d.is_dir():
        shutil.rmtree(d, ignore_errors=True)


def get_llm_endpoint_cache_path() -> Path:
    """Returns the JSON file persisting Custom-LLM endpoint probe results.

    Holds the chat-vs-responses API choice and the working chat payload
    variant per ``(endpoint, model)`` so CLI / MCP / desktop sessions
    don't re-pay the variant probe on every cold start.  Lives under the
    cache dir because it's regenerable best-effort state — wiping it
    just costs one round-trip on the next call.
    """
    return get_app_cache_dir() / "llm_endpoint_cache.json"


def get_app_logs_dir() -> Path:
    """Application log files."""
    return _get_base_app_dir("logs")


def get_app_temp_dir() -> Path:
    """System-level temporary directory for the current session."""
    return Path(tempfile.gettempdir())


def ensure_app_dirs_exist() -> None:
    """Ensures all necessary application directories exist on the system.

    Should be called during application startup.
    """
    get_app_data_dir()
    get_app_config_dir()
    get_app_cache_dir()
    get_app_logs_dir()


def configure_logging() -> None:
    """Configures centralized logging for the application.

    Sets up a file handler for all application loggers and a console
    handler for DEBUG+ messages. Should be called once from app startup.
    """
    log_dir = get_app_logs_dir()
    log_file = log_dir / "app.log"

    # Root logger config — all child loggers inherit this
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    # File handler — captures all levels
    file_handler = logging.FileHandler(str(log_file), encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    )

    # Console handler — debug and above for development visibility
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)
    console_handler.setFormatter(
        logging.Formatter("%(name)s - %(levelname)s - %(message)s")
    )

    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)


def get_desktop_path() -> Path:
    """Returns the user's Desktop directory path cross-platform.

    On Linux, reads ``XDG_DESKTOP_DIR`` from ``user-dirs.dirs`` if available.
    On Windows/macOS, ``~/Desktop`` is the standard location.
    Falls back to the user's home directory if the Desktop cannot be resolved.
    """
    home = Path.home()
    system = platform.system()

    if system == "Linux":
        # XDG user-dirs specification (handles non-English locales)
        user_dirs = home / ".config" / "user-dirs.dirs"
        if user_dirs.exists():
            try:
                for raw_line in user_dirs.read_text(encoding="utf-8").splitlines():
                    stripped = raw_line.strip()
                    if stripped.startswith("XDG_DESKTOP_DIR="):
                        # Format: XDG_DESKTOP_DIR="$HOME/Desktop"
                        raw = stripped.split("=", 1)[1].strip('"')
                        resolved = Path(raw.replace("$HOME", str(home)))
                        if resolved.exists():
                            return resolved
            except OSError:
                pass

    desktop = home / "Desktop"
    return desktop if desktop.exists() else home


def _resolve_output_dir(setting_key: str, source_parent: Path) -> Path:
    """Resolves the output directory from a setting key with fallback.

    Priority: user-configured storage path → source file's parent
    directory (if it exists) → Desktop fallback.  When the configured
    path can't be created (permission denied, read-only mount, etc.)
    the same fallback chain kicks in so a stale or invalid setting
    doesn't crash the translation pipeline.

    Args:
        setting_key: INI settings key for the storage path.
        source_parent: Parent directory of the source file.

    Returns:
        Resolved output directory (created if absent).
    """
    from src.utils.config_manager import load_setting  # noqa: PLC0415

    output_dir_str = load_setting(setting_key, "")
    candidates: list[Path] = []
    if output_dir_str:
        candidates.append(Path(output_dir_str))
    if source_parent.exists():
        candidates.append(source_parent)
    candidates.append(get_desktop_path())

    last_error: OSError | None = None
    for candidate in candidates:
        try:
            candidate.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            logger.warning(
                "Output directory %s is not writable (%s); trying next fallback",
                candidate,
                exc,
            )
            last_error = exc
            continue
        return candidate

    # All candidates failed — re-raise the last error so the caller can
    # surface it instead of silently writing nowhere.
    if last_error is not None:
        raise last_error
    return get_desktop_path()


def _unique_path(directory: Path, stem: str, ext: str) -> Path:
    """Returns a unique file path, appending ``_1``, ``_2``, … on collision.

    Args:
        directory: Target directory.
        stem: Base file name without extension.
        ext: File extension including the leading dot.

    Returns:
        A Path that does not collide with existing files.
    """
    target = directory / f"{stem}{ext}"
    if not target.exists():
        return target

    counter = 1
    while True:
        candidate = directory / f"{stem}_{counter}{ext}"
        if not candidate.exists():
            return candidate
        counter += 1


def generate_extraction_output_path(source_file_path: Path, ext: str = ".txt") -> Path:
    """Generates a unique output path for an extracted text file.

    Args:
        source_file_path: Original image file path.
        ext: Output file extension (e.g. ".txt", ".docx").

    Returns:
        Unique Path for the extracted text output file.
    """
    from src.constants.settings import SETTING_EXTRACT_STORAGE_PATH  # noqa: PLC0415

    output_dir = _resolve_output_dir(
        SETTING_EXTRACT_STORAGE_PATH, source_file_path.parent
    )
    return _unique_path(output_dir, f"{source_file_path.stem}_extracted", ext)


def generate_subtitle_output_path(
    source_file_path: Path,
    ext: str = ".srt",
) -> Path:
    """Generates a unique output path for a subtitle file.

    Args:
        source_file_path: Original audio/video file path.
        ext: Output file extension (e.g. ".srt", ".vtt").

    Returns:
        Unique Path for the subtitle output file.
    """
    from src.constants.settings import SETTING_SUBTITLE_STORAGE_PATH  # noqa: PLC0415

    output_dir = _resolve_output_dir(
        SETTING_SUBTITLE_STORAGE_PATH, source_file_path.parent
    )
    return _unique_path(output_dir, f"{source_file_path.stem}_subtitle", ext)


def generate_voice_output_path(
    source_file_path: Path,
    ext: str = ".mp3",
) -> Path:
    """Generates a unique output path for a voice audio file.

    Args:
        source_file_path: Original subtitle file path.
        ext: Output file extension (e.g. ".mp3", ".wav").

    Returns:
        Unique Path for the voice audio output file.
    """
    from src.constants.settings import SETTING_VOICE_STORAGE_PATH  # noqa: PLC0415

    output_dir = _resolve_output_dir(
        SETTING_VOICE_STORAGE_PATH, source_file_path.parent
    )
    return _unique_path(output_dir, f"{source_file_path.stem}_voice", ext)


def generate_live_session_output_path(
    *,
    extension: str,
    stem_prefix: str,
    timestamp: str | None = None,
) -> Path:
    """Generates a timestamped output path for a Live session artefact.

    Used by the Live page to save the session's audio recording
    (``.wav``) and/or transcript (``.txt``).  Both share the same
    folder and timestamp so a paired ``live_audio_<ts>.wav`` /
    ``live_transcript_<ts>.txt`` lands together.

    Storage folder = ``SETTING_LIVE_OUTPUT_PATH`` if set, else a
    ``live_audio/`` folder under the user's app-data directory.

    Args:
        extension: Output file extension (e.g. ``".wav"`` or ``".txt"``).
        stem_prefix: File name prefix (e.g. ``"live_audio"`` or
            ``"live_transcript"``).
        timestamp: Optional pre-formatted timestamp for pairing — pass
            the same string to two calls so the audio and transcript
            files share an exact stem suffix.  When None, a fresh
            timestamp is generated.
    """
    from datetime import datetime  # noqa: PLC0415

    from src.constants.settings import (  # noqa: PLC0415
        SETTING_LIVE_OUTPUT_PATH,
    )
    from src.utils.config_manager import load_setting  # noqa: PLC0415

    configured = load_setting(SETTING_LIVE_OUTPUT_PATH, "")
    if configured:
        try:
            output_dir = Path(str(configured)).expanduser()
            output_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            output_dir = get_default_live_output_dir()
            output_dir.mkdir(parents=True, exist_ok=True)
    else:
        output_dir = get_default_live_output_dir()
        output_dir.mkdir(parents=True, exist_ok=True)
    stamp = timestamp or datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return _unique_path(output_dir, f"{stem_prefix}_{stamp}", extension)


def get_default_live_output_dir() -> Path:
    """Returns the default folder for Live session recordings.

    ``~/Documents/AI Translate Live`` (cross-platform — ``Path.home()``
    works on Linux, macOS, and Windows).  Picked for discoverability:
    burying recordings in app-data leaves users unable to find their
    files without docs.  Documents is where users instinctively look
    for app-saved content.

    Used both as the silent fallback in
    :func:`generate_live_session_output_path` (when the configured
    path is empty / unwritable) AND as the default the Settings UI
    auto-fills into the path picker when the user opts into save mode.
    """
    return Path.home() / "Documents" / "AI Translate Live"


def get_dubbing_storage_dir(entry_id: int) -> Path:
    """Returns a persistent storage directory for a dubbing entry.

    Used to store checkpoints and intermediate files (voice audio)
    that survive pause/resume cycles.

    Args:
        entry_id: Dubbing history entry ID.

    Returns:
        Path to the storage directory (created if absent).
    """
    storage = get_app_data_dir() / "dubbing" / str(entry_id)
    storage.mkdir(parents=True, exist_ok=True)
    return storage


def generate_dubbing_output_path(
    source_file_path: Path,
    src_lang: str = "",
    target_lang: str = "",
) -> Path:
    """Generates a unique output path for a dubbed video file.

    Args:
        source_file_path: Original video file path.
        src_lang: Source language label (e.g. "English (US)").
        target_lang: Target language label (e.g. "Vietnamese").

    Returns:
        Unique Path for the dubbed video output file.
    """
    from src.constants.languages import get_locale_code  # noqa: PLC0415
    from src.constants.settings import SETTING_DUBBING_STORAGE_PATH  # noqa: PLC0415

    output_dir = _resolve_output_dir(
        SETTING_DUBBING_STORAGE_PATH, source_file_path.parent
    )
    ext = source_file_path.suffix or ".mp4"

    # Add locale codes when both languages are specified
    src_code = get_locale_code(src_lang) if src_lang else ""
    tgt_code = get_locale_code(target_lang) if target_lang else ""
    tag = f"_dubbed_{src_code}_{tgt_code}" if src_code and tgt_code else "_dubbed"

    return _unique_path(output_dir, f"{source_file_path.stem}{tag}", ext)


def generate_output_path(source_file_path: Path) -> Path:
    """Generates a unique output path for a translated file.

    Priority: user-configured storage path → source file's parent
    directory (if it exists) → Desktop fallback.

    Args:
        source_file_path: Original file path to translate.

    Returns:
        Unique Path for the translated output file.
    """
    from src.constants.settings import SETTING_STORAGE_PATH  # noqa: PLC0415

    output_dir = _resolve_output_dir(SETTING_STORAGE_PATH, source_file_path.parent)
    stem = f"translated_{source_file_path.stem}"
    return _unique_path(output_dir, stem, source_file_path.suffix)
