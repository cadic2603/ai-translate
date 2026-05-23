"""Tests for translator utility functions and TranslationWorker internals."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.constants.errors import (
    ERR_FILE_NOT_FOUND,
    ERR_FILE_PASSWORD_PROTECTED,
    ERR_LLM_API_KEY_INVALID,
    ERR_LLM_CONNECTION_FAILED,
    ERR_LLM_INVALID_RESPONSE,
    ERR_LLM_MODEL_NOT_FOUND,
    ERR_LLM_QUOTA_EXCEEDED,
    ERR_LLM_REQUEST_TOO_LARGE,
    ERR_LLM_SERVICE_UNAVAILABLE,
    ERR_LLM_TIMEOUT,
    ERR_LLM_VISION_NOT_SUPPORTED,
    ERR_OCR_ENGINE_NOT_FOUND,
    ERR_OCR_PROCESS_FAILED,
    ERR_OFFICE_CONVERTER_NOT_FOUND,
    ERR_TEXT_READ_FAILED,
    ERR_TEXT_WRITE_FAILED,
    ERR_UNKNOWN,
)
from src.core.config import TranslationConfig
from src.core.database import (
    add_history_entry,
    get_history,
    get_history_entry_status,
    update_history_status,
)
from src.core.translator import (
    TranslationWorker,
    _build_output_name,
    _fetch_all_glossary_entries,
    _get_unique_path,
    _map_error_to_code,
    _pipeline_finalize,
    _pipeline_process_image,
    _pipeline_process_text,
    _pipeline_run_llm,
    _pipeline_run_ocr,
    _resolve_output_dir,
    _update_storage_path,
    resume_unfinished_translations,
    run_translation_pipeline,
    setup_translation_tasks,
)

# ---------------------------------------------------------------------------
# _map_error_to_code
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("message", "expected_code"),
    [
        ("VISION_NOT_SUPPORTED: no vision", ERR_LLM_VISION_NOT_SUPPORTED),
        ("AUTH_ERROR: invalid API key", ERR_LLM_API_KEY_INVALID),
        ("MODEL_NOT_FOUND", ERR_LLM_MODEL_NOT_FOUND),
        ("REQUEST_TOO_LARGE: context exceeded", ERR_LLM_REQUEST_TOO_LARGE),
        ("QUOTA_ERROR: rate limit reached", ERR_LLM_QUOTA_EXCEEDED),
        ("SERVICE_UNAVAILABLE_ERROR", ERR_LLM_SERVICE_UNAVAILABLE),
        ("TIMEOUT_ERROR: request timed out", ERR_LLM_TIMEOUT),
        ("INVALID_RESPONSE: malformed JSON", ERR_LLM_INVALID_RESPONSE),
        ("CONNECTION_ERROR: unreachable", ERR_LLM_CONNECTION_FAILED),
        ("TEXT_READ_ERROR: encoding issue", ERR_TEXT_READ_FAILED),
        ("TEXT_WRITE_ERROR: disk full", ERR_TEXT_WRITE_FAILED),
        ("OFFICE_CONVERTER_NOT_FOUND: missing", ERR_OFFICE_CONVERTER_NOT_FOUND),
    ],
)
def test_map_error_to_code_known_keywords(message: str, expected_code: int) -> None:
    """Each known error keyword maps to the correct error code."""
    assert _map_error_to_code(message) == expected_code


def test_map_error_to_code_unknown_returns_err_unknown() -> None:
    """Unrecognised error strings fall back to ERR_UNKNOWN."""
    assert _map_error_to_code("SomethingTotallyUnrecognised") == ERR_UNKNOWN


def test_map_error_to_code_empty_string() -> None:
    """Empty error string returns ERR_UNKNOWN."""
    assert _map_error_to_code("") == ERR_UNKNOWN


def test_map_error_to_code_keyword_embedded_in_longer_msg() -> None:
    """Keyword match works when embedded inside a longer message."""
    result = _map_error_to_code("Received QUOTA_ERROR from upstream")
    assert result == ERR_LLM_QUOTA_EXCEEDED


# ---------------------------------------------------------------------------
# _get_unique_path
# ---------------------------------------------------------------------------


def test_get_unique_path_no_collision(tmp_path: Path) -> None:
    """Returns the original path when no collision exists."""
    target = tmp_path / "output.png"
    assert _get_unique_path(target) == target


def test_get_unique_path_single_collision(tmp_path: Path) -> None:
    """Returns _1 suffix when the target file already exists."""
    target = tmp_path / "output.png"
    target.touch()
    result = _get_unique_path(target)
    assert result == tmp_path / "output_1.png"
    assert not result.exists()


def test_get_unique_path_multiple_collisions(tmp_path: Path) -> None:
    """Increments suffix counter until a free path is found."""
    target = tmp_path / "output.png"
    target.touch()
    (tmp_path / "output_1.png").touch()
    (tmp_path / "output_2.png").touch()
    result = _get_unique_path(target)
    assert result == tmp_path / "output_3.png"


# ---------------------------------------------------------------------------
# setup_translation_tasks
# ---------------------------------------------------------------------------


def test_setup_translation_tasks_success(tmp_path: Path) -> None:
    """Normal case: DB entry created, file cloned, task returned."""
    src = tmp_path / "doc.txt"
    src.write_text("hello")

    with patch(
        "src.core.translator._path_manager.get_app_data_dir", return_value=tmp_path
    ):
        tasks = setup_translation_tasks([str(src)], "English", "French")

    assert len(tasks) == 1
    h_id, storage_path, src_lang, target_lang = tasks[0]
    assert h_id is not None
    assert Path(storage_path).exists()
    assert src_lang == "English"
    assert target_lang == "French"
    assert get_history_entry_status(h_id) == "Pending"


def test_setup_translation_tasks_missing_file_sets_failed(tmp_path: Path) -> None:
    """Clone failure marks the entry as Failed and it is not returned in tasks."""
    missing = tmp_path / "nonexistent_setup.txt"  # Does not exist

    with patch(
        "src.core.translator._path_manager.get_app_data_dir", return_value=tmp_path
    ):
        tasks = setup_translation_tasks([str(missing)], "English", "French")

    assert tasks == []
    history = get_history()
    entry = next((h for h in history if h[1] == "nonexistent_setup.txt"), None)
    assert entry is not None
    assert entry[4] == "Failed"
    assert entry[9] == ERR_UNKNOWN


# ---------------------------------------------------------------------------
# TranslationWorker._is_cancelled
# ---------------------------------------------------------------------------


def test_is_cancelled_when_worker_stopped(tmp_path: Path) -> None:
    """Returns True when _is_running is False (worker.stop() called)."""
    f = tmp_path / "cancel_stop.png"
    f.touch()
    h_id = add_history_entry(
        "cancel_stop.png", "En", "Fr", "Translating", storage_path=str(f)
    )

    worker = TranslationWorker([])
    worker.stop()  # Sets _is_running = False

    assert worker._is_cancelled(h_id) is True


def test_is_cancelled_when_status_not_translating(tmp_path: Path) -> None:
    """Returns True when DB status is not 'Translating'."""
    f = tmp_path / "cancel_paused.png"
    f.touch()
    h_id = add_history_entry(
        "cancel_paused.png", "En", "Fr", "Paused", storage_path=str(f)
    )

    worker = TranslationWorker([])
    # _is_running is True by default, but status is "Paused"
    assert worker._is_cancelled(h_id) is True


def test_is_cancelled_when_status_translating(tmp_path: Path) -> None:
    """Returns False when _is_running is True and status is 'Translating'."""
    f = tmp_path / "cancel_translating.png"
    f.touch()
    h_id = add_history_entry(
        "cancel_translating.png", "En", "Fr", "Translating", storage_path=str(f)
    )

    worker = TranslationWorker([])
    # _is_running is True, status is "Translating" → not cancelled
    assert worker._is_cancelled(h_id) is False


# ---------------------------------------------------------------------------
# TranslationWorker.run() — already-running guard
# ---------------------------------------------------------------------------


def test_translation_worker_already_running_guard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """run() returns immediately when _is_any_worker_running is True."""
    monkeypatch.setattr(TranslationWorker, "_is_any_worker_running", True)
    worker = TranslationWorker([])
    worker.run()  # Must return without processing anything

    # Flag is still True (early return — finally block not reached)
    assert TranslationWorker._is_any_worker_running is True


# ---------------------------------------------------------------------------
# _pipeline_run_ocr (module-level, extracted from TranslationWorker)
# ---------------------------------------------------------------------------


def test_run_ocr_step_import_error_sets_ocr_not_found(tmp_path: Path) -> None:
    """ImportError from run_ocr → ERR_OCR_ENGINE_NOT_FOUND, returns None."""
    f = tmp_path / "ocr_import.png"
    f.touch()
    h_id = add_history_entry(
        "ocr_import.png", "En", "Fr", "Translating", storage_path=str(f)
    )

    with (
        patch(
            "src.core.translator._ocr_engine.run_ocr",
            side_effect=ImportError("no module named tesseract"),
        ),
        patch("src.core.translator.load_setting", return_value="TesseractOCR"),
    ):
        result = _pipeline_run_ocr(h_id, f)

    assert result is None
    assert get_history_entry_status(h_id) == "Failed"
    entry = next(h for h in get_history() if h[0] == h_id)
    assert entry[9] == ERR_OCR_ENGINE_NOT_FOUND


def test_run_ocr_step_runtime_error_sets_ocr_not_found(tmp_path: Path) -> None:
    """RuntimeError from run_ocr → ERR_OCR_ENGINE_NOT_FOUND, returns None."""
    f = tmp_path / "ocr_runtime.png"
    f.touch()
    h_id = add_history_entry(
        "ocr_runtime.png", "En", "Fr", "Translating", storage_path=str(f)
    )

    with (
        patch(
            "src.core.translator._ocr_engine.run_ocr",
            side_effect=RuntimeError("OCR engine crash"),
        ),
        patch("src.core.translator.load_setting", return_value="TesseractOCR"),
    ):
        result = _pipeline_run_ocr(h_id, f)

    assert result is None
    assert get_history_entry_status(h_id) == "Failed"
    entry = next(h for h in get_history() if h[0] == h_id)
    assert entry[9] == ERR_OCR_ENGINE_NOT_FOUND


def test_run_ocr_step_auth_error_in_exception(tmp_path: Path) -> None:
    """Exception containing AUTH_ERROR → ERR_LLM_API_KEY_INVALID."""
    f = tmp_path / "ocr_auth.png"
    f.touch()
    h_id = add_history_entry(
        "ocr_auth.png", "En", "Fr", "Translating", storage_path=str(f)
    )

    with (
        patch(
            "src.core.translator._ocr_engine.run_ocr",
            side_effect=Exception("AUTH_ERROR: invalid API key"),
        ),
        patch("src.core.translator.load_setting", return_value="GoogleCloud"),
    ):
        result = _pipeline_run_ocr(h_id, f)

    assert result is None
    assert get_history_entry_status(h_id) == "Failed"
    entry = next(h for h in get_history() if h[0] == h_id)
    assert entry[9] == ERR_LLM_API_KEY_INVALID


def test_run_ocr_step_generic_exception_sets_ocr_process_failed(
    tmp_path: Path,
) -> None:
    """Unexpected exception → ERR_OCR_PROCESS_FAILED, returns None."""
    f = tmp_path / "ocr_generic.png"
    f.touch()
    h_id = add_history_entry(
        "ocr_generic.png", "En", "Fr", "Translating", storage_path=str(f)
    )

    with (
        patch(
            "src.core.translator._ocr_engine.run_ocr",
            side_effect=Exception("unexpected failure"),
        ),
        patch("src.core.translator.load_setting", return_value="TesseractOCR"),
    ):
        result = _pipeline_run_ocr(h_id, f)

    assert result is None
    assert get_history_entry_status(h_id) == "Failed"
    entry = next(h for h in get_history() if h[0] == h_id)
    assert entry[9] == ERR_OCR_PROCESS_FAILED


def test_run_ocr_step_success_returns_tuple(tmp_path: Path) -> None:
    """Successful OCR returns (ocr_results, raw_results, method) tuple."""
    f = tmp_path / "ocr_ok.png"
    f.touch()
    h_id = add_history_entry(
        "ocr_ok.png", "En", "Fr", "Translating", storage_path=str(f)
    )

    mock_result = MagicMock(text="Hello", x=0, y=0, w=50, h=20)

    with (
        patch("src.core.translator._ocr_engine.run_ocr", return_value=[mock_result]),
        patch("src.core.translator.load_setting", return_value="TesseractOCR"),
    ):
        result = _pipeline_run_ocr(h_id, f)

    assert result is not None
    ocr_results, raw_results, method = result
    assert len(ocr_results) == 1
    assert method == "TesseractOCR"


def test_run_ocr_step_forwards_src_lang(tmp_path: Path) -> None:
    """_pipeline_run_ocr forwards src_lang to run_ocr."""
    f = tmp_path / "ocr_lang.png"
    f.touch()
    h_id = add_history_entry(
        "ocr_lang.png", "Fr", "En", "Translating", storage_path=str(f)
    )

    mock_result = MagicMock(text="Bonjour", x=0, y=0, w=50, h=20)

    with (
        patch(
            "src.core.translator._ocr_engine.run_ocr", return_value=[mock_result]
        ) as mock_ocr,
        patch("src.core.translator.load_setting", return_value="TesseractOCR"),
    ):
        result = _pipeline_run_ocr(h_id, f, src_lang="French")

    assert result is not None
    mock_ocr.assert_called_once_with(
        str(f),
        method="TesseractOCR",
        src_lang="French",
    )


# ---------------------------------------------------------------------------
# resume_unfinished_translations
# ---------------------------------------------------------------------------


def test_resume_unfinished_returns_none_when_no_tasks() -> None:
    """Returns None when there are no unfinished translation tasks."""
    with patch("src.core.translator.get_unfinished_history", return_value=[]):
        result = resume_unfinished_translations()

    assert result is None


# ---------------------------------------------------------------------------
# _resolve_output_dir
# ---------------------------------------------------------------------------


def test_resolve_output_dir_custom_path(tmp_path: Path) -> None:
    """Returns the user-configured storage path when set."""
    custom = str(tmp_path / "custom_output")
    with patch("src.core.translator.load_setting", return_value=custom):
        result = _resolve_output_dir()

    assert result == Path(custom)


def test_resolve_output_dir_default_fallback(tmp_path: Path) -> None:
    """Falls back to get_desktop_path() when no setting and no source_path."""
    desktop = tmp_path / "FakeDesktop"
    desktop.mkdir()
    with (
        patch("src.core.translator.load_setting", return_value=""),
        patch("src.utils.path_manager.get_desktop_path", return_value=desktop),
    ):
        result = _resolve_output_dir()

    assert result == desktop


def test_resolve_output_dir_source_path_fallback(tmp_path: Path) -> None:
    """Falls back to source file's parent directory when it exists."""
    source_dir = tmp_path / "original"
    source_dir.mkdir()
    source_file = source_dir / "doc.txt"
    source_file.touch()

    with patch("src.core.translator.load_setting", return_value=""):
        result = _resolve_output_dir(source_path=source_file)

    assert result == source_dir


def test_resolve_output_dir_source_path_missing_falls_to_desktop(
    tmp_path: Path,
) -> None:
    """Falls back to Desktop when source directory no longer exists."""
    desktop = tmp_path / "FakeDesktop"
    desktop.mkdir()
    # source_path points to a directory that doesn't exist
    missing_source = tmp_path / "deleted_folder" / "doc.txt"

    with (
        patch("src.core.translator.load_setting", return_value=""),
        patch("src.utils.path_manager.get_desktop_path", return_value=desktop),
    ):
        result = _resolve_output_dir(source_path=missing_source)

    assert result == desktop


def test_resolve_output_dir_custom_path_overrides_source_path(
    tmp_path: Path,
) -> None:
    """User-configured storage path takes priority over source_path."""
    custom = str(tmp_path / "custom_output")
    source_dir = tmp_path / "original"
    source_dir.mkdir()
    source_file = source_dir / "doc.txt"
    source_file.touch()

    with patch("src.core.translator.load_setting", return_value=custom):
        result = _resolve_output_dir(source_path=source_file)

    assert result == Path(custom)


# ---------------------------------------------------------------------------
# _fetch_all_glossary_entries
# ---------------------------------------------------------------------------


def test_fetch_all_glossary_entries_multiple_sets() -> None:
    """Collects entries from multiple active glossary sets."""
    with (
        patch(
            "src.core.translator.get_active_glossary_sets",
            return_value=[(1, "Set A"), (2, "Set B")],
        ),
        patch(
            "src.core.translator.get_glossary_entries",
            side_effect=[
                [(1, "hello", "xin chào")],
                [(2, "world", "thế giới"), (3, "thanks", "cảm ơn")],
            ],
        ),
    ):
        result = _fetch_all_glossary_entries()

    assert len(result) == 3  # noqa: PLR2004
    assert result[0] == (1, "hello", "xin chào")
    assert result[2] == (3, "thanks", "cảm ơn")  # noqa: PLR2004


def test_fetch_all_glossary_entries_empty_when_no_sets() -> None:
    """Returns empty list when no glossary sets are active."""
    with patch(
        "src.core.translator.get_active_glossary_sets",
        return_value=[],
    ):
        result = _fetch_all_glossary_entries()

    assert result == []


# ---------------------------------------------------------------------------
# _build_output_name
# ---------------------------------------------------------------------------


def test_build_output_name_basic() -> None:
    """Produces stem_translated_src_tgt.ext format."""
    result = _build_output_name(
        Path("report.docx"),
        "English (US)",
        "Vietnamese",
    )
    assert result == "report_translated_en-US_vi.docx"


def test_build_output_name_preserves_extension() -> None:
    """Preserves the original file extension."""
    result = _build_output_name(Path("photo.png"), "Japanese", "French")
    assert result == "photo_translated_ja_fr.png"


def test_build_output_name_regional_codes() -> None:
    """Uses full BCP-47 codes for regional language variants."""
    result = _build_output_name(
        Path("data.xlsx"),
        "Chinese (Simplified)",
        "Portuguese (Brazil)",
    )
    assert result == "data_translated_zh-CN_pt-BR.xlsx"


def test_build_output_name_unknown_language_fallback() -> None:
    """Falls back to lowercased label for unknown languages."""
    result = _build_output_name(Path("file.txt"), "Klingon", "Elvish")
    assert result == "file_translated_klingon_elvish.txt"


def test_build_output_name_stem_with_dots() -> None:
    """Handles filenames containing dots in the stem."""
    result = _build_output_name(
        Path("my.report.v2.docx"),
        "German",
        "Spanish",
    )
    assert result == "my.report.v2_translated_de_es.docx"


# ---------------------------------------------------------------------------
# _map_error_to_code — exhaustive coverage of all 13 _ERROR_MAP entries
# ---------------------------------------------------------------------------


def test_map_error_to_code_password_protected() -> None:
    """PASSWORD_PROTECTED keyword maps to ERR_FILE_PASSWORD_PROTECTED."""
    assert _map_error_to_code("PASSWORD_PROTECTED") == ERR_FILE_PASSWORD_PROTECTED


def test_map_error_to_code_password_protected_in_longer_msg() -> None:
    """PASSWORD_PROTECTED embedded in a longer message is still matched."""
    result = _map_error_to_code("File is PASSWORD_PROTECTED and cannot be opened")
    assert result == ERR_FILE_PASSWORD_PROTECTED


@pytest.mark.parametrize(
    ("keyword", "expected_code"),
    [
        ("VISION_NOT_SUPPORTED", ERR_LLM_VISION_NOT_SUPPORTED),
        ("AUTH_ERROR", ERR_LLM_API_KEY_INVALID),
        ("MODEL_NOT_FOUND", ERR_LLM_MODEL_NOT_FOUND),
        ("REQUEST_TOO_LARGE", ERR_LLM_REQUEST_TOO_LARGE),
        ("QUOTA_ERROR", ERR_LLM_QUOTA_EXCEEDED),
        ("SERVICE_UNAVAILABLE_ERROR", ERR_LLM_SERVICE_UNAVAILABLE),
        ("TIMEOUT_ERROR", ERR_LLM_TIMEOUT),
        ("INVALID_RESPONSE", ERR_LLM_INVALID_RESPONSE),
        ("CONNECTION_ERROR", ERR_LLM_CONNECTION_FAILED),
        ("PASSWORD_PROTECTED", ERR_FILE_PASSWORD_PROTECTED),
        ("TEXT_READ_ERROR", ERR_TEXT_READ_FAILED),
        ("TEXT_WRITE_ERROR", ERR_TEXT_WRITE_FAILED),
        ("OFFICE_CONVERTER_NOT_FOUND", ERR_OFFICE_CONVERTER_NOT_FOUND),
    ],
)
def test_map_error_to_code_all_13_keywords(keyword: str, expected_code: int) -> None:
    """Every keyword in _ERROR_MAP maps to the correct error code (all 13)."""
    assert _map_error_to_code(keyword) == expected_code


def test_map_error_to_code_first_match_wins() -> None:
    """When multiple keywords appear, the first match in dict order wins."""
    # _ERROR_MAP iterates in insertion order; AUTH_ERROR appears before QUOTA_ERROR
    msg = "AUTH_ERROR then QUOTA_ERROR"
    assert _map_error_to_code(msg) == ERR_LLM_API_KEY_INVALID


def test_map_error_to_code_case_sensitive() -> None:
    """Keyword matching is case-sensitive."""
    # Lowercase should NOT match the uppercase keys
    assert _map_error_to_code("auth_error") == ERR_UNKNOWN
    assert _map_error_to_code("quota_error") == ERR_UNKNOWN


# ---------------------------------------------------------------------------
# _get_unique_path — additional collision avoidance tests
# ---------------------------------------------------------------------------


def test_get_unique_path_deep_collision_chain(tmp_path: Path) -> None:
    """Increments through many collisions to find a free slot."""
    target = tmp_path / "output.txt"
    target.touch()
    # Create collisions for _1 through _5
    for i in range(1, 6):  # noqa: PLR2004
        (tmp_path / f"output_{i}.txt").touch()
    result = _get_unique_path(target)
    assert result == tmp_path / "output_6.txt"
    assert not result.exists()


def test_get_unique_path_preserves_compound_extension(tmp_path: Path) -> None:
    """Preserves the final extension when stem has dots."""
    target = tmp_path / "my.report.v2.docx"
    target.touch()
    result = _get_unique_path(target)
    # Path.stem = "my.report.v2", Path.suffix = ".docx"
    assert result == tmp_path / "my.report.v2_1.docx"


def test_get_unique_path_no_extension(tmp_path: Path) -> None:
    """Handles files without extensions."""
    target = tmp_path / "Makefile"
    target.touch()
    result = _get_unique_path(target)
    assert result == tmp_path / "Makefile_1"
    assert not result.exists()


# ---------------------------------------------------------------------------
# run_translation_pipeline
# ---------------------------------------------------------------------------


class TestRunTranslationPipeline:
    """Tests for the pure-Python run_translation_pipeline() entry point."""

    def test_pipeline_no_pending_tasks_exits(self) -> None:
        """Empty DB → exits immediately, calls stop_soffice."""
        config = TranslationConfig()

        with (
            patch("src.core.translator.get_unfinished_history", return_value=[]),
            patch("src.core.translator.stop_soffice") as mock_stop,
        ):
            run_translation_pipeline(config)

        mock_stop.assert_called_once()

    def test_pipeline_processes_text_file(self, tmp_path: Path) -> None:
        """Pending .txt entry → calls _pipeline_process_text → marks Done."""
        f = tmp_path / "pipe_text.txt"
        f.write_text("hello")
        h_id = add_history_entry(
            "pipe_text.txt",
            "English",
            "French",
            "Pending",
            storage_path=str(f),
        )
        config = TranslationConfig()

        def _fake_process_text(h: int, *_a: object, **_kw: object) -> None:
            """Mark task Done so the pipeline loop terminates."""
            update_history_status(h, "Done")

        with (
            patch("src.core.translator.stop_soffice"),
            patch(
                "src.core.translator._pipeline_process_text",
                side_effect=_fake_process_text,
            ) as mock_proc,
        ):
            run_translation_pipeline(config)

        # Should have been called with the correct h_id and file path
        assert mock_proc.called
        call_args = mock_proc.call_args
        assert call_args[0][0] == h_id
        assert call_args[0][1] == f

    def test_pipeline_processes_image_file(self, tmp_path: Path) -> None:
        """Pending .png entry → calls _pipeline_process_image."""
        f = tmp_path / "pipe_image.png"
        f.touch()
        h_id = add_history_entry(
            "pipe_image.png",
            "English",
            "French",
            "Pending",
            storage_path=str(f),
        )
        config = TranslationConfig()

        def _fake_process_image(h: int, *_a: object, **_kw: object) -> None:
            """Mark task Done so the pipeline loop terminates."""
            update_history_status(h, "Done")

        with (
            patch("src.core.translator.stop_soffice"),
            patch(
                "src.core.translator._pipeline_process_image",
                side_effect=_fake_process_image,
            ) as mock_proc,
        ):
            run_translation_pipeline(config)

        assert mock_proc.called
        call_args = mock_proc.call_args
        assert call_args[0][0] == h_id

    def test_pipeline_unsupported_format_marks_failed(self, tmp_path: Path) -> None:
        """Pending .xyz entry → marks Failed with ERR_UNKNOWN."""
        f = tmp_path / "pipe_unsupported.xyz"
        f.touch()
        h_id = add_history_entry(
            "pipe_unsupported.xyz",
            "English",
            "French",
            "Pending",
            storage_path=str(f),
        )
        config = TranslationConfig()

        with patch("src.core.translator.stop_soffice"):
            run_translation_pipeline(config)

        assert get_history_entry_status(h_id) == "Failed"
        entry = next(h for h in get_history() if h[0] == h_id)
        assert entry[9] == ERR_UNKNOWN  # noqa: PLR2004

    def test_pipeline_global_cancel_stops_loop(self, tmp_path: Path) -> None:
        """is_cancelled returns True → breaks, calls stop_soffice."""
        f = tmp_path / "pipe_cancel.txt"
        f.write_text("hello")
        add_history_entry(
            "pipe_cancel.txt",
            "English",
            "French",
            "Pending",
            storage_path=str(f),
        )
        config = TranslationConfig()

        with (
            patch("src.core.translator.stop_soffice") as mock_stop,
            patch("src.core.translator._pipeline_process_text") as mock_proc,
        ):
            run_translation_pipeline(config, is_cancelled=lambda: True)

        # Process should not be called because is_cancelled is True
        mock_proc.assert_not_called()
        mock_stop.assert_called_once()

    def test_pipeline_file_not_found_marks_failed(self, tmp_path: Path) -> None:
        """Pending entry with nonexistent storage_path → Failed."""
        missing = tmp_path / "pipe_missing.txt"
        h_id = add_history_entry(
            "pipe_missing.txt",
            "English",
            "French",
            "Pending",
            storage_path=str(missing),
        )
        config = TranslationConfig()

        # Mock get_unfinished_history to return only this task, avoiding
        # contamination from entries created by earlier tests in the session.
        task = [(h_id, str(missing), "English", "French", str(missing))]
        call_count = 0

        def _controlled_history(statuses=None, task_ids=None):
            nonlocal call_count
            call_count += 1
            # First call returns the task; second call returns empty to exit loop
            return task if call_count == 1 else []

        with (
            patch("src.core.translator.stop_soffice"),
            patch(
                "src.core.translator.get_unfinished_history",
                side_effect=_controlled_history,
            ),
        ):
            run_translation_pipeline(config)

        assert get_history_entry_status(h_id) == "Failed"
        entry = next(h for h in get_history() if h[0] == h_id)
        assert entry[9] == ERR_FILE_NOT_FOUND  # noqa: PLR2004

    def test_pipeline_exception_marks_failed(self, tmp_path: Path) -> None:
        """_pipeline_process_text raises → marks Failed with ERR_UNKNOWN."""
        f = tmp_path / "pipe_exc.txt"
        f.write_text("hello")
        h_id = add_history_entry(
            "pipe_exc.txt",
            "English",
            "French",
            "Pending",
            storage_path=str(f),
        )
        config = TranslationConfig()

        with (
            patch("src.core.translator.stop_soffice"),
            patch(
                "src.core.translator._pipeline_process_text",
                side_effect=RuntimeError("boom"),
            ),
        ):
            run_translation_pipeline(config)

        assert get_history_entry_status(h_id) == "Failed"

    def test_pipeline_memory_error_marks_failed(self, tmp_path: Path) -> None:
        """MemoryError → marks Failed with ERR_UNKNOWN."""
        f = tmp_path / "pipe_mem.txt"
        f.write_text("hello")
        h_id = add_history_entry(
            "pipe_mem.txt",
            "English",
            "French",
            "Pending",
            storage_path=str(f),
        )
        config = TranslationConfig()

        with (
            patch("src.core.translator.stop_soffice"),
            patch(
                "src.core.translator._pipeline_process_text",
                side_effect=MemoryError("out of memory"),
            ),
        ):
            run_translation_pipeline(config)

        assert get_history_entry_status(h_id) == "Failed"
        entry = next(h for h in get_history() if h[0] == h_id)
        assert entry[9] == ERR_UNKNOWN  # noqa: PLR2004

    def test_pipeline_stops_soffice_on_exception(self, tmp_path: Path) -> None:
        """Even when an unexpected exception occurs, stop_soffice is called."""
        config = TranslationConfig()

        with (
            patch(
                "src.core.translator.get_unfinished_history",
                side_effect=RuntimeError("DB error"),
            ),
            patch("src.core.translator.stop_soffice") as mock_stop,
            pytest.raises(RuntimeError, match="DB error"),
        ):
            run_translation_pipeline(config)

        mock_stop.assert_called_once()

    def test_pipeline_strips_at_from_storage_path(self, tmp_path: Path) -> None:
        """storage_path starting with '@' gets stripped before use."""
        f = tmp_path / "pipe_at.txt"
        f.write_text("hello")
        # Prefix storage_path with '@' to simulate corruption
        add_history_entry(
            "pipe_at.txt",
            "English",
            "French",
            "Pending",
            storage_path="@" + str(f),
        )
        config = TranslationConfig()

        def _fake_process_text(h: int, *_a: object, **_kw: object) -> None:
            """Mark task Done so the pipeline loop terminates."""
            update_history_status(h, "Done")

        with (
            patch("src.core.translator.stop_soffice"),
            patch(
                "src.core.translator._pipeline_process_text",
                side_effect=_fake_process_text,
            ) as mock_proc,
        ):
            run_translation_pipeline(config)

        # The '@' should be stripped, so file_path arg should be the real path
        assert mock_proc.called
        call_args = mock_proc.call_args
        assert call_args[0][1] == f


# ---------------------------------------------------------------------------
# _pipeline_finalize
# ---------------------------------------------------------------------------


class TestPipelineFinalize:
    """Tests for _pipeline_finalize() status transitions."""

    def test_finalize_translating_to_done(self, tmp_path: Path) -> None:
        """status=Translating, auto_remove=False → Done."""
        f = tmp_path / "fin_done.txt"
        f.touch()
        h_id = add_history_entry(
            "fin_done.txt",
            "En",
            "Fr",
            "Translating",
            storage_path=str(f),
        )
        config = TranslationConfig(auto_remove_history=False)
        _pipeline_finalize(h_id, config)

        assert get_history_entry_status(h_id) == "Done"

    def test_finalize_auto_remove_deletes(self, tmp_path: Path) -> None:
        """status=Translating, auto_remove=True → entry deleted."""
        f = tmp_path / "fin_remove.txt"
        f.touch()
        h_id = add_history_entry(
            "fin_remove.txt",
            "En",
            "Fr",
            "Translating",
            storage_path=str(f),
        )
        config = TranslationConfig(auto_remove_history=True)
        _pipeline_finalize(h_id, config)

        # Entry should be gone
        assert get_history_entry_status(h_id) is None

    def test_finalize_failed_no_change(self, tmp_path: Path) -> None:
        """status=Failed → no status change (not deleted, not Done)."""
        f = tmp_path / "fin_failed.txt"
        f.touch()
        h_id = add_history_entry(
            "fin_failed.txt",
            "En",
            "Fr",
            "Failed",
            storage_path=str(f),
        )
        config = TranslationConfig(auto_remove_history=False)
        _pipeline_finalize(h_id, config)

        # Failed is allowed in the function, but only transitions
        # to Done if status was Translating
        assert get_history_entry_status(h_id) == "Failed"

    def test_finalize_paused_no_change(self, tmp_path: Path) -> None:
        """status=Paused → no-op (not in Translating/Failed)."""
        f = tmp_path / "fin_paused.txt"
        f.touch()
        h_id = add_history_entry(
            "fin_paused.txt",
            "En",
            "Fr",
            "Paused",
            storage_path=str(f),
        )
        config = TranslationConfig(auto_remove_history=False)
        _pipeline_finalize(h_id, config)

        assert get_history_entry_status(h_id) == "Paused"

    def test_finalize_auto_remove_failed_keeps(self, tmp_path: Path) -> None:
        """status=Failed, auto_remove=True → keeps entry (only removes Translating)."""
        f = tmp_path / "fin_keep_failed.txt"
        f.touch()
        h_id = add_history_entry(
            "fin_keep_failed.txt",
            "En",
            "Fr",
            "Failed",
            storage_path=str(f),
        )
        config = TranslationConfig(auto_remove_history=True)
        _pipeline_finalize(h_id, config)

        # Failed entries should NOT be deleted even with auto_remove=True
        assert get_history_entry_status(h_id) == "Failed"

    def test_finalize_config_injection(self, tmp_path: Path) -> None:
        """Config injection bypasses load_setting."""
        f = tmp_path / "fin_config.txt"
        f.touch()
        h_id = add_history_entry(
            "fin_config.txt",
            "En",
            "Fr",
            "Translating",
            storage_path=str(f),
        )
        # Config says do NOT auto-remove
        config = TranslationConfig(auto_remove_history=False)

        with patch("src.core.translator.load_setting") as mock_ls:
            _pipeline_finalize(h_id, config)

        # load_setting should NOT be called when config is provided
        mock_ls.assert_not_called()
        assert get_history_entry_status(h_id) == "Done"


# ---------------------------------------------------------------------------
# _pipeline_process_text
# ---------------------------------------------------------------------------


class TestPipelineProcessText:
    """Tests for _pipeline_process_text() text file translation pipeline."""

    def test_process_text_success(self, tmp_path: Path) -> None:
        """translate_file returns True → progress 100, finalized to Done."""
        f = tmp_path / "proc_ok.txt"
        f.write_text("hello")
        h_id = add_history_entry(
            "proc_ok.txt",
            "English",
            "French",
            "Translating",
            storage_path=str(f),
        )
        config = TranslationConfig(
            storage_path=str(tmp_path),
            auto_remove_history=False,
        )

        with (
            patch("src.core.translator.translate_file", return_value=True),
            patch(
                "src.core.translator._fetch_all_glossary_entries",
                return_value=[],
            ),
            patch("src.core.translator.clear_checkpoints"),
        ):
            _pipeline_process_text(h_id, f, "English", "French", config)

        assert get_history_entry_status(h_id) == "Done"

    def test_process_text_cancelled(self, tmp_path: Path) -> None:
        """translate_file returns False → no status change (cancelled)."""
        f = tmp_path / "proc_cancel.txt"
        f.write_text("hello")
        h_id = add_history_entry(
            "proc_cancel.txt",
            "English",
            "French",
            "Translating",
            storage_path=str(f),
        )
        config = TranslationConfig(
            storage_path=str(tmp_path),
            auto_remove_history=False,
        )

        with (
            patch("src.core.translator.translate_file", return_value=False),
            patch(
                "src.core.translator._fetch_all_glossary_entries",
                return_value=[],
            ),
        ):
            _pipeline_process_text(h_id, f, "English", "French", config)

        # Status should stay Translating (not finalized when cancelled)
        assert get_history_entry_status(h_id) == "Translating"

    def test_process_text_error_maps_to_code(self, tmp_path: Path) -> None:
        """translate_file raises ValueError('AUTH_ERROR') → Failed with correct code."""
        f = tmp_path / "proc_auth.txt"
        f.write_text("hello")
        h_id = add_history_entry(
            "proc_auth.txt",
            "English",
            "French",
            "Translating",
            storage_path=str(f),
        )
        config = TranslationConfig(
            storage_path=str(tmp_path),
            auto_remove_history=False,
        )

        with (
            patch(
                "src.core.translator.translate_file",
                side_effect=ValueError("AUTH_ERROR: invalid API key"),
            ),
            patch(
                "src.core.translator._fetch_all_glossary_entries",
                return_value=[],
            ),
        ):
            _pipeline_process_text(h_id, f, "English", "French", config)

        assert get_history_entry_status(h_id) == "Failed"
        entry = next(h for h in get_history() if h[0] == h_id)
        assert entry[9] == ERR_LLM_API_KEY_INVALID  # noqa: PLR2004

    def test_process_text_fetches_glossary(self, tmp_path: Path) -> None:
        """_pipeline_process_text calls _fetch_all_glossary_entries."""
        f = tmp_path / "proc_gloss.txt"
        f.write_text("hello")
        h_id = add_history_entry(
            "proc_gloss.txt",
            "English",
            "French",
            "Translating",
            storage_path=str(f),
        )
        config = TranslationConfig(
            storage_path=str(tmp_path),
            auto_remove_history=False,
        )

        with (
            patch("src.core.translator.translate_file", return_value=True),
            patch(
                "src.core.translator._fetch_all_glossary_entries",
                return_value=[(1, "hello", "bonjour")],
            ) as mock_gloss,
            patch("src.core.translator.clear_checkpoints"),
        ):
            _pipeline_process_text(h_id, f, "English", "French", config)

        mock_gloss.assert_called_once()

    def test_process_text_auto_convert_legacy(self, tmp_path: Path) -> None:
        """auto_convert_legacy=True, .doc file → convert_to_modern_format called."""
        f = tmp_path / "proc_legacy.doc"
        f.write_text("hello")
        h_id = add_history_entry(
            "proc_legacy.doc",
            "English",
            "French",
            "Translating",
            storage_path=str(f),
        )
        config = TranslationConfig(
            storage_path=str(tmp_path),
            auto_convert_legacy=True,
            auto_remove_history=False,
        )

        with (
            patch(
                "src.core.translator.convert_to_modern_format",
                return_value=True,
            ) as mock_convert,
            patch("src.core.translator.translate_file", return_value=True),
            patch(
                "src.core.translator._fetch_all_glossary_entries",
                return_value=[],
            ),
            patch("src.core.translator.clear_checkpoints"),
        ):
            _pipeline_process_text(h_id, f, "English", "French", config)

        # convert_to_modern_format should have been called
        mock_convert.assert_called_once()
        call_args = mock_convert.call_args[0]
        assert str(call_args[0]).endswith(".doc")
        assert str(call_args[1]).endswith(".docx")


# ---------------------------------------------------------------------------
# _update_storage_path
# ---------------------------------------------------------------------------


class TestPipelineOdfAutoConvert:
    """Tests for ODF auto-convert path in _pipeline_process_text."""

    def test_process_text_auto_convert_odf(self, tmp_path: Path) -> None:
        """auto_convert_odf=True, .odt file → convert_to_modern_format called."""
        f = tmp_path / "proc_odf.odt"
        f.write_text("hello")
        h_id = add_history_entry(
            "proc_odf.odt",
            "English",
            "French",
            "Translating",
            storage_path=str(f),
        )
        config = TranslationConfig(
            storage_path=str(tmp_path),
            auto_convert_odf=True,
            auto_remove_history=False,
        )

        with (
            patch(
                "src.core.translator.convert_to_modern_format",
                return_value=True,
            ) as mock_convert,
            patch(
                "src.core.translator.translate_file",
                return_value=True,
            ),
            patch(
                "src.core.translator._fetch_all_glossary_entries",
                return_value=[],
            ),
            patch("src.core.translator.clear_checkpoints"),
        ):
            _pipeline_process_text(
                h_id,
                f,
                "English",
                "French",
                config,
            )

        # convert_to_modern_format should have been called
        mock_convert.assert_called_once()
        call_args = mock_convert.call_args[0]
        assert str(call_args[0]).endswith(".odt")
        assert str(call_args[1]).endswith(".docx")


class TestPipelineConversionFailure:
    """Tests for convert_to_modern_format failure path in _pipeline_process_text."""

    def test_pipeline_legacy_conversion_failure_continues(
        self,
        tmp_path: Path,
    ) -> None:
        """Conversion failure → translation proceeds with original format."""
        f = tmp_path / "proc_legacy_fail.doc"
        f.write_text("hello")
        h_id = add_history_entry(
            "proc_legacy_fail.doc",
            "English",
            "French",
            "Translating",
            storage_path=str(f),
        )
        config = TranslationConfig(
            storage_path=str(tmp_path),
            auto_convert_legacy=True,
            auto_remove_history=False,
        )

        with (
            patch(
                "src.core.translator.convert_to_modern_format",
                return_value=False,
            ) as mock_convert,
            patch(
                "src.core.translator.translate_file",
                return_value=True,
            ) as mock_translate,
            patch(
                "src.core.translator._fetch_all_glossary_entries",
                return_value=[],
            ),
            patch("src.core.translator.clear_checkpoints"),
        ):
            _pipeline_process_text(
                h_id,
                f,
                "English",
                "French",
                config,
            )

        # convert_to_modern_format was attempted
        mock_convert.assert_called_once()
        # translate_file still called with original .doc (not .docx)
        assert mock_translate.called
        first_arg = mock_translate.call_args[0][0]
        assert str(first_arg).endswith(".doc")


# ---------------------------------------------------------------------------
# _update_storage_path
# ---------------------------------------------------------------------------


class TestUpdateStoragePath:
    """Tests for _update_storage_path (DB helper)."""

    def test_update_storage_path_valid(self) -> None:
        """Updating storage_path for an existing entry stores the new value."""
        h_id = add_history_entry(
            "usp_valid.png",
            "English",
            "French",
            "Translating",
            storage_path="/old/path.png",
        )
        _update_storage_path(h_id, "/new/path.png")

        rows = get_history()
        row = next(r for r in rows if r[0] == h_id)
        assert row[8] == "/new/path.png"  # noqa: PLR2004

    def test_update_storage_path_nonexistent_id(self) -> None:
        """Calling with a non-existent ID is a no-op (no crash)."""
        fake_id = 99999  # noqa: PLR2004
        # Should not raise — SQLite UPDATE on zero rows is valid
        _update_storage_path(fake_id, "/some/path.png")

    def test_update_storage_path_empty_path(self) -> None:
        """An empty string is a valid storage_path value in SQLite."""
        h_id = add_history_entry(
            "usp_empty.png",
            "English",
            "French",
            "Translating",
            storage_path="/initial/path.png",
        )
        _update_storage_path(h_id, "")

        rows = get_history()
        row = next(r for r in rows if r[0] == h_id)
        assert row[8] == ""


# ---------------------------------------------------------------------------
# _pipeline_run_llm
# ---------------------------------------------------------------------------


class TestPipelineRunLlm:
    """Tests for _pipeline_run_llm (LLM step of image pipeline)."""

    def test_pipeline_run_llm_success(self, tmp_path: Path) -> None:
        """Successful LLM call returns the merged paragraph tuple."""
        f = tmp_path / "llm_ok.png"
        f.write_bytes(b"\x89PNG")
        h_id = add_history_entry(
            "llm_ok.png",
            "English",
            "French",
            "Translating",
            storage_path=str(f),
        )
        ocr_data = (
            [{"text": "hello", "bbox": [0, 0, 100, 50]}],
            [{"text": "hello", "bbox": [0, 0, 100, 50]}],
            "tesseract",
        )
        merged = (["hello"], ["bonjour"], [{"text": "hello"}])
        with (
            patch(
                "src.core.translator._fetch_all_glossary_entries",
                return_value=[],
            ),
            patch(
                "src.core.translator._llm_engine.translate_image_content",
                return_value={"paragraphs": []},
            ),
            patch(
                "src.core.translator.merge_to_paragraphs",
                return_value=merged,
            ) as mock_merge,
            patch("src.core.translator.update_history_progress"),
        ):
            result = _pipeline_run_llm(h_id, f, ocr_data, "English", "French")

        assert result == merged
        mock_merge.assert_called_once()

    def test_pipeline_run_llm_error_marks_failed(self, tmp_path: Path) -> None:
        """AUTH_ERROR during LLM marks the entry as Failed."""
        f = tmp_path / "llm_fail.png"
        f.write_bytes(b"\x89PNG")
        h_id = add_history_entry(
            "llm_fail.png",
            "English",
            "French",
            "Translating",
            storage_path=str(f),
        )
        ocr_data = (
            [{"text": "hello"}],
            [{"text": "hello"}],
            "tesseract",
        )
        with (
            patch(
                "src.core.translator._fetch_all_glossary_entries",
                return_value=[],
            ),
            patch(
                "src.core.translator._llm_engine.translate_image_content",
                side_effect=ValueError("AUTH_ERROR"),
            ),
            patch("src.core.translator.update_history_progress"),
        ):
            result = _pipeline_run_llm(h_id, f, ocr_data, "English", "French")

        assert result is None
        status = get_history_entry_status(h_id)
        assert status == "Failed"

    def test_pipeline_run_llm_empty_ocr(self, tmp_path: Path) -> None:
        """Empty ocr_results list still calls translate_image_content."""
        f = tmp_path / "llm_empty.png"
        f.write_bytes(b"\x89PNG")
        h_id = add_history_entry(
            "llm_empty.png",
            "English",
            "French",
            "Translating",
            storage_path=str(f),
        )
        ocr_data: tuple[list, list, str] = ([], [], "tesseract")
        merged = ([], [], [])
        with (
            patch(
                "src.core.translator._fetch_all_glossary_entries",
                return_value=[],
            ),
            patch(
                "src.core.translator._llm_engine.translate_image_content",
                return_value={"paragraphs": []},
            ) as mock_tic,
            patch(
                "src.core.translator.merge_to_paragraphs",
                return_value=merged,
            ),
            patch("src.core.translator.update_history_progress"),
        ):
            result = _pipeline_run_llm(h_id, f, ocr_data, "English", "French")

        assert result == merged
        mock_tic.assert_called_once()


# ---------------------------------------------------------------------------
# _pipeline_process_image
# ---------------------------------------------------------------------------


class TestPipelineProcessImage:
    """Tests for _pipeline_process_image (full image pipeline)."""

    def test_pipeline_process_image_file_not_exist(
        self,
        tmp_path: Path,
    ) -> None:
        """Non-existent file path does not crash (early stages handle it)."""
        missing = tmp_path / "no_such_file.png"
        h_id = add_history_entry(
            "no_such_file.png",
            "English",
            "French",
            "Translating",
            storage_path=str(missing),
        )
        config = TranslationConfig(
            storage_path=str(tmp_path),
            auto_remove_history=False,
        )
        with (
            patch(
                "src.core.translator.load_llm_checkpoint",
                return_value=None,
            ),
            patch(
                "src.core.translator.load_ocr_checkpoint",
                return_value=None,
            ),
            patch(
                "src.core.translator._pipeline_run_ocr",
                return_value=None,
            ) as mock_ocr,
        ):
            # Should not raise even though the file doesn't exist
            _pipeline_process_image(
                h_id,
                missing,
                "English",
                "French",
                config,
            )
        # OCR step was attempted (returned None → pipeline exits gracefully)
        mock_ocr.assert_called_once()

    def test_pipeline_process_image_cancelled_between_ocr_llm(
        self,
        tmp_path: Path,
    ) -> None:
        """Cancellation after OCR prevents LLM from running."""
        f = tmp_path / "cancel_mid.png"
        f.write_bytes(b"\x89PNG")
        h_id = add_history_entry(
            "cancel_mid.png",
            "English",
            "French",
            "Translating",
            storage_path=str(f),
        )
        config = TranslationConfig(
            storage_path=str(tmp_path),
            auto_remove_history=False,
        )
        ocr_data = (
            [{"text": "hello"}],
            [{"text": "hello"}],
            "tesseract",
        )
        with (
            patch(
                "src.core.translator.load_llm_checkpoint",
                return_value=None,
            ),
            patch(
                "src.core.translator.load_ocr_checkpoint",
                return_value=ocr_data,
            ),
            patch("src.core.translator.update_history_progress"),
            patch(
                "src.core.translator._pipeline_run_llm",
            ) as mock_llm,
        ):
            # cancel_check returns True → pipeline should stop before LLM
            _pipeline_process_image(
                h_id,
                f,
                "English",
                "French",
                config,
                cancel_check=lambda _: True,
            )
        mock_llm.assert_not_called()

    def test_pipeline_process_image_success(self, tmp_path: Path) -> None:
        """Full successful pipeline marks entry as Done."""
        f = tmp_path / "img_ok.png"
        f.write_bytes(b"\x89PNG")
        h_id = add_history_entry(
            "img_ok.png",
            "English",
            "French",
            "Translating",
            storage_path=str(f),
        )
        config = TranslationConfig(
            storage_path=str(tmp_path),
            auto_remove_history=False,
        )
        llm_checkpoint = (
            [{"text": "hello"}],
            ["bonjour"],
            [{"text": "hello"}],
        )
        with (
            patch(
                "src.core.translator.load_llm_checkpoint",
                return_value=llm_checkpoint,
            ),
            patch("src.core.translator.update_history_progress"),
            patch(
                "src.core.translator._resolve_output_dir",
                return_value=tmp_path,
            ),
            patch(
                "src.core.translator.process_image_translation",
                return_value=True,
            ),
            patch("src.core.translator.clear_checkpoints"),
        ):
            _pipeline_process_image(
                h_id,
                f,
                "English",
                "French",
                config,
            )

        status = get_history_entry_status(h_id)
        assert status == "Done"


# ---------------------------------------------------------------------------
# _pipeline_finalize — auto_remove wipe + skip non-translating (new tests)
# ---------------------------------------------------------------------------

_MOD = "src.core.translator"


class TestPipelineFinalizeAutoRemoveWipe:
    """Verify _pipeline_finalize calls wipe_history_directory on auto-remove."""

    def test_pipeline_finalize_auto_remove_on_success(self, tmp_path: Path) -> None:
        """auto_remove=True + Translating → delete + wipe."""
        f = tmp_path / "fin_wipe.txt"
        f.touch()
        h_id = add_history_entry(
            "fin_wipe.txt",
            "En",
            "Fr",
            "Translating",
            storage_path=str(f),
        )
        fake_storage = "/fake/storage/path"

        with (
            patch(
                f"{_MOD}.get_history_entry_status",
                return_value="Translating",
            ),
            patch(
                f"{_MOD}.delete_history_entry",
                return_value=fake_storage,
            ) as mock_delete,
            patch(
                f"{_MOD}.wipe_history_directory",
            ) as mock_wipe,
            patch(f"{_MOD}.load_setting", return_value=True),
        ):
            _pipeline_finalize(h_id)

        mock_delete.assert_called_once_with(h_id)
        mock_wipe.assert_called_once_with(fake_storage)


class TestPipelineFinalizeSkipsNonTranslating:
    """Verify _pipeline_finalize is a no-op for non-Translating/Failed statuses."""

    def test_pipeline_finalize_skips_non_translating(self, tmp_path: Path) -> None:
        """status=Paused → no update_history_status call."""
        f = tmp_path / "fin_skip.txt"
        f.touch()
        h_id = add_history_entry(
            "fin_skip.txt",
            "En",
            "Fr",
            "Paused",
            storage_path=str(f),
        )

        with (
            patch(
                f"{_MOD}.get_history_entry_status",
                return_value="Paused",
            ),
            patch(f"{_MOD}.update_history_status") as mock_update,
            patch(f"{_MOD}.delete_history_entry") as mock_delete,
        ):
            config = TranslationConfig(auto_remove_history=False)
            _pipeline_finalize(h_id, config)

        mock_update.assert_not_called()
        mock_delete.assert_not_called()

    def test_pipeline_finalize_skips_done_status(self, tmp_path: Path) -> None:
        """status=Done → no-op (not in Translating/Failed)."""
        f = tmp_path / "fin_done2.txt"
        f.touch()
        h_id = add_history_entry(
            "fin_done2.txt",
            "En",
            "Fr",
            "Done",
            storage_path=str(f),
        )

        with (
            patch(
                f"{_MOD}.get_history_entry_status",
                return_value="Done",
            ),
            patch(f"{_MOD}.update_history_status") as mock_update,
            patch(f"{_MOD}.delete_history_entry") as mock_delete,
        ):
            config = TranslationConfig(auto_remove_history=True)
            _pipeline_finalize(h_id, config)

        mock_update.assert_not_called()
        mock_delete.assert_not_called()


# ---------------------------------------------------------------------------
# run_translation_pipeline — MemoryError on image processing
# ---------------------------------------------------------------------------


class TestPipelineMemoryErrorImage:
    """Verify MemoryError during image processing maps to ERR_UNKNOWN."""

    def test_pipeline_run_translation_memory_error(self, tmp_path: Path) -> None:
        """MemoryError in _pipeline_process_image → Failed with ERR_UNKNOWN."""
        f = tmp_path / "pipe_mem_img.png"
        f.touch()
        h_id = add_history_entry(
            "pipe_mem_img.png",
            "English",
            "French",
            "Pending",
            storage_path=str(f),
        )
        config = TranslationConfig()

        # Mock get_unfinished_history to return only this task, avoiding
        # contamination from entries created by earlier tests in the session.
        task = [(h_id, str(f), "English", "French", str(f))]
        call_count = 0

        def _controlled_history(statuses=None, task_ids=None):
            nonlocal call_count
            call_count += 1
            return task if call_count == 1 else []

        with (
            patch(f"{_MOD}.stop_soffice"),
            patch(
                f"{_MOD}.get_unfinished_history",
                side_effect=_controlled_history,
            ),
            patch(
                f"{_MOD}._pipeline_process_image",
                side_effect=MemoryError("out of memory"),
            ),
        ):
            run_translation_pipeline(config)

        assert get_history_entry_status(h_id) == "Failed"
        entry = next(h for h in get_history() if h[0] == h_id)
        assert entry[9] == ERR_UNKNOWN  # noqa: PLR2004


# ---------------------------------------------------------------------------
# resume_unfinished_translations — worker creation, config forwarding, statuses
# ---------------------------------------------------------------------------


class TestResumeUnfinishedTranslations:
    """Tests for resume_unfinished_translations() worker lifecycle."""

    def test_resume_unfinished_creates_worker_when_tasks_exist(
        self,
        tmp_path: Path,
    ) -> None:
        """Worker is created and started when tasks exist."""
        tasks = [
            (1, str(tmp_path / "a.txt"), "English", "French", str(tmp_path)),
        ]
        with (
            patch(
                "src.core.translator.get_unfinished_history",
                return_value=tasks,
            ),
            patch.object(TranslationWorker, "start") as mock_start,
        ):
            worker = resume_unfinished_translations()

        assert worker is not None
        assert isinstance(worker, TranslationWorker)
        mock_start.assert_called_once()

    def test_resume_unfinished_forwards_config(
        self,
        tmp_path: Path,
    ) -> None:
        """Config parameter is forwarded to the TranslationWorker."""
        tasks = [
            (1, str(tmp_path / "a.txt"), "English", "French", str(tmp_path)),
        ]
        config = TranslationConfig(storage_path="/custom/path")
        with (
            patch(
                "src.core.translator.get_unfinished_history",
                return_value=tasks,
            ),
            patch.object(TranslationWorker, "start"),
        ):
            worker = resume_unfinished_translations(config=config)

        assert worker is not None
        assert worker._config is config

    def test_resume_unfinished_respects_custom_statuses(self) -> None:
        """Custom statuses tuple is forwarded to get_unfinished_history."""
        custom_statuses = ("Pending",)
        with (
            patch(
                "src.core.translator.get_unfinished_history",
                return_value=[],
            ) as mock_get,
        ):
            result = resume_unfinished_translations(statuses=custom_statuses)

        assert result is None
        mock_get.assert_called_once_with(statuses=custom_statuses)


# ---------------------------------------------------------------------------
# _pipeline_process_text — update_history_file_name on legacy convert
# ---------------------------------------------------------------------------


class TestPipelineProcessTextFilenameUpdate:
    """Verify update_history_file_name is called after legacy->modern conversion."""

    def test_process_text_updates_db_file_name_on_convert(
        self,
        tmp_path: Path,
    ) -> None:
        """After legacy->modern conversion, update_history_file_name is called."""
        f = tmp_path / "legacy_rename.doc"
        f.write_text("hello")
        h_id = add_history_entry(
            "legacy_rename.doc",
            "English",
            "French",
            "Translating",
            storage_path=str(f),
        )
        config = TranslationConfig(
            storage_path=str(tmp_path),
            auto_convert_legacy=True,
            auto_remove_history=False,
        )

        with (
            patch(
                "src.core.translator.convert_to_modern_format",
                return_value=True,
            ),
            patch(
                "src.core.translator.update_history_file_name",
            ) as mock_rename,
            patch(
                "src.core.translator.translate_file",
                return_value=True,
            ),
            patch(
                "src.core.translator._fetch_all_glossary_entries",
                return_value=[],
            ),
            patch("src.core.translator.clear_checkpoints"),
        ):
            _pipeline_process_text(
                h_id,
                f,
                "English",
                "French",
                config,
            )

        # update_history_file_name should be called with the modern filename
        mock_rename.assert_called_once_with(h_id, "legacy_rename.docx")


# ---------------------------------------------------------------------------
# _pipeline_process_image — OCR checkpoint resume
# ---------------------------------------------------------------------------


class TestPipelineProcessImageOcrCheckpoint:
    """Verify OCR checkpoint resume skips OCR step."""

    def test_pipeline_process_image_ocr_checkpoint_resume(
        self,
        tmp_path: Path,
    ) -> None:
        """OCR checkpoint is reused, skipping _pipeline_run_ocr."""
        f = tmp_path / "img_ocr_cp.png"
        f.write_bytes(b"\x89PNG")
        h_id = add_history_entry(
            "img_ocr_cp.png",
            "English",
            "French",
            "Translating",
            storage_path=str(f),
        )
        config = TranslationConfig(
            storage_path=str(tmp_path),
            auto_remove_history=False,
        )
        # OCR checkpoint data: (ocr_results, raw_ocr_results, method)
        ocr_checkpoint = (
            [{"text": "hello", "bbox": [0, 0, 100, 50]}],
            [{"text": "hello", "bbox": [0, 0, 100, 50]}],
            "tesseract",
        )
        merged = (["hello"], ["bonjour"], [{"text": "hello"}])

        with (
            patch(
                "src.core.translator.load_llm_checkpoint",
                return_value=None,
            ),
            patch(
                "src.core.translator.load_ocr_checkpoint",
                return_value=ocr_checkpoint,
            ),
            patch(
                "src.core.translator._pipeline_run_ocr",
            ) as mock_run_ocr,
            patch("src.core.translator.update_history_progress"),
            patch(
                "src.core.translator._pipeline_run_llm",
                return_value=merged,
            ),
            patch("src.core.translator.save_llm_checkpoint"),
            patch(
                "src.core.translator._resolve_output_dir",
                return_value=tmp_path,
            ),
            patch(
                "src.core.translator.process_image_translation",
                return_value=True,
            ),
            patch("src.core.translator.clear_checkpoints"),
        ):
            _pipeline_process_image(
                h_id,
                f,
                "English",
                "French",
                config,
            )

        # _pipeline_run_ocr should NOT be called — OCR checkpoint was loaded
        mock_run_ocr.assert_not_called()


# ---------------------------------------------------------------------------
# _map_error_to_code — all keyword→code mappings in a class
# ---------------------------------------------------------------------------


class TestMapErrorToCodeAllKeywords:
    """Verify all keyword->code mappings via map_tag_to_code."""

    @pytest.mark.parametrize(
        ("keyword", "expected_code"),
        [
            ("VISION_NOT_SUPPORTED", ERR_LLM_VISION_NOT_SUPPORTED),
            ("AUTH_ERROR", ERR_LLM_API_KEY_INVALID),
            ("MODEL_NOT_FOUND", ERR_LLM_MODEL_NOT_FOUND),
            ("REQUEST_TOO_LARGE", ERR_LLM_REQUEST_TOO_LARGE),
            ("QUOTA_ERROR", ERR_LLM_QUOTA_EXCEEDED),
            ("SERVICE_UNAVAILABLE_ERROR", ERR_LLM_SERVICE_UNAVAILABLE),
            ("TIMEOUT_ERROR", ERR_LLM_TIMEOUT),
            ("INVALID_RESPONSE", ERR_LLM_INVALID_RESPONSE),
            ("CONNECTION_ERROR", ERR_LLM_CONNECTION_FAILED),
            ("PASSWORD_PROTECTED", ERR_FILE_PASSWORD_PROTECTED),
            ("TEXT_READ_ERROR", ERR_TEXT_READ_FAILED),
            ("TEXT_WRITE_ERROR", ERR_TEXT_WRITE_FAILED),
            ("OFFICE_CONVERTER_NOT_FOUND", ERR_OFFICE_CONVERTER_NOT_FOUND),
        ],
    )
    def test_map_error_keyword_isolated(
        self,
        keyword: str,
        expected_code: int,
    ) -> None:
        """Each keyword maps to the correct error code when used alone."""
        assert _map_error_to_code(keyword) == expected_code

    def test_unknown_keyword_returns_err_unknown(self) -> None:
        """An unrecognized keyword returns ERR_UNKNOWN."""
        assert _map_error_to_code("TOTALLY_UNKNOWN_STUFF") == ERR_UNKNOWN


# ---------------------------------------------------------------------------
# _map_error_to_code — unmapped errors
# ---------------------------------------------------------------------------


class TestMapErrorToCodeUnmapped:
    """Tests for _map_error_to_code with unmapped error strings."""

    def test_unmapped_error_returns_unknown(self) -> None:
        """Completely unknown error string returns ERR_UNKNOWN."""
        from src.constants.errors import ERR_UNKNOWN  # noqa: PLC0415
        from src.core.translator import _map_error_to_code  # noqa: PLC0415

        result = _map_error_to_code("CustomUnmappedError: something went wrong")
        assert result == ERR_UNKNOWN

    def test_empty_string_returns_unknown(self) -> None:
        """Empty error message returns ERR_UNKNOWN."""
        from src.constants.errors import ERR_UNKNOWN  # noqa: PLC0415
        from src.core.translator import _map_error_to_code  # noqa: PLC0415

        result = _map_error_to_code("")
        assert result == ERR_UNKNOWN

    def test_partial_tag_match_still_matches(self) -> None:
        """Error message containing a known tag as substring matches."""
        from src.constants.errors import ERR_LLM_API_KEY_INVALID  # noqa: PLC0415
        from src.core.translator import _map_error_to_code  # noqa: PLC0415

        result = _map_error_to_code("SomePrefix AUTH_ERROR happened")
        assert result == ERR_LLM_API_KEY_INVALID


# ---------------------------------------------------------------------------
# _resolve_output_dir — config injection
# ---------------------------------------------------------------------------


class TestResolveOutputDirConfigInjection:
    """Verify _resolve_output_dir respects TranslationConfig injection."""

    def test_resolve_output_dir_config_with_storage_path(
        self,
        tmp_path: Path,
    ) -> None:
        """Config with a non-empty storage_path returns that path directly."""
        target_dir = str(tmp_path / "configured_output")
        config = TranslationConfig(storage_path=target_dir)

        result = _resolve_output_dir(config)

        assert result == Path(target_dir)

    def test_resolve_output_dir_config_empty_storage_path_falls_to_source(
        self,
        tmp_path: Path,
    ) -> None:
        """Config with storage_path='' falls through to source_path parent."""
        source_dir = tmp_path / "source_folder"
        source_dir.mkdir()
        source_file = source_dir / "document.txt"
        source_file.touch()

        config = TranslationConfig(storage_path="")

        result = _resolve_output_dir(config, source_path=source_file)

        assert result == source_dir

    def test_resolve_output_dir_config_empty_no_source_falls_to_desktop(
        self,
        tmp_path: Path,
    ) -> None:
        """Config with storage_path='' and no source_path falls to desktop."""
        desktop = tmp_path / "MockDesktop"
        desktop.mkdir()
        config = TranslationConfig(storage_path="")

        with patch(
            "src.utils.path_manager.get_desktop_path",
            return_value=desktop,
        ):
            result = _resolve_output_dir(config)

        assert result == desktop


# ---------------------------------------------------------------------------
# _build_output_name — empty stem (dotfiles)
# ---------------------------------------------------------------------------


class TestBuildOutputNameEmptyStem:
    """Verify _build_output_name handles dotfiles whose stem is their name."""

    def test_build_output_name_dotfile(self) -> None:
        """A dotfile like .gitignore has stem='.gitignore' and suffix=''."""
        result = _build_output_name(
            Path(".gitignore"),
            "English (US)",
            "Vietnamese",
        )
        # Path(".gitignore").stem == ".gitignore", .suffix == ""
        assert result == ".gitignore_translated_en-US_vi"

    def test_build_output_name_dotfile_with_extension(self) -> None:
        """A file like .env.bak has stem='.env' and suffix='.bak'."""
        result = _build_output_name(
            Path(".env.bak"),
            "English (US)",
            "French",
        )
        # Path(".env.bak").stem == ".env", .suffix == ".bak"
        assert result == ".env_translated_en-US_fr.bak"


# ---------------------------------------------------------------------------
# _pipeline_finalize — delete_history_entry returns empty string
# ---------------------------------------------------------------------------


class TestPipelineFinalizeDeleteReturnsEmpty:
    """Verify wipe is NOT called when delete_history_entry returns ''."""

    def test_finalize_delete_returns_empty_string_no_wipe(
        self,
        tmp_path: Path,
    ) -> None:
        """delete_history_entry returning '' → wipe_history_directory NOT called."""
        f = tmp_path / "fin_empty_del.txt"
        f.touch()
        h_id = add_history_entry(
            "fin_empty_del.txt",
            "En",
            "Fr",
            "Translating",
            storage_path=str(f),
        )
        config = TranslationConfig(auto_remove_history=True)

        with (
            patch(
                f"{_MOD}.get_history_entry_status",
                return_value="Translating",
            ),
            patch(
                f"{_MOD}.delete_history_entry",
                return_value="",
            ) as mock_delete,
            patch(
                f"{_MOD}.wipe_history_directory",
            ) as mock_wipe,
        ):
            _pipeline_finalize(h_id, config)

        mock_delete.assert_called_once_with(h_id)
        # Empty string is falsy → wipe should NOT be called
        mock_wipe.assert_not_called()

    def test_finalize_delete_returns_none_no_wipe(
        self,
        tmp_path: Path,
    ) -> None:
        """delete_history_entry returning None → wipe_history_directory NOT called."""
        f = tmp_path / "fin_none_del.txt"
        f.touch()
        h_id = add_history_entry(
            "fin_none_del.txt",
            "En",
            "Fr",
            "Translating",
            storage_path=str(f),
        )
        config = TranslationConfig(auto_remove_history=True)

        with (
            patch(
                f"{_MOD}.get_history_entry_status",
                return_value="Translating",
            ),
            patch(
                f"{_MOD}.delete_history_entry",
                return_value=None,
            ) as mock_delete,
            patch(
                f"{_MOD}.wipe_history_directory",
            ) as mock_wipe,
        ):
            _pipeline_finalize(h_id, config)

        mock_delete.assert_called_once_with(h_id)
        mock_wipe.assert_not_called()


# ---------------------------------------------------------------------------
# _pipeline_process_text — non-ValueError exception maps to ERR_UNKNOWN
# ---------------------------------------------------------------------------


class TestPipelineProcessTextNonValueError:
    """Verify non-ValueError exceptions are caught and mapped to ERR_UNKNOWN."""

    def test_process_text_oserror_maps_to_err_unknown(
        self,
        tmp_path: Path,
    ) -> None:
        """OSError('disk full') from translate_file → Failed with ERR_UNKNOWN."""
        f = tmp_path / "proc_oserr.txt"
        f.write_text("hello")
        h_id = add_history_entry(
            "proc_oserr.txt",
            "English",
            "French",
            "Translating",
            storage_path=str(f),
        )
        config = TranslationConfig(
            storage_path=str(tmp_path),
            auto_remove_history=False,
        )

        with (
            patch(
                "src.core.translator.translate_file",
                side_effect=OSError("disk full"),
            ),
            patch(
                "src.core.translator._fetch_all_glossary_entries",
                return_value=[],
            ),
        ):
            _pipeline_process_text(
                h_id,
                f,
                "English",
                "French",
                config,
            )

        assert get_history_entry_status(h_id) == "Failed"
        entry = next(h for h in get_history() if h[0] == h_id)
        assert entry[9] == ERR_UNKNOWN  # noqa: PLR2004

    def test_process_text_runtime_error_maps_to_err_unknown(
        self,
        tmp_path: Path,
    ) -> None:
        """RuntimeError from translate_file → Failed with ERR_UNKNOWN."""
        f = tmp_path / "proc_rterr.txt"
        f.write_text("hello")
        h_id = add_history_entry(
            "proc_rterr.txt",
            "English",
            "French",
            "Translating",
            storage_path=str(f),
        )
        config = TranslationConfig(
            storage_path=str(tmp_path),
            auto_remove_history=False,
        )

        with (
            patch(
                "src.core.translator.translate_file",
                side_effect=RuntimeError("unexpected crash"),
            ),
            patch(
                "src.core.translator._fetch_all_glossary_entries",
                return_value=[],
            ),
        ):
            _pipeline_process_text(
                h_id,
                f,
                "English",
                "French",
                config,
            )

        assert get_history_entry_status(h_id) == "Failed"
        entry = next(h for h in get_history() if h[0] == h_id)
        assert entry[9] == ERR_UNKNOWN  # noqa: PLR2004


# ---------------------------------------------------------------------------
# _pipeline_process_text — empty glossary → None conversion
# ---------------------------------------------------------------------------


class TestPipelineProcessTextEmptyGlossary:
    """Verify that empty glossary list is converted to None for translate_file."""

    def test_process_text_empty_glossary_passes_none(
        self,
        tmp_path: Path,
    ) -> None:
        """Empty glossary list is converted to None for translate_file."""
        f = tmp_path / "proc_gloss_none.txt"
        f.write_text("hello")
        h_id = add_history_entry(
            "proc_gloss_none.txt",
            "English",
            "French",
            "Translating",
            storage_path=str(f),
        )
        config = TranslationConfig(
            storage_path=str(tmp_path),
            auto_remove_history=False,
        )

        with (
            patch(
                "src.core.translator.translate_file",
                return_value=True,
            ) as mock_translate,
            patch(
                "src.core.translator._fetch_all_glossary_entries",
                return_value=[],
            ),
            patch("src.core.translator.clear_checkpoints"),
        ):
            _pipeline_process_text(
                h_id,
                f,
                "English",
                "French",
                config,
            )

        # Verify translate_file was called with glossary_entries=None
        mock_translate.assert_called_once()
        call_kwargs = mock_translate.call_args
        # glossary_entries is passed as a keyword argument
        assert call_kwargs.kwargs["glossary_entries"] is None

    def test_process_text_nonempty_glossary_passes_list(
        self,
        tmp_path: Path,
    ) -> None:
        """Non-empty glossary list is passed as-is to translate_file."""
        f = tmp_path / "proc_gloss_list.txt"
        f.write_text("hello")
        h_id = add_history_entry(
            "proc_gloss_list.txt",
            "English",
            "French",
            "Translating",
            storage_path=str(f),
        )
        config = TranslationConfig(
            storage_path=str(tmp_path),
            auto_remove_history=False,
        )
        glossary = [(1, "hello", "bonjour"), (2, "world", "monde")]

        with (
            patch(
                "src.core.translator.translate_file",
                return_value=True,
            ) as mock_translate,
            patch(
                "src.core.translator._fetch_all_glossary_entries",
                return_value=glossary,
            ),
            patch("src.core.translator.clear_checkpoints"),
        ):
            _pipeline_process_text(
                h_id,
                f,
                "English",
                "French",
                config,
            )

        # Verify translate_file was called with the actual glossary list
        mock_translate.assert_called_once()
        call_kwargs = mock_translate.call_args
        assert call_kwargs.kwargs["glossary_entries"] == glossary
