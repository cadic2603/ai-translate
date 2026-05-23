"""Integration: each feature writes and reads its own LLM model independently.

Verifies the cross-feature invariants that matter to users:

* Picking a model in one feature does NOT silently change another's model.
* ``SETTING_LLM_LAST_MODEL`` (the shared default owned by Settings → LLM)
  is only written by the Settings tab — never by feature-page pickers.
* When a feature has no override, it falls through to the shared default.
* When neither is set, ``load_model_for_feature`` returns the empty
  string so the caller's ``_resolve_provider_model`` fallback kicks in.
"""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest

from src.constants.settings import (
    SETTING_LLM_LAST_MODEL,
    SETTING_LLM_MODEL_DUBBING,
    SETTING_LLM_MODEL_EXTRACT,
    SETTING_LLM_MODEL_LIVE,
    SETTING_LLM_MODEL_SCREEN,
    SETTING_LLM_MODEL_SUBTITLE,
    SETTING_LLM_MODEL_TRANSLATE_DOCUMENT,
    SETTING_LLM_MODEL_TRANSLATE_TEXT,
)
from src.utils.config_manager import (
    load_model_for_feature,
    load_setting,
    save_model_for_feature,
    save_setting,
)

_FEATURE_KEYS = [
    SETTING_LLM_MODEL_TRANSLATE_TEXT,
    SETTING_LLM_MODEL_TRANSLATE_DOCUMENT,
    SETTING_LLM_MODEL_SUBTITLE,
    SETTING_LLM_MODEL_DUBBING,
    SETTING_LLM_MODEL_LIVE,
    SETTING_LLM_MODEL_SCREEN,
    SETTING_LLM_MODEL_EXTRACT,
]


@pytest.fixture(autouse=True)
def mock_keyring(monkeypatch: pytest.MonkeyPatch) -> None:
    """Block real OS keyring access so secure settings round-trip in memory."""
    storage: dict[str, str] = {}
    monkeypatch.setattr(
        "keyring.set_password",
        lambda s, u, p: storage.__setitem__(f"{s}:{u}", p),
    )
    monkeypatch.setattr(
        "keyring.get_password",
        lambda s, u: storage.get(f"{s}:{u}"),
    )

    def _delete(s: str, u: str) -> None:
        key = f"{s}:{u}"
        if key in storage:
            del storage[key]
        else:
            from keyring.errors import PasswordDeleteError  # noqa: PLC0415

            raise PasswordDeleteError()

    monkeypatch.setattr("keyring.delete_password", _delete)


@pytest.fixture
def clean_settings(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[Path, None, None]:
    """Isolated settings.ini for each test so writes don't leak."""
    config_path = tmp_path / "settings.ini"
    monkeypatch.setattr(
        "src.utils.config_manager._get_config_path",
        lambda: config_path,
    )
    yield config_path


class TestPerFeatureModelIndependence:
    """Feature pickers never cross-contaminate each other or the default."""

    def test_each_feature_stores_independently(
        self,
        clean_settings: Path,
    ) -> None:
        """Seven features, seven distinct models, zero cross-contamination."""
        models = [f"Gemini:model-for-feature-{i}" for i in range(len(_FEATURE_KEYS))]
        for key, model in zip(_FEATURE_KEYS, models, strict=True):
            save_model_for_feature(key, model)
        for key, expected in zip(_FEATURE_KEYS, models, strict=True):
            assert load_setting(key, "") == expected

    def test_feature_write_does_not_touch_shared_default(
        self,
        clean_settings: Path,
    ) -> None:
        """Changing one feature's model does not update SETTING_LLM_LAST_MODEL."""
        save_setting(SETTING_LLM_LAST_MODEL, "Gemini:the-default")
        for key in _FEATURE_KEYS:
            save_model_for_feature(key, f"Custom:override-{key}")
            # Shared default is immutable from feature pickers.
            assert load_setting(SETTING_LLM_LAST_MODEL, "") == "Gemini:the-default"

    def test_feature_without_override_falls_back_to_default(
        self,
        clean_settings: Path,
    ) -> None:
        """An unset feature key resolves to the shared default via the helper."""
        save_setting(SETTING_LLM_LAST_MODEL, "Gemini:shared")
        for key in _FEATURE_KEYS:
            # No per-feature save — helper should surface the default.
            assert load_model_for_feature(key) == "Gemini:shared"

    def test_feature_override_wins_over_default(
        self,
        clean_settings: Path,
    ) -> None:
        """With both set, feature key wins; default only fills unsets."""
        save_setting(SETTING_LLM_LAST_MODEL, "Gemini:shared")
        save_model_for_feature(SETTING_LLM_MODEL_SCREEN, "Custom:screen-only")
        # Screen uses its own pick.
        assert load_model_for_feature(SETTING_LLM_MODEL_SCREEN) == (
            "Custom:screen-only"
        )
        # Unset features still see the shared default.
        for key in _FEATURE_KEYS:
            if key == SETTING_LLM_MODEL_SCREEN:
                continue
            assert load_model_for_feature(key) == "Gemini:shared"

    def test_returns_empty_when_no_default_and_no_override(
        self,
        clean_settings: Path,
    ) -> None:
        """With neither set, helper yields '' so caller's own fallback fires."""
        for key in _FEATURE_KEYS:
            assert load_model_for_feature(key) == ""


@pytest.mark.usefixtures("clean_settings")
class TestDefaultModelSavePath:
    """The Settings → LLM default combo is the one legitimate writer."""

    def test_default_combo_write_only_updates_shared_key(
        self,
        clean_settings: Path,
    ) -> None:
        """Simulate the Settings picker: it writes SETTING_LLM_LAST_MODEL directly."""
        save_setting(SETTING_LLM_LAST_MODEL, "Gemini:new-default")
        # No feature key got touched by the Settings write.
        for key in _FEATURE_KEYS:
            assert load_setting(key, "") == ""

    def test_new_feature_inherits_latest_default(
        self,
        clean_settings: Path,
    ) -> None:
        """After the user updates the default, features without overrides pick it up."""
        save_setting(SETTING_LLM_LAST_MODEL, "Gemini:v1")
        assert load_model_for_feature(SETTING_LLM_MODEL_LIVE) == "Gemini:v1"
        save_setting(SETTING_LLM_LAST_MODEL, "Gemini:v2")
        assert load_model_for_feature(SETTING_LLM_MODEL_LIVE) == "Gemini:v2"
