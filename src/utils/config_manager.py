"""Utility for managing persistent application settings using configparser."""

import configparser
import contextlib
import logging
from pathlib import Path
from typing import Any

import keyring

logger = logging.getLogger("config_manager")

_SERVICE_NAME = "ai-translate"

# Keys that should be stored securely in the OS keychain
_SECURE_KEYS = {
    "cloud/google_api_key",
    "llm/gemini_api_key",
    "llm/custom_api_key",
    "llm/custom_providers",  # JSON blob containing per-provider api_key fields
    "service/soniox_api_key",
    "service/elevenlabs_api_key",
}

# Default section for settings in the INI file
_SECTION = "General"


def _get_config_path() -> Path:
    """Returns the path to the settings INI file."""
    from src.utils.path_manager import get_app_config_dir  # noqa: PLC0415

    return get_app_config_dir() / "settings.ini"


def get_settings() -> configparser.ConfigParser:
    """Returns a ConfigParser instance loaded from the settings file.

    Returns:
        configparser.ConfigParser: The loaded configuration.
    """
    config = configparser.ConfigParser()
    config.optionxform = str  # preserve key casing
    config_path = _get_config_path()
    if config_path.exists():
        config.read(str(config_path), encoding="utf-8")
    return config


def _save_config(config: configparser.ConfigParser) -> None:
    """Writes the config to disk, creating the parent directory if needed.

    All values are sanitised in-place before serialisation so that any
    pre-existing multi-line values (inherited from a previously corrupted
    INI) are collapsed to a single line and can't round-trip back as
    stray continuation lines.
    """
    for section in config.sections():
        for key in config.options(section):
            raw = config.get(section, key, raw=True)
            clean = _sanitize_ini_value(raw)
            if clean != raw:
                config.set(section, key, clean)
    config_path = _get_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with config_path.open("w", encoding="utf-8") as fh:
        config.write(fh)


def _sanitize_ini_value(value: Any) -> str:  # noqa: ANN401
    """Strips newlines from *value* before it reaches configparser.

    ``configparser`` treats indented lines that follow a key as multi-line
    continuations of that key's value.  If a caller ever saves a string
    containing a newline, the round-trip can corrupt neighbouring keys on
    the next load — which historically leaked stray ``= m`` lines into
    ``settings.ini`` and contaminated shortcut values.  Collapse newlines
    at the storage boundary while preserving in-line whitespace (so
    whitespace-only values keep their legacy truthy semantics).
    """
    if value is None:
        return ""
    text = str(value)
    if "\n" in text or "\r" in text:
        # Keep only the first line so legitimate first values survive while
        # any accidental continuation lines are dropped.
        first_line = text.splitlines()[0] if text.splitlines() else ""
        text = first_line
    return text


def save_setting(key: str, value: Any) -> None:  # noqa: ANN401
    """Saves a setting value for the given key.

    Args:
        key (str): The setting key.
        value (Any): The value to save.
    """
    # Defensive: an empty key produces a bare "= value" line in the INI,
    # which on reload becomes a continuation of whichever key came before
    # it — corrupting that key's value. Ignore silently instead of letting
    # configparser write it.
    if not key:
        logger.warning("save_setting called with empty key; ignoring")
        return

    sanitised = _sanitize_ini_value(value)

    if key in _SECURE_KEYS:
        try:
            if sanitised:
                keyring.set_password(_SERVICE_NAME, key, sanitised)
            else:
                with contextlib.suppress(keyring.errors.PasswordDeleteError):
                    keyring.delete_password(_SERVICE_NAME, key)
        except Exception as e:
            logger.error("Failed to save secure setting %s: %s", key, e)
            # Fallback to configparser if keyring fails
            config = get_settings()
            if not config.has_section(_SECTION):
                config.add_section(_SECTION)
            config.set(_SECTION, key, sanitised)
            _save_config(config)
        return

    config = get_settings()
    if not config.has_section(_SECTION):
        config.add_section(_SECTION)
    config.set(_SECTION, key, sanitised)
    _save_config(config)


def load_setting(key: str, default: Any = None) -> Any:  # noqa: ANN401, PLR0911, PLR0912
    """Loads a setting value for the given key.

    Args:
        key (str): The setting key.
        default (Any, optional): The default value if key is not found.

    Returns:
        Any: The loaded value or default.
    """
    if key in _SECURE_KEYS:
        try:
            val = keyring.get_password(_SERVICE_NAME, key)
            if val is not None:
                return val
        except Exception as e:
            logger.error("Failed to load secure setting %s: %s", key, e)

    config = get_settings()
    try:
        val = config.get(_SECTION, key)
    except (configparser.NoSectionError, configparser.NoOptionError):
        return default

    # Opportunistically migrate legacy plaintext values for secure keys into
    # the OS keychain, then strip them from the INI. No-op if keyring fails.
    if key in _SECURE_KEYS and val:
        try:
            keyring.set_password(_SERVICE_NAME, key, val)
            config.remove_option(_SECTION, key)
            _save_config(config)
            logger.info("Migrated secure key %s from INI to keyring", key)
        except Exception as e:
            logger.error("Failed to migrate secure key %s: %s", key, e)

    # Type casting based on default
    if isinstance(default, bool):
        str_val = val.lower()
        if str_val in ("true", "1", "yes", "on"):
            return True
        if str_val in ("false", "0", "no", "off"):
            return False
        return default
    if isinstance(default, int):
        try:
            return int(val)
        except (ValueError, TypeError):
            return default
    if isinstance(default, float):
        try:
            return float(val)
        except (ValueError, TypeError):
            return default

    return val


def load_custom_providers() -> list[dict[str, str]]:
    """Loads the list of custom LLM provider configurations.

    Each provider dict has ``name``, ``api_key``, ``endpoint``, and
    ``models`` (comma-separated) keys.  Migrates the legacy single-provider
    settings on first call if the new JSON setting is empty.

    Returns:
        List of provider config dicts.
    """
    import json  # noqa: PLC0415

    from src.constants.settings import (  # noqa: PLC0415
        SETTING_LLM_CUSTOM_API_KEY,
        SETTING_LLM_CUSTOM_ENDPOINT,
        SETTING_LLM_CUSTOM_MODEL,
        SETTING_LLM_CUSTOM_PROVIDERS,
    )

    raw = load_setting(SETTING_LLM_CUSTOM_PROVIDERS, "")
    if raw:
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return []

    # Migrate legacy single-provider settings
    api_key = load_setting(SETTING_LLM_CUSTOM_API_KEY, "")
    endpoint = load_setting(SETTING_LLM_CUSTOM_ENDPOINT, "")
    models = load_setting(SETTING_LLM_CUSTOM_MODEL, "")
    if api_key or endpoint or models:
        provider = {
            "name": "Custom",
            "api_key": api_key,
            "endpoint": endpoint,
            "models": models,
        }
        save_custom_providers([provider])
        return [provider]
    return []


def save_custom_providers(providers: list[dict[str, str]]) -> None:
    """Saves the list of custom LLM provider configurations.

    Args:
        providers: List of provider config dicts with ``name``,
            ``api_key``, ``endpoint``, and ``models`` keys.
    """
    import json  # noqa: PLC0415

    from src.constants.settings import SETTING_LLM_CUSTOM_PROVIDERS  # noqa: PLC0415

    save_setting(SETTING_LLM_CUSTOM_PROVIDERS, json.dumps(providers))


def get_custom_provider_for_model(model: str) -> dict[str, str] | None:
    """Finds the custom provider config that contains a given model name.

    Args:
        model: The model name to look up.

    Returns:
        The provider dict, or None if not found.
    """
    for provider in load_custom_providers():
        model_names = [m.strip() for m in provider.get("models", "").split(",")]
        if model in model_names:
            return provider
    return None


def get_available_models() -> list[tuple[str, str]]:
    """Returns all available (provider, model_name) tuples from configured providers.

    A provider is available when its required credentials are non-empty.
    Gemini contributes all entries from ``GEMINI_MODELS``; each custom
    provider contributes its comma-separated model names.

    Returns:
        List of (provider, model_name) tuples, e.g.
        ``[("Gemini", "gemini-3-flash-preview"), ("Custom", "gpt-4o")]``.
    """
    from src.constants.llm import (  # noqa: PLC0415
        GEMINI_MODELS,
        LLM_METHOD_CUSTOM,
        LLM_METHOD_GEMINI,
    )
    from src.constants.settings import (  # noqa: PLC0415
        SETTING_LLM_GEMINI_API_KEY,
        SETTING_LLM_GEMINI_USE_VERTEX,
        SETTING_LLM_VERTEX_PROJECT,
    )

    models: list[tuple[str, str]] = []

    # Gemini: configured via Developer API key OR Vertex AI project.
    has_dev_key = bool(load_setting(SETTING_LLM_GEMINI_API_KEY, ""))
    has_vertex = bool(load_setting(SETTING_LLM_GEMINI_USE_VERTEX, False)) and bool(
        load_setting(SETTING_LLM_VERTEX_PROJECT, "").strip(),
    )
    if has_dev_key or has_vertex:
        for m in GEMINI_MODELS:
            models.append((LLM_METHOD_GEMINI, m))

    # Custom providers: endpoint + models required, api_key optional.
    # Truthiness alone accepted garbage like ``endpoint="e"`` which then
    # failed downstream with a confusing network error — gate on a
    # well-formed http(s) URL instead.
    for provider in load_custom_providers():
        endpoint = provider.get("endpoint", "")
        model_raw = provider.get("models", "")
        if is_valid_endpoint(endpoint) and model_raw:
            for raw_name in model_raw.split(","):
                stripped = raw_name.strip()
                if stripped:
                    models.append((LLM_METHOD_CUSTOM, stripped))

    return models


def load_model_for_feature(feature_key: str) -> str:
    """Returns the model id to use for a given feature.

    Resolution order:

    1. The feature's own key (e.g. ``SETTING_LLM_MODEL_LIVE``) if set.
    2. Global fallback ``SETTING_LLM_LAST_MODEL`` so first-time users don't
       have to pick a model in every feature before using it.
    3. Empty string — callers then fall through to the first available
       model via ``_resolve_provider_model``.
    """
    from src.constants.settings import SETTING_LLM_LAST_MODEL  # noqa: PLC0415

    value = load_setting(feature_key, "").strip()
    if value:
        return value
    return load_setting(SETTING_LLM_LAST_MODEL, "").strip()


def save_model_for_feature(feature_key: str, model_id: str) -> None:
    """Persists *model_id* under the feature's own key.

    The global default (``SETTING_LLM_LAST_MODEL``) is owned exclusively by
    the Settings → LLM "Default model" picker — this function deliberately
    does not touch it, so picking a model inside one feature can never
    silently change another feature's behaviour.
    """
    save_setting(feature_key, model_id)


def is_valid_endpoint(url: str) -> bool:
    """Returns True when *url* is a well-formed http / https endpoint.

    Accepts only ``http://`` and ``https://`` schemes — most OpenAI-compatible
    inference endpoints use these, and anything else (ftp, file, bare host)
    is almost certainly a typo.  Requires a non-empty netloc so ``https://``
    alone is rejected.
    """
    from urllib.parse import urlparse  # noqa: PLC0415

    raw = (url or "").strip()
    if not raw:
        return False
    try:
        parsed = urlparse(raw)
    except (TypeError, ValueError):
        return False
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def format_model_id(provider: str, model: str) -> str:
    """Formats a provider/model pair into a combined ``"Provider:model"`` string."""
    return f"{provider}:{model}"


def parse_model_id(model_id: str) -> tuple[str, str]:
    """Parses ``"Provider:model_name"`` into ``(provider, model_name)``.

    Falls back to ``(LLM_METHOD_GEMINI, DEFAULT_GEMINI_MODEL)`` when the
    string is empty or missing the separator.
    """
    from src.constants.llm import (  # noqa: PLC0415
        DEFAULT_GEMINI_MODEL,
        LLM_METHOD_GEMINI,
    )

    if not model_id or ":" not in model_id:
        return (LLM_METHOD_GEMINI, DEFAULT_GEMINI_MODEL)
    provider, model = model_id.split(":", 1)
    return (provider, model)


def check_llm_setup() -> bool:
    """Checks if at least one LLM provider has valid credentials.

    Returns:
        bool: True if any provider is configured, False otherwise.
    """
    return bool(get_available_models())


def load_google_cloud_api_key() -> str:
    """Loads the Google Cloud API key.

    Returns:
        str: The API key, or empty string if not configured.
    """
    from src.constants.settings import SETTING_GOOGLE_CLOUD_API_KEY  # noqa: PLC0415

    return load_setting(SETTING_GOOGLE_CLOUD_API_KEY, "")


def check_google_cloud_setup() -> bool:
    """Checks if the Google Cloud API key is configured.

    Returns:
        bool: True if the API key is present, False otherwise.
    """
    return bool(load_google_cloud_api_key())


def check_elevenlabs_setup() -> bool:
    """Checks if the ElevenLabs API key is configured.

    Returns:
        bool: True if the API key is present, False otherwise.
    """
    from src.constants.settings import SETTING_ELEVENLABS_API_KEY  # noqa: PLC0415

    return bool(load_setting(SETTING_ELEVENLABS_API_KEY, "").strip())


def check_soniox_setup() -> bool:
    """Checks if the Soniox API key is configured.

    Returns:
        bool: True if the API key is present, False otherwise.
    """
    from src.constants.settings import SETTING_SONIOX_API_KEY  # noqa: PLC0415

    return bool(load_setting(SETTING_SONIOX_API_KEY, "").strip())


def check_gemini_setup() -> bool:
    """Checks if the Gemini provider is configured.

    Two valid configurations:
    1. **Developer API** — non-empty ``llm/gemini_api_key``.
    2. **Vertex AI** — ``llm/gemini_use_vertex`` is True AND a project
       ID is set.  Credentials may come from a service-account JSON
       file (``llm/vertex_credentials``) or from Application Default
       Credentials (gcloud user creds, env var, or instance metadata).
       We can't easily probe ADC without a network call, so we trust
       the project setting and surface ADC failures at request time
       via ``AUTH_ERROR``.

    Returns:
        bool: True when either configuration looks valid.
    """
    from src.constants import (  # noqa: PLC0415
        SETTING_LLM_GEMINI_API_KEY,
        SETTING_LLM_GEMINI_USE_VERTEX,
        SETTING_LLM_VERTEX_PROJECT,
    )

    if load_setting(SETTING_LLM_GEMINI_USE_VERTEX, False):
        return bool(load_setting(SETTING_LLM_VERTEX_PROJECT, "").strip())
    return bool(load_setting(SETTING_LLM_GEMINI_API_KEY, "").strip())


def check_ocr_setup() -> bool:
    """Checks if a valid OCR configuration exists for the selected method.

    Returns:
        bool: True if OCR is set up, False otherwise.
    """
    from src.constants import OCR_METHOD_TESSERACT, SETTING_OCR_METHOD  # noqa: PLC0415

    # Fall back to Tesseract when no method has been explicitly saved yet.
    method = load_setting(SETTING_OCR_METHOD, OCR_METHOD_TESSERACT)
    return check_ocr_setup_for_method(method)


def check_ocr_setup_for_method(method: str) -> bool:
    """Checks OCR readiness for an explicit OCR method.

    Args:
        method: Canonical OCR method name.

    Returns:
        True when the requested OCR backend is configured or available.
    """
    from src.constants import OCR_METHOD_GOOGLE_CLOUD  # noqa: PLC0415
    from src.utils.ocr_checker import check_ocr_availability  # noqa: PLC0415

    if method == OCR_METHOD_GOOGLE_CLOUD:
        return check_google_cloud_setup()

    # For local OCR methods, check if they are available on the system.
    is_ready, _ = check_ocr_availability(method)
    return is_ready


def check_msoffice_available() -> bool:
    """Checks if Microsoft Office is available via win32com (Windows only).

    Returns:
        bool: True if win32com can be imported, False otherwise.
    """
    try:
        import win32com.client  # noqa: F401, PLC0415

        return True
    except ImportError:
        return False


def check_libreoffice_available() -> bool:
    """Checks if LibreOffice UNO is available.

    Adds platform-specific search paths to ``sys.path`` so that a
    system-installed LibreOffice is found even inside a virtualenv.

    Returns:
        bool: True if the ``uno`` module can be imported, False otherwise.
    """
    import sys  # noqa: PLC0415

    from src.core.office_lifecycle import _get_uno_search_paths  # noqa: PLC0415

    for p in _get_uno_search_paths():
        if p not in sys.path and Path(p).is_dir():
            sys.path.append(p)

    try:
        import uno  # noqa: F401, PLC0415

        return True
    except ImportError:
        return False


def check_office_converter_setup() -> bool:
    """Checks if an office converter backend (win32com or UNO) is available.

    These backends are required to convert legacy/ODF files to modern format.

    Returns:
        bool: True if at least one converter is available, False otherwise.
    """
    return check_msoffice_available() or check_libreoffice_available()
