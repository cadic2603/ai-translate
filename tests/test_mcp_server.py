"""Tests for the MCP server tools."""

import tempfile
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Force bootstrap to be a no-op — conftest.py already handles DB setup.
import src.mcp_server as mcp_mod

mcp_mod._bootstrapped = True


# ── list_languages ─────────────────────────────────────────────────


class TestListLanguages:
    """Tests for list_languages MCP tool."""

    def test_returns_all_languages(self):
        from src.constants.languages import LANGUAGES

        result = mcp_mod.list_languages()
        assert len(result) == len(LANGUAGES)

    def test_entry_shape(self):
        result = mcp_mod.list_languages()
        entry = result[0]
        assert "locale" in entry
        assert "name" in entry
        assert "native_name" in entry

    def test_contains_known_language(self):
        result = mcp_mod.list_languages()
        names = [e["name"] for e in result]
        assert "Vietnamese" in names
        assert "French" in names
        assert "Japanese" in names

    def test_locale_codes(self):
        result = mcp_mod.list_languages()
        locales = {e["locale"] for e in result}
        assert "vi" in locales
        assert "zh-CN" in locales
        assert "en-US" in locales


# ── _validate_language / _validate_source_language ────────────────


class TestValidateLanguage:
    """Tests for the _validate_language helper."""

    def test_exact_match(self):
        assert mcp_mod._validate_language("French", "target language") == "French"

    def test_case_insensitive(self):
        assert mcp_mod._validate_language("french", "target language") == "French"
        assert (
            mcp_mod._validate_language("VIETNAMESE", "target language") == "Vietnamese"
        )

    def test_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown target language"):
            mcp_mod._validate_language("Klingon", "target language")

    def test_source_empty_returns_empty(self):
        assert mcp_mod._validate_source_language("") == ""

    def test_source_valid(self):
        assert mcp_mod._validate_source_language("French") == "French"

    def test_source_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown source language"):
            mcp_mod._validate_source_language("Klingon")


# ── _resolve_content_type ──────────────────────────────────────────


class TestResolveContentType:
    """Tests for the _resolve_content_type helper."""

    def test_plain_text(self):
        result = mcp_mod._resolve_content_type("plain_text")
        assert result  # non-empty string

    def test_html(self):
        from src.constants.llm import CONTENT_HTML

        assert mcp_mod._resolve_content_type("html") == CONTENT_HTML

    def test_case_insensitive(self):
        from src.constants.llm import CONTENT_HTML

        assert mcp_mod._resolve_content_type("HTML") == CONTENT_HTML

    def test_unknown_falls_back_to_plain(self):
        from src.constants.llm import CONTENT_PLAIN_TEXT

        assert mcp_mod._resolve_content_type("unknown_format") == CONTENT_PLAIN_TEXT


# ── translate_text ─────────────────────────────────────────────────


class TestTranslateText:
    """Tests for translate_text MCP tool."""

    @patch("src.core.llm_engine.translate_text")
    @patch("src.utils.config_manager.check_llm_setup", return_value=True)
    def test_basic_translation(self, _mock_setup, mock_translate):
        mock_translate.return_value = ["Bonjour"]

        result = mcp_mod.translate_text(
            texts=["Hello"],
            target_language="French",
        )

        assert result == ["Bonjour"]
        mock_translate.assert_called_once()
        call_kwargs = mock_translate.call_args
        assert call_kwargs.kwargs["target_lang"] == "French"
        assert call_kwargs.kwargs["source_lang"] == ""

    @patch("src.core.llm_engine.translate_text")
    @patch("src.utils.config_manager.check_llm_setup", return_value=True)
    def test_with_source_language(self, _mock_setup, mock_translate):
        mock_translate.return_value = ["Xin chào"]

        result = mcp_mod.translate_text(
            texts=["Hello"],
            target_language="Vietnamese",
            source_language="English (US)",
        )

        assert result == ["Xin chào"]
        call_kwargs = mock_translate.call_args
        assert call_kwargs.kwargs["source_lang"] == "English (US)"

    @patch("src.core.llm_engine.translate_text")
    @patch("src.utils.config_manager.check_llm_setup", return_value=True)
    def test_multiple_texts(self, _mock_setup, mock_translate):
        mock_translate.return_value = ["Bonjour", "Au revoir"]

        result = mcp_mod.translate_text(
            texts=["Hello", "Goodbye"],
            target_language="French",
        )

        assert result == ["Bonjour", "Au revoir"]

    @patch("src.core.llm_engine.translate_text")
    @patch("src.utils.config_manager.check_llm_setup", return_value=True)
    def test_content_type_passed(self, _mock_setup, mock_translate):
        from src.constants.llm import CONTENT_HTML

        mock_translate.return_value = ["<p>Bonjour</p>"]

        mcp_mod.translate_text(
            texts=["<p>Hello</p>"],
            target_language="French",
            content_type="html",
        )

        call_kwargs = mock_translate.call_args
        assert call_kwargs.kwargs["content_type"] == CONTENT_HTML

    def test_unknown_target_language_raises(self):
        with pytest.raises(ValueError, match="Unknown target language"):
            mcp_mod.translate_text(texts=["Hello"], target_language="Klingon")

    @patch("src.utils.config_manager.check_llm_setup", return_value=True)
    def test_unknown_source_language_raises(self, _mock_setup):
        with pytest.raises(ValueError, match="Unknown source language"):
            mcp_mod.translate_text(
                texts=["Hello"],
                target_language="French",
                source_language="Klingon",
            )

    def test_llm_not_configured_raises(self):
        with (
            patch("src.utils.config_manager.check_llm_setup", return_value=False),
            pytest.raises(RuntimeError, match="LLM is not configured"),
        ):
            mcp_mod.translate_text(texts=["Hello"], target_language="French")


# ── extract_image_text ─────────────────────────────────────────────


class TestExtractImageText:
    """Tests for extract_image_text MCP tool."""

    def test_file_not_found_raises(self):
        with pytest.raises(FileNotFoundError, match="File not found"):
            mcp_mod.extract_image_text("/nonexistent/image.png")

    def test_unsupported_format_raises(self):
        with (
            tempfile.NamedTemporaryFile(suffix=".txt") as f,
            pytest.raises(ValueError, match="Unsupported image format"),
        ):
            mcp_mod.extract_image_text(f.name)

    @patch("src.core.llm_engine.extract_image_text", return_value="Hello world")
    @patch("src.utils.config_manager.check_llm_setup", return_value=True)
    def test_llm_extraction(self, _mock_setup, _mock_extract):
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(b"\x89PNG\r\n\x1a\n")  # minimal PNG header
            tmp_path = f.name

        try:
            result = mcp_mod.extract_image_text(tmp_path)
            assert result["text"] == "Hello world"
            assert result["method"] == "llm"
            assert result["blocks"] == []
        finally:
            Path(tmp_path).unlink()

    @patch("src.utils.config_manager.load_setting", return_value="Tesseract")
    @patch("src.core.ocr_engine.run_ocr")
    @patch("src.utils.config_manager.check_ocr_setup", return_value=True)
    @patch(
        "src.core.llm_engine.extract_image_text",
        return_value="",  # LLM returns empty → fall back to OCR
    )
    @patch("src.utils.config_manager.check_llm_setup", return_value=True)
    def test_ocr_fallback(
        self, _llm_setup, _llm_extract, _ocr_setup, mock_ocr, _load_setting
    ):
        # Build a minimal OCRResult-like mock
        mock_result = MagicMock()
        mock_result.text = "OCR text"
        mock_result.x = 10
        mock_result.y = 20
        mock_result.w = 100
        mock_result.h = 30
        mock_result.confidence = 0.95
        mock_ocr.return_value = [mock_result]

        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
            f.write(b"\xff\xd8\xff\xe0")  # minimal JPEG header
            tmp_path = f.name

        try:
            result = mcp_mod.extract_image_text(tmp_path)
            assert result["text"] == "OCR text"
            assert result["method"] == "ocr"
            assert len(result["blocks"]) == 1
            assert result["blocks"][0]["box"] == [10, 20, 100, 30]
            assert result["blocks"][0]["confidence"] == 0.95
        finally:
            Path(tmp_path).unlink()

    @patch("src.utils.config_manager.check_ocr_setup", return_value=False)
    @patch("src.utils.config_manager.check_llm_setup", return_value=False)
    def test_no_backend_configured_raises(self, _llm, _ocr):
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(b"\x89PNG\r\n\x1a\n")
            tmp_path = f.name

        try:
            with pytest.raises(RuntimeError, match="Neither LLM nor OCR"):
                mcp_mod.extract_image_text(tmp_path)
        finally:
            Path(tmp_path).unlink()


# ── translate_document ─────────────────────────────────────────────


class TestTranslateDocument:
    """Tests for translate_document MCP tool."""

    @patch("src.core.translator.run_translation_pipeline")
    @patch(
        "src.core.translator.setup_translation_tasks",
        return_value=[(1, "/tmp/store/doc.docx", "", "French")],
    )
    @patch("src.utils.config_manager.check_llm_setup", return_value=True)
    def test_basic_document_translation(self, _llm, mock_setup, mock_pipeline):
        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as f:
            f.write(b"PK")
            tmp_path = f.name

        try:
            result = mcp_mod.translate_document(
                file_paths=[tmp_path],
                target_language="French",
            )

            assert result["task_ids"] == [1]
            assert result["file_count"] == 1
            mock_setup.assert_called_once()

            # Wait for background thread to finish
            with mcp_mod._pipelines_lock:
                entry = mcp_mod._active_pipelines.get(1)
            if entry:
                entry[0].join(timeout=5)

            mock_pipeline.assert_called_once()
        finally:
            Path(tmp_path).unlink()

    @patch("src.core.translator.run_translation_pipeline")
    @patch(
        "src.core.translator.setup_translation_tasks",
        return_value=[
            (10, "/tmp/store/a.pdf", "", "Japanese"),
            (11, "/tmp/store/b.pdf", "", "Japanese"),
        ],
    )
    @patch("src.utils.config_manager.check_llm_setup", return_value=True)
    def test_multiple_files(self, _llm, mock_setup, mock_pipeline):
        files = []
        try:
            for _ in range(2):
                with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
                    f.write(b"%PDF")
                    files.append(f.name)

            result = mcp_mod.translate_document(
                file_paths=files,
                target_language="Japanese",
            )

            assert result["task_ids"] == [10, 11]
            assert result["file_count"] == 2
        finally:
            for fp in files:
                Path(fp).unlink()

    def test_unknown_target_language_raises(self):
        with pytest.raises(ValueError, match="Unknown target language"):
            mcp_mod.translate_document(
                file_paths=["/tmp/test.docx"],
                target_language="Klingon",
            )

    @patch("src.utils.config_manager.check_llm_setup", return_value=True)
    def test_unknown_source_language_raises(self, _llm):
        with pytest.raises(ValueError, match="Unknown source language"):
            mcp_mod.translate_document(
                file_paths=["/tmp/test.docx"],
                target_language="French",
                source_language="Klingon",
            )

    def test_llm_not_configured_raises(self):
        with (
            patch("src.utils.config_manager.check_llm_setup", return_value=False),
            pytest.raises(RuntimeError, match="LLM is not configured"),
        ):
            mcp_mod.translate_document(
                file_paths=["/tmp/test.docx"],
                target_language="French",
            )

    @patch("src.utils.config_manager.check_llm_setup", return_value=True)
    def test_file_not_found_raises(self, _llm):
        with pytest.raises(FileNotFoundError, match="File not found"):
            mcp_mod.translate_document(
                file_paths=["/nonexistent/file.docx"],
                target_language="French",
            )

    @patch("src.utils.config_manager.check_llm_setup", return_value=True)
    def test_unsupported_format_raises(self, _llm):
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            f.write(b"\xff\xfb")
            tmp_path = f.name

        try:
            with pytest.raises(ValueError, match="Unsupported file format"):
                mcp_mod.translate_document(
                    file_paths=[tmp_path],
                    target_language="French",
                )
        finally:
            Path(tmp_path).unlink()

    @patch("src.core.translator.run_translation_pipeline")
    @patch(
        "src.core.translator.setup_translation_tasks",
        return_value=[(5, "/tmp/store/img.png", "English (US)", "Vietnamese")],
    )
    @patch("src.utils.config_manager.check_ocr_setup", return_value=True)
    @patch("src.utils.config_manager.check_llm_setup", return_value=True)
    def test_options_passed_to_config(self, _llm, _ocr, mock_setup, mock_pipeline):
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(b"\x89PNG")
            tmp_path = f.name

        try:
            mcp_mod.translate_document(
                file_paths=[tmp_path],
                target_language="Vietnamese",
                source_language="English (US)",
                translate_images=True,
                translate_comments=True,
            )

            # Wait for thread
            with mcp_mod._pipelines_lock:
                entry = mcp_mod._active_pipelines.get(5)
            if entry:
                entry[0].join(timeout=5)

            config = mock_pipeline.call_args.kwargs["config"]
            assert config.translate_doc_images is True
            assert config.translate_doc_comments is True
            assert config.ocr_is_configured is True
            assert config.auto_remove_history is False
        finally:
            Path(tmp_path).unlink()

    @patch("src.core.translator.run_translation_pipeline")
    @patch(
        "src.core.translator.setup_translation_tasks",
        return_value=[(7, "/tmp/store/doc.docx", "", "French")],
    )
    @patch("src.utils.config_manager.check_ocr_setup", return_value=True)
    @patch("src.utils.config_manager.check_llm_setup", return_value=True)
    def test_explicit_model_arg_lands_in_translation_config(
        self, _llm, _ocr, _setup, mock_pipeline,
    ):
        """``translate_document(model="Provider:m")`` reaches the engine.

        Pin the per-feature model contract: a caller-passed ``model``
        threads through into ``TranslationConfig.llm_provider`` and
        ``llm_model`` so the background pipeline uses that exact
        engine for the per-batch LLM calls — not the global default.
        """
        from unittest.mock import patch  # noqa: PLC0415

        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as f:
            f.write(b"PK")
            tmp_path = f.name

        try:
            with patch(
                "src.utils.config_manager.get_available_models",
                return_value=[("Custom", "azure/gpt-5.2-chat")],
            ):
                mcp_mod.translate_document(
                    file_paths=[tmp_path],
                    target_language="French",
                    model="Custom:azure/gpt-5.2-chat",
                )
            with mcp_mod._pipelines_lock:
                entry = mcp_mod._active_pipelines.get(7)
            if entry:
                entry[0].join(timeout=5)

            config = mock_pipeline.call_args.kwargs["config"]
            assert config.llm_provider == "Custom", (
                f"provider missing in config: {config.llm_provider!r}"
            )
            assert config.llm_model == "azure/gpt-5.2-chat", (
                f"model missing in config: {config.llm_model!r}"
            )
        finally:
            Path(tmp_path).unlink()

    @patch(
        "src.core.translator.setup_translation_tasks",
        return_value=[],
    )
    @patch("src.utils.config_manager.check_llm_setup", return_value=True)
    def test_setup_failure_raises(self, _llm, _setup):
        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as f:
            f.write(b"PK")
            tmp_path = f.name

        try:
            with pytest.raises(RuntimeError, match="Failed to set up"):
                mcp_mod.translate_document(
                    file_paths=[tmp_path],
                    target_language="French",
                )
        finally:
            Path(tmp_path).unlink()

    @patch("src.utils.config_manager.check_llm_setup", return_value=True)
    def test_unknown_ocr_method_raises(self, _llm):
        """Unknown ocr_method surfaces early with a ValueError."""
        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as f:
            f.write(b"PK")
            tmp_path = f.name

        try:
            with pytest.raises(ValueError, match="Unknown OCR method"):
                mcp_mod.translate_document(
                    file_paths=[tmp_path],
                    target_language="French",
                    ocr_method="Bogus",
                )
        finally:
            Path(tmp_path).unlink()

    @patch("src.core.translator.run_translation_pipeline")
    @patch(
        "src.core.translator.setup_translation_tasks",
        return_value=[(7, "/tmp/store/x.png", "", "French")],
    )
    @patch("src.utils.config_manager.check_llm_setup", return_value=True)
    def test_ocr_method_resolves_friendly_spelling(
        self,
        _llm,
        _setup,
        mock_pipeline,
    ):
        """Friendly 'easyocr' resolves to the canonical 'EasyOCR'."""
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(b"\x89PNG")
            tmp_path = f.name

        try:
            mcp_mod.translate_document(
                file_paths=[tmp_path],
                target_language="French",
                ocr_method="easyocr",
            )

            with mcp_mod._pipelines_lock:
                entry = mcp_mod._active_pipelines.get(7)
            if entry:
                entry[0].join(timeout=5)

            config = mock_pipeline.call_args.kwargs["config"]
            assert config.ocr_method == "EasyOCR"
        finally:
            Path(tmp_path).unlink()


# ── get_task_status ───────────────────────────────────────────────


class TestGetTaskStatus:
    """Tests for get_task_status MCP tool.

    Implementation was refactored to use the batch ``get_history_
    entry_details`` helper — a single ``WHERE id IN (...)`` query
    in place of the prior per-id N+1 loop.  Tests therefore patch
    the batch helper and return a ``{id: detail}`` map.
    """

    @patch("src.core.database.get_history_entry_details")
    def test_basic_status(self, mock_details):
        mock_details.return_value = {1: {
            "id": 1,
            "file_name": "report.docx",
            "file_size": 1024,
            "source_path": "/home/user/report.docx",
            "storage_path": "/tmp/store/report.docx",
            "source_lang": "",
            "target_lang": "French",
            "status": "Translating",
            "progress": 50,
            "error_code": 0,
            "created_at": "2026-04-01 12:00:00",
        }}

        result = mcp_mod.get_task_status(task_ids=[1])

        assert len(result) == 1
        assert result[0]["task_id"] == 1
        assert result[0]["status"] == "Translating"
        assert result[0]["progress"] == 50
        assert result[0]["file_name"] == "report.docx"
        assert result[0]["target_lang"] == "French"

    @patch("src.core.database.get_history_entry_details")
    def test_multiple_tasks(self, mock_details):
        mock_details.return_value = {
            1: {
                "id": 1,
                "file_name": "a.docx",
                "file_size": 100,
                "source_path": "/a.docx",
                "storage_path": "/s/a.docx",
                "source_lang": "",
                "target_lang": "French",
                "status": "Done",
                "progress": 100,
                "error_code": 0,
                "created_at": "2026-04-01 12:00:00",
            },
            2: {
                "id": 2,
                "file_name": "b.pdf",
                "file_size": 200,
                "source_path": "/b.pdf",
                "storage_path": "/s/b.pdf",
                "source_lang": "",
                "target_lang": "French",
                "status": "Failed",
                "progress": 30,
                "error_code": 31,
                "created_at": "2026-04-01 12:01:00",
            },
        }

        result = mcp_mod.get_task_status(task_ids=[1, 2])

        assert len(result) == 2
        assert result[0]["status"] == "Done"
        assert result[1]["status"] == "Failed"
        assert result[1]["error_code"] == 31

    @patch("src.core.database.get_history_entry_details")
    def test_removed_entry_returns_null_status(self, mock_details):
        mock_details.return_value = {}  # auto-removed → absent from batch map

        result = mcp_mod.get_task_status(task_ids=[999])

        assert len(result) == 1
        assert result[0]["task_id"] == 999
        assert result[0]["status"] is None
        assert result[0]["progress"] == 100
        # Sentinel record also exposes error_message=None for shape parity.
        assert result[0]["error_message"] is None

    @patch("src.core.database.get_history_entry_details")
    def test_error_message_field_preserves_service_suffix(self, mock_details):
        """``get_task_status`` exposes the raw ``AUTH_ERROR:Service`` tag.

        MCP clients need the suffix to render service-aware
        copy on their own UI ("Invalid Gemini API key" → which
        Settings tab to open).  Without ``error_message`` in the
        response shape, clients only see ``error_code=30`` and
        have no way to know which backend failed.
        """
        mock_details.return_value = {1: {
            "id": 1,
            "file_name": "f.docx",
            "file_size": 100,
            "source_path": "/f.docx",
            "storage_path": "/s/f.docx",
            "source_lang": "English",
            "target_lang": "Vietnamese",
            "status": "Failed",
            "progress": 30,
            "error_code": 30,
            "error_message": "AUTH_ERROR:Gemini",
            "created_at": "2026-04-01 12:00:00",
        }}

        result = mcp_mod.get_task_status(task_ids=[1])

        assert result[0]["error_code"] == 30
        assert result[0]["error_message"] == "AUTH_ERROR:Gemini"

    @patch("src.core.database.get_history_entry_details")
    def test_error_message_field_null_for_successful_task(self, mock_details):
        """Successful tasks return ``error_message=None``."""
        mock_details.return_value = {1: {
            "id": 1,
            "file_name": "ok.docx",
            "file_size": 100,
            "source_path": "/ok.docx",
            "storage_path": "/s/ok.docx",
            "source_lang": "",
            "target_lang": "French",
            "status": "Done",
            "progress": 100,
            "error_code": 0,
            "error_message": None,
            "created_at": "2026-04-01 12:00:00",
        }}

        result = mcp_mod.get_task_status(task_ids=[1])

        assert result[0]["error_message"] is None

    @patch("src.core.database.get_history_entry_details")
    def test_empty_task_ids(self, mock_details):
        mock_details.return_value = {}
        result = mcp_mod.get_task_status(task_ids=[])
        assert result == []

    @patch("src.core.database.get_history_entry_details")
    def test_uses_single_batch_query_for_many_ids(self, mock_details):
        """N task_ids → 1 DB call, not N.  Regression guard for the N+1 fix.

        Previously ``get_task_status`` called ``get_history_entry_
        detail`` per task ID, generating one SQLite round-trip per
        ID.  For a client polling 100 tasks that was a textbook
        N+1.  Pin the new single-call contract so a future refactor
        can't silently regress to per-id queries.
        """
        # 50 task IDs.  Return one entry to keep assertions
        # cheap — what matters is the call_count is 1.
        mock_details.return_value = {
            5: {
                "id": 5, "file_name": "a.docx", "file_size": 0,
                "source_path": "/a", "storage_path": "/s",
                "source_lang": "", "target_lang": "French",
                "status": "Done", "progress": 100, "error_code": 0,
                "created_at": "2026-04-01 12:00:00",
            },
        }
        task_ids = list(range(1, 51))
        result = mcp_mod.get_task_status(task_ids=task_ids)

        assert mock_details.call_count == 1
        assert mock_details.call_args.args[0] == task_ids
        assert len(result) == 50  # noqa: PLR2004 — one entry per requested id
        # The one ID that exists in the map carries real data;
        # the rest get the auto-removed sentinel.
        statuses = {r["task_id"]: r["status"] for r in result}
        assert statuses[5] == "Done"
        assert statuses[1] is None


# ── get_history_entry_detail (DB helper) ──────────────────────────


class TestGetHistoryEntryDetail:
    """Tests for get_history_entry_detail in database."""

    def test_returns_none_for_nonexistent(self):
        from src.core.database import get_history_entry_detail

        result = get_history_entry_detail(999999)
        assert result is None

    def test_returns_dict_for_existing_entry(self):
        from src.core.database import add_history_entry, get_history_entry_detail

        h_id = add_history_entry(
            "test_mcp.docx",
            "",
            "French",
            "Pending",
            source_path="/tmp/test_mcp.docx",
            file_size=512,
        )
        assert h_id is not None

        detail = get_history_entry_detail(h_id)
        assert detail is not None
        assert detail["id"] == h_id
        assert detail["file_name"] == "test_mcp.docx"
        assert detail["target_lang"] == "French"
        assert detail["status"] == "Pending"
        assert detail["progress"] == 0
        assert detail["error_code"] is None

        # Cleanup
        from src.core.database import delete_history_entry

        delete_history_entry(h_id)


# ── Pipeline background thread cleanup ────────────────────────────


class TestPipelineBackground:
    """Tests for the background pipeline runner."""

    def test_active_pipelines_cleaned_up_after_run(self):
        """Thread entries are removed from _active_pipelines after completion."""
        done_event = threading.Event()

        def fake_pipeline(**_kwargs):
            done_event.set()

        cancel_event = threading.Event()
        with patch(
            "src.core.translator.run_translation_pipeline", side_effect=fake_pipeline
        ):
            mcp_mod._run_pipeline_background(
                [42],
                config=MagicMock(),
                cancel_event=cancel_event,
            )

        # After _run_pipeline_background returns, entries should be cleaned up
        with mcp_mod._pipelines_lock:
            assert 42 not in mcp_mod._active_pipelines

    def test_active_pipelines_cleaned_up_on_error(self):
        """Thread entries are cleaned up even if the pipeline raises."""

        def exploding_pipeline(**_kwargs):
            raise RuntimeError("boom")

        cancel_event = threading.Event()
        with patch(
            "src.core.translator.run_translation_pipeline",
            side_effect=exploding_pipeline,
        ):
            # Should not raise — errors are caught internally
            mcp_mod._run_pipeline_background(
                [99],
                config=MagicMock(),
                cancel_event=cancel_event,
            )

        with mcp_mod._pipelines_lock:
            assert 99 not in mcp_mod._active_pipelines

    def test_pipeline_is_scoped_to_owned_task_ids(self) -> None:
        """Background runner passes its task IDs into the global pipeline."""
        captured: dict[str, object] = {}

        def fake_pipeline(**kwargs: object) -> None:
            captured.update(kwargs)

        cancel_event = threading.Event()
        with patch(
            "src.core.translator.run_translation_pipeline",
            side_effect=fake_pipeline,
        ):
            mcp_mod._run_pipeline_background(
                [7, 8],
                config=MagicMock(),
                cancel_event=cancel_event,
            )

        assert captured["task_ids"] == [7, 8]


# ── cancel_task ────────────────────────────────────────────────────


class TestCancelTask:
    """Tests for cancel_task MCP tool."""

    def teardown_method(self) -> None:
        """Clear any leftover tracked pipelines between tests."""
        with mcp_mod._pipelines_lock:
            mcp_mod._active_pipelines.clear()

    def test_known_task_id_signals_cancel(self) -> None:
        """cancel_task flips the registered event and reports the ID."""
        event = threading.Event()
        thread = MagicMock()
        with mcp_mod._pipelines_lock:
            mcp_mod._active_pipelines[42] = (thread, event)

        result = mcp_mod.cancel_task([42])

        assert result["cancelled"] == [42]
        assert result["unknown"] == []
        assert event.is_set()

    def test_unknown_task_id_reported_not_raised(self) -> None:
        """Unknown IDs go into 'unknown', not an exception."""
        result = mcp_mod.cancel_task([99])
        assert result["cancelled"] == []
        assert result["unknown"] == [99]

    def test_shared_event_set_only_once(self) -> None:
        """Shared-pipeline event is flipped exactly once even with many IDs.

        Multiple task IDs sharing a pipeline each count as cancelled, but
        the underlying ``threading.Event`` is set a single time.
        """
        event = MagicMock(spec=threading.Event())
        thread = MagicMock()
        with mcp_mod._pipelines_lock:
            mcp_mod._active_pipelines[1] = (thread, event)
            mcp_mod._active_pipelines[2] = (thread, event)

        result = mcp_mod.cancel_task([1, 2])

        assert sorted(result["cancelled"]) == [1, 2]
        assert event.set.call_count == 1

    def test_cancel_pauses_all_tasks_sharing_pipeline_event(self) -> None:
        """Cancelling one task pauses every task owned by the same thread."""
        event = threading.Event()
        thread = MagicMock()
        with mcp_mod._pipelines_lock:
            mcp_mod._active_pipelines[1] = (thread, event)
            mcp_mod._active_pipelines[2] = (thread, event)

        with patch("src.core.database.batch_pause_history_entries") as mock_pause:
            result = mcp_mod.cancel_task([1])

        assert result["cancelled"] == [1]
        assert event.is_set()
        mock_pause.assert_called_once_with([1, 2])


# ── transcribe_audio ──────────────────────────────────────────────


class TestTranscribeAudio:
    """Tests for transcribe_audio MCP tool."""

    def test_file_not_found_raises(self):
        with pytest.raises(FileNotFoundError, match="File not found"):
            mcp_mod.transcribe_audio("/nonexistent/audio.mp3")

    def test_unsupported_format_raises(self):
        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as f:
            f.write(b"PK")
            tmp = f.name
        try:
            with pytest.raises(ValueError, match="Unsupported audio/video format"):
                mcp_mod.transcribe_audio(tmp)
        finally:
            Path(tmp).unlink()

    def test_unknown_language_raises(self):
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            f.write(b"\xff\xfb")
            tmp = f.name
        try:
            with pytest.raises(ValueError, match="Unknown source language"):
                mcp_mod.transcribe_audio(tmp, source_language="Klingon")
        finally:
            Path(tmp).unlink()

    def test_unknown_stt_method_raises(self):
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            f.write(b"\xff\xfb")
            tmp = f.name
        try:
            with pytest.raises(ValueError, match="Unknown STT method"):
                mcp_mod.transcribe_audio(tmp, stt_method="DeepSpeech")
        finally:
            Path(tmp).unlink()

    @patch(
        "src.core.speech_engine.transcribe_audio",
        return_value="1\n00:00:00,000 --> 00:00:01,000\nHello\n",
    )
    def test_whisper_transcription(self, mock_transcribe):
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(b"RIFF")
            tmp = f.name
        try:
            result = mcp_mod.transcribe_audio(tmp, stt_method="Whisper")
            assert "srt" in result
            assert result["method"] == "Whisper"
            mock_transcribe.assert_called_once()
            assert mock_transcribe.call_args.kwargs["stt_method"] == "Whisper"
        finally:
            Path(tmp).unlink()

    @patch(
        "src.core.speech_engine.transcribe_audio",
        return_value="1\n00:00:00,000 --> 00:00:02,000\nBonjour\n",
    )
    def test_with_source_language(self, mock_transcribe):
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as f:
            f.write(b"\x00\x00\x00")
            tmp = f.name
        try:
            result = mcp_mod.transcribe_audio(
                tmp,
                source_language="French",
                stt_method="Whisper",
            )
            assert result["srt"].startswith("1\n")
            assert mock_transcribe.call_args.kwargs["src_lang"] == "French"
        finally:
            Path(tmp).unlink()

    @patch(
        "src.core.speech_engine.transcribe_audio",
        return_value="1\n00:00:00,000 --> 00:00:01,000\nTest\n",
    )
    def test_google_cloud_method(self, mock_transcribe):
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            f.write(b"\xff\xfb")
            tmp = f.name
        try:
            result = mcp_mod.transcribe_audio(tmp, stt_method="Google Cloud")
            assert result["method"] == "Google Cloud"
            assert mock_transcribe.call_args.kwargs["stt_method"] == "Google Cloud"
        finally:
            Path(tmp).unlink()


# ── synthesize_speech ─────────────────────────────────────────────


class TestSynthesizeSpeech:
    """Tests for synthesize_speech MCP tool."""

    def test_empty_text_raises(self):
        with pytest.raises(ValueError, match="Text cannot be empty"):
            mcp_mod.synthesize_speech(text="", target_language="French")

    def test_whitespace_only_raises(self):
        with pytest.raises(ValueError, match="Text cannot be empty"):
            mcp_mod.synthesize_speech(text="   ", target_language="French")

    def test_unknown_target_language_raises(self):
        with pytest.raises(ValueError, match="Unknown target language"):
            mcp_mod.synthesize_speech(text="Hello", target_language="Klingon")

    def test_unknown_tts_method_raises(self):
        with pytest.raises(ValueError, match="Unknown TTS method"):
            mcp_mod.synthesize_speech(
                text="Hello",
                target_language="French",
                tts_method="Piper",
            )

    def test_piper_tts_routes_to_engine(self, tmp_path):
        """``tts_method="Piper TTS"`` resolves to ``VOICE_TTS_PIPER``.

        The previous bug shipped Piper as a TTS engine but left the
        MCP ``method_map`` un-updated — calls with ``"Piper TTS"``
        raised ``"Unknown TTS method"``.  Pin the positive path so a
        future ``method_map`` regression breaks this test.
        """
        from unittest.mock import patch  # noqa: PLC0415

        from src.constants.settings import VOICE_TTS_PIPER  # noqa: PLC0415

        out_path = str(tmp_path / "out.mp3")
        with patch(
            "src.core.speech_engine.synthesize_speech",
            return_value=out_path,
        ) as mock_engine:
            mcp_mod.synthesize_speech(
                text="Hello",
                target_language="French",
                tts_method="Piper TTS",
                output_path=out_path,
            )
        mock_engine.assert_called_once()
        assert mock_engine.call_args.kwargs["tts_method"] == VOICE_TTS_PIPER

    def test_gemini_tts_routes_to_engine(self, tmp_path):
        """``tts_method="Gemini TTS"`` resolves to ``VOICE_TTS_GEMINI``.

        Same regression guard as Piper — both gaps were fixed in the
        same change set.
        """
        from unittest.mock import patch  # noqa: PLC0415

        from src.constants.settings import VOICE_TTS_GEMINI  # noqa: PLC0415

        out_path = str(tmp_path / "out.mp3")
        with patch(
            "src.core.speech_engine.synthesize_speech",
            return_value=out_path,
        ) as mock_engine:
            mcp_mod.synthesize_speech(
                text="Hello",
                target_language="French",
                tts_method="Gemini TTS",
                output_path=out_path,
            )
        mock_engine.assert_called_once()
        assert mock_engine.call_args.kwargs["tts_method"] == VOICE_TTS_GEMINI

    def test_unsupported_audio_format_raises(self):
        """Only .mp3 / .wav are allowed — .ogg et al. must error out early."""
        with pytest.raises(ValueError, match="Unsupported audio_format"):
            mcp_mod.synthesize_speech(
                text="Hello",
                target_language="French",
                audio_format=".ogg",
            )

    @patch("src.core.speech_engine.synthesize_speech", return_value="/tmp/out.wav")
    def test_audio_format_accepts_missing_dot(self, mock_synth):
        """'wav' and '.wav' both resolve to '.wav'."""
        result = mcp_mod.synthesize_speech(
            text="Hello",
            target_language="French",
            audio_format="wav",
        )
        assert result["output_path"] == "/tmp/out.wav"
        assert mock_synth.call_args.kwargs["audio_format"] == ".wav"

    @patch("src.core.speech_engine.synthesize_speech", return_value="/tmp/tts_out.mp3")
    def test_basic_synthesis(self, mock_synth):
        result = mcp_mod.synthesize_speech(
            text="Hello world",
            target_language="French",
        )
        assert result["output_path"] == "/tmp/tts_out.mp3"
        assert result["method"] == "Edge TTS"
        mock_synth.assert_called_once()
        assert mock_synth.call_args.kwargs["target_lang"] == "French"
        assert mock_synth.call_args.kwargs["voice_gender"] == "FEMALE"

    @patch("src.core.speech_engine.synthesize_speech", return_value="/tmp/out.wav")
    def test_custom_options(self, mock_synth):
        result = mcp_mod.synthesize_speech(
            text="Bonjour",
            target_language="French",
            voice_gender="MALE",
            tts_method="Edge TTS",
            audio_format=".wav",
        )
        assert result["output_path"] == "/tmp/out.wav"
        assert mock_synth.call_args.kwargs["voice_gender"] == "MALE"
        assert mock_synth.call_args.kwargs["audio_format"] == ".wav"

    @patch(
        "src.core.speech_engine.synthesize_speech", return_value="/tmp/specified.mp3"
    )
    def test_explicit_output_path(self, mock_synth):
        result = mcp_mod.synthesize_speech(
            text="Test",
            target_language="Vietnamese",
            output_path="/tmp/specified.mp3",
        )
        assert result["output_path"] == "/tmp/specified.mp3"
        assert mock_synth.call_args.kwargs["output_path"] == "/tmp/specified.mp3"

    @patch("src.core.speech_engine.synthesize_speech")
    def test_auto_generated_temp_path(self, mock_synth):
        mock_synth.side_effect = lambda **kwargs: kwargs["output_path"]

        result = mcp_mod.synthesize_speech(
            text="Hello",
            target_language="French",
        )
        # Should have generated a temp path
        assert result["output_path"]
        assert "tts_" in result["output_path"]
        assert result["output_path"].endswith(".mp3")


# ── query_glossary ────────────────────────────────────────────────


class TestQueryGlossary:
    """Tests for query_glossary MCP tool."""

    def test_list_sets_empty(self):
        result = mcp_mod.query_glossary()
        assert "sets" in result
        assert isinstance(result["sets"], list)

    def test_list_sets_with_data(self):
        from src.core.database import (
            add_glossary_entry,
            create_glossary_set,
            delete_glossary_set,
            get_glossary_sets,
        )

        # Create a test set
        create_glossary_set("MCP Test Set")
        all_sets = get_glossary_sets()
        test_set = next(s for s in all_sets if s[1] == "MCP Test Set")
        sid = test_set[0]

        try:
            add_glossary_entry(sid, "hello", "bonjour")
            add_glossary_entry(sid, "world", "monde")

            result = mcp_mod.query_glossary(active_only=False)
            assert "sets" in result
            mcp_set = next(
                (s for s in result["sets"] if s["name"] == "MCP Test Set"),
                None,
            )
            assert mcp_set is not None
            assert mcp_set["entry_count"] == 2
            assert mcp_set["is_active"] is True
        finally:
            delete_glossary_set(sid)

    def test_query_entries_for_set(self):
        from src.core.database import (
            add_glossary_entry,
            create_glossary_set,
            delete_glossary_set,
            get_glossary_sets,
        )

        create_glossary_set("MCP Entries Test")
        all_sets = get_glossary_sets()
        test_set = next(s for s in all_sets if s[1] == "MCP Entries Test")
        sid = test_set[0]

        try:
            add_glossary_entry(sid, "cat", "chat")
            add_glossary_entry(sid, "dog", "chien")

            result = mcp_mod.query_glossary(set_id=sid)
            assert result["set_id"] == sid
            assert len(result["entries"]) == 2
            sources = {e["source"] for e in result["entries"]}
            assert sources == {"cat", "dog"}
        finally:
            delete_glossary_set(sid)

    def test_query_entries_empty_set(self):
        from src.core.database import (
            create_glossary_set,
            delete_glossary_set,
            get_glossary_sets,
        )

        create_glossary_set("MCP Empty Set")
        all_sets = get_glossary_sets()
        test_set = next(s for s in all_sets if s[1] == "MCP Empty Set")
        sid = test_set[0]

        try:
            result = mcp_mod.query_glossary(set_id=sid)
            assert result["set_id"] == sid
            assert result["entries"] == []
        finally:
            delete_glossary_set(sid)

    @patch(
        "src.core.database.get_active_glossary_sets", return_value=[(1, "Active Set")]
    )
    @patch("src.core.database.get_glossary_entry_count", return_value=5)
    def test_active_only_filter(self, _count, _sets):
        result = mcp_mod.query_glossary(active_only=True)
        assert len(result["sets"]) == 1
        assert result["sets"][0]["is_active"] is True
        assert result["sets"][0]["entry_count"] == 5


# ── Bootstrap ──────────────────────────────────────────────────────


class TestBootstrap:
    """Tests for the MCP server _bootstrap helper."""

    def test_bootstrap_idempotent(self):
        """Calling _bootstrap multiple times should be safe."""
        mcp_mod._bootstrapped = True
        mcp_mod._bootstrap()  # should return immediately
        assert mcp_mod._bootstrapped is True

    @patch("src.core.database.init_db")
    @patch("src.utils.path_manager.configure_logging")
    @patch("src.utils.path_manager.ensure_app_dirs_exist")
    def test_bootstrap_runs_once(self, mock_dirs, mock_log, mock_db):
        mcp_mod._bootstrapped = False
        mcp_mod._bootstrap()
        assert mcp_mod._bootstrapped is True
        mock_dirs.assert_called_once()
        mock_log.assert_called_once()
        mock_db.assert_called_once()

        # Second call should be a no-op
        mcp_mod._bootstrap()
        mock_dirs.assert_called_once()


# ===================================================================
# Backfill — concurrent translate_document, query_glossary scaling,
# transcribe_audio FFmpeg-missing, synthesize_speech early empty check.
# ===================================================================


class TestTranslateDocumentConcurrent:
    """Tests for thread-safety of translate_document tracking."""

    def teardown_method(self) -> None:
        """Drain any leftover entries between tests."""
        with mcp_mod._pipelines_lock:
            mcp_mod._active_pipelines.clear()

    def test_two_threads_both_register_in_active_pipelines(
        self,
        tmp_path: Path,
    ) -> None:
        """Concurrent translate_document calls don't corrupt _active_pipelines.

        Mocks setup_translation_tasks to return a unique ID per call and
        run_translation_pipeline to a sleep, then fires two parallel
        invocations; both task IDs must end up tracked, both threads must
        complete cleanly, and no duplicate-key corruption occurs.
        """
        import time  # noqa: PLC0415

        f1 = tmp_path / "a.docx"
        f1.write_bytes(b"PK")
        f2 = tmp_path / "b.docx"
        f2.write_bytes(b"PK")

        # Each call returns a different task ID.
        ids_iter = iter([(100, str(f1), "", "French"), (200, str(f2), "", "French")])

        def _setup_one(*_args: object, **_kwargs: object) -> list[tuple]:
            return [next(ids_iter)]

        def _slow_pipeline(**_kwargs: object) -> None:
            time.sleep(0.05)

        results: list[dict] = []

        def _call(p: str) -> None:
            r = mcp_mod.translate_document(
                file_paths=[p],
                target_language="French",
            )
            results.append(r)

        with (
            patch(
                "src.utils.config_manager.check_llm_setup",
                return_value=True,
            ),
            patch(
                "src.core.translator.setup_translation_tasks",
                side_effect=_setup_one,
            ),
            patch(
                "src.core.translator.run_translation_pipeline",
                side_effect=_slow_pipeline,
            ),
        ):
            t1 = threading.Thread(target=_call, args=(str(f1),))
            t2 = threading.Thread(target=_call, args=(str(f2),))
            t1.start()
            t2.start()
            t1.join(timeout=5)
            t2.join(timeout=5)

        # Both calls returned a task id.
        assert len(results) == 2
        ids_returned = sorted(r["task_ids"][0] for r in results)
        assert ids_returned == [100, 200]

        # Wait for the daemon pipeline threads to finish so they
        # remove themselves from _active_pipelines.
        for tid in (100, 200):
            with mcp_mod._pipelines_lock:
                entry = mcp_mod._active_pipelines.get(tid)
            if entry:
                entry[0].join(timeout=5)

        with mcp_mod._pipelines_lock:
            assert 100 not in mcp_mod._active_pipelines
            assert 200 not in mcp_mod._active_pipelines

    def test_two_calls_same_file_get_disjoint_task_ids(
        self,
        tmp_path: Path,
    ) -> None:
        """Two concurrent calls on the same file get disjoint task IDs.

        Regression for the failure mode: two concurrent calls naming
        the same file path must receive non-overlapping task IDs and
        non-colliding storage.

        ``setup_translation_tasks`` clones each input into a fresh
        per-task storage directory under a unique task ID, so even if
        an MCP caller (e.g. an LLM acting on a user request twice)
        translates the same file twice, the two requests must each
        get an independent task (no shared output path, no shared
        DB row, no race condition on the cloned source).  Without
        this isolation a double-call would either silently merge
        progress or fail with a "task already exists" error.
        """
        import time  # noqa: PLC0415

        shared = tmp_path / "shared.docx"
        shared.write_bytes(b"PK")

        # Each setup_translation_tasks invocation returns a fresh
        # task ID — mirrors the real DB insert behaviour (auto-
        # increment primary key).
        ids_iter = iter([
            (300, str(shared), "", "French"),
            (301, str(shared), "", "French"),
        ])

        def _setup_one(*_args: object, **_kwargs: object) -> list[tuple]:
            return [next(ids_iter)]

        def _slow_pipeline(**_kwargs: object) -> None:
            time.sleep(0.05)

        results: list[dict] = []

        def _call() -> None:
            r = mcp_mod.translate_document(
                file_paths=[str(shared)],
                target_language="French",
            )
            results.append(r)

        with (
            patch(
                "src.utils.config_manager.check_llm_setup",
                return_value=True,
            ),
            patch(
                "src.core.translator.setup_translation_tasks",
                side_effect=_setup_one,
            ),
            patch(
                "src.core.translator.run_translation_pipeline",
                side_effect=_slow_pipeline,
            ),
        ):
            t1 = threading.Thread(target=_call)
            t2 = threading.Thread(target=_call)
            t1.start()
            t2.start()
            t1.join(timeout=5)
            t2.join(timeout=5)

        assert len(results) == 2
        ids = sorted(r["task_ids"][0] for r in results)
        # Disjoint task IDs even though both calls targeted the same
        # source file path.
        assert ids == [300, 301]

        # Both daemon threads finish cleanly and deregister.
        for tid in (300, 301):
            with mcp_mod._pipelines_lock:
                entry = mcp_mod._active_pipelines.get(tid)
            if entry:
                entry[0].join(timeout=5)
        with mcp_mod._pipelines_lock:
            assert 300 not in mcp_mod._active_pipelines
            assert 301 not in mcp_mod._active_pipelines


class TestQueryGlossaryScaling:
    """Tests verifying query_glossary handles many sets at once."""

    def test_fifty_sets_all_returned(self) -> None:
        """50 mocked sets are all returned with correct entry counts."""
        fake_sets = [(i, f"Set {i}", 1) for i in range(1, 51)]

        def _count(sid: int) -> int:
            return sid * 2  # deterministic but distinct per set

        with (
            patch(
                "src.core.database.get_glossary_sets",
                return_value=fake_sets,
            ),
            patch(
                "src.core.database.get_glossary_entry_count",
                side_effect=_count,
            ),
        ):
            result = mcp_mod.query_glossary(active_only=False)

        assert "sets" in result
        assert len(result["sets"]) == 50  # noqa: PLR2004
        # Spot-check: ID-3 → entry_count=6, ID-50 → entry_count=100.
        by_id = {s["id"]: s for s in result["sets"]}
        assert by_id[3]["entry_count"] == 6  # noqa: PLR2004
        assert by_id[50]["entry_count"] == 100  # noqa: PLR2004
        assert by_id[3]["name"] == "Set 3"


class TestTranscribeAudioFFmpegMissing:
    """Tests for transcribe_audio when FFmpeg is missing.

    The MCP wrapper does not check FFmpeg up front; it delegates to the
    speech engine, which raises ``RuntimeError('FFMPEG_NOT_FOUND')`` from
    inside ``_audio_to_flac()``. The MCP layer simply propagates that.
    """

    def test_m4a_with_missing_ffmpeg_raises_runtime_error(self) -> None:
        """`.m4a` with FFmpeg missing → RuntimeError with a friendly message.

        The bare engine tag ``FFMPEG_NOT_FOUND`` is re-wrapped at the MCP
        boundary so external callers get an actionable error rather than
        an internal sentinel.
        """
        with tempfile.NamedTemporaryFile(suffix=".m4a", delete=False) as f:
            f.write(b"\x00\x00\x00\x20ftypM4A ")
            tmp = f.name

        try:
            with (
                patch(
                    "src.core.speech_engine.transcribe_audio",
                    side_effect=RuntimeError("FFMPEG_NOT_FOUND"),
                ),
                pytest.raises(RuntimeError, match="FFmpeg is required"),
            ):
                mcp_mod.transcribe_audio(tmp, stt_method="Whisper")
        finally:
            Path(tmp).unlink()

    def test_google_cloud_stt_also_rewraps_ffmpeg_not_found(self) -> None:
        """Google Cloud STT also re-wraps the FFMPEG_NOT_FOUND tag.

        The re-wrap is method-agnostic, so the same friendly message
        surfaces regardless of which STT backend reported the error.
        """
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            f.write(b"ID3")
            tmp = f.name

        try:
            with (
                patch(
                    "src.core.speech_engine.transcribe_audio",
                    side_effect=RuntimeError("FFMPEG_NOT_FOUND"),
                ),
                pytest.raises(RuntimeError, match="FFmpeg is required"),
            ):
                mcp_mod.transcribe_audio(tmp, stt_method="Google Cloud")
        finally:
            Path(tmp).unlink()

    def test_other_runtime_errors_pass_through_unchanged(self) -> None:
        """Non-FFmpeg RuntimeErrors propagate unchanged (no false rewrap)."""
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            f.write(b"ID3")
            tmp = f.name

        try:
            with (
                patch(
                    "src.core.speech_engine.transcribe_audio",
                    side_effect=RuntimeError("MODEL_NOT_FOUND"),
                ),
                pytest.raises(RuntimeError, match="MODEL_NOT_FOUND"),
            ):
                mcp_mod.transcribe_audio(tmp, stt_method="Whisper")
        finally:
            Path(tmp).unlink()


class TestSynthesizeSpeechEarlyValidation:
    """Tests verifying synthesize_speech early-rejects bad input."""

    def test_empty_text_rejected_before_engine_invoked(self) -> None:
        """Empty text raises ValueError before any engine call.

        Patching the engine with a side_effect that fails the test if
        invoked confirms early validation: empty/whitespace text never
        reaches the synthesizer.
        """

        def _fail_if_called(**_kwargs: object) -> str:
            pytest.fail("synthesize_speech engine should not have been called")
            return ""

        with patch(
            "src.core.speech_engine.synthesize_speech",
            side_effect=_fail_if_called,
        ):
            with pytest.raises(ValueError, match="Text cannot be empty"):
                mcp_mod.synthesize_speech(text="", target_language="French")
            with pytest.raises(ValueError, match="Text cannot be empty"):
                mcp_mod.synthesize_speech(
                    text="   \t  \n",
                    target_language="French",
                )


# ── Triple-check gap coverage ──────────────────────────────────────


class TestTranslateTextEmptyList:
    """``translate_text`` with an empty ``texts`` list: behaviour pin-down.

    The MCP wrapper does NOT validate ``texts`` to be non-empty up front;
    it forwards the empty list to ``llm_engine.translate_text``. Lock in
    the current pass-through so a future regression that adds early
    validation will break this test deliberately.
    """

    @patch("src.core.llm_engine.translate_text", return_value=[])
    @patch("src.utils.config_manager.check_llm_setup", return_value=True)
    def test_empty_texts_passed_through_unchanged(
        self,
        _mock_setup,
        mock_translate,
    ) -> None:
        result = mcp_mod.translate_text(texts=[], target_language="French")
        assert result == []
        mock_translate.assert_called_once()
        # Empty list flows through to the LLM engine — no early-raise gate.
        assert mock_translate.call_args.kwargs["texts"] == []


class TestTranslateDocumentEmptyList:
    """``translate_document`` with an empty ``file_paths`` list.

    No file-presence loop body executes, but ``setup_translation_tasks``
    is still invoked. With it returning [] the wrapper raises
    "Failed to set up" — surfacing as a RuntimeError. This guards the
    "no work to do" path against silent success.
    """

    @patch("src.core.translator.setup_translation_tasks", return_value=[])
    @patch("src.utils.config_manager.check_llm_setup", return_value=True)
    def test_empty_file_paths_raises_setup_failure(
        self,
        _mock_setup,
        _mock_setup_tasks,
    ) -> None:
        with pytest.raises(RuntimeError, match="Failed to set up"):
            mcp_mod.translate_document(file_paths=[], target_language="French")


class TestTranscribeAudioGenericRuntimeError:
    """``transcribe_audio`` propagates non-FFMPEG RuntimeError unchanged.

    The wrapper has no special-case handling for non-FFMPEG_NOT_FOUND
    runtime errors from the speech engine. Asserts pass-through plus
    ``__cause__`` chain preservation so original tracebacks survive.
    """

    def test_generic_runtime_error_passes_through(self) -> None:
        original = RuntimeError("model load failed: out of memory")
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            f.write(b"\xff\xfb")
            tmp = f.name

        try:
            with (
                patch(
                    "src.core.speech_engine.transcribe_audio",
                    side_effect=original,
                ),
                pytest.raises(
                    RuntimeError,
                    match="model load failed",
                ) as exc_info,
            ):
                mcp_mod.transcribe_audio(tmp, stt_method="Whisper")
        finally:
            Path(tmp).unlink()

        # Pass-through: same exception object, NOT wrapped/replaced.
        assert exc_info.value is original
        # __cause__ stays None — the wrapper does not chain a new exc.
        assert exc_info.value.__cause__ is None

    def test_value_error_from_engine_passes_through(self) -> None:
        """Non-RuntimeError engine errors also propagate (e.g. ValueError)."""
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(b"RIFF")
            tmp = f.name

        try:
            with (
                patch(
                    "src.core.speech_engine.transcribe_audio",
                    side_effect=ValueError("invalid audio header"),
                ),
                pytest.raises(ValueError, match="invalid audio header"),
            ):
                mcp_mod.transcribe_audio(tmp, stt_method="Whisper")
        finally:
            Path(tmp).unlink()


class TestRunPipelineBackgroundCancelEventWired:
    """``_run_pipeline_background`` passes the cancel event into the pipeline.

    Pins that ``cancel_event.is_set`` is the ``is_cancelled`` callable
    handed to ``run_translation_pipeline``. Without this wiring, the
    MCP ``cancel_task`` tool would set the event but the pipeline
    would never check it — making cancellation a silent no-op.
    """

    def test_cancel_event_is_set_is_passed_as_is_cancelled(self) -> None:
        """Cancellable callable comes from the supplied event."""
        import threading  # noqa: PLC0415
        from unittest.mock import MagicMock, patch  # noqa: PLC0415

        captured: dict[str, object] = {}

        def fake_pipeline(**kwargs: object) -> None:
            captured.update(kwargs)

        cancel_event = threading.Event()
        with patch(
            "src.core.translator.run_translation_pipeline",
            side_effect=fake_pipeline,
        ):
            mcp_mod._run_pipeline_background(
                [11],
                config=MagicMock(),
                cancel_event=cancel_event,
            )

        is_cancelled = captured.get("is_cancelled")
        assert callable(is_cancelled)
        # Initially not set → False.
        assert is_cancelled() is False
        # After event.set() → True.
        cancel_event.set()
        assert is_cancelled() is True


class TestSynthesizeSpeechAudioFormatNormalization:
    """``audio_format`` normalisation handles case + whitespace.

    Pins behaviours documented inline in ``synthesize_speech``:
    ``MP3`` / ``  .mp3  `` / ``mp3`` all collapse to ``.mp3``. Without
    this, an MCP caller passing the string from a config UI dropdown
    (which often title-cases / pads values) would surface a confusing
    "Unsupported audio_format" error for what is functionally identical
    input. The negative path (.ogg) is already covered.
    """

    def test_uppercase_extension_accepted(self) -> None:
        """``MP3`` / ``WAV`` (no leading dot) normalise to lowercase."""
        from unittest.mock import patch  # noqa: PLC0415

        with patch(
            "src.core.speech_engine.synthesize_speech",
            return_value="/tmp/out.mp3",
        ) as mock_synth:
            mcp_mod.synthesize_speech(
                text="Hello",
                target_language="French",
                audio_format="MP3",
            )
            assert mock_synth.call_args.kwargs["audio_format"] == ".mp3"

    def test_whitespace_padding_stripped(self) -> None:
        """Surrounding whitespace is trimmed before format dispatch."""
        from unittest.mock import patch  # noqa: PLC0415

        with patch(
            "src.core.speech_engine.synthesize_speech",
            return_value="/tmp/out.wav",
        ) as mock_synth:
            mcp_mod.synthesize_speech(
                text="Hello",
                target_language="French",
                audio_format="  .wav  ",
            )
            assert mock_synth.call_args.kwargs["audio_format"] == ".wav"
