"""Tests for src.core.config — TranslationConfig dataclass."""

import dataclasses
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.core.config import TranslationConfig
from src.core.translator import (
    _build_output_name,
    _pipeline_finalize,
    _pipeline_run_ocr,
    _resolve_output_dir,
    run_translation_pipeline,
)

# ── Default values ──────────────────────────────────────────────────


class TestDefaults:
    """Default field values match expected fallbacks."""

    def test_storage_path_empty(self) -> None:
        cfg = TranslationConfig()
        assert cfg.storage_path == ""

    def test_ocr_method_tesseract(self) -> None:
        cfg = TranslationConfig()
        assert cfg.ocr_method == "Tesseract"

    def test_translate_doc_images_false(self) -> None:
        cfg = TranslationConfig()
        assert cfg.translate_doc_images is False

    def test_translate_doc_comments_false(self) -> None:
        cfg = TranslationConfig()
        assert cfg.translate_doc_comments is False

    def test_translate_doc_shapes_false(self) -> None:
        cfg = TranslationConfig()
        assert cfg.translate_doc_shapes is False

    def test_ocr_is_configured_false(self) -> None:
        cfg = TranslationConfig()
        assert cfg.ocr_is_configured is False

    def test_auto_convert_legacy_false(self) -> None:
        cfg = TranslationConfig()
        assert cfg.auto_convert_legacy is False

    def test_auto_convert_odf_false(self) -> None:
        cfg = TranslationConfig()
        assert cfg.auto_convert_odf is False

    def test_auto_remove_history_false(self) -> None:
        """Default is False (matches the other 4 page-level settings).

        Voice / Subtitle / Dubbing / Extract Text all default False,
        so history entries persist after a successful translation
        unless the user opts in.
        """
        cfg = TranslationConfig()
        assert cfg.auto_remove_history is False

    def test_libreoffice_path_empty(self) -> None:
        cfg = TranslationConfig()
        assert cfg.libreoffice_path == ""

    def test_translate_doc_notes_false(self) -> None:
        """translate_doc_notes defaults to False."""
        cfg = TranslationConfig()
        assert cfg.translate_doc_notes is False

    def test_translate_sheet_names_false(self) -> None:
        """translate_sheet_names defaults to False."""
        cfg = TranslationConfig()
        assert cfg.translate_sheet_names is False


# ── Frozen immutability ─────────────────────────────────────────────


class TestFrozen:
    """TranslationConfig is immutable after creation."""

    def test_cannot_set_field(self) -> None:
        cfg = TranslationConfig()
        with pytest.raises(AttributeError):
            cfg.ocr_method = "EasyOCR"  # type: ignore[misc]

    def test_cannot_delete_field(self) -> None:
        cfg = TranslationConfig()
        with pytest.raises(AttributeError):
            del cfg.ocr_method  # type: ignore[misc]

    def test_cannot_set_storage_path(self) -> None:
        """Cannot mutate storage_path after construction."""
        cfg = TranslationConfig(storage_path="/tmp/original")
        with pytest.raises(AttributeError):
            cfg.storage_path = "/tmp/changed"  # type: ignore[misc]

    def test_cannot_set_bool_field(self) -> None:
        """Cannot mutate boolean fields after construction."""
        cfg = TranslationConfig(translate_doc_images=True)
        with pytest.raises(AttributeError):
            cfg.translate_doc_images = False  # type: ignore[misc]

    def test_cannot_add_new_attribute(self) -> None:
        """Cannot add arbitrary attributes (slots=True + frozen)."""
        cfg = TranslationConfig()
        with pytest.raises((AttributeError, TypeError)):
            cfg.new_field = "value"  # type: ignore[attr-defined]

    def test_cannot_set_libreoffice_path(self) -> None:
        """Cannot mutate libreoffice_path after construction."""
        cfg = TranslationConfig(libreoffice_path="/usr/bin/lo")
        with pytest.raises(AttributeError):
            cfg.libreoffice_path = "/other/path"  # type: ignore[misc]


# ── should_translate_images property ────────────────────────────────


class TestShouldTranslateImages:
    """Computed property combining translate_doc_images and ocr_is_configured."""

    def test_both_true(self) -> None:
        cfg = TranslationConfig(translate_doc_images=True, ocr_is_configured=True)
        assert cfg.should_translate_images is True

    def test_images_true_ocr_false(self) -> None:
        cfg = TranslationConfig(translate_doc_images=True, ocr_is_configured=False)
        assert cfg.should_translate_images is False

    def test_images_false_ocr_true(self) -> None:
        cfg = TranslationConfig(translate_doc_images=False, ocr_is_configured=True)
        assert cfg.should_translate_images is False

    def test_both_false(self) -> None:
        cfg = TranslationConfig(translate_doc_images=False, ocr_is_configured=False)
        assert cfg.should_translate_images is False

    def test_default_is_false(self) -> None:
        """Default config has should_translate_images False."""
        cfg = TranslationConfig()
        assert cfg.should_translate_images is False

    def test_is_property_not_field(self) -> None:
        """should_translate_images is a property, not a dataclass field."""
        fields = {f.name for f in dataclasses.fields(TranslationConfig)}
        assert "should_translate_images" not in fields


# ── from_settings() ─────────────────────────────────────────────────


class TestFromSettings:
    """Bridge method reads load_setting() and check_ocr_setup() once."""

    @patch("src.utils.config_manager.check_ocr_setup", return_value=True)
    @patch(
        "src.utils.config_manager.load_setting",
        side_effect=lambda key, default="": {
            "app/storage_path": "/tmp/output",
            "ocr/method": "EasyOCR",
            "translation/translate_doc_images": True,
            "translation/translate_doc_comments": True,
            "translation/translate_doc_shapes": False,
            "translation/translate_doc_notes": True,
            "translation/translate_sheet_names": True,
            "translation/auto_convert_legacy": True,
            "translation/auto_convert_odf": False,
            "app/auto_remove_history": False,
            "office/libreoffice_path": "/usr/bin/libreoffice",
        }.get(key, default),
    )
    def test_reads_all_settings(self, _mock_load: object, _mock_ocr: object) -> None:
        cfg = TranslationConfig.from_settings()
        assert cfg.storage_path == "/tmp/output"
        assert cfg.ocr_method == "EasyOCR"
        assert cfg.translate_doc_images is True
        assert cfg.translate_doc_comments is True
        assert cfg.translate_doc_shapes is False
        assert cfg.translate_doc_notes is True
        assert cfg.translate_sheet_names is True
        assert cfg.ocr_is_configured is True
        assert cfg.auto_convert_legacy is True
        assert cfg.auto_convert_odf is False
        assert cfg.auto_remove_history is False
        assert cfg.libreoffice_path == "/usr/bin/libreoffice"

    @patch("src.utils.config_manager.check_ocr_setup", return_value=False)
    @patch(
        "src.utils.config_manager.load_setting",
        side_effect=lambda key, default="": default,
    )
    def test_ocr_not_configured(self, _mock_load: object, _mock_ocr: object) -> None:
        cfg = TranslationConfig.from_settings()
        assert cfg.ocr_is_configured is False
        assert cfg.should_translate_images is False

    @patch("src.utils.config_manager.check_ocr_setup", return_value=False)
    @patch(
        "src.utils.config_manager.load_setting",
        side_effect=lambda key, default="": default,
    )
    def test_uses_defaults_when_no_settings(
        self, _mock_load: object, _mock_ocr: object
    ) -> None:
        """When load_setting returns defaults, config matches TranslationConfig()."""
        cfg = TranslationConfig.from_settings()
        assert cfg.storage_path == ""
        assert cfg.auto_remove_history is False

    @patch("src.utils.config_manager.check_ocr_setup", return_value=True)
    @patch(
        "src.utils.config_manager.load_setting",
        side_effect=lambda key, default="": {
            "ocr/method": "Google Cloud OCR",
        }.get(key, default),
    )
    def test_google_cloud_ocr_method(
        self, _mock_load: object, _mock_ocr: object
    ) -> None:
        """from_settings reads Google Cloud OCR method."""
        cfg = TranslationConfig.from_settings()
        assert cfg.ocr_method == "Google Cloud OCR"
        assert cfg.ocr_is_configured is True

    @patch("src.utils.config_manager.check_ocr_setup", return_value=False)
    @patch(
        "src.utils.config_manager.load_setting",
        side_effect=lambda key, default="": {
            "translation/translate_doc_images": True,
        }.get(key, default),
    )
    def test_images_enabled_but_ocr_not_configured(
        self, _mock_load: object, _mock_ocr: object
    ) -> None:
        """Images enabled + OCR unconfigured => should_translate_images False."""
        cfg = TranslationConfig.from_settings()
        assert cfg.translate_doc_images is True
        assert cfg.ocr_is_configured is False
        assert cfg.should_translate_images is False

    @patch("src.utils.config_manager.check_ocr_setup", return_value=False)
    @patch(
        "src.utils.config_manager.load_setting",
        side_effect=lambda key, default="": {
            "translation/auto_convert_legacy": True,
            "translation/auto_convert_odf": True,
        }.get(key, default),
    )
    def test_both_auto_convert_enabled(
        self, _mock_load: object, _mock_ocr: object
    ) -> None:
        """Both auto_convert_legacy and auto_convert_odf can be True."""
        cfg = TranslationConfig.from_settings()
        assert cfg.auto_convert_legacy is True
        assert cfg.auto_convert_odf is True

    @patch("src.utils.config_manager.check_ocr_setup", return_value=False)
    @patch(
        "src.utils.config_manager.load_setting",
        side_effect=lambda key, default="": {
            "app/storage_path": "/custom/path/to/output",
            "office/libreoffice_path": "/opt/libreoffice/soffice",
        }.get(key, default),
    )
    def test_custom_paths(self, _mock_load: object, _mock_ocr: object) -> None:
        """Custom storage_path and libreoffice_path are read correctly."""
        cfg = TranslationConfig.from_settings()
        assert cfg.storage_path == "/custom/path/to/output"
        assert cfg.libreoffice_path == "/opt/libreoffice/soffice"

    @patch("src.utils.config_manager.check_ocr_setup", return_value=False)
    @patch(
        "src.utils.config_manager.load_setting",
        side_effect=lambda key, default="": {
            "translation/translate_doc_shapes": True,
            "translation/translate_doc_notes": True,
            "translation/translate_sheet_names": True,
        }.get(key, default),
    )
    def test_all_optional_features_enabled(
        self, _mock_load: object, _mock_ocr: object
    ) -> None:
        """Shapes, notes, and sheet_names can all be enabled."""
        cfg = TranslationConfig.from_settings()
        assert cfg.translate_doc_shapes is True
        assert cfg.translate_doc_notes is True
        assert cfg.translate_sheet_names is True

    @patch("src.utils.config_manager.check_ocr_setup", return_value=False)
    @patch(
        "src.utils.config_manager.load_setting",
        side_effect=lambda key, default="": default,
    )
    def test_load_setting_call_count(
        self, mock_load: MagicMock, _mock_ocr: object
    ) -> None:
        """from_settings calls load_setting once per setting key."""
        TranslationConfig.from_settings()
        # 13 setting keys are read via load_setting (ocr_is_configured is
        # derived, not loaded; llm_provider / llm_model are read as part of
        # the LLM-method resolution).
        assert mock_load.call_count == 12  # noqa: PLR2004

    @patch("src.utils.config_manager.check_ocr_setup", return_value=False)
    @patch(
        "src.utils.config_manager.load_setting",
        side_effect=lambda key, default="": default,
    )
    def test_check_ocr_setup_called_once(
        self, _mock_load: object, mock_ocr: MagicMock
    ) -> None:
        """from_settings calls check_ocr_setup exactly once."""
        TranslationConfig.from_settings()
        mock_ocr.assert_called_once()

    @patch("src.utils.config_manager.check_ocr_setup", return_value=False)
    @patch("src.utils.config_manager.load_model_for_feature")
    @patch(
        "src.utils.config_manager.load_setting",
        side_effect=lambda key, default="": default,
    )
    def test_feature_model_key_resolves_llm_model(
        self,
        _mock_load: object,
        mock_load_model: MagicMock,
        _mock_ocr: object,
    ) -> None:
        """from_settings can resolve a feature-specific LLM model key."""
        from src.constants.settings import SETTING_LLM_MODEL_TRANSLATE_DOCUMENT

        mock_load_model.return_value = "Custom:doc-model"

        cfg = TranslationConfig.from_settings(
            model_setting_key=SETTING_LLM_MODEL_TRANSLATE_DOCUMENT,
        )

        mock_load_model.assert_called_once_with(SETTING_LLM_MODEL_TRANSLATE_DOCUMENT)
        assert cfg.llm_provider == "Custom"
        assert cfg.llm_model == "doc-model"


# ── Custom construction ─────────────────────────────────────────────


class TestCustomConstruction:
    """Headless callers construct TranslationConfig directly."""

    def test_headless_config(self) -> None:
        cfg = TranslationConfig(
            ocr_method="EasyOCR",
            translate_doc_images=True,
            ocr_is_configured=True,
            storage_path="/tmp/translations",
        )
        assert cfg.ocr_method == "EasyOCR"
        assert cfg.should_translate_images is True
        assert cfg.storage_path == "/tmp/translations"

    def test_slots(self) -> None:
        """Frozen + slots prevents __dict__ attribute."""
        cfg = TranslationConfig()
        assert not hasattr(cfg, "__dict__")

    def test_all_custom_values(self) -> None:
        """Construct config with every field set to non-default values."""
        cfg = TranslationConfig(
            storage_path="/custom/storage",
            ocr_method="EasyOCR",
            translate_doc_images=True,
            translate_doc_comments=True,
            translate_doc_shapes=True,
            translate_doc_notes=True,
            translate_sheet_names=True,
            ocr_is_configured=True,
            auto_convert_legacy=True,
            auto_convert_odf=True,
            auto_remove_history=False,
            libreoffice_path="/usr/lib/libreoffice",
        )
        assert cfg.storage_path == "/custom/storage"
        assert cfg.ocr_method == "EasyOCR"
        assert cfg.translate_doc_images is True
        assert cfg.translate_doc_comments is True
        assert cfg.translate_doc_shapes is True
        assert cfg.translate_doc_notes is True
        assert cfg.translate_sheet_names is True
        assert cfg.ocr_is_configured is True
        assert cfg.auto_convert_legacy is True
        assert cfg.auto_convert_odf is True
        assert cfg.auto_remove_history is False
        assert cfg.libreoffice_path == "/usr/lib/libreoffice"

    def test_partial_custom_values(self) -> None:
        """Only some fields set; rest use defaults."""
        cfg = TranslationConfig(
            storage_path="/output",
            translate_doc_comments=True,
        )
        assert cfg.storage_path == "/output"
        assert cfg.translate_doc_comments is True
        # Defaults
        assert cfg.ocr_method == "Tesseract"
        assert cfg.translate_doc_images is False
        assert cfg.auto_remove_history is False

    def test_is_dataclass(self) -> None:
        """TranslationConfig is a proper dataclass."""
        assert dataclasses.is_dataclass(TranslationConfig)

    def test_is_frozen(self) -> None:
        """TranslationConfig is a frozen dataclass."""
        cfg = TranslationConfig()
        assert dataclasses.is_dataclass(cfg)
        with pytest.raises(AttributeError):
            cfg.ocr_method = "X"  # type: ignore[misc]

    def test_field_names(self) -> None:
        """All expected fields are present."""
        field_names = {f.name for f in dataclasses.fields(TranslationConfig)}
        expected = {
            "storage_path",
            "ocr_method",
            "translate_doc_images",
            "translate_doc_comments",
            "translate_doc_shapes",
            "translate_doc_notes",
            "translate_sheet_names",
            "ocr_is_configured",
            "auto_convert_legacy",
            "auto_convert_odf",
            "auto_remove_history",
            "libreoffice_path",
            "llm_provider",
            "llm_model",
        }
        assert field_names == expected

    def test_field_count(self) -> None:
        """TranslationConfig has exactly 14 fields."""
        assert len(dataclasses.fields(TranslationConfig)) == 14  # noqa: PLR2004


# ── Equality ────────────────────────────────────────────────────────


class TestEquality:
    """Frozen dataclasses support equality comparison by value."""

    def test_equal_defaults(self) -> None:
        """Two default configs are equal."""
        cfg1 = TranslationConfig()
        cfg2 = TranslationConfig()
        assert cfg1 == cfg2

    def test_equal_custom_values(self) -> None:
        """Two configs with identical custom values are equal."""
        kwargs = {
            "storage_path": "/tmp/out",
            "ocr_method": "EasyOCR",
            "translate_doc_images": True,
            "ocr_is_configured": True,
            "auto_remove_history": False,
        }
        cfg1 = TranslationConfig(**kwargs)
        cfg2 = TranslationConfig(**kwargs)
        assert cfg1 == cfg2

    def test_not_equal_different_storage_path(self) -> None:
        """Configs with different storage_path are not equal."""
        cfg1 = TranslationConfig(storage_path="/a")
        cfg2 = TranslationConfig(storage_path="/b")
        assert cfg1 != cfg2

    def test_not_equal_different_ocr_method(self) -> None:
        """Configs with different ocr_method are not equal."""
        cfg1 = TranslationConfig(ocr_method="Tesseract")
        cfg2 = TranslationConfig(ocr_method="EasyOCR")
        assert cfg1 != cfg2

    def test_not_equal_different_bool(self) -> None:
        """Configs with different boolean fields are not equal."""
        cfg1 = TranslationConfig(translate_doc_images=True)
        cfg2 = TranslationConfig(translate_doc_images=False)
        assert cfg1 != cfg2

    def test_not_equal_different_auto_remove(self) -> None:
        """Configs with different auto_remove_history are not equal."""
        cfg1 = TranslationConfig(auto_remove_history=True)
        cfg2 = TranslationConfig(auto_remove_history=False)
        assert cfg1 != cfg2

    def test_not_equal_to_non_config(self) -> None:
        """Config is not equal to non-TranslationConfig objects."""
        cfg = TranslationConfig()
        assert cfg != "not a config"
        assert cfg != 42
        assert cfg != None  # noqa: E711

    def test_hash_equal_for_equal_configs(self) -> None:
        """Equal frozen configs produce the same hash."""
        cfg1 = TranslationConfig(storage_path="/x")
        cfg2 = TranslationConfig(storage_path="/x")
        assert hash(cfg1) == hash(cfg2)

    def test_hash_different_for_different_configs(self) -> None:
        """Different configs generally produce different hashes."""
        cfg1 = TranslationConfig(storage_path="/x")
        cfg2 = TranslationConfig(storage_path="/y")
        # Not guaranteed but extremely likely
        assert hash(cfg1) != hash(cfg2)

    def test_usable_as_dict_key(self) -> None:
        """Frozen dataclass can be used as a dictionary key."""
        cfg = TranslationConfig(storage_path="/test")
        d = {cfg: "value"}
        assert d[cfg] == "value"

    def test_usable_in_set(self) -> None:
        """Frozen dataclass can be added to a set."""
        cfg1 = TranslationConfig()
        cfg2 = TranslationConfig()
        s = {cfg1, cfg2}
        assert len(s) == 1


# ── Config injection into pipeline functions ────────────────────────


class TestConfigInjection:
    """Pipeline functions respect injected config over load_setting()."""

    def test_pipeline_run_ocr_uses_config_ocr_method(self, tmp_path: Path) -> None:
        """_pipeline_run_ocr uses config.ocr_method instead of load_setting."""
        f = tmp_path / "test.png"
        f.touch()
        cfg = TranslationConfig(ocr_method="EasyOCR")
        mock_result = MagicMock(text="Hello")

        with patch(
            "src.core.translator._ocr_engine.run_ocr", return_value=[mock_result]
        ) as m:
            result = _pipeline_run_ocr(999, f, config=cfg)

        assert result is not None
        m.assert_called_once_with(str(f), method="EasyOCR", src_lang="")

    def test_resolve_output_dir_uses_config_storage_path(self, tmp_path: Path) -> None:
        """_resolve_output_dir uses config.storage_path instead of load_setting."""
        cfg = TranslationConfig(storage_path="/custom/output")
        result = _resolve_output_dir(config=cfg)
        assert result == Path("/custom/output")

    def test_pipeline_finalize_uses_config_auto_remove(self) -> None:
        """_pipeline_finalize uses config.auto_remove_history."""
        cfg = TranslationConfig(auto_remove_history=False)
        with (
            patch(
                "src.core.translator.get_history_entry_status",
                return_value="Translating",
            ),
            patch("src.core.translator.update_history_status") as m,
        ):
            _pipeline_finalize(1, config=cfg)

        # auto_remove=False + status=Translating → update to Done
        m.assert_called_once_with(1, "Done")

    def test_run_translation_pipeline_no_tasks(self) -> None:
        """Pipeline exits immediately when no pending tasks exist."""
        cfg = TranslationConfig()
        with (
            patch("src.core.translator.get_unfinished_history", return_value=[]),
            patch("src.core.translator.stop_soffice"),
        ):
            run_translation_pipeline(cfg)  # Should not raise

    def test_run_translation_pipeline_respects_is_cancelled(self) -> None:
        """Pipeline exits when is_cancelled returns True."""
        cfg = TranslationConfig()
        with patch("src.core.translator.stop_soffice"):
            run_translation_pipeline(cfg, is_cancelled=lambda: True)

    def test_resolve_output_dir_empty_config_falls_back_to_source(
        self, tmp_path: Path
    ) -> None:
        """Empty storage_path in config falls back to source file's directory."""
        cfg = TranslationConfig(storage_path="")
        source = tmp_path / "docs" / "file.txt"
        source.parent.mkdir(parents=True)
        source.touch()
        result = _resolve_output_dir(config=cfg, source_path=source)
        assert result == source.parent

    def test_resolve_output_dir_no_config_no_source_falls_to_desktop(self) -> None:
        """No config, no source path falls back to desktop path."""
        with (
            patch(
                "src.core.translator.load_setting",
                return_value="",
            ),
            patch(
                "src.utils.path_manager.get_desktop_path",
                return_value=Path("/home/user/Desktop"),
            ),
        ):
            result = _resolve_output_dir(config=None, source_path=None)
        assert result == Path("/home/user/Desktop")

    def test_resolve_output_dir_source_parent_does_not_exist(self) -> None:
        """Falls to desktop when source parent directory does not exist."""
        cfg = TranslationConfig(storage_path="")
        source = Path("/nonexistent/directory/file.txt")
        with patch(
            "src.utils.path_manager.get_desktop_path",
            return_value=Path("/home/user/Desktop"),
        ):
            result = _resolve_output_dir(config=cfg, source_path=source)
        assert result == Path("/home/user/Desktop")

    def test_pipeline_finalize_auto_remove_true_deletes(self) -> None:
        """auto_remove_history=True + status=Translating → delete entry."""
        cfg = TranslationConfig(auto_remove_history=True)
        with (
            patch(
                "src.core.translator.get_history_entry_status",
                return_value="Translating",
            ),
            patch(
                "src.core.translator.delete_history_entry",
                return_value="/some/path",
            ) as mock_del,
            patch("src.core.translator.wipe_history_directory") as mock_wipe,
        ):
            _pipeline_finalize(1, config=cfg)

        mock_del.assert_called_once_with(1)
        mock_wipe.assert_called_once_with("/some/path")

    def test_pipeline_finalize_failed_status_not_removed(self) -> None:
        """auto_remove_history=True + status=Failed → no delete, no status update."""
        cfg = TranslationConfig(auto_remove_history=True)
        with (
            patch(
                "src.core.translator.get_history_entry_status",
                return_value="Failed",
            ),
            patch("src.core.translator.delete_history_entry") as mock_del,
            patch("src.core.translator.update_history_status") as mock_update,
        ):
            _pipeline_finalize(1, config=cfg)

        mock_del.assert_not_called()
        mock_update.assert_not_called()

    def test_pipeline_finalize_done_status_skipped(self) -> None:
        """Status already 'Done' means finalize does nothing."""
        cfg = TranslationConfig(auto_remove_history=False)
        with (
            patch(
                "src.core.translator.get_history_entry_status",
                return_value="Done",
            ),
            patch("src.core.translator.delete_history_entry") as mock_del,
            patch("src.core.translator.update_history_status") as mock_update,
        ):
            _pipeline_finalize(1, config=cfg)

        mock_del.assert_not_called()
        mock_update.assert_not_called()

    def test_pipeline_finalize_paused_status_skipped(self) -> None:
        """Status 'Paused' means finalize does nothing."""
        cfg = TranslationConfig(auto_remove_history=True)
        with (
            patch(
                "src.core.translator.get_history_entry_status",
                return_value="Paused",
            ),
            patch("src.core.translator.delete_history_entry") as mock_del,
            patch("src.core.translator.update_history_status") as mock_update,
        ):
            _pipeline_finalize(1, config=cfg)

        mock_del.assert_not_called()
        mock_update.assert_not_called()

    def test_build_output_name_uses_locale_codes(self) -> None:
        """_build_output_name converts language labels to locale codes."""
        result = _build_output_name(Path("report.docx"), "English (US)", "Vietnamese")
        assert result == "report_translated_en-US_vi.docx"

    def test_build_output_name_preserves_suffix(self) -> None:
        """Output name preserves the original file extension."""
        result = _build_output_name(Path("data.xlsx"), "French", "German")
        assert result == "data_translated_fr_de.xlsx"


# =====================================================================
# EXPANDED TESTS — TranslationConfig dataclass
# =====================================================================


class TestTranslationConfigRepr:
    """Tests for TranslationConfig repr, str, and introspection."""

    def test_repr_contains_class_name(self) -> None:
        """Repr includes 'TranslationConfig'."""
        cfg = TranslationConfig()
        assert "TranslationConfig" in repr(cfg)

    def test_repr_contains_field_values(self) -> None:
        """Repr includes field values."""
        cfg = TranslationConfig(storage_path="/test")
        assert "/test" in repr(cfg)

    def test_str_equals_repr(self) -> None:
        """Str and repr are the same for frozen dataclasses."""
        cfg = TranslationConfig()
        assert str(cfg) == repr(cfg)

    def test_no_dict_attribute(self) -> None:
        """Slots=True prevents __dict__."""
        cfg = TranslationConfig()
        assert not hasattr(cfg, "__dict__")

    def test_has_slots(self) -> None:
        """TranslationConfig has __slots__."""
        assert hasattr(TranslationConfig, "__slots__")


class TestTranslationConfigDefaults2:
    """Additional default value edge cases."""

    def test_all_bool_defaults_are_bool_type(self) -> None:
        """All bool fields default to actual bool values."""
        cfg = TranslationConfig()
        for field in dataclasses.fields(cfg):
            if isinstance(field.default, bool):
                val = getattr(cfg, field.name)
                assert isinstance(val, bool), f"{field.name} is not bool"

    def test_all_str_defaults_are_str_type(self) -> None:
        """All str fields default to actual str values."""
        cfg = TranslationConfig()
        for field in dataclasses.fields(cfg):
            if isinstance(field.default, str):
                val = getattr(cfg, field.name)
                assert isinstance(val, str), f"{field.name} is not str"


class TestFrozenExtended:
    """Additional frozen immutability tests."""

    def test_cannot_set_translate_doc_comments(self) -> None:
        """Cannot mutate translate_doc_comments."""
        cfg = TranslationConfig()
        with pytest.raises(AttributeError):
            cfg.translate_doc_comments = True  # type: ignore[misc]

    def test_cannot_set_translate_doc_shapes(self) -> None:
        """Cannot mutate translate_doc_shapes."""
        cfg = TranslationConfig()
        with pytest.raises(AttributeError):
            cfg.translate_doc_shapes = True  # type: ignore[misc]

    def test_cannot_set_translate_doc_notes(self) -> None:
        """Cannot mutate translate_doc_notes."""
        cfg = TranslationConfig()
        with pytest.raises(AttributeError):
            cfg.translate_doc_notes = True  # type: ignore[misc]

    def test_cannot_set_translate_sheet_names(self) -> None:
        """Cannot mutate translate_sheet_names."""
        cfg = TranslationConfig()
        with pytest.raises(AttributeError):
            cfg.translate_sheet_names = True  # type: ignore[misc]

    def test_cannot_set_ocr_is_configured(self) -> None:
        """Cannot mutate ocr_is_configured."""
        cfg = TranslationConfig()
        with pytest.raises(AttributeError):
            cfg.ocr_is_configured = True  # type: ignore[misc]

    def test_cannot_set_auto_convert_legacy(self) -> None:
        """Cannot mutate auto_convert_legacy."""
        cfg = TranslationConfig()
        with pytest.raises(AttributeError):
            cfg.auto_convert_legacy = True  # type: ignore[misc]

    def test_cannot_set_auto_convert_odf(self) -> None:
        """Cannot mutate auto_convert_odf."""
        cfg = TranslationConfig()
        with pytest.raises(AttributeError):
            cfg.auto_convert_odf = True  # type: ignore[misc]

    def test_cannot_set_auto_remove_history(self) -> None:
        """Cannot mutate auto_remove_history."""
        cfg = TranslationConfig()
        with pytest.raises(AttributeError):
            cfg.auto_remove_history = False  # type: ignore[misc]

    def test_cannot_set_translate_doc_images(self) -> None:
        """Cannot mutate translate_doc_images."""
        cfg = TranslationConfig()
        with pytest.raises(AttributeError):
            cfg.translate_doc_images = True  # type: ignore[misc]

    def test_cannot_set_ocr_method(self) -> None:
        """Cannot mutate ocr_method."""
        cfg = TranslationConfig()
        with pytest.raises(AttributeError):
            cfg.ocr_method = "NewOCR"  # type: ignore[misc]


class TestShouldTranslateImagesExtended:
    """Extended tests for should_translate_images property."""

    def test_property_descriptor(self) -> None:
        """should_translate_images is a property on the class."""
        assert isinstance(
            TranslationConfig.__dict__["should_translate_images"], property
        )

    def test_with_custom_ocr_method_both_true(self) -> None:
        """should_translate_images with EasyOCR and both True."""
        cfg = TranslationConfig(
            ocr_method="EasyOCR",
            translate_doc_images=True,
            ocr_is_configured=True,
        )
        assert cfg.should_translate_images is True

    def test_with_custom_ocr_method_images_false(self) -> None:
        """should_translate_images False when images disabled even with OCR."""
        cfg = TranslationConfig(
            ocr_method="EasyOCR",
            translate_doc_images=False,
            ocr_is_configured=True,
        )
        assert cfg.should_translate_images is False


class TestFromSettingsExtended:
    """Extended tests for from_settings()."""

    @patch("src.utils.config_manager.check_ocr_setup", return_value=False)
    @patch(
        "src.utils.config_manager.load_setting",
        side_effect=lambda key, default="": {
            "translation/translate_doc_comments": True,
            "translation/translate_doc_shapes": True,
        }.get(key, default),
    )
    def test_comments_and_shapes_enabled(
        self, _mock_load: object, _mock_ocr: object
    ) -> None:
        """Both comments and shapes can be enabled from settings."""
        cfg = TranslationConfig.from_settings()
        assert cfg.translate_doc_comments is True
        assert cfg.translate_doc_shapes is True

    @patch("src.utils.config_manager.check_ocr_setup", return_value=True)
    @patch(
        "src.utils.config_manager.load_setting",
        side_effect=lambda key, default="": {
            "ocr/method": "Tesseract",
            "translation/translate_doc_images": True,
        }.get(key, default),
    )
    def test_should_translate_images_true_from_settings(
        self, _mock_load: object, _mock_ocr: object
    ) -> None:
        """from_settings can produce should_translate_images=True."""
        cfg = TranslationConfig.from_settings()
        assert cfg.should_translate_images is True

    @patch("src.utils.config_manager.check_ocr_setup", return_value=False)
    @patch(
        "src.utils.config_manager.load_setting",
        side_effect=lambda key, default="": {
            "app/auto_remove_history": False,
        }.get(key, default),
    )
    def test_auto_remove_false_from_settings(
        self, _mock_load: object, _mock_ocr: object
    ) -> None:
        """auto_remove_history=False from settings."""
        cfg = TranslationConfig.from_settings()
        assert cfg.auto_remove_history is False

    @patch("src.utils.config_manager.check_ocr_setup", return_value=False)
    @patch(
        "src.utils.config_manager.load_setting",
        side_effect=lambda key, default="": {
            "office/libreoffice_path": "",
        }.get(key, default),
    )
    def test_empty_libreoffice_path(
        self, _mock_load: object, _mock_ocr: object
    ) -> None:
        """Empty libreoffice_path from settings."""
        cfg = TranslationConfig.from_settings()
        assert cfg.libreoffice_path == ""

    @patch("src.utils.config_manager.check_ocr_setup", return_value=False)
    @patch(
        "src.utils.config_manager.load_setting",
        side_effect=lambda key, default="": {
            "translation/auto_convert_legacy": True,
        }.get(key, default),
    )
    def test_auto_convert_legacy_only(
        self, _mock_load: object, _mock_ocr: object
    ) -> None:
        """Only auto_convert_legacy enabled."""
        cfg = TranslationConfig.from_settings()
        assert cfg.auto_convert_legacy is True
        assert cfg.auto_convert_odf is False

    @patch("src.utils.config_manager.check_ocr_setup", return_value=False)
    @patch(
        "src.utils.config_manager.load_setting",
        side_effect=lambda key, default="": {
            "translation/auto_convert_odf": True,
        }.get(key, default),
    )
    def test_auto_convert_odf_only(self, _mock_load: object, _mock_ocr: object) -> None:
        """Only auto_convert_odf enabled."""
        cfg = TranslationConfig.from_settings()
        assert cfg.auto_convert_legacy is False
        assert cfg.auto_convert_odf is True

    @patch("src.utils.config_manager.check_ocr_setup", return_value=False)
    @patch(
        "src.utils.config_manager.load_setting",
        side_effect=lambda key, default="": {
            "translation/translate_sheet_names": True,
        }.get(key, default),
    )
    def test_sheet_names_enabled(self, _mock_load: object, _mock_ocr: object) -> None:
        """translate_sheet_names can be True from settings."""
        cfg = TranslationConfig.from_settings()
        assert cfg.translate_sheet_names is True

    @patch("src.utils.config_manager.check_ocr_setup", return_value=False)
    @patch(
        "src.utils.config_manager.load_setting",
        side_effect=lambda key, default="": {
            "translation/translate_doc_notes": True,
        }.get(key, default),
    )
    def test_doc_notes_enabled(self, _mock_load: object, _mock_ocr: object) -> None:
        """translate_doc_notes can be True from settings."""
        cfg = TranslationConfig.from_settings()
        assert cfg.translate_doc_notes is True


class TestCustomConstructionExtended:
    """Extended tests for direct construction."""

    def test_construct_with_only_storage_path(self) -> None:
        """Only storage_path set; rest default."""
        cfg = TranslationConfig(storage_path="/output")
        assert cfg.storage_path == "/output"
        assert cfg.ocr_method == "Tesseract"
        assert cfg.translate_doc_images is False

    def test_construct_with_only_ocr_method(self) -> None:
        """Only ocr_method set; rest default."""
        cfg = TranslationConfig(ocr_method="EasyOCR")
        assert cfg.ocr_method == "EasyOCR"
        assert cfg.storage_path == ""

    def test_construct_with_only_translate_doc_images(self) -> None:
        """Only translate_doc_images set; rest default."""
        cfg = TranslationConfig(translate_doc_images=True)
        assert cfg.translate_doc_images is True
        assert cfg.ocr_is_configured is False
        assert cfg.should_translate_images is False

    def test_construct_with_only_ocr_is_configured(self) -> None:
        """Only ocr_is_configured set; rest default."""
        cfg = TranslationConfig(ocr_is_configured=True)
        assert cfg.ocr_is_configured is True
        assert cfg.translate_doc_images is False
        assert cfg.should_translate_images is False

    def test_construct_with_only_auto_remove_history_false(self) -> None:
        """Setting auto_remove_history to False."""
        cfg = TranslationConfig(auto_remove_history=False)
        assert cfg.auto_remove_history is False

    def test_construct_with_only_libreoffice_path(self) -> None:
        """Only libreoffice_path set."""
        cfg = TranslationConfig(libreoffice_path="/usr/bin/soffice")
        assert cfg.libreoffice_path == "/usr/bin/soffice"

    def test_construct_with_only_auto_convert_legacy(self) -> None:
        """Only auto_convert_legacy set."""
        cfg = TranslationConfig(auto_convert_legacy=True)
        assert cfg.auto_convert_legacy is True
        assert cfg.auto_convert_odf is False

    def test_construct_with_only_auto_convert_odf(self) -> None:
        """Only auto_convert_odf set."""
        cfg = TranslationConfig(auto_convert_odf=True)
        assert cfg.auto_convert_odf is True
        assert cfg.auto_convert_legacy is False

    def test_construct_with_all_features_on(self) -> None:
        """All translatable features enabled."""
        cfg = TranslationConfig(
            translate_doc_images=True,
            translate_doc_comments=True,
            translate_doc_shapes=True,
            translate_doc_notes=True,
            translate_sheet_names=True,
            ocr_is_configured=True,
            auto_convert_legacy=True,
            auto_convert_odf=True,
        )
        assert cfg.should_translate_images is True
        assert cfg.translate_doc_comments is True
        assert cfg.translate_doc_shapes is True
        assert cfg.translate_doc_notes is True
        assert cfg.translate_sheet_names is True

    def test_construct_with_all_features_off(self) -> None:
        """All translatable features disabled."""
        cfg = TranslationConfig(
            translate_doc_images=False,
            translate_doc_comments=False,
            translate_doc_shapes=False,
            translate_doc_notes=False,
            translate_sheet_names=False,
            ocr_is_configured=False,
            auto_convert_legacy=False,
            auto_convert_odf=False,
            auto_remove_history=False,
        )
        assert cfg.should_translate_images is False
        assert cfg.translate_doc_comments is False
        assert cfg.auto_remove_history is False


class TestEqualityExtended:
    """Extended equality and hashing tests."""

    def test_not_equal_different_translate_doc_shapes(self) -> None:
        """Configs with different translate_doc_shapes are not equal."""
        cfg1 = TranslationConfig(translate_doc_shapes=True)
        cfg2 = TranslationConfig(translate_doc_shapes=False)
        assert cfg1 != cfg2

    def test_not_equal_different_translate_doc_notes(self) -> None:
        """Configs with different translate_doc_notes are not equal."""
        cfg1 = TranslationConfig(translate_doc_notes=True)
        cfg2 = TranslationConfig(translate_doc_notes=False)
        assert cfg1 != cfg2

    def test_not_equal_different_translate_sheet_names(self) -> None:
        """Configs with different translate_sheet_names are not equal."""
        cfg1 = TranslationConfig(translate_sheet_names=True)
        cfg2 = TranslationConfig(translate_sheet_names=False)
        assert cfg1 != cfg2

    def test_not_equal_different_auto_convert_legacy(self) -> None:
        """Configs with different auto_convert_legacy are not equal."""
        cfg1 = TranslationConfig(auto_convert_legacy=True)
        cfg2 = TranslationConfig(auto_convert_legacy=False)
        assert cfg1 != cfg2

    def test_not_equal_different_auto_convert_odf(self) -> None:
        """Configs with different auto_convert_odf are not equal."""
        cfg1 = TranslationConfig(auto_convert_odf=True)
        cfg2 = TranslationConfig(auto_convert_odf=False)
        assert cfg1 != cfg2

    def test_not_equal_different_libreoffice_path(self) -> None:
        """Configs with different libreoffice_path are not equal."""
        cfg1 = TranslationConfig(libreoffice_path="/a")
        cfg2 = TranslationConfig(libreoffice_path="/b")
        assert cfg1 != cfg2

    def test_not_equal_different_ocr_is_configured(self) -> None:
        """Configs with different ocr_is_configured are not equal."""
        cfg1 = TranslationConfig(ocr_is_configured=True)
        cfg2 = TranslationConfig(ocr_is_configured=False)
        assert cfg1 != cfg2

    def test_not_equal_different_translate_doc_comments(self) -> None:
        """Configs with different translate_doc_comments are not equal."""
        cfg1 = TranslationConfig(translate_doc_comments=True)
        cfg2 = TranslationConfig(translate_doc_comments=False)
        assert cfg1 != cfg2

    def test_hash_works_for_all_fields_combination(self) -> None:
        """Two identical configs with all fields non-default produce same hash."""
        kwargs = {
            "storage_path": "/x",
            "ocr_method": "EasyOCR",
            "translate_doc_images": True,
            "translate_doc_comments": True,
            "translate_doc_shapes": True,
            "translate_doc_notes": True,
            "translate_sheet_names": True,
            "ocr_is_configured": True,
            "auto_convert_legacy": True,
            "auto_convert_odf": True,
            "auto_remove_history": False,
            "libreoffice_path": "/lo",
        }
        cfg1 = TranslationConfig(**kwargs)
        cfg2 = TranslationConfig(**kwargs)
        assert hash(cfg1) == hash(cfg2)

    def test_set_deduplication(self) -> None:
        """Duplicate configs in a set are deduplicated."""
        cfg1 = TranslationConfig(storage_path="/a")
        cfg2 = TranslationConfig(storage_path="/a")
        cfg3 = TranslationConfig(storage_path="/b")
        s = {cfg1, cfg2, cfg3}
        assert len(s) == 2  # noqa: PLR2004

    def test_not_equal_to_list(self) -> None:
        """Config is not equal to a list."""
        cfg = TranslationConfig()
        assert cfg != []

    def test_not_equal_to_dict(self) -> None:
        """Config is not equal to a dict."""
        cfg = TranslationConfig()
        assert cfg != {}


class TestDataclassUtilities:
    """Tests for dataclass utility functions with TranslationConfig."""

    def test_asdict(self) -> None:
        """dataclasses.asdict produces a dict with all fields."""
        cfg = TranslationConfig(storage_path="/test")
        d = dataclasses.asdict(cfg)
        assert isinstance(d, dict)
        assert d["storage_path"] == "/test"
        assert d["ocr_method"] == "Tesseract"

    def test_astuple(self) -> None:
        """dataclasses.astuple produces a tuple."""
        cfg = TranslationConfig()
        t = dataclasses.astuple(cfg)
        assert isinstance(t, tuple)
        assert len(t) == 14  # noqa: PLR2004

    def test_replace(self) -> None:
        """dataclasses.replace creates a modified copy."""
        cfg = TranslationConfig(storage_path="/original")
        new_cfg = dataclasses.replace(cfg, storage_path="/modified")
        assert new_cfg.storage_path == "/modified"
        assert cfg.storage_path == "/original"  # Original unchanged

    def test_replace_preserves_other_fields(self) -> None:
        """dataclasses.replace only changes specified fields."""
        cfg = TranslationConfig(
            storage_path="/orig",
            ocr_method="EasyOCR",
            translate_doc_images=True,
        )
        new_cfg = dataclasses.replace(cfg, storage_path="/new")
        assert new_cfg.ocr_method == "EasyOCR"
        assert new_cfg.translate_doc_images is True

    def test_replace_multiple_fields(self) -> None:
        """dataclasses.replace can change multiple fields at once."""
        cfg = TranslationConfig()
        new_cfg = dataclasses.replace(
            cfg,
            storage_path="/new",
            ocr_method="EasyOCR",
            auto_remove_history=False,
        )
        assert new_cfg.storage_path == "/new"
        assert new_cfg.ocr_method == "EasyOCR"
        assert new_cfg.auto_remove_history is False

    def test_field_defaults(self) -> None:
        """Field defaults match the expected values."""
        fields = {f.name: f.default for f in dataclasses.fields(TranslationConfig)}
        assert fields["storage_path"] == ""
        assert fields["ocr_method"] == "Tesseract"
        assert fields["translate_doc_images"] is False
        assert fields["translate_doc_comments"] is False
        assert fields["translate_doc_shapes"] is False
        assert fields["translate_doc_notes"] is False
        assert fields["translate_sheet_names"] is False
        assert fields["ocr_is_configured"] is False
        assert fields["auto_convert_legacy"] is False
        assert fields["auto_convert_odf"] is False
        assert fields["auto_remove_history"] is False
        assert fields["libreoffice_path"] == ""

    def test_field_types(self) -> None:
        """Field types are str or bool."""
        for field in dataclasses.fields(TranslationConfig):
            assert field.type in (str, bool, "str", "bool"), (
                f"{field.name} has type {field.type}"
            )


class TestConfigInjectionExtended:
    """Extended pipeline config injection tests."""

    def test_pipeline_run_ocr_no_config_uses_load_setting(
        self,
        tmp_path: Path,
    ) -> None:
        """_pipeline_run_ocr with config=None reads ocr_method from settings."""
        f = tmp_path / "img.png"
        f.touch()
        mock_result = MagicMock(text="test")

        with (
            patch(
                "src.core.translator.load_setting",
                return_value="Google Cloud OCR",
            ),
            patch(
                "src.core.translator._ocr_engine.run_ocr", return_value=[mock_result]
            ) as m,
        ):
            _pipeline_run_ocr(1, f, config=None)

        m.assert_called_once_with(str(f), method="Google Cloud OCR", src_lang="")

    def test_resolve_output_dir_config_priority_over_source(
        self,
        tmp_path: Path,
    ) -> None:
        """Config storage_path takes priority over source path parent."""
        cfg = TranslationConfig(storage_path="/config/output")
        source = tmp_path / "file.txt"
        source.touch()
        result = _resolve_output_dir(config=cfg, source_path=source)
        assert result == Path("/config/output")

    def test_pipeline_finalize_auto_remove_true_failed_status(self) -> None:
        """auto_remove=True + Failed status does not delete or update."""
        cfg = TranslationConfig(auto_remove_history=True)
        with (
            patch(
                "src.core.translator.get_history_entry_status",
                return_value="Failed",
            ),
            patch("src.core.translator.delete_history_entry") as mock_del,
            patch("src.core.translator.update_history_status") as mock_update,
        ):
            _pipeline_finalize(1, config=cfg)
        mock_del.assert_not_called()
        mock_update.assert_not_called()

    def test_build_output_name_english_uk_to_vietnamese(self) -> None:
        """English (UK) to Vietnamese produces correct locale codes."""
        result = _build_output_name(Path("doc.pdf"), "English (UK)", "Vietnamese")
        assert result == "doc_translated_en-UK_vi.pdf"

    def test_build_output_name_korean_to_japanese(self) -> None:
        """Korean to Japanese produces correct locale codes."""
        result = _build_output_name(Path("file.txt"), "Korean", "Japanese")
        assert result == "file_translated_ko_ja.txt"

    def test_build_output_name_italian_to_spanish(self) -> None:
        """Italian to Spanish produces correct locale codes."""
        result = _build_output_name(Path("file.docx"), "Italian", "Spanish")
        assert result == "file_translated_it_es.docx"

    def test_run_pipeline_exits_on_empty_db(self) -> None:
        """Pipeline exits immediately with no pending tasks."""
        cfg = TranslationConfig()
        with (
            patch("src.core.translator.get_unfinished_history", return_value=[]),
            patch("src.core.translator.stop_soffice"),
        ):
            run_translation_pipeline(cfg)
        # No crash — just exits

    def test_resolve_output_dir_with_tilde_path(self) -> None:
        """Config with tilde path is returned as-is."""
        cfg = TranslationConfig(storage_path="~/Documents/output")
        result = _resolve_output_dir(config=cfg)
        assert result == Path("~/Documents/output")


# =====================================================================
# EXPANDED TESTS — Parametrized field mutation tests
# =====================================================================


class TestFrozenAllFields:
    """Test immutability for every field via parameterized tests."""

    @pytest.mark.parametrize(
        ("field_name", "value"),
        [
            ("storage_path", "/new"),
            ("ocr_method", "EasyOCR"),
            ("translate_doc_images", True),
            ("translate_doc_comments", True),
            ("translate_doc_shapes", True),
            ("translate_doc_notes", True),
            ("translate_sheet_names", True),
            ("ocr_is_configured", True),
            ("auto_convert_legacy", True),
            ("auto_convert_odf", True),
            ("auto_remove_history", False),
            ("libreoffice_path", "/new/path"),
        ],
    )
    def test_field_immutable(self, field_name: str, value: object) -> None:
        """Every field raises AttributeError when set after construction."""
        cfg = TranslationConfig()
        with pytest.raises(AttributeError):
            setattr(cfg, field_name, value)


class TestEqualityParametrized:
    """Parametrized equality/inequality tests."""

    @pytest.mark.parametrize(
        ("field_name", "val1", "val2"),
        [
            ("storage_path", "/a", "/b"),
            ("ocr_method", "Tesseract", "EasyOCR"),
            ("translate_doc_images", True, False),
            ("translate_doc_comments", True, False),
            ("translate_doc_shapes", True, False),
            ("translate_doc_notes", True, False),
            ("translate_sheet_names", True, False),
            ("ocr_is_configured", True, False),
            ("auto_convert_legacy", True, False),
            ("auto_convert_odf", True, False),
            ("auto_remove_history", False, True),
            ("libreoffice_path", "/a", "/b"),
        ],
    )
    def test_different_single_field_not_equal(
        self,
        field_name: str,
        val1: object,
        val2: object,
    ) -> None:
        """Configs differing in one field are not equal."""
        cfg1 = TranslationConfig(**{field_name: val1})
        cfg2 = TranslationConfig(**{field_name: val2})
        assert cfg1 != cfg2


class TestReplaceParametrized:
    """Parametrized replace tests for all fields."""

    @pytest.mark.parametrize(
        ("field_name", "original", "replacement"),
        [
            ("storage_path", "", "/new/path"),
            ("ocr_method", "Tesseract", "EasyOCR"),
            ("translate_doc_images", False, True),
            ("translate_doc_comments", False, True),
            ("translate_doc_shapes", False, True),
            ("translate_doc_notes", False, True),
            ("translate_sheet_names", False, True),
            ("ocr_is_configured", False, True),
            ("auto_convert_legacy", False, True),
            ("auto_convert_odf", False, True),
            ("auto_remove_history", False, True),
            ("libreoffice_path", "", "/usr/bin/lo"),
        ],
    )
    def test_replace_single_field(
        self,
        field_name: str,
        original: object,
        replacement: object,
    ) -> None:
        """dataclasses.replace on each field produces correct result."""
        cfg = TranslationConfig()
        assert getattr(cfg, field_name) == original
        new_cfg = dataclasses.replace(cfg, **{field_name: replacement})
        assert getattr(new_cfg, field_name) == replacement
        # Original is unchanged
        assert getattr(cfg, field_name) == original


class TestFromSettingsEdgeCases:
    """Edge cases for from_settings()."""

    @patch("src.utils.config_manager.check_ocr_setup", return_value=True)
    @patch(
        "src.utils.config_manager.load_setting",
        side_effect=lambda key, default="": {
            "ocr/method": "EasyOCR",
            "translation/translate_doc_images": True,
        }.get(key, default),
    )
    def test_easyocr_with_images_enabled(
        self,
        _mock_load: object,
        _mock_ocr: object,
    ) -> None:
        """EasyOCR + images enabled + OCR configured = should_translate_images True."""
        cfg = TranslationConfig.from_settings()
        assert cfg.ocr_method == "EasyOCR"
        assert cfg.should_translate_images is True

    @patch("src.utils.config_manager.check_ocr_setup", return_value=False)
    @patch(
        "src.utils.config_manager.load_setting",
        side_effect=lambda key, default="": default,
    )
    def test_all_defaults_from_settings(
        self,
        _mock_load: object,
        _mock_ocr: object,
    ) -> None:
        """from_settings with all defaults produces expected config.

        Note: OCR_METHOD_TESSERACT constant is 'TesseractOCR', while the
        dataclass default is 'Tesseract'. from_settings() reads the constant,
        so the ocr_method differs from TranslationConfig().
        """
        cfg = TranslationConfig.from_settings()
        # OCR method defaults to OCR_METHOD_TESSERACT = "TesseractOCR"
        assert cfg.ocr_method == "TesseractOCR"
        # Other fields match default constructor
        assert cfg.storage_path == ""
        assert cfg.auto_remove_history is False
        assert cfg.translate_doc_images is False

    @patch("src.utils.config_manager.check_ocr_setup", return_value=False)
    @patch(
        "src.utils.config_manager.load_setting",
        side_effect=lambda key, default="": {
            "app/storage_path": "/tmp/custom",
            "ocr/method": "Google Cloud OCR",
            "translation/translate_doc_images": True,
            "translation/translate_doc_comments": True,
            "translation/translate_doc_shapes": True,
            "translation/translate_doc_notes": True,
            "translation/translate_sheet_names": True,
            "translation/auto_convert_legacy": True,
            "translation/auto_convert_odf": True,
            "app/auto_remove_history": False,
            "office/libreoffice_path": "/opt/lo",
        }.get(key, default),
    )
    def test_all_fields_non_default(
        self,
        _mock_load: object,
        _mock_ocr: object,
    ) -> None:
        """All fields can be set to non-default from settings."""
        cfg = TranslationConfig.from_settings()
        assert cfg.storage_path == "/tmp/custom"
        assert cfg.ocr_method == "Google Cloud OCR"
        assert cfg.translate_doc_images is True
        assert cfg.translate_doc_comments is True
        assert cfg.translate_doc_shapes is True
        assert cfg.translate_doc_notes is True
        assert cfg.translate_sheet_names is True
        assert cfg.auto_convert_legacy is True
        assert cfg.auto_convert_odf is True
        assert cfg.auto_remove_history is False
        assert cfg.libreoffice_path == "/opt/lo"
        assert cfg.ocr_is_configured is False
        # Images disabled because OCR not configured
        assert cfg.should_translate_images is False


class TestConfigCopying:
    """Tests for copying TranslationConfig instances."""

    def test_copy_via_replace(self) -> None:
        """Copy via replace with no changes produces equal config."""
        cfg = TranslationConfig(storage_path="/test", auto_remove_history=False)
        copy = dataclasses.replace(cfg)
        assert cfg == copy
        assert cfg is not copy

    def test_asdict_roundtrip(self) -> None:
        """Converting to dict and back produces equal config."""
        cfg = TranslationConfig(
            storage_path="/roundtrip",
            ocr_method="EasyOCR",
            translate_doc_images=True,
        )
        d = dataclasses.asdict(cfg)
        cfg2 = TranslationConfig(**d)
        assert cfg == cfg2
