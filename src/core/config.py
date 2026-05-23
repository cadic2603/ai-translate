"""Injectable configuration snapshot for the translation pipeline.

Bundles all runtime settings into a frozen dataclass so the core
pipeline can be called from any entry point (GUI, CLI, REST API)
without depending on the desktop config system.
"""

import dataclasses


@dataclasses.dataclass(frozen=True, slots=True)
class TranslationConfig:
    """Immutable snapshot of runtime translation settings.

    Attributes:
        storage_path: User-configured output directory for translated files.
        ocr_method: OCR engine to use (e.g. "Tesseract", "EasyOCR").
        translate_doc_images: Whether to translate embedded images in documents.
        translate_doc_comments: Whether to translate comments in Office files.
        translate_doc_shapes: Whether to translate shapes/text-boxes.
        translate_doc_notes: Whether to translate speaker notes in PowerPoint.
        translate_sheet_names: Whether to translate sheet names in Excel.
        ocr_is_configured: Whether the selected OCR engine is ready.
        auto_convert_legacy: Pre-convert legacy formats (.doc/.xls/.ppt).
        auto_convert_odf: Pre-convert ODF formats (.odt/.ods/.odp).
        auto_remove_history: Delete history entries after successful translation.
        libreoffice_path: User-configured LibreOffice install directory.
        llm_provider: LLM provider name (e.g. "Gemini", "Custom").
        llm_model: LLM model name (e.g. "gemini-3-flash-preview").
    """

    storage_path: str = ""
    ocr_method: str = "Tesseract"
    translate_doc_images: bool = False
    translate_doc_comments: bool = False
    translate_doc_shapes: bool = False
    translate_doc_notes: bool = False
    translate_sheet_names: bool = False
    ocr_is_configured: bool = False
    auto_convert_legacy: bool = False
    auto_convert_odf: bool = False
    auto_remove_history: bool = False
    libreoffice_path: str = ""
    llm_provider: str = ""
    llm_model: str = ""

    @property
    def should_translate_images(self) -> bool:
        """Returns True when image translation is enabled AND OCR is ready."""
        return self.translate_doc_images and self.ocr_is_configured

    @classmethod
    def from_settings(cls, model_setting_key: str = "") -> "TranslationConfig":
        """Creates a config snapshot from the current user settings.

        This is the single bridge between the UI config system and the
        core pipeline.  Only the UI layer should call this method;
        headless callers construct ``TranslationConfig`` directly.

        Args:
            model_setting_key: Optional feature-specific model setting key.
                When provided, it is resolved before falling back to the
                global default model.
        """
        from src.constants.ocr import OCR_METHOD_TESSERACT  # noqa: PLC0415
        from src.constants.settings import (  # noqa: PLC0415
            SETTING_AUTO_CONVERT_LEGACY,
            SETTING_AUTO_CONVERT_ODF,
            SETTING_AUTO_REMOVE_HISTORY,
            SETTING_LIBREOFFICE_PATH,
            SETTING_LLM_LAST_MODEL,
            SETTING_OCR_METHOD,
            SETTING_STORAGE_PATH,
            SETTING_TRANSLATE_DOC_COMMENTS,
            SETTING_TRANSLATE_DOC_IMAGES,
            SETTING_TRANSLATE_DOC_NOTES,
            SETTING_TRANSLATE_DOC_SHAPES,
            SETTING_TRANSLATE_SHEET_NAMES,
        )
        from src.utils.config_manager import (  # noqa: PLC0415
            check_ocr_setup,
            load_model_for_feature,
            load_setting,
            parse_model_id,
        )

        model_id = (
            load_model_for_feature(model_setting_key)
            if model_setting_key
            else load_setting(SETTING_LLM_LAST_MODEL, "")
        )
        llm_provider, llm_model = parse_model_id(
            model_id,
        )

        return cls(
            storage_path=load_setting(SETTING_STORAGE_PATH, ""),
            ocr_method=load_setting(SETTING_OCR_METHOD, OCR_METHOD_TESSERACT),
            translate_doc_images=load_setting(SETTING_TRANSLATE_DOC_IMAGES, False),
            translate_doc_comments=load_setting(SETTING_TRANSLATE_DOC_COMMENTS, False),
            translate_doc_shapes=load_setting(SETTING_TRANSLATE_DOC_SHAPES, False),
            translate_doc_notes=load_setting(SETTING_TRANSLATE_DOC_NOTES, False),
            translate_sheet_names=load_setting(SETTING_TRANSLATE_SHEET_NAMES, False),
            ocr_is_configured=check_ocr_setup(),
            auto_convert_legacy=load_setting(SETTING_AUTO_CONVERT_LEGACY, False),
            auto_convert_odf=load_setting(SETTING_AUTO_CONVERT_ODF, False),
            auto_remove_history=load_setting(SETTING_AUTO_REMOVE_HISTORY, False),
            libreoffice_path=load_setting(SETTING_LIBREOFFICE_PATH, ""),
            llm_provider=llm_provider,
            llm_model=llm_model,
        )
