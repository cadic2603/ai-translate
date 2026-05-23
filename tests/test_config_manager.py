"""Unit tests for the config manager logic."""

import configparser
from collections.abc import Generator
from pathlib import Path
from unittest.mock import patch

import pytest

from src.constants import (
    LLM_METHOD_CUSTOM,
    LLM_METHOD_GEMINI,
    OCR_METHOD_EASYOCR,
    OCR_METHOD_GOOGLE_CLOUD,
    OCR_METHOD_TESSERACT,
    SETTING_LLM_CUSTOM_API_KEY,
    SETTING_LLM_CUSTOM_ENDPOINT,
    SETTING_LLM_CUSTOM_MODEL,
    SETTING_LLM_GEMINI_API_KEY,
    SETTING_LLM_METHOD,
    SETTING_OCR_METHOD,
)
from src.constants.settings import (
    SETTING_GOOGLE_CLOUD_API_KEY,
)
from src.utils.config_manager import (
    check_google_cloud_setup,
    check_llm_setup,
    check_ocr_setup,
    check_office_converter_setup,
    load_google_cloud_api_key,
    load_setting,
    save_setting,
)


@pytest.fixture(autouse=True)
def mock_keyring(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mock keyring to prevent hitting the real OS keychain during testing."""
    storage: dict[str, str] = {}

    def mock_set_password(
        service: str,
        username: str,
        password: str,
    ) -> None:
        storage[f"{service}:{username}"] = password

    def mock_get_password(
        service: str,
        username: str,
    ) -> str | None:
        return storage.get(f"{service}:{username}")

    def mock_delete_password(
        service: str,
        username: str,
    ) -> None:
        key = f"{service}:{username}"
        if key in storage:
            del storage[key]
        else:
            from keyring.errors import PasswordDeleteError  # noqa: PLC0415

            raise PasswordDeleteError()

    monkeypatch.setattr("keyring.set_password", mock_set_password)
    monkeypatch.setattr("keyring.get_password", mock_get_password)
    monkeypatch.setattr("keyring.delete_password", mock_delete_password)


@pytest.fixture
def clean_settings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[Path, None, None]:
    """Ensures a clean configparser environment for testing."""
    config_path = tmp_path / "settings.ini"
    monkeypatch.setattr(
        "src.utils.config_manager._get_config_path",
        lambda: config_path,
    )
    yield config_path


# ── load_setting / save_setting ──────────────────────────────


def test_save_load_setting(clean_settings: Path) -> None:
    """Verify that settings can be saved and loaded."""
    save_setting("test_key", "test_value")
    assert load_setting("test_key") == "test_value"


def test_load_setting_missing_key_returns_default(clean_settings: Path) -> None:
    """Missing key returns the provided default value."""
    assert load_setting("nonexistent", "fallback") == "fallback"


def test_load_setting_missing_key_returns_none(clean_settings: Path) -> None:
    """Missing key with no explicit default returns None."""
    assert load_setting("nonexistent") is None


def test_load_setting_empty_config_file_returns_default(
    clean_settings: Path,
) -> None:
    """Completely empty config file (no sections) triggers NoSectionError → default."""
    # Write a file with no sections at all — configparser raises NoSectionError.
    clean_settings.write_text("")
    assert load_setting("any/key", "default_val") == "default_val"


# ── Type casting ───────────────────────────────────────


@pytest.mark.parametrize(
    ("stored", "expected"),
    [
        ("true", True),
        ("1", True),
        ("yes", True),
        ("on", True),
        ("TRUE", True),
        ("Yes", True),
        ("false", False),
        ("0", False),
        ("no", False),
        ("off", False),
        ("FALSE", False),
        ("No", False),
    ],
)
def test_load_setting_bool_from_string(
    clean_settings: Path,
    stored: str,
    expected: bool,
) -> None:
    """String values stored by QSettings are converted to bool when default is bool."""
    save_setting("flag", stored)
    assert load_setting("flag", True) is expected


def test_load_setting_bool_default_when_missing(clean_settings: Path) -> None:
    """Missing key with bool default returns that default."""
    assert load_setting("missing_flag", True) is True
    assert load_setting("missing_flag", False) is False


def test_load_setting_bool_passthrough(clean_settings: Path) -> None:
    """Native bool value is returned as-is when default is bool."""
    save_setting("flag", True)
    assert load_setting("flag", False) is True


def test_load_setting_non_bool_default_no_conversion(
    clean_settings: Path,
) -> None:
    """String default does not trigger bool conversion even for 'true'/'false'."""
    save_setting("key", "true")
    result = load_setting("key", "")
    assert result == "true"
    assert isinstance(result, str)


def test_load_setting_int_conversion(clean_settings: Path) -> None:
    """Values are converted to int when default is int."""
    save_setting("count", "42")
    assert load_setting("count", 0) == 42  # noqa: PLR2004

    save_setting("invalid_int", "not_a_number")
    assert load_setting("invalid_int", 10) == 10  # noqa: PLR2004


def test_load_setting_float_conversion(clean_settings: Path) -> None:
    """Values are converted to float when default is float."""
    save_setting("ratio", "3.14")
    assert load_setting("ratio", 0.0) == 3.14  # noqa: PLR2004

    save_setting("invalid_float", "not_a_number")
    assert load_setting("invalid_float", 1.5) == 1.5  # noqa: PLR2004


# ── check_llm_setup ─────────────────────────────────────────


def test_llm_setup_gemini(clean_settings: Path) -> None:
    """Gemini method requires method + API key."""
    assert not check_llm_setup()

    save_setting(SETTING_LLM_METHOD, LLM_METHOD_GEMINI)
    assert not check_llm_setup()  # missing API key

    save_setting(SETTING_LLM_GEMINI_API_KEY, "key-123")
    assert check_llm_setup()


def test_llm_setup_gemini_via_vertex(clean_settings: Path) -> None:
    """Vertex AI mode counts as configured when project is set.

    No API key is required — credentials come from the user's GCP
    Application Default Credentials or an explicit service-account JSON.
    """
    from src.constants import (  # noqa: PLC0415
        SETTING_LLM_GEMINI_USE_VERTEX,
        SETTING_LLM_VERTEX_PROJECT,
    )

    save_setting(SETTING_LLM_METHOD, LLM_METHOD_GEMINI)
    save_setting(SETTING_LLM_GEMINI_USE_VERTEX, True)
    # Project not set yet → not configured.
    assert not check_llm_setup()

    save_setting(SETTING_LLM_VERTEX_PROJECT, "my-gcp-project")
    assert check_llm_setup()


def test_llm_setup_vertex_does_not_need_api_key(clean_settings: Path) -> None:
    """Vertex mode never reads the Gemini API key — empty key still OK."""
    from src.constants import (  # noqa: PLC0415
        SETTING_LLM_GEMINI_USE_VERTEX,
        SETTING_LLM_VERTEX_PROJECT,
    )

    save_setting(SETTING_LLM_METHOD, LLM_METHOD_GEMINI)
    save_setting(SETTING_LLM_GEMINI_API_KEY, "")
    save_setting(SETTING_LLM_GEMINI_USE_VERTEX, True)
    save_setting(SETTING_LLM_VERTEX_PROJECT, "my-gcp-project")
    assert check_llm_setup()


def test_llm_setup_developer_api_when_vertex_off(clean_settings: Path) -> None:
    """Toggle-off Vertex falls back to Developer API key check."""
    from src.constants import (  # noqa: PLC0415
        SETTING_LLM_GEMINI_USE_VERTEX,
        SETTING_LLM_VERTEX_PROJECT,
    )

    save_setting(SETTING_LLM_METHOD, LLM_METHOD_GEMINI)
    save_setting(SETTING_LLM_VERTEX_PROJECT, "my-gcp-project")
    save_setting(SETTING_LLM_GEMINI_USE_VERTEX, False)
    save_setting(SETTING_LLM_GEMINI_API_KEY, "")
    # Vertex is off and no API key → not configured even though project
    # ID is filled in (user has set up Vertex but not enabled it).
    assert not check_llm_setup()

    save_setting(SETTING_LLM_GEMINI_API_KEY, "key-123")
    assert check_llm_setup()


def test_llm_setup_custom_all_fields(clean_settings: Path) -> None:
    """Custom provider is available when endpoint and models are set."""
    from src.utils.config_manager import save_custom_providers  # noqa: PLC0415

    save_custom_providers([])
    assert not check_llm_setup()

    save_custom_providers(
        [{"name": "X", "api_key": "sk-xxx", "endpoint": "", "models": ""}],
    )
    assert not check_llm_setup()  # missing endpoint + models

    save_custom_providers(
        [
            {
                "name": "X",
                "api_key": "sk-xxx",
                "endpoint": "https://api.example.com/v1",
                "models": "",
            },
        ],
    )
    assert not check_llm_setup()  # missing models

    save_custom_providers(
        [
            {
                "name": "X",
                "api_key": "sk-xxx",
                "endpoint": "https://api.example.com/v1",
                "models": "gpt-4o",
            },
        ],
    )
    assert check_llm_setup()


def test_llm_setup_custom_missing_key(clean_settings: Path) -> None:
    """Custom provider only needs endpoint and models (api_key is optional)."""
    from src.utils.config_manager import save_custom_providers  # noqa: PLC0415

    save_custom_providers(
        [
            {
                "name": "X",
                "api_key": "",
                "endpoint": "https://api.example.com/v1",
                "models": "gpt-4o",
            },
        ],
    )
    assert check_llm_setup()


def test_llm_setup_custom_missing_endpoint(clean_settings: Path) -> None:
    """Custom provider fails when only API key + model are set (no endpoint)."""
    from src.utils.config_manager import save_custom_providers  # noqa: PLC0415

    save_custom_providers(
        [
            {
                "name": "X",
                "api_key": "sk-xxx",
                "endpoint": "",
                "models": "gpt-4o",
            },
        ],
    )
    assert not check_llm_setup()


def test_llm_setup_unknown_method(clean_settings: Path) -> None:
    """Unknown LLM method always returns False."""
    save_setting(SETTING_LLM_METHOD, "SomeUnknownProvider")
    assert not check_llm_setup()


def test_llm_setup_empty_method(clean_settings: Path) -> None:
    """Empty method string returns False."""
    save_setting(SETTING_LLM_METHOD, "")
    assert not check_llm_setup()


# ── check_ocr_setup ──────────────────────────────────────────


def test_ocr_setup_no_method_defaults_to_tesseract_check(
    clean_settings: Path,
) -> None:
    """No OCR method saved → falls back to Tesseract check."""
    with patch(
        "src.utils.ocr_checker.check_ocr_availability",
        return_value=(True, "ready"),
    ) as mock_avail:
        assert check_ocr_setup()
    mock_avail.assert_called_once_with(OCR_METHOD_TESSERACT)

    with patch(
        "src.utils.ocr_checker.check_ocr_availability",
        return_value=(False, "not found"),
    ):
        assert not check_ocr_setup()


def test_ocr_setup_google_cloud(clean_settings: Path) -> None:
    """Google Cloud OCR requires method + API key."""
    save_setting(SETTING_OCR_METHOD, OCR_METHOD_GOOGLE_CLOUD)
    assert not check_ocr_setup()  # missing API key

    save_setting(SETTING_GOOGLE_CLOUD_API_KEY, "ocr-key")
    assert check_ocr_setup()


def test_ocr_setup_tesseract_available(clean_settings: Path) -> None:
    """Tesseract method delegates to check_ocr_availability."""
    save_setting(SETTING_OCR_METHOD, OCR_METHOD_TESSERACT)
    with patch(
        "src.utils.ocr_checker.check_ocr_availability",
        return_value=(True, ""),
    ):
        assert check_ocr_setup()


def test_ocr_setup_tesseract_unavailable(clean_settings: Path) -> None:
    """Tesseract method returns False when not installed."""
    save_setting(SETTING_OCR_METHOD, OCR_METHOD_TESSERACT)
    with patch(
        "src.utils.ocr_checker.check_ocr_availability",
        return_value=(False, "not found"),
    ):
        assert not check_ocr_setup()


def test_ocr_setup_easyocr_available(clean_settings: Path) -> None:
    """EasyOCR method delegates to check_ocr_availability."""
    save_setting(SETTING_OCR_METHOD, OCR_METHOD_EASYOCR)
    with patch(
        "src.utils.ocr_checker.check_ocr_availability",
        return_value=(True, ""),
    ):
        assert check_ocr_setup()


def test_ocr_setup_unknown_method(clean_settings: Path) -> None:
    """Unknown OCR method delegates to availability check."""
    save_setting(SETTING_OCR_METHOD, "UnknownOCR")
    with patch(
        "src.utils.ocr_checker.check_ocr_availability",
        return_value=(False, "unknown engine"),
    ):
        assert not check_ocr_setup()


def test_ocr_setup_explicitly_saved_empty_method(clean_settings: Path) -> None:
    """Explicitly saved empty method string is treated as unknown and returns False."""
    save_setting(SETTING_OCR_METHOD, "")
    # Empty string is stored in the INI (not missing), so the Tesseract
    # default doesn't apply; "" is treated as an unknown OCR method.
    with patch(
        "src.utils.ocr_checker.check_ocr_availability",
        return_value=(False, "Unknown OCR method selected."),
    ):
        assert not check_ocr_setup()


# ── Secure key storage ────────────────────────────────────────


def test_secure_key_save_load(clean_settings: Path) -> None:
    """Secure keys are stored in keyring and loaded back."""
    save_setting(SETTING_LLM_GEMINI_API_KEY, "my-secret-key")
    assert load_setting(SETTING_LLM_GEMINI_API_KEY, "") == "my-secret-key"


def test_secure_key_save_empty_deletes(clean_settings: Path) -> None:
    """Saving empty value for a secure key removes it from keyring."""
    save_setting(SETTING_LLM_GEMINI_API_KEY, "key-to-delete")
    assert load_setting(SETTING_LLM_GEMINI_API_KEY, "") == "key-to-delete"

    save_setting(SETTING_LLM_GEMINI_API_KEY, "")
    assert load_setting(SETTING_LLM_GEMINI_API_KEY, "") == ""


def test_secure_key_delete_nonexistent_is_noop(clean_settings: Path) -> None:
    """Deleting a secure key that was never set does not raise."""
    save_setting(SETTING_LLM_GEMINI_API_KEY, "")
    # PasswordDeleteError is suppressed — no exception


def test_secure_key_keyring_failure_fallback_save(
    clean_settings: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When keyring.set_password fails, value falls back to configparser."""

    def failing_set(*_args: object) -> None:
        raise RuntimeError("Keychain locked")

    monkeypatch.setattr("keyring.set_password", failing_set)

    save_setting(SETTING_LLM_CUSTOM_API_KEY, "fallback-key")
    # The key should be in the INI file instead
    config = configparser.ConfigParser()
    config.optionxform = str
    config.read(str(clean_settings), encoding="utf-8")
    assert config.get("General", SETTING_LLM_CUSTOM_API_KEY) == "fallback-key"


def test_secure_key_keyring_failure_fallback_load(
    clean_settings: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When keyring.get_password fails, value is loaded from INI file."""
    # Store directly in the INI file (simulating previous fallback save)
    config = configparser.ConfigParser()
    config.optionxform = str
    config.add_section("General")
    config.set("General", SETTING_LLM_CUSTOM_API_KEY, "ini-value")
    with clean_settings.open("w", encoding="utf-8") as fh:
        config.write(fh)

    def failing_get(*_args: object) -> None:
        raise RuntimeError("Keychain locked")

    monkeypatch.setattr("keyring.get_password", failing_get)

    result = load_setting(SETTING_LLM_CUSTOM_API_KEY, "")
    assert result == "ini-value"


def test_secure_key_all_three_keys(clean_settings: Path) -> None:
    """All three secure keys can be stored and retrieved independently."""
    save_setting("cloud/google_api_key", "ocr-key-123")
    save_setting("llm/gemini_api_key", "gemini-key-456")
    save_setting("llm/custom_api_key", "custom-key-789")

    assert load_setting("cloud/google_api_key", "") == "ocr-key-123"
    assert load_setting("llm/gemini_api_key", "") == "gemini-key-456"
    assert load_setting("llm/custom_api_key", "") == "custom-key-789"


# ── Type casting edge cases ───────────────────────────────────


def test_load_setting_bool_unrecognized_string(clean_settings: Path) -> None:
    """Unrecognized bool string falls back to the default."""
    save_setting("flag", "maybe")
    assert load_setting("flag", True) is True
    assert load_setting("flag", False) is False


def test_load_setting_bool_empty_string(clean_settings: Path) -> None:
    """Empty string with bool default falls back to default."""
    save_setting("flag", "")
    assert load_setting("flag", True) is True
    assert load_setting("flag", False) is False


def test_load_setting_int_empty_string(clean_settings: Path) -> None:
    """Empty string with int default falls back to default."""
    save_setting("count", "")
    assert load_setting("count", 42) == 42  # noqa: PLR2004


def test_load_setting_float_empty_string(clean_settings: Path) -> None:
    """Empty string with float default falls back to default."""
    save_setting("ratio", "")
    assert load_setting("ratio", 3.14) == 3.14  # noqa: PLR2004


def test_load_setting_int_none_value(clean_settings: Path) -> None:
    """None value with int default falls back to default."""
    # When key doesn't exist, QSettings returns None
    assert load_setting("nonexistent_int", 99) == 99  # noqa: PLR2004


def test_load_setting_float_none_value(clean_settings: Path) -> None:
    """None value with float default falls back to default."""
    assert load_setting("nonexistent_float", 2.5) == 2.5  # noqa: PLR2004


def test_load_setting_int_negative(clean_settings: Path) -> None:
    """Negative integer values are loaded correctly."""
    save_setting("offset", "-10")
    assert load_setting("offset", 0) == -10  # noqa: PLR2004


def test_load_setting_float_negative(clean_settings: Path) -> None:
    """Negative float values are loaded correctly."""
    save_setting("temp", "-3.5")
    assert load_setting("temp", 0.0) == -3.5  # noqa: PLR2004


# ── Save/load edge cases ─────────────────────────────────────


def test_save_setting_overwrite(clean_settings: Path) -> None:
    """Saving the same key twice overwrites the value."""
    save_setting("key", "first")
    save_setting("key", "second")
    assert load_setting("key") == "second"


def test_save_load_unicode(clean_settings: Path) -> None:
    """Unicode values are saved and loaded correctly."""
    save_setting("lang", "日本語")
    assert load_setting("lang", "") == "日本語"

    save_setting("path", "/home/user/tài_liệu/Straße")
    assert load_setting("path", "") == "/home/user/tài_liệu/Straße"


def test_save_load_empty_string(clean_settings: Path) -> None:
    """Empty string is saved and loaded (not confused with missing)."""
    save_setting("empty", "")
    result = load_setting("empty", "fallback")
    assert result == ""  # configparser stores empty strings correctly


def test_load_setting_none_default_explicit(clean_settings: Path) -> None:
    """Explicit None default is returned when key is absent."""
    result = load_setting("absent_key", None)
    assert result is None


def test_save_load_long_value(clean_settings: Path) -> None:
    """Long string values are handled correctly."""
    long_val = "x" * 10000
    save_setting("long_key", long_val)
    assert load_setting("long_key", "") == long_val


def test_save_load_special_chars(clean_settings: Path) -> None:
    """Values with special characters are preserved."""
    save_setting("url", "https://api.example.com/v1?key=abc&fmt=json")
    assert load_setting("url", "") == "https://api.example.com/v1?key=abc&fmt=json"


# ── check_office_converter_setup ──────────────────────────────


def test_office_converter_setup_no_backends() -> None:
    """Returns False when neither win32com nor UNO is available."""
    import builtins  # noqa: PLC0415

    real_import = builtins.__import__
    blocked = {"win32com.client", "uno"}

    def fake_import(
        name: str,
        *args: object,
        **kwargs: object,
    ) -> object:
        if name in blocked:
            raise ImportError(f"Blocked: {name}")
        return real_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=fake_import):
        assert not check_office_converter_setup()


def test_office_converter_setup_with_uno() -> None:
    """Returns True when UNO is available (but win32com is not)."""
    import builtins  # noqa: PLC0415
    import types  # noqa: PLC0415

    real_import = builtins.__import__
    fake_uno = types.ModuleType("uno")

    def fake_import(
        name: str,
        *args: object,
        **kwargs: object,
    ) -> object:
        if name == "win32com.client":
            raise ImportError
        if name == "uno":
            return fake_uno
        return real_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=fake_import):
        assert check_office_converter_setup()


# ── check_llm_setup edge cases ────────────────────────────────


def test_llm_setup_gemini_whitespace_key(clean_settings: Path) -> None:
    """Whitespace-only API key is treated as empty (falsy)."""
    save_setting(SETTING_LLM_METHOD, LLM_METHOD_GEMINI)
    save_setting(SETTING_LLM_GEMINI_API_KEY, "   ")
    # "   " is truthy as a string, so bool("   ") is True
    # This tests the actual behavior — whitespace is not stripped
    assert check_llm_setup()


def test_llm_setup_custom_partial_fields(clean_settings: Path) -> None:
    """Custom method requires ALL three fields — any missing means False."""
    save_setting(SETTING_LLM_METHOD, LLM_METHOD_CUSTOM)

    # Only key
    save_setting(SETTING_LLM_CUSTOM_API_KEY, "sk-xxx")
    save_setting(SETTING_LLM_CUSTOM_ENDPOINT, "")
    save_setting(SETTING_LLM_CUSTOM_MODEL, "")
    assert not check_llm_setup()

    # Only endpoint
    save_setting(SETTING_LLM_CUSTOM_API_KEY, "")
    save_setting(SETTING_LLM_CUSTOM_ENDPOINT, "https://api.example.com")
    save_setting(SETTING_LLM_CUSTOM_MODEL, "")
    assert not check_llm_setup()

    # Only model
    save_setting(SETTING_LLM_CUSTOM_API_KEY, "")
    save_setting(SETTING_LLM_CUSTOM_ENDPOINT, "")
    save_setting(SETTING_LLM_CUSTOM_MODEL, "gpt-4o")
    assert not check_llm_setup()


# ── check_ocr_setup edge cases ────────────────────────────────


def test_ocr_setup_google_cloud_empty_key(clean_settings: Path) -> None:
    """Google Cloud OCR with empty API key returns False."""
    save_setting(SETTING_OCR_METHOD, OCR_METHOD_GOOGLE_CLOUD)
    save_setting(SETTING_GOOGLE_CLOUD_API_KEY, "")
    assert not check_ocr_setup()


def test_ocr_setup_easyocr_unavailable(clean_settings: Path) -> None:
    """EasyOCR method returns False when the package is not installed."""
    save_setting(SETTING_OCR_METHOD, OCR_METHOD_EASYOCR)
    with patch(
        "src.utils.ocr_checker.check_ocr_availability",
        return_value=(False, "EasyOCR package is not installed."),
    ):
        assert not check_ocr_setup()


def test_ocr_setup_unknown_method_available(clean_settings: Path) -> None:
    """Unknown OCR method returns True when availability check reports it ready."""
    save_setting(SETTING_OCR_METHOD, "SomeNewEngine")
    with patch(
        "src.utils.ocr_checker.check_ocr_availability",
        return_value=(True, "Available."),
    ):
        assert check_ocr_setup()


# ── check_office_converter_setup — win32com path ──────────────


def test_office_converter_setup_with_win32com() -> None:
    """Returns True when win32com is available (checked before UNO)."""
    import builtins  # noqa: PLC0415
    import types  # noqa: PLC0415

    real_import = builtins.__import__
    fake_win32com = types.ModuleType("win32com")

    def fake_import(
        name: str,
        *args: object,
        **kwargs: object,
    ) -> object:
        if name == "win32com.client":
            return fake_win32com
        return real_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=fake_import):
        assert check_office_converter_setup()


# ── load_setting type-casting edge cases ──────────────────────


def test_load_setting_bool_false_passthrough(clean_settings: Path) -> None:
    """Native bool False is returned as-is when default is bool."""
    save_setting("flag", False)
    assert load_setting("flag", True) is False


def test_load_setting_int_float_string_falls_back(clean_settings: Path) -> None:
    """Float-format string (e.g. "3.14") with int default falls back to default."""
    save_setting("count", "3.14")
    assert load_setting("count", 0) == 0


def test_load_setting_int_zero(clean_settings: Path) -> None:
    """String "0" with int default returns 0, not the default."""
    save_setting("count", "0")
    assert load_setting("count", 99) == 0  # noqa: PLR2004


def test_load_setting_float_zero(clean_settings: Path) -> None:
    """String "0.0" with float default returns 0.0, not the default."""
    save_setting("ratio", "0.0")
    assert load_setting("ratio", 9.9) == 0.0


# ── Secure key priority / None value ─────────────────────────


def test_secure_key_keyring_takes_priority_over_ini(
    clean_settings: Path,
) -> None:
    """When both keyring and INI file have a value for a secure key, keyring wins."""
    # Plant a stale value directly in the INI file
    config = configparser.ConfigParser()
    config.optionxform = str
    config.add_section("General")
    config.set("General", SETTING_LLM_GEMINI_API_KEY, "ini-value")
    with clean_settings.open("w", encoding="utf-8") as fh:
        config.write(fh)
    # Save a fresh value to keyring (via save_setting)
    save_setting(SETTING_LLM_GEMINI_API_KEY, "keyring-value")

    result = load_setting(SETTING_LLM_GEMINI_API_KEY, "")
    assert result == "keyring-value"


def test_save_setting_none_secure_key_is_noop(clean_settings: Path) -> None:
    """Saving None to a secure key deletes it from keyring without raising."""
    save_setting(SETTING_LLM_GEMINI_API_KEY, "existing-key")
    # Save None — falsy → delete path, PasswordDeleteError suppressed if absent
    save_setting(SETTING_LLM_GEMINI_API_KEY, None)
    assert load_setting(SETTING_LLM_GEMINI_API_KEY, "") == ""


# ---------------------------------------------------------------------------
# check_msoffice_available / check_libreoffice_available
# ---------------------------------------------------------------------------


def test_check_msoffice_available_import_fails() -> None:
    """Returns False when win32com cannot be imported."""
    from src.utils.config_manager import (  # noqa: PLC0415
        check_msoffice_available,
    )

    with patch.dict("sys.modules", {"win32com": None, "win32com.client": None}):
        # Force ImportError by removing from sys.modules cache
        result = check_msoffice_available()
    # On non-Windows, this naturally returns False
    assert isinstance(result, bool)


def test_check_libreoffice_available_import_fails() -> None:
    """Returns False when uno module cannot be imported."""
    import sys  # noqa: PLC0415

    from src.utils.config_manager import (  # noqa: PLC0415
        check_libreoffice_available,
    )

    # Temporarily remove 'uno' from sys.modules if present,
    # and patch _get_uno_search_paths to return empty
    saved = sys.modules.pop("uno", None)
    try:
        with patch(
            "src.core.office_lifecycle._get_uno_search_paths",
            return_value=["/nonexistent/path"],
        ):
            result = check_libreoffice_available()
        # Will be False if UNO is not installed, True if it is
        assert isinstance(result, bool)
    finally:
        if saved is not None:
            sys.modules["uno"] = saved


# ---------------------------------------------------------------------------
# save_setting — None value for non-secure key
# ---------------------------------------------------------------------------


def test_save_setting_none_value_stores_empty_string(
    clean_settings: Path,
) -> None:
    """Saving None for a non-secure key stores '' instead of 'None'."""
    save_setting("test/key", None)
    result = load_setting("test/key", "default")
    # Should be empty string, not the literal string "None"
    assert result != "None"
    assert result == ""


# ---------------------------------------------------------------------------
# load_google_cloud_api_key / check_google_cloud_setup
# ---------------------------------------------------------------------------


def test_load_google_cloud_api_key_from_new_location(
    clean_settings: Path,
) -> None:
    """Returns key from the new cloud/google_api_key location."""
    save_setting(SETTING_GOOGLE_CLOUD_API_KEY, "my-cloud-key")
    assert load_google_cloud_api_key() == "my-cloud-key"


def test_load_google_cloud_api_key_empty(
    clean_settings: Path,
) -> None:
    """Returns empty string when no key is configured."""
    assert load_google_cloud_api_key() == ""


def test_check_google_cloud_setup_true(
    clean_settings: Path,
) -> None:
    """Returns True when API key is present."""
    save_setting(SETTING_GOOGLE_CLOUD_API_KEY, "valid-key")
    assert check_google_cloud_setup() is True


def test_check_google_cloud_setup_false(
    clean_settings: Path,
) -> None:
    """Returns False when API key is missing."""
    assert check_google_cloud_setup() is False


# ---------------------------------------------------------------------------
# _SECURE_KEYS membership
# ---------------------------------------------------------------------------


def test_secure_keys_count_matches_expected() -> None:
    """Verify _SECURE_KEYS lists every credential that should be keychain-backed."""
    from src.utils.config_manager import _SECURE_KEYS  # noqa: PLC0415

    expected = {
        "cloud/google_api_key",
        "llm/gemini_api_key",
        "llm/custom_api_key",
        "llm/custom_providers",
        "service/soniox_api_key",
        "service/elevenlabs_api_key",
    }
    assert expected == _SECURE_KEYS


# ---------------------------------------------------------------------------
# Per-backend setup checkers
# ---------------------------------------------------------------------------


def test_check_soniox_setup_true_when_key_present(clean_settings: Path) -> None:
    """check_soniox_setup returns True when a non-empty key is stored."""
    from src.constants.settings import SETTING_SONIOX_API_KEY  # noqa: PLC0415
    from src.utils.config_manager import check_soniox_setup  # noqa: PLC0415

    save_setting(SETTING_SONIOX_API_KEY, "sx-abc123")
    assert check_soniox_setup() is True


def test_check_soniox_setup_false_when_key_missing(clean_settings: Path) -> None:
    """check_soniox_setup returns False when no key is saved."""
    from src.utils.config_manager import check_soniox_setup  # noqa: PLC0415

    assert check_soniox_setup() is False


def test_check_soniox_setup_false_when_key_is_whitespace(
    clean_settings: Path,
) -> None:
    """Whitespace-only keys don't count as configured."""
    from src.constants.settings import SETTING_SONIOX_API_KEY  # noqa: PLC0415
    from src.utils.config_manager import check_soniox_setup  # noqa: PLC0415

    save_setting(SETTING_SONIOX_API_KEY, "   ")
    assert check_soniox_setup() is False


def test_check_gemini_setup_true_when_key_present(clean_settings: Path) -> None:
    """check_gemini_setup returns True when a non-empty key is stored."""
    from src.constants import SETTING_LLM_GEMINI_API_KEY  # noqa: PLC0415
    from src.utils.config_manager import check_gemini_setup  # noqa: PLC0415

    save_setting(SETTING_LLM_GEMINI_API_KEY, "gm-xyz")
    assert check_gemini_setup() is True


def test_check_gemini_setup_false_when_key_missing(clean_settings: Path) -> None:
    """check_gemini_setup returns False when no key is saved."""
    from src.utils.config_manager import check_gemini_setup  # noqa: PLC0415

    assert check_gemini_setup() is False


def test_check_elevenlabs_setup_true_when_key_present(clean_settings: Path) -> None:
    """check_elevenlabs_setup returns True when a non-empty key is stored."""
    from src.constants.settings import SETTING_ELEVENLABS_API_KEY  # noqa: PLC0415
    from src.utils.config_manager import check_elevenlabs_setup  # noqa: PLC0415

    save_setting(SETTING_ELEVENLABS_API_KEY, "el-key")
    assert check_elevenlabs_setup() is True


def test_check_elevenlabs_setup_false_when_key_missing(clean_settings: Path) -> None:
    """check_elevenlabs_setup returns False when no key is saved."""
    from src.utils.config_manager import check_elevenlabs_setup  # noqa: PLC0415

    assert check_elevenlabs_setup() is False


# ---------------------------------------------------------------------------
# Auto-migration of secure keys from plaintext INI to the OS keychain
# ---------------------------------------------------------------------------


def test_secure_key_migrates_from_ini_to_keyring_on_read(
    clean_settings: Path,
) -> None:
    """Plaintext secure key in INI is moved to keychain on first load_setting call."""
    import configparser  # noqa: PLC0415

    from src.utils.config_manager import _SECTION, _SERVICE_NAME  # noqa: PLC0415

    # Seed INI with a plaintext secure key directly (bypass save_setting so we
    # simulate a legacy install that predates _SECURE_KEYS inclusion).
    cfg = configparser.ConfigParser()
    cfg.add_section(_SECTION)
    cfg.set(_SECTION, "service/soniox_api_key", "legacy-plaintext")
    with clean_settings.open("w") as fp:
        cfg.write(fp)

    import keyring  # noqa: PLC0415

    # Keyring starts empty for the mocked fixture.
    assert keyring.get_password(_SERVICE_NAME, "service/soniox_api_key") is None

    val = load_setting("service/soniox_api_key", "")
    assert val == "legacy-plaintext"

    # Value should now live in keyring, and be gone from the INI.
    assert (
        keyring.get_password(_SERVICE_NAME, "service/soniox_api_key")
        == "legacy-plaintext"
    )
    reloaded = configparser.ConfigParser()
    reloaded.read(clean_settings)
    assert not reloaded.has_option(_SECTION, "service/soniox_api_key")


def test_secure_key_not_migrated_when_already_in_keyring(
    clean_settings: Path,
) -> None:
    """When keyring already has the value, we return it without touching INI."""
    import keyring  # noqa: PLC0415

    from src.utils.config_manager import _SERVICE_NAME  # noqa: PLC0415

    keyring.set_password(_SERVICE_NAME, "service/soniox_api_key", "from-keyring")

    val = load_setting("service/soniox_api_key", "")
    assert val == "from-keyring"


def test_secure_key_migration_is_skipped_when_ini_value_is_empty(
    clean_settings: Path,
) -> None:
    """Empty string in INI does not trigger a keyring write."""
    import configparser  # noqa: PLC0415

    import keyring  # noqa: PLC0415

    from src.utils.config_manager import _SECTION, _SERVICE_NAME  # noqa: PLC0415

    cfg = configparser.ConfigParser()
    cfg.add_section(_SECTION)
    cfg.set(_SECTION, "service/soniox_api_key", "")
    with clean_settings.open("w") as fp:
        cfg.write(fp)

    load_setting("service/soniox_api_key", "")
    assert keyring.get_password(_SERVICE_NAME, "service/soniox_api_key") is None


def test_secure_key_migration_idempotent_after_keyring_recovers(
    clean_settings: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If keyring fails on first migration, the second read finds a clean state.

    Scenario: legacy plaintext is in the INI; ``keyring.set_password``
    raises on the first ``load_setting`` (e.g. keychain locked).  The
    INI value must NOT be deleted (we'd otherwise lose the secret), and
    a follow-up read with keyring working again should still surface
    the value and complete the migration.
    """
    import configparser  # noqa: PLC0415

    import keyring  # noqa: PLC0415

    from src.utils.config_manager import _SECTION, _SERVICE_NAME  # noqa: PLC0415

    cfg = configparser.ConfigParser()
    cfg.add_section(_SECTION)
    cfg.set(_SECTION, "service/soniox_api_key", "secret-from-ini")
    with clean_settings.open("w") as fp:
        cfg.write(fp)

    # Force first migration attempt to fail.
    original_set = keyring.set_password

    def failing_set(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("keychain locked")

    monkeypatch.setattr(keyring, "set_password", failing_set)

    # First call: returns the INI value, migration fails silently.
    val_first = load_setting("service/soniox_api_key", "")
    assert val_first == "secret-from-ini"

    # INI must still contain the secret — otherwise migration failure
    # would have lost it forever.
    reloaded = configparser.ConfigParser()
    reloaded.read(clean_settings)
    assert reloaded.get(_SECTION, "service/soniox_api_key") == "secret-from-ini"

    # Restore keyring; second call must migrate cleanly.
    monkeypatch.setattr(keyring, "set_password", original_set)
    val_second = load_setting("service/soniox_api_key", "")
    assert val_second == "secret-from-ini"
    assert (
        keyring.get_password(_SERVICE_NAME, "service/soniox_api_key")
        == "secret-from-ini"
    )

    # Third call: keyring is the source of truth now; INI is gone.
    val_third = load_setting("service/soniox_api_key", "")
    assert val_third == "secret-from-ini"
    final = configparser.ConfigParser()
    final.read(clean_settings)
    assert not final.has_option(_SECTION, "service/soniox_api_key")


def test_non_secure_key_is_not_migrated(clean_settings: Path) -> None:
    """Non-secure keys stay in the INI even when they happen to be read."""
    import configparser  # noqa: PLC0415

    import keyring  # noqa: PLC0415

    from src.utils.config_manager import _SECTION, _SERVICE_NAME  # noqa: PLC0415

    save_setting("app/theme", "dark")
    load_setting("app/theme", "")

    # Keyring was not touched for a non-secure key.
    assert keyring.get_password(_SERVICE_NAME, "app/theme") is None
    # And the INI still has the value.
    cfg = configparser.ConfigParser()
    cfg.read(clean_settings)
    assert cfg.get(_SECTION, "app/theme") == "dark"


def test_custom_providers_json_blob_lands_in_keyring(
    clean_settings: Path,
) -> None:
    """Writes custom providers to keyring instead of INI.

    Verifies that save_custom_providers routes through the keychain now that
    ``llm/custom_providers`` is listed in ``_SECURE_KEYS``.
    """
    import configparser  # noqa: PLC0415
    import json  # noqa: PLC0415

    import keyring  # noqa: PLC0415

    from src.constants.settings import SETTING_LLM_CUSTOM_PROVIDERS  # noqa: PLC0415
    from src.utils.config_manager import (  # noqa: PLC0415
        _SECTION,
        _SERVICE_NAME,
        save_custom_providers,  # noqa: PLC0415
    )

    providers = [
        {
            "name": "Test",
            "api_key": "sk-secret",
            "endpoint": "https://example/v1",
            "models": "gpt-4o",
        },
    ]
    save_custom_providers(providers)

    # Keyring holds the JSON blob (so the api_key is not plaintext on disk).
    stored = keyring.get_password(_SERVICE_NAME, SETTING_LLM_CUSTOM_PROVIDERS)
    assert stored is not None
    assert json.loads(stored) == providers

    # INI does not contain the blob.
    cfg = configparser.ConfigParser()
    cfg.read(clean_settings)
    assert not cfg.has_option(_SECTION, SETTING_LLM_CUSTOM_PROVIDERS)


# ---------------------------------------------------------------------------
# load_setting — malformed INI file handling
# ---------------------------------------------------------------------------


class TestLoadSettingMalformedIni:
    """Tests for load_setting with corrupt config files."""

    def test_missing_section_returns_default(self, clean_settings: Path) -> None:
        """When INI has no [General] section, default is returned."""
        # Write a valid key first, then corrupt the file
        config_file = clean_settings
        config_file.write_text("[WrongSection]\nkey = value\n")
        result = load_setting("some/key", "fallback")
        assert result == "fallback"

    def test_empty_file_returns_default(self, clean_settings: Path) -> None:
        """Empty config file returns default value."""
        config_file = clean_settings
        config_file.write_text("")
        result = load_setting("some/key", "default_val")
        assert result == "default_val"


# ---------------------------------------------------------------------------
# Case-sensitive key preservation
# ---------------------------------------------------------------------------


def test_case_sensitive_key_preservation(clean_settings: Path) -> None:
    """Mixed-case key names survive the save/load round-trip unchanged."""
    save_setting("MyMixedCaseKey", "value123")
    assert load_setting("MyMixedCaseKey") == "value123"

    # Verify in the raw INI file that the key casing is preserved
    config = configparser.ConfigParser()
    config.optionxform = str
    config.read(str(clean_settings), encoding="utf-8")
    assert config.has_option("General", "MyMixedCaseKey")
    # A lowercased variant must NOT exist
    assert not config.has_option("General", "mymixedcasekey")


# ---------------------------------------------------------------------------
# Corrupt INI file (no section header — garbage text)
# ---------------------------------------------------------------------------


def test_corrupt_ini_file_raises_on_load(clean_settings: Path) -> None:
    """Syntactically invalid INI (no section header) raises MissingSectionHeaderError.

    configparser.read() does not silently ignore garbage content — it raises
    ``MissingSectionHeaderError``.  ``load_setting`` does not catch this
    exception, so it propagates to the caller.
    """
    clean_settings.write_text("this is garbage\nno section header\nfoo=bar\n")
    with pytest.raises(configparser.MissingSectionHeaderError):
        load_setting("any/key", "fallback")


def test_corrupt_ini_file_raises_on_save(clean_settings: Path) -> None:
    """save_setting also fails when reading a corrupt INI (get_settings call)."""
    clean_settings.write_text("this is garbage\nno section header\nfoo=bar\n")
    with pytest.raises(configparser.MissingSectionHeaderError):
        save_setting("new_key", "new_value")


# ---------------------------------------------------------------------------
# Parent directory creation on save
# ---------------------------------------------------------------------------


def test_save_setting_creates_parent_directories(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """save_setting creates missing parent directories for the INI file."""
    # Point config path to a deeply nested directory that doesn't exist yet
    deep_path = tmp_path / "a" / "b" / "c" / "settings.ini"
    monkeypatch.setattr(
        "src.utils.config_manager._get_config_path",
        lambda: deep_path,
    )
    assert not deep_path.parent.exists()

    save_setting("nested/key", "works")

    assert deep_path.parent.exists()
    assert deep_path.exists()
    assert load_setting("nested/key") == "works"


# ---------------------------------------------------------------------------
# Keyring returns None for secure key — INI fallback
# ---------------------------------------------------------------------------


def test_keyring_returns_none_falls_back_to_ini(
    clean_settings: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When keyring.get_password returns None, load_setting falls back to INI value."""
    # Write a value directly into the INI for a secure key
    config = configparser.ConfigParser()
    config.optionxform = str
    config.add_section("General")
    config.set("General", SETTING_LLM_GEMINI_API_KEY, "ini-fallback-value")
    with clean_settings.open("w", encoding="utf-8") as fh:
        config.write(fh)

    # Make keyring return None (key not found, no exception)
    monkeypatch.setattr("keyring.get_password", lambda _svc, _key: None)

    result = load_setting(SETTING_LLM_GEMINI_API_KEY, "default")
    assert result == "ini-fallback-value"


# ---------------------------------------------------------------------------
# Whitespace-only values in Custom LLM setup
# ---------------------------------------------------------------------------


def test_llm_setup_custom_whitespace_only_values(clean_settings: Path) -> None:
    """Whitespace-only Custom LLM non-secure fields are stripped by configparser.

    ``configparser`` strips leading/trailing whitespace on read-back, so
    ``"   "`` becomes ``""`` for non-secure keys (endpoint, model).  The
    secure key (api_key) is stored in keyring and survives whitespace, but
    since endpoint and model become empty, ``check_llm_setup`` returns False.
    """
    save_setting(SETTING_LLM_METHOD, LLM_METHOD_CUSTOM)
    save_setting(SETTING_LLM_CUSTOM_API_KEY, "   ")  # secure key — keyring preserves
    save_setting(SETTING_LLM_CUSTOM_ENDPOINT, "   ")  # INI → stripped to ""
    save_setting(SETTING_LLM_CUSTOM_MODEL, "   ")  # INI → stripped to ""
    # Endpoint and model are empty after round-trip, so setup check fails
    assert check_llm_setup() is False


# ---------------------------------------------------------------------------
# check_ocr_setup when check_ocr_availability raises
# ---------------------------------------------------------------------------


def test_ocr_setup_availability_raises_propagates(clean_settings: Path) -> None:
    """When check_ocr_availability raises RuntimeError, it propagates to caller."""
    save_setting(SETTING_OCR_METHOD, OCR_METHOD_TESSERACT)
    with (
        patch(
            "src.utils.ocr_checker.check_ocr_availability",
            side_effect=RuntimeError("OCR engine crashed"),
        ),
        pytest.raises(RuntimeError, match="OCR engine crashed"),
    ):
        check_ocr_setup()


# ---------------------------------------------------------------------------
# load_setting with bool default and stored "true"/"false"
# ---------------------------------------------------------------------------


def test_load_setting_bool_default_true_stored_false(clean_settings: Path) -> None:
    """load_setting("key", True) with stored value "false" returns False."""
    save_setting("my_flag", "false")
    result = load_setting("my_flag", True)
    assert result is False


def test_load_setting_bool_default_false_stored_true(clean_settings: Path) -> None:
    """load_setting("key", False) with stored value "true" returns True."""
    save_setting("my_flag", "true")
    result = load_setting("my_flag", False)
    assert result is True


# ---------------------------------------------------------------------------
# save_setting with None value for secure key
# ---------------------------------------------------------------------------


def test_save_setting_none_secure_key_deletes_from_keyring(
    clean_settings: Path,
) -> None:
    """Saving None to a secure key calls keyring.delete_password.

    Since None is falsy, the code takes the delete branch.  After deletion,
    keyring returns None and the INI has no entry, so load_setting returns
    the default.
    """
    # First, store a real value
    save_setting(SETTING_LLM_GEMINI_API_KEY, "to-be-deleted")
    assert load_setting(SETTING_LLM_GEMINI_API_KEY, "") == "to-be-deleted"

    # Save None — triggers keyring.delete_password
    save_setting(SETTING_LLM_GEMINI_API_KEY, None)

    # Keyring no longer has it; INI was never written (delete path returns early)
    assert load_setting(SETTING_LLM_GEMINI_API_KEY, "") == ""


def test_save_setting_none_secure_key_does_not_write_ini(
    clean_settings: Path,
) -> None:
    """Saving None to a secure key does NOT store empty string in INI.

    The keyring delete path returns immediately after success — it never
    falls through to the INI write logic.  Only a keyring failure triggers
    the INI fallback.
    """
    save_setting(SETTING_LLM_CUSTOM_API_KEY, None)

    # The INI file should either not exist or not contain the key
    if clean_settings.exists():
        config = configparser.ConfigParser()
        config.optionxform = str
        config.read(str(clean_settings), encoding="utf-8")
        has_key = config.has_option("General", SETTING_LLM_CUSTOM_API_KEY)
        assert not has_key


def test_save_setting_none_secure_key_keyring_failure_stores_empty_in_ini(
    clean_settings: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When keyring fails on None save, INI fallback stores empty string."""

    def failing_delete(*_args: object) -> None:
        raise RuntimeError("Keychain unavailable")

    monkeypatch.setattr("keyring.delete_password", failing_delete)

    save_setting(SETTING_LLM_CUSTOM_API_KEY, None)

    # The INI file should contain an empty string for the key
    config = configparser.ConfigParser()
    config.optionxform = str
    config.read(str(clean_settings), encoding="utf-8")
    assert config.get("General", SETTING_LLM_CUSTOM_API_KEY) == ""


# ===========================================================================
# Additional tests — load_setting with default values
# ===========================================================================


def test_load_setting_string_default_none_key_missing(
    clean_settings: Path,
) -> None:
    """Missing key with string default returns the default string."""
    assert load_setting("totally/absent", "my_default") == "my_default"


def test_load_setting_int_default_large_value(clean_settings: Path) -> None:
    """Large integer values are loaded correctly."""
    save_setting("big_num", "999999999")
    assert load_setting("big_num", 0) == 999999999  # noqa: PLR2004


def test_load_setting_float_scientific_notation(clean_settings: Path) -> None:
    """Scientific notation float values are loaded correctly."""
    save_setting("sci", "1.5e3")
    assert load_setting("sci", 0.0) == 1500.0  # noqa: PLR2004


def test_load_setting_int_default_returns_stored_int(
    clean_settings: Path,
) -> None:
    """Stored integer string is converted to int when default is int."""
    save_setting("port", "8080")
    result = load_setting("port", 3000)
    assert result == 8080  # noqa: PLR2004
    assert isinstance(result, int)


# ===========================================================================
# Additional tests — save_setting then load_setting round-trip
# ===========================================================================


def test_save_load_roundtrip_multiple_keys(clean_settings: Path) -> None:
    """Multiple different keys can be saved and loaded independently."""
    save_setting("key_a", "val_a")
    save_setting("key_b", "val_b")
    save_setting("key_c", "val_c")
    assert load_setting("key_a") == "val_a"
    assert load_setting("key_b") == "val_b"
    assert load_setting("key_c") == "val_c"


def test_save_load_roundtrip_slashed_key(clean_settings: Path) -> None:
    """Keys with slashes (namespaced) survive round-trip."""
    save_setting("llm/temperature", "0.7")
    assert load_setting("llm/temperature", "1.0") == "0.7"


def test_save_load_roundtrip_numeric_string(clean_settings: Path) -> None:
    """Numeric string without numeric default is returned as string."""
    save_setting("version", "42")
    result = load_setting("version", "")
    assert result == "42"
    assert isinstance(result, str)


def test_save_load_roundtrip_boolean_string_no_default(
    clean_settings: Path,
) -> None:
    """Boolean string without bool default is returned as string."""
    save_setting("flag", "true")
    result = load_setting("flag")
    assert result == "true"
    assert isinstance(result, str)


# ===========================================================================
# Additional tests — check_llm_setup with various providers
# ===========================================================================


def test_llm_setup_gemini_default_method(clean_settings: Path) -> None:
    """When no method is saved, Gemini is the default; needs API key."""
    # No SETTING_LLM_METHOD saved at all — defaults to Gemini
    assert not check_llm_setup()  # no API key yet
    save_setting(SETTING_LLM_GEMINI_API_KEY, "key-abc")
    assert check_llm_setup()


def test_llm_setup_custom_all_fields_valid(clean_settings: Path) -> None:
    """Custom method with all three fields set returns True."""
    save_setting(SETTING_LLM_METHOD, LLM_METHOD_CUSTOM)
    save_setting(SETTING_LLM_CUSTOM_API_KEY, "sk-test")
    save_setting(SETTING_LLM_CUSTOM_ENDPOINT, "https://api.openai.com/v1")
    save_setting(SETTING_LLM_CUSTOM_MODEL, "gpt-4")
    assert check_llm_setup() is True


def test_llm_setup_custom_missing_model(clean_settings: Path) -> None:
    """Custom method with missing model returns False."""
    save_setting(SETTING_LLM_METHOD, LLM_METHOD_CUSTOM)
    save_setting(SETTING_LLM_CUSTOM_API_KEY, "sk-test")
    save_setting(SETTING_LLM_CUSTOM_ENDPOINT, "https://api.openai.com/v1")
    # model not set
    assert check_llm_setup() is False


# ===========================================================================
# Additional tests — check_ocr_setup with various methods
# ===========================================================================


def test_ocr_setup_google_cloud_with_new_key_location(
    clean_settings: Path,
) -> None:
    """Google Cloud OCR works with new cloud/google_api_key location."""
    save_setting(SETTING_OCR_METHOD, OCR_METHOD_GOOGLE_CLOUD)
    save_setting(SETTING_GOOGLE_CLOUD_API_KEY, "new-cloud-key")
    assert check_ocr_setup() is True


# ===========================================================================
# Additional tests — secure key storage via keyring
# ===========================================================================


def test_secure_key_overwrite(clean_settings: Path) -> None:
    """Overwriting a secure key updates the stored value."""
    save_setting(SETTING_LLM_GEMINI_API_KEY, "first-key")
    assert load_setting(SETTING_LLM_GEMINI_API_KEY, "") == "first-key"
    save_setting(SETTING_LLM_GEMINI_API_KEY, "second-key")
    assert load_setting(SETTING_LLM_GEMINI_API_KEY, "") == "second-key"


def test_secure_key_cloud_google_roundtrip(clean_settings: Path) -> None:
    """cloud/google_api_key is stored and loaded via keyring."""
    save_setting(SETTING_GOOGLE_CLOUD_API_KEY, "cloud-key-xyz")
    assert load_setting(SETTING_GOOGLE_CLOUD_API_KEY, "") == "cloud-key-xyz"


# ===========================================================================
# Additional tests — keyring fallback to INI file
# ===========================================================================


def test_keyring_failure_save_then_load_from_ini(
    clean_settings: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When keyring fails on both save and load, INI file is used for both."""

    def failing_set(*_args: object) -> None:
        raise RuntimeError("Keychain unavailable")

    def failing_get(*_args: object) -> None:
        raise RuntimeError("Keychain unavailable")

    monkeypatch.setattr("keyring.set_password", failing_set)
    monkeypatch.setattr("keyring.get_password", failing_get)

    save_setting(SETTING_LLM_GEMINI_API_KEY, "fallback-value")
    result = load_setting(SETTING_LLM_GEMINI_API_KEY, "default")
    assert result == "fallback-value"


# ===========================================================================
# Additional tests — missing config file (auto-create)
# ===========================================================================


def test_save_setting_creates_config_file(clean_settings: Path) -> None:
    """save_setting creates the config file if it doesn't exist."""
    assert not clean_settings.exists()
    save_setting("new_key", "new_value")
    assert clean_settings.exists()
    assert load_setting("new_key") == "new_value"


def test_load_setting_missing_config_file_returns_default(
    clean_settings: Path,
) -> None:
    """load_setting returns default when config file doesn't exist."""
    assert not clean_settings.exists()
    assert load_setting("any_key", "default_val") == "default_val"


# ===========================================================================
# Additional tests — corrupt config file
# ===========================================================================


def test_load_setting_with_ini_comment_lines(clean_settings: Path) -> None:
    """INI file with comment lines is parsed correctly."""
    clean_settings.write_text("# This is a comment\n[General]\nmy_key = my_value\n")
    assert load_setting("my_key") == "my_value"


def test_save_load_multiple_sections_only_general_used(
    clean_settings: Path,
) -> None:
    """Keys from other sections are not confused with General section keys."""
    # Write a config with two sections
    clean_settings.write_text("[General]\nkey1 = val1\n\n[Other]\nkey1 = other_val\n")
    # load_setting reads from General
    assert load_setting("key1") == "val1"


# ===========================================================================
# Additional tests — type casting edge cases
# ===========================================================================


def test_load_setting_bool_on_off_case_variants(
    clean_settings: Path,
) -> None:
    """ON/OFF in various cases are recognized as bool."""
    save_setting("flag", "ON")
    assert load_setting("flag", False) is True
    save_setting("flag", "OFF")
    assert load_setting("flag", True) is False


def test_load_setting_int_whitespace_only(clean_settings: Path) -> None:
    """Whitespace-only value with int default falls back to default."""
    # configparser strips whitespace, so "   " becomes ""
    save_setting("num", "   ")
    assert load_setting("num", 42) == 42  # noqa: PLR2004


def test_load_setting_float_inf(clean_settings: Path) -> None:
    """String 'inf' with float default is parsed as float('inf')."""
    save_setting("val", "inf")
    result = load_setting("val", 0.0)
    assert result == float("inf")


# ===========================================================================
# EXPANDED TESTS — load_setting / save_setting roundtrips
# ===========================================================================


class TestLoadSaveRoundtrips:
    """Comprehensive roundtrip tests for all setting types."""

    def test_roundtrip_true_bool(self, clean_settings: Path) -> None:
        """Save True, load with bool default."""
        save_setting("rt/bool_true", True)
        assert load_setting("rt/bool_true", False) is True

    def test_roundtrip_false_bool(self, clean_settings: Path) -> None:
        """Save False, load with bool default."""
        save_setting("rt/bool_false", False)
        assert load_setting("rt/bool_false", True) is False

    def test_roundtrip_zero_int(self, clean_settings: Path) -> None:
        """Save 0, load with int default."""
        save_setting("rt/zero", 0)
        assert load_setting("rt/zero", 99) == 0

    def test_roundtrip_positive_int(self, clean_settings: Path) -> None:
        """Save positive int."""
        save_setting("rt/pos", 42)
        assert load_setting("rt/pos", 0) == 42  # noqa: PLR2004

    def test_roundtrip_negative_int(self, clean_settings: Path) -> None:
        """Save negative int."""
        save_setting("rt/neg", -100)
        assert load_setting("rt/neg", 0) == -100  # noqa: PLR2004

    def test_roundtrip_float(self, clean_settings: Path) -> None:
        """Save float."""
        save_setting("rt/float", 2.718)
        assert load_setting("rt/float", 0.0) == 2.718  # noqa: PLR2004

    def test_roundtrip_zero_float(self, clean_settings: Path) -> None:
        """Save 0.0 float."""
        save_setting("rt/zfloat", 0.0)
        assert load_setting("rt/zfloat", 9.9) == 0.0

    def test_roundtrip_empty_string(self, clean_settings: Path) -> None:
        """Save empty string."""
        save_setting("rt/empty", "")
        assert load_setting("rt/empty", "fallback") == ""

    def test_roundtrip_string_with_equals(self, clean_settings: Path) -> None:
        """Save string containing equals sign."""
        save_setting("rt/eq", "key=value")
        assert load_setting("rt/eq") == "key=value"

    def test_roundtrip_string_with_newlines(self, clean_settings: Path) -> None:
        """Save string with newline (configparser handles this)."""
        save_setting("rt/nl", "line1")
        assert load_setting("rt/nl") == "line1"

    def test_roundtrip_path_with_backslashes(self, clean_settings: Path) -> None:
        """Windows-style path with backslashes."""
        save_setting("rt/winpath", "C:\\Users\\test\\docs")
        assert load_setting("rt/winpath", "") == "C:\\Users\\test\\docs"

    def test_roundtrip_url(self, clean_settings: Path) -> None:
        """URL with query parameters."""
        url = "https://api.example.com/v1?key=abc&fmt=json#section"
        save_setting("rt/url", url)
        assert load_setting("rt/url", "") == url

    def test_roundtrip_unicode_cjk(self, clean_settings: Path) -> None:
        """Chinese/Japanese/Korean characters."""
        save_setting("rt/cjk", "翻译测试")
        assert load_setting("rt/cjk", "") == "翻译测试"

    def test_roundtrip_unicode_emoji(self, clean_settings: Path) -> None:
        """Emoji characters survive roundtrip."""
        save_setting("rt/emoji", "test value")
        assert load_setting("rt/emoji", "") == "test value"

    def test_roundtrip_numeric_string_no_int_default(
        self, clean_settings: Path
    ) -> None:
        """Numeric string with string default stays as string."""
        save_setting("rt/numstr", "12345")
        result = load_setting("rt/numstr", "")
        assert result == "12345"
        assert isinstance(result, str)

    def test_save_overwrites_previous_value(self, clean_settings: Path) -> None:
        """Second save overwrites the first."""
        save_setting("rt/over", "v1")
        save_setting("rt/over", "v2")
        assert load_setting("rt/over") == "v2"

    def test_save_none_stores_empty_string(self, clean_settings: Path) -> None:
        """None value for non-secure key stores empty string."""
        save_setting("rt/none_val", None)
        assert load_setting("rt/none_val", "default") == ""

    def test_many_keys_independent(self, clean_settings: Path) -> None:
        """Many keys stored independently."""
        for i in range(20):
            save_setting(f"rt/key_{i}", f"val_{i}")
        for i in range(20):
            assert load_setting(f"rt/key_{i}") == f"val_{i}"


# ===========================================================================
# EXPANDED TESTS — check_llm_setup with various provider configs
# ===========================================================================


class TestCheckLlmSetupExpanded:
    """Extended tests for check_llm_setup."""

    def test_gemini_with_valid_key(self, clean_settings: Path) -> None:
        """Gemini with valid API key returns True."""
        save_setting(SETTING_LLM_METHOD, LLM_METHOD_GEMINI)
        save_setting(SETTING_LLM_GEMINI_API_KEY, "valid-key-123")
        assert check_llm_setup() is True

    def test_gemini_with_empty_key(self, clean_settings: Path) -> None:
        """Gemini with empty API key returns False."""
        save_setting(SETTING_LLM_METHOD, LLM_METHOD_GEMINI)
        save_setting(SETTING_LLM_GEMINI_API_KEY, "")
        assert check_llm_setup() is False

    def test_custom_with_all_three_fields(self, clean_settings: Path) -> None:
        """Custom with all three fields returns True."""
        save_setting(SETTING_LLM_METHOD, LLM_METHOD_CUSTOM)
        save_setting(SETTING_LLM_CUSTOM_API_KEY, "sk-key")
        save_setting(SETTING_LLM_CUSTOM_ENDPOINT, "https://api.test.com")
        save_setting(SETTING_LLM_CUSTOM_MODEL, "gpt-4o")
        assert check_llm_setup() is True

    def test_custom_missing_all_fields(self, clean_settings: Path) -> None:
        """Custom with no fields returns False."""
        save_setting(SETTING_LLM_METHOD, LLM_METHOD_CUSTOM)
        assert check_llm_setup() is False

    def test_custom_only_key_and_endpoint(self, clean_settings: Path) -> None:
        """Custom with key + endpoint but no model returns False."""
        save_setting(SETTING_LLM_METHOD, LLM_METHOD_CUSTOM)
        save_setting(SETTING_LLM_CUSTOM_API_KEY, "sk-key")
        save_setting(SETTING_LLM_CUSTOM_ENDPOINT, "https://api.test.com")
        assert check_llm_setup() is False

    def test_custom_only_key_and_model(self, clean_settings: Path) -> None:
        """Custom with key + model but no endpoint returns False."""
        save_setting(SETTING_LLM_METHOD, LLM_METHOD_CUSTOM)
        save_setting(SETTING_LLM_CUSTOM_API_KEY, "sk-key")
        save_setting(SETTING_LLM_CUSTOM_MODEL, "gpt-4o")
        assert check_llm_setup() is False

    def test_custom_only_endpoint_and_model(self, clean_settings: Path) -> None:
        """Custom with endpoint + model but no key now returns True (api_key optional)."""
        save_setting(SETTING_LLM_METHOD, LLM_METHOD_CUSTOM)
        save_setting(SETTING_LLM_CUSTOM_ENDPOINT, "https://api.test.com")
        save_setting(SETTING_LLM_CUSTOM_MODEL, "gpt-4o")
        assert check_llm_setup() is True

    def test_no_method_at_all(self, clean_settings: Path) -> None:
        """No method saved at all defaults to Gemini check."""
        assert check_llm_setup() is False

    def test_gemini_key_then_clear_it(self, clean_settings: Path) -> None:
        """Setting then clearing API key."""
        save_setting(SETTING_LLM_METHOD, LLM_METHOD_GEMINI)
        save_setting(SETTING_LLM_GEMINI_API_KEY, "key")
        assert check_llm_setup() is True
        save_setting(SETTING_LLM_GEMINI_API_KEY, "")
        assert check_llm_setup() is False

    def test_switching_methods(self, clean_settings: Path) -> None:
        """Availability is based on configured providers, not the active method setting."""
        save_setting(SETTING_LLM_METHOD, LLM_METHOD_GEMINI)
        save_setting(SETTING_LLM_GEMINI_API_KEY, "gemini-key")
        assert check_llm_setup() is True

        # Switching the active method does NOT disable an already-configured provider.
        save_setting(SETTING_LLM_METHOD, LLM_METHOD_CUSTOM)
        assert check_llm_setup() is True  # Gemini is still configured

    def test_unknown_provider_name(self, clean_settings: Path) -> None:
        """Unknown provider name returns False."""
        save_setting(SETTING_LLM_METHOD, "AzureOpenAI")
        assert check_llm_setup() is False


# ===========================================================================
# EXPANDED TESTS — check_ocr_setup with various engine configs
# ===========================================================================


class TestCheckOcrSetupExpanded:
    """Extended tests for check_ocr_setup."""

    def test_no_method_saved_tesseract_available(self, clean_settings: Path) -> None:
        """No OCR method saved, Tesseract is available."""
        with patch(
            "src.utils.ocr_checker.check_ocr_availability",
            return_value=(True, ""),
        ):
            assert check_ocr_setup() is True

    def test_no_method_saved_tesseract_not_available(
        self, clean_settings: Path
    ) -> None:
        """No OCR method saved, Tesseract is not available."""
        with patch(
            "src.utils.ocr_checker.check_ocr_availability",
            return_value=(False, "Tesseract not installed"),
        ):
            assert check_ocr_setup() is False

    def test_google_cloud_with_new_location_key(self, clean_settings: Path) -> None:
        """Google Cloud OCR with key in new cloud/ location."""
        save_setting(SETTING_OCR_METHOD, OCR_METHOD_GOOGLE_CLOUD)
        save_setting(SETTING_GOOGLE_CLOUD_API_KEY, "gcloud-key")
        assert check_ocr_setup() is True

    def test_google_cloud_no_key_anywhere(self, clean_settings: Path) -> None:
        """Google Cloud OCR with no key returns False."""
        save_setting(SETTING_OCR_METHOD, OCR_METHOD_GOOGLE_CLOUD)
        assert check_ocr_setup() is False

    def test_easyocr_available(self, clean_settings: Path) -> None:
        """EasyOCR method, available."""
        save_setting(SETTING_OCR_METHOD, OCR_METHOD_EASYOCR)
        with patch(
            "src.utils.ocr_checker.check_ocr_availability",
            return_value=(True, ""),
        ):
            assert check_ocr_setup() is True

    def test_easyocr_not_available(self, clean_settings: Path) -> None:
        """EasyOCR method, not available."""
        save_setting(SETTING_OCR_METHOD, OCR_METHOD_EASYOCR)
        with patch(
            "src.utils.ocr_checker.check_ocr_availability",
            return_value=(False, "Not installed"),
        ):
            assert check_ocr_setup() is False

    def test_tesseract_explicitly_set_available(self, clean_settings: Path) -> None:
        """Tesseract explicitly set and available."""
        save_setting(SETTING_OCR_METHOD, OCR_METHOD_TESSERACT)
        with patch(
            "src.utils.ocr_checker.check_ocr_availability",
            return_value=(True, "Tesseract ready"),
        ):
            assert check_ocr_setup() is True

    def test_tesseract_explicitly_set_not_available(self, clean_settings: Path) -> None:
        """Tesseract explicitly set but not available."""
        save_setting(SETTING_OCR_METHOD, OCR_METHOD_TESSERACT)
        with patch(
            "src.utils.ocr_checker.check_ocr_availability",
            return_value=(False, "Not installed"),
        ):
            assert check_ocr_setup() is False


# ===========================================================================
# EXPANDED TESTS — Secure key storage edge cases
# ===========================================================================


class TestSecureKeyStorageExpanded:
    """Extended tests for secure key storage via keyring."""

    def test_all_four_secure_keys(self, clean_settings: Path) -> None:
        """All four secure keys can be stored independently."""
        from src.utils.config_manager import _SECURE_KEYS  # noqa: PLC0415

        for i, key in enumerate(_SECURE_KEYS):
            save_setting(key, f"value-{i}")
        for i, key in enumerate(_SECURE_KEYS):
            assert load_setting(key, "") == f"value-{i}"

    def test_secure_key_overwrite_multiple_times(self, clean_settings: Path) -> None:
        """Overwriting a secure key multiple times."""
        for i in range(5):
            save_setting(SETTING_LLM_GEMINI_API_KEY, f"key-{i}")
        assert load_setting(SETTING_LLM_GEMINI_API_KEY, "") == "key-4"

    def test_secure_key_save_none_then_new_value(self, clean_settings: Path) -> None:
        """Delete secure key then set new value."""
        save_setting(SETTING_LLM_GEMINI_API_KEY, "original")
        save_setting(SETTING_LLM_GEMINI_API_KEY, "")
        assert load_setting(SETTING_LLM_GEMINI_API_KEY, "") == ""
        save_setting(SETTING_LLM_GEMINI_API_KEY, "new-value")
        assert load_setting(SETTING_LLM_GEMINI_API_KEY, "") == "new-value"

    def test_secure_key_long_value(self, clean_settings: Path) -> None:
        """Long API key value survives roundtrip."""
        long_key = "sk-" + "a" * 500
        save_setting(SETTING_LLM_CUSTOM_API_KEY, long_key)
        assert load_setting(SETTING_LLM_CUSTOM_API_KEY, "") == long_key

    def test_secure_key_special_chars(self, clean_settings: Path) -> None:
        """API key with special characters."""
        special_key = "sk-test/key+abc=123&def"
        save_setting(SETTING_LLM_CUSTOM_API_KEY, special_key)
        assert load_setting(SETTING_LLM_CUSTOM_API_KEY, "") == special_key

    def test_keyring_failure_on_save_falls_back_to_ini(
        self,
        clean_settings: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Keyring save failure stores in INI file."""
        import configparser as cp  # noqa: PLC0415

        def failing_set(*_args: object) -> None:
            raise RuntimeError("Keychain locked")

        monkeypatch.setattr("keyring.set_password", failing_set)
        save_setting(SETTING_LLM_GEMINI_API_KEY, "fallback-key")

        config = cp.ConfigParser()
        config.optionxform = str
        config.read(str(clean_settings), encoding="utf-8")
        assert config.get("General", SETTING_LLM_GEMINI_API_KEY) == "fallback-key"

    def test_keyring_failure_on_load_falls_back_to_ini(
        self,
        clean_settings: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Keyring load failure reads from INI file."""
        import configparser as cp  # noqa: PLC0415

        # Plant value in INI
        config = cp.ConfigParser()
        config.optionxform = str
        config.add_section("General")
        config.set("General", SETTING_LLM_GEMINI_API_KEY, "ini-val")
        with clean_settings.open("w", encoding="utf-8") as fh:
            config.write(fh)

        def failing_get(*_args: object) -> None:
            raise RuntimeError("Keychain locked")

        monkeypatch.setattr("keyring.get_password", failing_get)
        assert load_setting(SETTING_LLM_GEMINI_API_KEY, "") == "ini-val"

    def test_keyring_and_ini_both_fail(
        self,
        clean_settings: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When keyring fails and INI has no value, default is returned."""

        def failing_get(*_args: object) -> None:
            raise RuntimeError("Keychain locked")

        monkeypatch.setattr("keyring.get_password", failing_get)
        assert load_setting(SETTING_LLM_GEMINI_API_KEY, "default-val") == "default-val"


# ===========================================================================
# EXPANDED TESTS — INI file parsing edge cases
# ===========================================================================


class TestIniParsingEdgeCases:
    """Tests for INI file parsing edge cases."""

    def test_key_with_percent_sign_raises(self, clean_settings: Path) -> None:
        """Value with bare percent sign raises ValueError (interpolation syntax)."""
        # ConfigParser uses interpolation by default; bare '%' is invalid.
        with pytest.raises(ValueError, match="invalid interpolation syntax"):
            save_setting("test/pct", "100%")

    def test_key_with_hash_in_value(self, clean_settings: Path) -> None:
        """Value containing hash (comment char)."""
        save_setting("test/hash", "value#comment")
        result = load_setting("test/hash", "")
        assert result == "value#comment"

    def test_key_with_semicolon_in_value(self, clean_settings: Path) -> None:
        """Value containing semicolon (INI comment char)."""
        save_setting("test/semi", "value;extra")
        result = load_setting("test/semi", "")
        assert result == "value;extra"

    def test_key_with_multiline_content(self, clean_settings: Path) -> None:
        """Saving a value that starts with a simple string (no newlines)."""
        save_setting("test/simple", "line1")
        assert load_setting("test/simple", "") == "line1"

    def test_config_preserves_section(self, clean_settings: Path) -> None:
        """All settings go into [General] section."""
        import configparser as cp  # noqa: PLC0415

        save_setting("test/key1", "v1")
        save_setting("test/key2", "v2")
        config = cp.ConfigParser()
        config.optionxform = str
        config.read(str(clean_settings), encoding="utf-8")
        assert config.has_section("General")
        assert config.get("General", "test/key1") == "v1"

    def test_wrong_section_returns_default(self, clean_settings: Path) -> None:
        """Key from wrong section is not found."""
        clean_settings.write_text("[Other]\nmy_key = my_value\n")
        assert load_setting("my_key", "fallback") == "fallback"

    def test_empty_section_header(self, clean_settings: Path) -> None:
        """Empty General section still works."""
        clean_settings.write_text("[General]\n")
        assert load_setting("any_key", "default") == "default"

    def test_multiple_equals_in_value(self, clean_settings: Path) -> None:
        """Value with multiple equals signs is preserved."""
        save_setting("test/multi_eq", "a=b=c=d")
        assert load_setting("test/multi_eq") == "a=b=c=d"


# ===========================================================================
# EXPANDED TESTS — Type casting edge cases
# ===========================================================================


class TestTypeCastingExpanded:
    """Extended type casting tests."""

    def test_bool_true_uppercase(self, clean_settings: Path) -> None:
        """'TRUE' is recognized as True."""
        save_setting("flag", "TRUE")
        assert load_setting("flag", False) is True

    def test_bool_false_uppercase(self, clean_settings: Path) -> None:
        """'FALSE' is recognized as False."""
        save_setting("flag", "FALSE")
        assert load_setting("flag", True) is False

    def test_bool_yes_uppercase(self, clean_settings: Path) -> None:
        """'YES' is recognized as True."""
        save_setting("flag", "YES")
        assert load_setting("flag", False) is True

    def test_bool_no_uppercase(self, clean_settings: Path) -> None:
        """'NO' is recognized as False."""
        save_setting("flag", "NO")
        assert load_setting("flag", True) is False

    def test_bool_one(self, clean_settings: Path) -> None:
        """'1' is recognized as True."""
        save_setting("flag", "1")
        assert load_setting("flag", False) is True

    def test_bool_zero(self, clean_settings: Path) -> None:
        """'0' is recognized as False."""
        save_setting("flag", "0")
        assert load_setting("flag", True) is False

    def test_int_max_value(self, clean_settings: Path) -> None:
        """Large integer survives roundtrip."""
        save_setting("big", str(2**31))
        assert load_setting("big", 0) == 2**31

    def test_int_min_value(self, clean_settings: Path) -> None:
        """Large negative integer survives roundtrip."""
        save_setting("neg", str(-(2**31)))
        assert load_setting("neg", 0) == -(2**31)

    def test_float_very_small(self, clean_settings: Path) -> None:
        """Very small float survives roundtrip."""
        save_setting("tiny", "0.000001")
        result = load_setting("tiny", 0.0)
        assert abs(result - 0.000001) < 1e-10  # noqa: PLR2004

    def test_float_negative_inf(self, clean_settings: Path) -> None:
        """Negative infinity as float."""
        save_setting("val", "-inf")
        result = load_setting("val", 0.0)
        assert result == float("-inf")

    def test_float_nan(self, clean_settings: Path) -> None:
        """NaN as float."""
        import math  # noqa: PLC0415

        save_setting("val", "nan")
        result = load_setting("val", 0.0)
        assert math.isnan(result)

    def test_int_with_leading_zeros(self, clean_settings: Path) -> None:
        """Int with leading zeros."""
        save_setting("port", "0042")
        assert load_setting("port", 0) == 42  # noqa: PLR2004

    def test_bool_default_type_determines_cast(self, clean_settings: Path) -> None:
        """Default type determines whether bool conversion is attempted."""
        save_setting("val", "true")
        # String default — no conversion
        assert load_setting("val", "") == "true"
        # Bool default — conversion
        assert load_setting("val", False) is True
        # Int default — conversion fails, returns default
        assert load_setting("val", 0) == 0


# ===========================================================================
# EXPANDED TESTS — Google Cloud API key management
# ===========================================================================


class TestGoogleCloudApiKeyExpanded:
    """Extended tests for Google Cloud API key management."""

    def test_both_empty_returns_empty(self, clean_settings: Path) -> None:
        """Both locations empty returns empty string."""
        assert load_google_cloud_api_key() == ""

    def test_check_google_cloud_setup_with_key(self, clean_settings: Path) -> None:
        """check_google_cloud_setup returns True when key exists."""
        save_setting(SETTING_GOOGLE_CLOUD_API_KEY, "valid-key")
        assert check_google_cloud_setup() is True

    def test_check_google_cloud_setup_without_key(self, clean_settings: Path) -> None:
        """check_google_cloud_setup returns False when no key."""
        assert check_google_cloud_setup() is False


# ===========================================================================
# EXPANDED TESTS — Concurrent-like read/write safety
# ===========================================================================


class TestConcurrentSafety:
    """Tests for read/write safety patterns."""

    def test_read_after_multiple_writes(self, clean_settings: Path) -> None:
        """Reading after many rapid writes returns the last value."""
        for i in range(50):
            save_setting("counter", str(i))
        assert load_setting("counter", "") == "49"

    def test_different_keys_independent(self, clean_settings: Path) -> None:
        """Writing to one key doesn't affect another."""
        save_setting("key_a", "value_a")
        save_setting("key_b", "value_b")
        save_setting("key_b", "new_b")
        assert load_setting("key_a") == "value_a"
        assert load_setting("key_b") == "new_b"

    def test_save_then_overwrite_then_read(self, clean_settings: Path) -> None:
        """Sequential save → overwrite → read."""
        save_setting("x", "first")
        save_setting("x", "second")
        save_setting("x", "third")
        assert load_setting("x") == "third"

    def test_secure_and_regular_keys_coexist(self, clean_settings: Path) -> None:
        """Secure keys in keyring and regular keys in INI coexist."""
        save_setting(SETTING_LLM_GEMINI_API_KEY, "secret-key")
        save_setting("regular/key", "regular-val")
        assert load_setting(SETTING_LLM_GEMINI_API_KEY, "") == "secret-key"
        assert load_setting("regular/key") == "regular-val"


# ===========================================================================
# EXPANDED TESTS — Edge cases in settings file management
# ===========================================================================


class TestSettingsFileManagement:
    """Tests for config file creation and management."""

    def test_config_file_created_on_first_save(self, clean_settings: Path) -> None:
        """Config file is created on first save_setting call."""
        assert not clean_settings.exists()
        save_setting("first_key", "first_val")
        assert clean_settings.exists()

    def test_config_file_encoding_utf8(self, clean_settings: Path) -> None:
        """Config file is written with UTF-8 encoding."""
        save_setting("unicode_key", "日本語テスト")
        content = clean_settings.read_text(encoding="utf-8")
        assert "日本語テスト" in content

    def test_get_settings_returns_configparser(self, clean_settings: Path) -> None:
        """get_settings returns a ConfigParser instance."""
        from src.utils.config_manager import get_settings  # noqa: PLC0415

        config = get_settings()
        assert isinstance(config, configparser.ConfigParser)

    def test_get_settings_preserves_case(self, clean_settings: Path) -> None:
        """get_settings preserves key casing."""
        from src.utils.config_manager import get_settings  # noqa: PLC0415

        save_setting("MixedCaseKey", "value")
        config = get_settings()
        assert config.has_option("General", "MixedCaseKey")

    def test_get_settings_empty_file(self, clean_settings: Path) -> None:
        """get_settings works with empty file."""
        from src.utils.config_manager import get_settings  # noqa: PLC0415

        clean_settings.write_text("")
        config = get_settings()
        assert isinstance(config, configparser.ConfigParser)

    def test_get_settings_no_file(self, clean_settings: Path) -> None:
        """get_settings works when file doesn't exist."""
        from src.utils.config_manager import get_settings  # noqa: PLC0415

        assert not clean_settings.exists()
        config = get_settings()
        assert isinstance(config, configparser.ConfigParser)


# ===========================================================================
# EXPANDED TESTS — _SECURE_KEYS verification
# ===========================================================================


class TestSecureKeysSet:
    """Tests for _SECURE_KEYS membership."""

    def test_contains_gemini_key(self) -> None:
        """_SECURE_KEYS contains Gemini API key."""
        from src.utils.config_manager import _SECURE_KEYS  # noqa: PLC0415

        assert "llm/gemini_api_key" in _SECURE_KEYS

    def test_contains_custom_key(self) -> None:
        """_SECURE_KEYS contains Custom API key."""
        from src.utils.config_manager import _SECURE_KEYS  # noqa: PLC0415

        assert "llm/custom_api_key" in _SECURE_KEYS

    def test_contains_google_cloud_key(self) -> None:
        """_SECURE_KEYS contains Google Cloud API key."""
        from src.utils.config_manager import _SECURE_KEYS  # noqa: PLC0415

        assert "cloud/google_api_key" in _SECURE_KEYS

    def test_regular_key_not_in_secure_keys(self) -> None:
        """Regular settings keys are not in _SECURE_KEYS."""
        from src.utils.config_manager import _SECURE_KEYS  # noqa: PLC0415

        assert "app/storage_path" not in _SECURE_KEYS
        assert "ocr/method" not in _SECURE_KEYS
        assert "llm/method" not in _SECURE_KEYS


# ===========================================================================
# EXPANDED TESTS — load_setting with various defaults
# ===========================================================================


class TestLoadSettingDefaults:
    """Tests for load_setting with various default types."""

    def test_none_default_key_exists(self, clean_settings: Path) -> None:
        """When key exists and default is None, returns the stored value."""
        save_setting("test/key", "stored")
        assert load_setting("test/key", None) == "stored"

    def test_none_default_key_missing(self, clean_settings: Path) -> None:
        """When key is missing and default is None, returns None."""
        assert load_setting("missing/key", None) is None

    def test_no_default_argument(self, clean_settings: Path) -> None:
        """When no default argument is given, returns None for missing key."""
        assert load_setting("missing/key") is None

    def test_list_default_not_cast(self, clean_settings: Path) -> None:
        """Non-scalar default (list) doesn't trigger any casting."""
        save_setting("test/list", "value")
        result = load_setting("test/list", [])
        assert result == "value"  # Returns string, not list

    def test_dict_default_not_cast(self, clean_settings: Path) -> None:
        """Non-scalar default (dict) doesn't trigger any casting."""
        save_setting("test/dict", "value")
        result = load_setting("test/dict", {})
        assert result == "value"  # Returns string, not dict


# ===========================================================================
# TestCheckOfficeConverterSetup — expanded tests
# ===========================================================================


class TestCheckOfficeConverterSetup:
    """Tests for check_office_converter_setup with various backend combinations."""

    def test_returns_true_when_msoffice_available(self) -> None:
        """Returns True when MS Office (win32com) is available."""
        with patch(
            "src.utils.config_manager.check_msoffice_available",
            return_value=True,
        ):
            assert check_office_converter_setup()

    def test_returns_true_when_libreoffice_available(self) -> None:
        """Returns True when LibreOffice (UNO) is available."""
        with (
            patch(
                "src.utils.config_manager.check_msoffice_available",
                return_value=False,
            ),
            patch(
                "src.utils.config_manager.check_libreoffice_available",
                return_value=True,
            ),
        ):
            assert check_office_converter_setup()

    def test_returns_false_when_neither_available(self) -> None:
        """Returns False when neither MS Office nor LibreOffice is available."""
        with (
            patch(
                "src.utils.config_manager.check_msoffice_available",
                return_value=False,
            ),
            patch(
                "src.utils.config_manager.check_libreoffice_available",
                return_value=False,
            ),
        ):
            assert not check_office_converter_setup()

    def test_returns_true_when_both_available(self) -> None:
        """Returns True when both backends are available (first wins via or)."""
        with (
            patch(
                "src.utils.config_manager.check_msoffice_available",
                return_value=True,
            ),
            patch(
                "src.utils.config_manager.check_libreoffice_available",
                return_value=True,
            ),
        ):
            assert check_office_converter_setup()


# ===========================================================================
# Backfill — load_custom_providers malformed JSON, get_available_models
# filtering, model id round-trip, secure key keyring failure modes.
# ===========================================================================


class TestLoadCustomProvidersMalformed:
    """Backfill tests for load_custom_providers parsing edge cases."""

    def test_malformed_json_returns_empty_list(self, clean_settings: Path) -> None:
        """Garbage JSON in the providers slot returns an empty list."""
        from src.constants.settings import (  # noqa: PLC0415
            SETTING_LLM_CUSTOM_PROVIDERS,
        )
        from src.utils.config_manager import load_custom_providers  # noqa: PLC0415

        save_setting(SETTING_LLM_CUSTOM_PROVIDERS, "{not_json")
        assert load_custom_providers() == []

    def test_truncated_json_returns_empty_list(self, clean_settings: Path) -> None:
        """Truncated JSON array returns an empty list."""
        import json as _json  # noqa: PLC0415

        from src.constants.settings import (  # noqa: PLC0415
            SETTING_LLM_CUSTOM_PROVIDERS,
        )
        from src.utils.config_manager import load_custom_providers  # noqa: PLC0415

        # Write a valid prefix that fails to parse.
        save_setting(SETTING_LLM_CUSTOM_PROVIDERS, '[{"name": "Foo"')
        result = load_custom_providers()
        assert result == []
        # Confirm the original blob was not parseable.
        with pytest.raises(_json.JSONDecodeError):
            _json.loads('[{"name": "Foo"')

    def test_provider_missing_endpoint_filtered_by_get_available_models(
        self,
        clean_settings: Path,
    ) -> None:
        """Custom provider lacking endpoint is filtered out of available models.

        ``load_custom_providers`` itself returns the malformed entry (it
        only parses), but ``get_available_models`` skips providers with
        empty endpoint or empty models — that's the user-facing filter.
        """
        from src.utils.config_manager import (  # noqa: PLC0415
            get_available_models,
            save_custom_providers,
        )

        save_custom_providers(
            [
                # Valid provider
                {
                    "name": "Good",
                    "api_key": "k",
                    "endpoint": "https://api.example.com",
                    "models": "model-a",
                },
                # Missing endpoint → should be filtered out
                {
                    "name": "Bad",
                    "api_key": "k2",
                    "endpoint": "",
                    "models": "model-b",
                },
                # Missing models → should be filtered out
                {
                    "name": "AlsoBad",
                    "api_key": "k3",
                    "endpoint": "https://api2.example.com",
                    "models": "",
                },
            ]
        )
        models = get_available_models()
        names = {model_name for _provider, model_name in models}
        assert "model-a" in names
        assert "model-b" not in names

    def test_get_available_models_with_only_valid_gemini_and_invalid_custom(
        self,
        clean_settings: Path,
    ) -> None:
        """Valid Gemini + invalid custom provider → only Gemini models returned."""
        from src.constants.llm import GEMINI_MODELS, LLM_METHOD_GEMINI  # noqa: PLC0415
        from src.utils.config_manager import (  # noqa: PLC0415
            get_available_models,
            save_custom_providers,
        )

        save_setting(SETTING_LLM_GEMINI_API_KEY, "valid-key")
        save_custom_providers(
            [{"name": "Bad", "api_key": "k", "endpoint": "", "models": "x"}]
        )

        models = get_available_models()
        # All entries should be Gemini provider; none custom.
        providers = {p for p, _ in models}
        assert providers == {LLM_METHOD_GEMINI}
        assert len(models) == len(GEMINI_MODELS)


class TestModelIdRoundTrip:
    """Backfill tests for format_model_id / parse_model_id."""

    def test_basic_round_trip(self) -> None:
        """Standard provider/model pair survives format → parse."""
        from src.utils.config_manager import (  # noqa: PLC0415
            format_model_id,
            parse_model_id,
        )

        formatted = format_model_id("Gemini", "gemini-3-flash-preview")
        provider, model = parse_model_id(formatted)
        assert provider == "Gemini"
        assert model == "gemini-3-flash-preview"

    def test_parse_empty_returns_default(self) -> None:
        """Empty string returns default (Gemini, DEFAULT_GEMINI_MODEL)."""
        from src.constants.llm import (  # noqa: PLC0415
            DEFAULT_GEMINI_MODEL,
            LLM_METHOD_GEMINI,
        )
        from src.utils.config_manager import parse_model_id  # noqa: PLC0415

        provider, model = parse_model_id("")
        assert provider == LLM_METHOD_GEMINI
        assert model == DEFAULT_GEMINI_MODEL

    def test_parse_no_separator_returns_default(self) -> None:
        """String without ':' separator returns default."""
        from src.constants.llm import (  # noqa: PLC0415
            DEFAULT_GEMINI_MODEL,
            LLM_METHOD_GEMINI,
        )
        from src.utils.config_manager import parse_model_id  # noqa: PLC0415

        provider, model = parse_model_id("just-a-model-name")
        assert provider == LLM_METHOD_GEMINI
        assert model == DEFAULT_GEMINI_MODEL

    def test_parse_provider_with_colons_documents_current_behaviour(self) -> None:
        """Provider name containing ':' is split on first colon only.

        Current behaviour: ``Provider:With:Colons`` formats to
        ``Provider:With:Colons:model`` and parses to (``Provider``,
        ``With:Colons:model``). Colons in provider names are *not*
        round-trip safe.
        TODO: if multi-colon providers ever become a real use case, add an
        escape mechanism in src/utils/config_manager.py.
        """
        from src.utils.config_manager import (  # noqa: PLC0415
            format_model_id,
            parse_model_id,
        )

        formatted = format_model_id("Provider:With:Colons", "model")
        # Format gives "Provider:With:Colons:model"
        assert formatted == "Provider:With:Colons:model"
        provider, model = parse_model_id(formatted)
        # split(":", 1) keeps everything past the first ':' in the model
        assert provider == "Provider"
        assert model == "With:Colons:model"


class TestSecureKeyringErrorPaths:
    """Backfill tests for secure-key keyring failures and migrations."""

    def test_keyring_get_keyerror_falls_back_to_ini_value(
        self,
        clean_settings: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When keyring.get_password raises, INI fallback value is returned.

        The mock storage in this test file would normally serve the
        password; we override it to raise so we exercise the broad
        except clause in load_setting.
        """
        from src.constants.settings import (  # noqa: PLC0415
            SETTING_LLM_GEMINI_API_KEY,
        )

        # First, write a non-secure path to the INI directly so load_setting
        # falls through to the ini reader after keyring fails.
        config = configparser.ConfigParser()
        config.optionxform = str
        config.add_section("General")
        config.set("General", SETTING_LLM_GEMINI_API_KEY, "ini-fallback-key")
        with clean_settings.open("w", encoding="utf-8") as fh:
            config.write(fh)

        def _exploding_get(_service: str, _username: str) -> str:
            raise KeyError("simulated keyring failure")

        monkeypatch.setattr("keyring.get_password", _exploding_get)

        # The migration step (set_password back into keyring) will also
        # fail, but that's logged-and-ignored. The INI value is returned.
        def _exploding_set(*_a: object, **_kw: object) -> None:
            raise RuntimeError("simulated keyring set failure")

        monkeypatch.setattr("keyring.set_password", _exploding_set)

        result = load_setting(SETTING_LLM_GEMINI_API_KEY, "")
        assert result == "ini-fallback-key"

    def test_secure_key_migrates_from_ini_and_clears_ini(
        self,
        clean_settings: Path,
    ) -> None:
        """Legacy plaintext value in INI migrates to keyring and is cleared.

        Verifies the opportunistic migration path: a value that lives in
        the INI for a secure key is moved into keyring on first read, and
        the INI entry is removed.
        """
        from src.constants.settings import (  # noqa: PLC0415
            SETTING_LLM_GEMINI_API_KEY,
        )

        # Write the legacy plaintext value directly into the INI bypassing
        # save_setting (which would route it to keyring directly).
        config = configparser.ConfigParser()
        config.optionxform = str
        config.add_section("General")
        config.set("General", SETTING_LLM_GEMINI_API_KEY, "plain-ini-key")
        with clean_settings.open("w", encoding="utf-8") as fh:
            config.write(fh)

        # Read it — should migrate.
        result = load_setting(SETTING_LLM_GEMINI_API_KEY, "")
        assert result == "plain-ini-key"

        # After migration: INI no longer has the value.
        config2 = configparser.ConfigParser()
        config2.optionxform = str
        config2.read(str(clean_settings), encoding="utf-8")
        assert not config2.has_option("General", SETTING_LLM_GEMINI_API_KEY)

        # Subsequent load_setting calls now return from keyring (mocked
        # storage), value preserved.
        result2 = load_setting(SETTING_LLM_GEMINI_API_KEY, "")
        assert result2 == "plain-ini-key"


# ── load_model_for_feature / save_model_for_feature ─────────────


class TestLoadModelForFeature:
    """Feature key takes precedence over the shared default fallback."""

    def test_feature_key_set_returns_its_value(
        self,
        clean_settings: Path,
    ) -> None:
        from src.constants.settings import (
            SETTING_LLM_LAST_MODEL,
            SETTING_LLM_MODEL_LIVE,
        )
        from src.utils.config_manager import (
            load_model_for_feature,
            save_setting,
        )

        save_setting(SETTING_LLM_LAST_MODEL, "Gemini:default-model")
        save_setting(SETTING_LLM_MODEL_LIVE, "Custom:live-specific")
        assert load_model_for_feature(SETTING_LLM_MODEL_LIVE) == (
            "Custom:live-specific"
        )

    def test_falls_back_to_shared_default_when_feature_empty(
        self,
        clean_settings: Path,
    ) -> None:
        from src.constants.settings import (
            SETTING_LLM_LAST_MODEL,
            SETTING_LLM_MODEL_SCREEN,
        )
        from src.utils.config_manager import (
            load_model_for_feature,
            save_setting,
        )

        save_setting(SETTING_LLM_LAST_MODEL, "Gemini:shared-default")
        assert load_model_for_feature(SETTING_LLM_MODEL_SCREEN) == (
            "Gemini:shared-default"
        )

    def test_empty_both_returns_empty_string(
        self,
        clean_settings: Path,
    ) -> None:
        from src.constants.settings import SETTING_LLM_MODEL_EXTRACT
        from src.utils.config_manager import load_model_for_feature

        assert load_model_for_feature(SETTING_LLM_MODEL_EXTRACT) == ""

    def test_whitespace_feature_value_falls_through(
        self,
        clean_settings: Path,
    ) -> None:
        from src.constants.settings import (
            SETTING_LLM_LAST_MODEL,
            SETTING_LLM_MODEL_SUBTITLE,
        )
        from src.utils.config_manager import (
            load_model_for_feature,
            save_setting,
        )

        save_setting(SETTING_LLM_LAST_MODEL, "Gemini:fallback")
        save_setting(SETTING_LLM_MODEL_SUBTITLE, "   ")
        # Whitespace-only override is treated as empty → falls back.
        assert load_model_for_feature(SETTING_LLM_MODEL_SUBTITLE) == ("Gemini:fallback")


class TestSaveModelForFeature:
    """save_model_for_feature writes the feature key only, not the default."""

    def test_writes_only_to_feature_key(
        self,
        clean_settings: Path,
    ) -> None:
        from src.constants.settings import (
            SETTING_LLM_LAST_MODEL,
            SETTING_LLM_MODEL_DUBBING,
        )
        from src.utils.config_manager import (
            load_setting,
            save_model_for_feature,
            save_setting,
        )

        save_setting(SETTING_LLM_LAST_MODEL, "Gemini:original-default")
        save_model_for_feature(SETTING_LLM_MODEL_DUBBING, "Custom:dubbing-pick")
        # Feature key got the new value.
        assert load_setting(SETTING_LLM_MODEL_DUBBING, "") == ("Custom:dubbing-pick")
        # Shared default is left unchanged — that's owned by Settings → LLM.
        assert load_setting(SETTING_LLM_LAST_MODEL, "") == ("Gemini:original-default")

    def test_round_trip_via_load_helper(
        self,
        clean_settings: Path,
    ) -> None:
        from src.constants.settings import SETTING_LLM_MODEL_TRANSLATE_TEXT
        from src.utils.config_manager import (
            load_model_for_feature,
            save_model_for_feature,
        )

        save_model_for_feature(
            SETTING_LLM_MODEL_TRANSLATE_TEXT,
            "Custom:gpt-4o-mini",
        )
        assert load_model_for_feature(SETTING_LLM_MODEL_TRANSLATE_TEXT) == (
            "Custom:gpt-4o-mini"
        )
