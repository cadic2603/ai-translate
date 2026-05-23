"""Unit tests for OCR utility functions and OCR engine edge cases."""

import builtins
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest

from src.constants.ocr import (
    _LANG_OCR_CODES,
    OCR_METHOD_EASYOCR,
    OCR_METHOD_GOOGLE_CLOUD,
    OCR_METHOD_TESSERACT,
    OCR_PADDING_DEFAULT,
    OCR_PADDING_EASYOCR,
    get_easyocr_langs,
    get_google_lang_hints,
    get_tesseract_lang,
)
from src.core.ocr_engine import (
    OCRResult,
    _bypass_uno_import,
    _easyocr_readers,
    _run_easyocr,
    _run_google_cloud,
    _run_tesseract,
    run_ocr,
)
from src.utils.ocr_utils import get_ocr_padding

# ---------------------------------------------------------------------------
# get_ocr_padding tests
# ---------------------------------------------------------------------------


def test_get_ocr_padding_tesseract() -> None:
    """Tesseract returns the default padding values."""
    assert get_ocr_padding(OCR_METHOD_TESSERACT) == OCR_PADDING_DEFAULT


def test_get_ocr_padding_easyocr() -> None:
    """EasyOCR returns its specific padding values."""
    assert get_ocr_padding(OCR_METHOD_EASYOCR) == OCR_PADDING_EASYOCR


def test_get_ocr_padding_google_cloud() -> None:
    """Google Cloud OCR uses the default padding (not EasyOCR-specific)."""
    assert get_ocr_padding(OCR_METHOD_GOOGLE_CLOUD) == OCR_PADDING_DEFAULT


def test_get_ocr_padding_unknown_method() -> None:
    """Unknown OCR method falls back to default padding."""
    assert get_ocr_padding("SomeUnknownMethod") == OCR_PADDING_DEFAULT


def test_ocr_padding_values() -> None:
    """Verify the actual constant values match expectations."""
    assert OCR_PADDING_DEFAULT == (1, 1)
    assert OCR_PADDING_EASYOCR == (0, -2)


# ---------------------------------------------------------------------------
# _run_google_cloud edge cases
# ---------------------------------------------------------------------------


@patch("src.core.ocr_engine.load_google_cloud_api_key", return_value="")
def test_google_cloud_missing_api_key(mock_setting: MagicMock) -> None:
    """Raises AUTH_ERROR when API key is empty."""
    with pytest.raises(ValueError, match="AUTH_ERROR"):
        _run_google_cloud("test.jpg")


@patch("src.core.ocr_engine.load_google_cloud_api_key", return_value=None)
def test_google_cloud_none_api_key(mock_setting: MagicMock) -> None:
    """Raises AUTH_ERROR when API key is None (falsy)."""
    with pytest.raises(ValueError, match="AUTH_ERROR"):
        _run_google_cloud("test.jpg")


# ---------------------------------------------------------------------------
# run_ocr dispatch tests
# ---------------------------------------------------------------------------


@patch("src.core.ocr_engine._run_tesseract")
def test_run_ocr_tesseract_dispatch(mock_tesseract: MagicMock) -> None:
    """run_ocr dispatches to _run_tesseract for the Tesseract method."""
    mock_tesseract.return_value = [OCRResult("Hello", 0, 0, 50, 20, 0.9)]

    results = run_ocr("image.png", method=OCR_METHOD_TESSERACT)

    mock_tesseract.assert_called_once_with("image.png", lang="eng")
    assert isinstance(results, list)


@patch("src.core.ocr_engine._run_tesseract")
def test_run_ocr_tesseract_forwards_src_lang(mock_tesseract: MagicMock) -> None:
    """run_ocr forwards src_lang as the correct Tesseract language code."""
    mock_tesseract.return_value = [OCRResult("Bonjour", 0, 0, 50, 20, 0.9)]

    run_ocr("image.png", method=OCR_METHOD_TESSERACT, src_lang="French")

    mock_tesseract.assert_called_once_with("image.png", lang="fra")


@patch("src.core.ocr_engine._run_easyocr")
def test_run_ocr_easyocr_dispatch(mock_easyocr: MagicMock) -> None:
    """run_ocr dispatches to _run_easyocr for the EasyOCR method."""
    mock_easyocr.return_value = [OCRResult("World", 0, 0, 60, 20, 0.8)]

    results = run_ocr("image.png", method=OCR_METHOD_EASYOCR)

    mock_easyocr.assert_called_once_with("image.png", languages=["en"])
    assert isinstance(results, list)


@patch("src.core.ocr_engine._run_easyocr")
def test_run_ocr_easyocr_forwards_src_lang(mock_easyocr: MagicMock) -> None:
    """run_ocr forwards src_lang as EasyOCR language list with English."""
    mock_easyocr.return_value = []

    run_ocr("image.png", method=OCR_METHOD_EASYOCR, src_lang="Japanese")

    mock_easyocr.assert_called_once_with("image.png", languages=["ja", "en"])


@patch("src.core.ocr_engine._run_google_cloud")
def test_run_ocr_google_cloud_dispatch(mock_gcloud: MagicMock) -> None:
    """run_ocr dispatches to _run_google_cloud for the Google Cloud method."""
    mock_gcloud.return_value = [OCRResult("Text", 0, 0, 40, 20, 1.0)]

    results = run_ocr("image.png", method=OCR_METHOD_GOOGLE_CLOUD)

    mock_gcloud.assert_called_once_with("image.png", lang_hints=None)
    assert isinstance(results, list)


@patch("src.core.ocr_engine._run_google_cloud")
def test_run_ocr_google_cloud_forwards_src_lang(mock_gcloud: MagicMock) -> None:
    """run_ocr forwards src_lang as Google Cloud language hints."""
    mock_gcloud.return_value = []

    run_ocr("image.png", method=OCR_METHOD_GOOGLE_CLOUD, src_lang="Arabic")

    mock_gcloud.assert_called_once_with("image.png", lang_hints=["ar"])


@patch("src.core.ocr_engine._run_tesseract")
def test_run_ocr_unknown_method(mock_tesseract: MagicMock) -> None:
    """Unknown OCR method returns empty list without calling any backend."""
    results = run_ocr("image.png", method="MagicOCR")

    mock_tesseract.assert_not_called()
    assert results == []


# ---------------------------------------------------------------------------
# _run_google_cloud success path
# ---------------------------------------------------------------------------


@patch("src.core.ocr_engine.load_google_cloud_api_key", return_value="fake-api-key")
@patch("urllib.request.urlopen")
def test_google_cloud_success(
    mock_urlopen: MagicMock,
    mock_load: MagicMock,
    tmp_path: Path,
) -> None:
    """_run_google_cloud returns OCRResult list from a successful API response."""
    img = tmp_path / "test.jpg"
    img.write_bytes(b"fake image data")

    response_data = {
        "responses": [
            {
                "textAnnotations": [
                    # First annotation is the full-text block — skipped by [1:]
                    {
                        "description": "Full text",
                        "boundingPoly": {
                            "vertices": [
                                {"x": 0, "y": 0},
                                {"x": 100, "y": 0},
                                {"x": 100, "y": 20},
                                {"x": 0, "y": 20},
                            ]
                        },
                    },
                    # Individual word annotation
                    {
                        "description": "word",
                        "boundingPoly": {
                            "vertices": [
                                {"x": 10, "y": 5},
                                {"x": 50, "y": 5},
                                {"x": 50, "y": 15},
                                {"x": 10, "y": 15},
                            ]
                        },
                    },
                ],
            }
        ]
    }

    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps(response_data).encode("utf-8")
    mock_response.__enter__.return_value = mock_response
    mock_response.__exit__.return_value = False
    mock_urlopen.return_value = mock_response

    results = _run_google_cloud(str(img))

    # Only annotations[1:] are processed (full-text block is skipped)
    assert len(results) == 1
    assert results[0].text == "word"
    assert results[0].x == 10  # noqa: PLR2004
    assert results[0].y == 5  # noqa: PLR2004


@patch("src.core.ocr_engine.load_google_cloud_api_key", return_value="fake-api-key")
@patch("urllib.request.urlopen")
def test_google_cloud_empty_annotations(
    mock_urlopen: MagicMock,
    mock_load: MagicMock,
    tmp_path: Path,
) -> None:
    """_run_google_cloud returns empty list when textAnnotations is absent."""
    img = tmp_path / "test.jpg"
    img.write_bytes(b"fake image data")

    response_data = {"responses": [{}]}  # no textAnnotations key

    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps(response_data).encode("utf-8")
    mock_response.__enter__.return_value = mock_response
    mock_response.__exit__.return_value = False
    mock_urlopen.return_value = mock_response

    results = _run_google_cloud(str(img))

    assert results == []


# ---------------------------------------------------------------------------
# Language mapping helper tests
# ---------------------------------------------------------------------------


def test_get_tesseract_lang_known() -> None:
    """Known language label returns the correct Tesseract code."""
    assert get_tesseract_lang("French") == "fra"
    assert get_tesseract_lang("Japanese") == "jpn"
    assert get_tesseract_lang("Chinese (Simplified)") == "chi_sim"


def test_get_tesseract_lang_english_variants() -> None:
    """Both English variants return 'eng'."""
    assert get_tesseract_lang("English (US)") == "eng"
    assert get_tesseract_lang("English (UK)") == "eng"


def test_get_tesseract_lang_unknown() -> None:
    """Unknown language label falls back to 'eng'."""
    assert get_tesseract_lang("Klingon") == "eng"


def test_get_tesseract_lang_empty() -> None:
    """Empty string falls back to 'eng'."""
    assert get_tesseract_lang("") == "eng"


def test_get_easyocr_langs_known() -> None:
    """Known non-English language returns [code, 'en']."""
    assert get_easyocr_langs("Japanese") == ["ja", "en"]
    assert get_easyocr_langs("Arabic") == ["ar", "en"]


def test_get_easyocr_langs_english() -> None:
    """English variants return just ['en']."""
    assert get_easyocr_langs("English (US)") == ["en"]
    assert get_easyocr_langs("English (UK)") == ["en"]


def test_get_easyocr_langs_unknown() -> None:
    """Unknown language label falls back to ['en']."""
    assert get_easyocr_langs("Klingon") == ["en"]


def test_get_easyocr_langs_empty() -> None:
    """Empty string falls back to ['en']."""
    assert get_easyocr_langs("") == ["en"]


def test_get_google_lang_hints_known() -> None:
    """Known language returns a single-element hint list."""
    assert get_google_lang_hints("French") == ["fr"]
    assert get_google_lang_hints("Chinese (Simplified)") == ["zh"]


def test_get_google_lang_hints_unknown() -> None:
    """Unknown language returns None (auto-detect)."""
    assert get_google_lang_hints("Klingon") is None


def test_get_google_lang_hints_empty() -> None:
    """Empty string returns None (auto-detect)."""
    assert get_google_lang_hints("") is None


@patch("src.core.ocr_engine.load_google_cloud_api_key", return_value="fake-api-key")
@patch("urllib.request.urlopen")
def test_google_cloud_lang_hints_in_payload(
    mock_urlopen: MagicMock,
    mock_load: MagicMock,
    tmp_path: Path,
) -> None:
    """_run_google_cloud includes languageHints in the request when provided."""
    img = tmp_path / "test.jpg"
    img.write_bytes(b"fake image data")

    response_data = {"responses": [{}]}
    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps(response_data).encode("utf-8")
    mock_response.__enter__.return_value = mock_response
    mock_response.__exit__.return_value = False
    mock_urlopen.return_value = mock_response

    _run_google_cloud(str(img), lang_hints=["fr"])

    # Verify the request payload includes imageContext with languageHints
    call_args = mock_urlopen.call_args
    import urllib.request  # noqa: PLC0415

    req_obj = call_args[0][0]
    assert isinstance(req_obj, urllib.request.Request)
    payload = json.loads(req_obj.data.decode("utf-8"))
    request_body = payload["requests"][0]
    assert request_body["imageContext"]["languageHints"] == ["fr"]


@patch("src.core.ocr_engine.load_google_cloud_api_key", return_value="fake-api-key")
@patch("urllib.request.urlopen")
def test_google_cloud_no_lang_hints_omits_image_context(
    mock_urlopen: MagicMock,
    mock_load: MagicMock,
    tmp_path: Path,
) -> None:
    """_run_google_cloud omits imageContext from payload when lang_hints is None."""
    img = tmp_path / "test.jpg"
    img.write_bytes(b"fake image data")
    response_data = {"responses": [{}]}
    mock_response = MagicMock()
    mock_response.read.return_value = json.dumps(response_data).encode("utf-8")
    mock_response.__enter__.return_value = mock_response
    mock_response.__exit__.return_value = False
    mock_urlopen.return_value = mock_response

    _run_google_cloud(str(img), lang_hints=None)

    import urllib.request as _ur  # noqa: PLC0415

    req_obj = mock_urlopen.call_args[0][0]
    assert isinstance(req_obj, _ur.Request)
    payload = json.loads(req_obj.data.decode("utf-8"))
    assert "imageContext" not in payload["requests"][0]


# ---------------------------------------------------------------------------
# _run_tesseract — language fallback and edge cases
# ---------------------------------------------------------------------------


def test_run_tesseract_falls_back_to_eng_on_missing_lang_pack(
    tmp_path: Path,
) -> None:
    """_run_tesseract retries with 'eng' when the requested lang pack is missing."""
    called_cmds: list[list[str]] = []

    def fake_run(cmd, check, capture_output):  # noqa: ANN001, ANN202
        called_cmds.append(cmd)
        if "fra" in cmd:
            # First call: language pack not installed
            raise subprocess.CalledProcessError(1, cmd)
        # Second call (eng): succeed and write an empty TSV so the parser runs
        # cmd = ["tesseract", img, out_base, "-l", "eng", "tsv"]
        out_base = Path(cmd[2])
        tsv = out_base.with_suffix(".tsv")
        tsv.write_text(
            "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n"
        )

    with patch("src.core.ocr_engine.subprocess.run", side_effect=fake_run):
        results = _run_tesseract("img.png", lang="fra")

    assert len(called_cmds) == 2  # noqa: PLR2004
    assert "fra" in called_cmds[0]
    assert "eng" in called_cmds[1]
    assert results == []  # Header-only TSV → no word-level rows


def test_run_tesseract_logs_warning_on_lang_fallback(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """_run_tesseract logs a warning when falling back to English."""
    import logging  # noqa: PLC0415

    def fake_run(cmd, check, capture_output):  # noqa: ANN001, ANN202
        if "-l" in cmd and "fra" in cmd:
            raise subprocess.CalledProcessError(1, cmd)
        # Eng fallback: write a minimal TSV so the function completes successfully
        out_base = Path(cmd[2])
        tsv = out_base.with_suffix(".tsv")
        tsv.write_text(
            "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num"
            "\tleft\ttop\twidth\theight\tconf\ttext\n",
        )

    with (
        patch("src.core.ocr_engine.subprocess.run", side_effect=fake_run),
        caplog.at_level(logging.WARNING, logger="ocr_engine"),
    ):
        _run_tesseract("img.png", lang="fra")

    assert "fra" in caplog.text
    assert "eng" in caplog.text


def test_run_tesseract_eng_failure_returns_empty(tmp_path: Path) -> None:
    """_run_tesseract returns [] (no crash) when lang='eng' subprocess fails."""
    with patch(
        "src.core.ocr_engine.subprocess.run",
        side_effect=subprocess.CalledProcessError(1, "tesseract"),
    ):
        results = _run_tesseract("img.png", lang="eng")

    assert results == []


# ---------------------------------------------------------------------------
# _run_easyocr — language fallback and edge cases
# ---------------------------------------------------------------------------


def test_run_easyocr_falls_back_to_english_on_unsupported_lang() -> None:
    """_run_easyocr retries with ['en'] when the requested language is unsupported."""
    _easyocr_readers.clear()
    call_languages = []

    class _FakeReader:
        def __init__(self, langs, **kwargs):  # noqa: ANN001, ANN003, ANN204
            call_languages.append(langs)
            if langs != ["en"]:
                raise ValueError("Language not supported")

        def readtext(self, path):  # noqa: ANN001, ANN202
            return []

    mock_easyocr = MagicMock()
    mock_easyocr.Reader = _FakeReader

    with patch.dict(sys.modules, {"easyocr": mock_easyocr}):
        results = _run_easyocr("img.png", languages=["km", "en"])

    assert results == []
    assert ["km", "en"] in call_languages
    assert ["en"] in call_languages  # fallback was attempted
    _easyocr_readers.clear()


def test_run_easyocr_reraises_when_default_langs_fail() -> None:
    """_run_easyocr propagates the exception when even ['en'] fails."""
    _easyocr_readers.clear()
    mock_easyocr = MagicMock()
    mock_easyocr.Reader.side_effect = RuntimeError("EasyOCR crashed")

    with (
        patch.dict(sys.modules, {"easyocr": mock_easyocr}),
        pytest.raises(RuntimeError, match="EasyOCR crashed"),
    ):
        _run_easyocr("img.png", languages=["en"])
    _easyocr_readers.clear()


def test_run_easyocr_import_error_raises_with_message() -> None:
    """_run_easyocr raises ImportError with 'not installed' message."""
    with (
        patch.dict(sys.modules, {"easyocr": None}),
        pytest.raises(ImportError, match="not installed"),
    ):
        _run_easyocr("img.png")


# ---------------------------------------------------------------------------
# _bypass_uno_import — UNO import hook workaround
# ---------------------------------------------------------------------------


def test_bypass_uno_import_no_uno_module() -> None:
    """Returns None when 'uno' is not in sys.modules."""
    with patch.dict(sys.modules, {}, clear=False):
        sys.modules.pop("uno", None)
        assert _bypass_uno_import() is None


def test_bypass_uno_import_swaps_hook() -> None:
    """Swaps UNO's hook out and returns it for later restore."""
    real_import = builtins.__import__

    # Create a fake UNO module with a _builtin_import attribute
    fake_uno = ModuleType("uno")
    fake_uno._builtin_import = real_import  # type: ignore[attr-defined]

    # Simulate UNO hook being active
    def _fake_uno_hook(*a, **kw) -> None:  # noqa: ANN002, ANN003
        pass

    builtins.__import__ = _fake_uno_hook
    try:
        with patch.dict(sys.modules, {"uno": fake_uno}):
            saved = _bypass_uno_import()
            # Should have restored the real import
            assert builtins.__import__ is real_import
            # Should return the UNO hook for later restore
            assert saved is _fake_uno_hook
    finally:
        builtins.__import__ = real_import


def test_bypass_uno_import_noop_when_already_real() -> None:
    """Returns None when builtins.__import__ is already the real import."""
    real_import = builtins.__import__

    fake_uno = ModuleType("uno")
    fake_uno._builtin_import = real_import  # type: ignore[attr-defined]

    # builtins.__import__ IS the same as uno._builtin_import → no swap needed
    builtins.__import__ = real_import
    try:
        with patch.dict(sys.modules, {"uno": fake_uno}):
            assert _bypass_uno_import() is None
    finally:
        builtins.__import__ = real_import


def test_easyocr_import_with_uno_hook_active() -> None:
    """_get_easyocr_reader restores UNO hook after importing easyocr."""
    _easyocr_readers.clear()
    real_import = builtins.__import__

    fake_uno = ModuleType("uno")
    fake_uno._builtin_import = real_import  # type: ignore[attr-defined]

    call_count = 0

    def _counting_hook(name, *args, **kwargs) -> object:  # noqa: ANN001, ANN002, ANN003
        nonlocal call_count
        call_count += 1
        return real_import(name, *args, **kwargs)

    class _FakeReader:
        def __init__(self, langs, **kwargs):  # noqa: ANN001, ANN003, ANN204
            pass

        def readtext(self, path):  # noqa: ANN001, ANN202
            return []

    mock_easyocr = MagicMock()
    mock_easyocr.Reader = _FakeReader

    builtins.__import__ = _counting_hook
    try:
        with patch.dict(sys.modules, {"uno": fake_uno, "easyocr": mock_easyocr}):
            from src.core.ocr_engine import _get_easyocr_reader  # noqa: PLC0415

            _get_easyocr_reader(["en"])
            # After the call, the UNO hook should be restored
            assert builtins.__import__ is _counting_hook
    finally:
        builtins.__import__ = real_import
        _easyocr_readers.clear()


# ---------------------------------------------------------------------------
# Language mapping — additional coverage
# ---------------------------------------------------------------------------


def test_get_tesseract_lang_chinese_traditional() -> None:
    """Chinese (Traditional) returns its distinct Tesseract code."""
    assert get_tesseract_lang("Chinese (Traditional)") == "chi_tra"


def test_get_google_lang_hints_chinese_traditional() -> None:
    """Chinese (Traditional) returns zh-TW hint (distinct from Simplified zh)."""
    assert get_google_lang_hints("Chinese (Traditional)") == ["zh-TW"]
    assert get_google_lang_hints("Chinese (Simplified)") == ["zh"]


@pytest.mark.parametrize("lang,codes", list(_LANG_OCR_CODES.items()))
def test_lang_ocr_codes_entry_structure(lang: str, codes: tuple) -> None:
    """Every _LANG_OCR_CODES entry is a 3-tuple of non-empty strings."""
    assert isinstance(codes, tuple), f"{lang}: expected tuple, got {type(codes)}"
    assert len(codes) == 3, f"{lang}: expected 3-element tuple, got {len(codes)}"  # noqa: PLR2004
    for i, code in enumerate(codes):
        assert isinstance(code, str) and code, (
            f"{lang}[{i}]: expected non-empty str, got {code!r}"
        )


# ---------------------------------------------------------------------------
# get_ocr_padding — additional edge cases
# ---------------------------------------------------------------------------


def test_get_ocr_padding_empty_string() -> None:
    """Empty string method name falls back to default padding."""
    assert get_ocr_padding("") == OCR_PADDING_DEFAULT


def test_get_ocr_padding_case_sensitivity() -> None:
    """OCR method matching is case-sensitive."""
    # "easyocr" (lowercase) is not the same as the constant OCR_METHOD_EASYOCR
    assert get_ocr_padding("easyocr") == OCR_PADDING_DEFAULT
    # Exact match should return EasyOCR padding
    assert get_ocr_padding(OCR_METHOD_EASYOCR) == OCR_PADDING_EASYOCR


def test_get_ocr_padding_return_types() -> None:
    """Padding values are returned as 2-tuples of integers."""
    result = get_ocr_padding(OCR_METHOD_TESSERACT)
    assert isinstance(result, tuple)
    assert len(result) == 2  # noqa: PLR2004
    assert isinstance(result[0], int)
    assert isinstance(result[1], int)


def test_get_ocr_padding_easyocr_negative_insertion() -> None:
    """EasyOCR padding has negative insertion value (inward bias)."""
    remove, insert = get_ocr_padding(OCR_METHOD_EASYOCR)
    assert remove == 0
    assert insert < 0


def test_get_ocr_padding_default_positive_values() -> None:
    """Default padding has both positive removal and insertion."""
    remove, insert = get_ocr_padding(OCR_METHOD_TESSERACT)
    assert remove > 0
    assert insert > 0


# ---------------------------------------------------------------------------
# Padding calculation verification
# ---------------------------------------------------------------------------


def test_padding_values_are_symmetric_for_default() -> None:
    """Default padding has equal removal and insertion values."""
    remove, insert = OCR_PADDING_DEFAULT
    assert remove == insert


def test_padding_values_easyocr_asymmetric() -> None:
    """EasyOCR padding is asymmetric (different removal and insertion)."""
    remove, insert = OCR_PADDING_EASYOCR
    assert remove != insert


# ---------------------------------------------------------------------------
# OCR constants verification
# ---------------------------------------------------------------------------


def test_ocr_methods_list_completeness() -> None:
    """All three OCR methods are present in OCR_METHODS."""
    from src.constants.ocr import OCR_METHODS  # noqa: PLC0415

    assert OCR_METHOD_TESSERACT in OCR_METHODS
    assert OCR_METHOD_EASYOCR in OCR_METHODS
    assert OCR_METHOD_GOOGLE_CLOUD in OCR_METHODS
    assert len(OCR_METHODS) == 3  # noqa: PLR2004


def test_ocr_layout_metrics_positive() -> None:
    """All layout metric constants are positive numbers."""
    from src.constants.ocr import (  # noqa: PLC0415
        OCR_DEFAULT_LINE_HEIGHT,
        OCR_EASYOCR_HEIGHT_MULTIPLIER,
        OCR_LINE_GAP_THRESHOLD_RATIO,
        OCR_MAX_LINE_HEIGHT,
        OCR_MIN_LINE_HEIGHT,
        OCR_SINGLE_LINE_HEIGHT,
    )

    assert OCR_LINE_GAP_THRESHOLD_RATIO > 0
    assert OCR_DEFAULT_LINE_HEIGHT > 0
    assert OCR_SINGLE_LINE_HEIGHT > 0
    assert OCR_MIN_LINE_HEIGHT > 0
    assert OCR_MAX_LINE_HEIGHT > 0
    assert OCR_EASYOCR_HEIGHT_MULTIPLIER > 0


def test_ocr_line_height_bounds() -> None:
    """Line height min < default < max."""
    from src.constants.ocr import (  # noqa: PLC0415
        OCR_DEFAULT_LINE_HEIGHT,
        OCR_MAX_LINE_HEIGHT,
        OCR_MIN_LINE_HEIGHT,
    )

    assert OCR_MIN_LINE_HEIGHT < OCR_DEFAULT_LINE_HEIGHT
    assert OCR_DEFAULT_LINE_HEIGHT < OCR_MAX_LINE_HEIGHT


def test_ocr_merge_thresholds_positive() -> None:
    """Merge threshold ratios are positive floats."""
    from src.constants.ocr import (  # noqa: PLC0415
        OCR_HORIZONTAL_GAP_RATIO,
        OCR_VERTICAL_OVERLAP_RATIO,
    )

    assert OCR_VERTICAL_OVERLAP_RATIO > 0
    assert OCR_HORIZONTAL_GAP_RATIO > 0


def test_tesseract_confidence_scale() -> None:
    """Tesseract confidence scale is 100.0."""
    from src.constants.ocr import TESSERACT_CONFIDENCE_SCALE  # noqa: PLC0415

    expected = 100.0  # noqa: PLR2004
    assert expected == TESSERACT_CONFIDENCE_SCALE


def test_google_cloud_ocr_timeout_positive() -> None:
    """Google Cloud OCR timeout is a positive integer."""
    from src.constants.ocr import GOOGLE_CLOUD_OCR_TIMEOUT  # noqa: PLC0415

    assert GOOGLE_CLOUD_OCR_TIMEOUT > 0


# ---------------------------------------------------------------------------
# OCRResult — bounding box / data integrity
# ---------------------------------------------------------------------------


def test_ocr_result_fields() -> None:
    """OCRResult stores text, position, dimensions and confidence."""
    r = OCRResult("hello", 10, 20, 100, 30, 0.95)
    assert r.text == "hello"
    assert r.x == 10  # noqa: PLR2004
    assert r.y == 20  # noqa: PLR2004
    assert r.w == 100  # noqa: PLR2004
    assert r.h == 30  # noqa: PLR2004
    assert r.confidence == 0.95  # noqa: PLR2004


def test_ocr_result_zero_size_box() -> None:
    """OCRResult with zero width and height is valid."""
    r = OCRResult("", 0, 0, 0, 0, 0.0)
    assert r.w == 0
    assert r.h == 0
    assert r.confidence == 0.0


def test_ocr_result_negative_coordinates() -> None:
    """OCRResult with negative coordinates is constructible (no validation)."""
    r = OCRResult("neg", -5, -10, 50, 20, 0.5)
    assert r.x == -5  # noqa: PLR2004
    assert r.y == -10  # noqa: PLR2004


def test_ocr_result_large_dimensions() -> None:
    """OCRResult can hold large image dimensions."""
    r = OCRResult("big", 0, 0, 10000, 8000, 1.0)
    assert r.w == 10000  # noqa: PLR2004
    assert r.h == 8000  # noqa: PLR2004


def test_ocr_result_low_confidence() -> None:
    """OCRResult with very low (but valid) confidence."""
    r = OCRResult("uncertain", 0, 0, 50, 20, 0.01)
    assert r.confidence == 0.01  # noqa: PLR2004


def test_ocr_result_full_confidence() -> None:
    """OCRResult with perfect confidence score."""
    r = OCRResult("certain", 0, 0, 50, 20, 1.0)
    assert r.confidence == 1.0  # noqa: PLR2004


# ---------------------------------------------------------------------------
# run_ocr — edge cases
# ---------------------------------------------------------------------------


@patch("src.core.ocr_engine._run_tesseract")
def test_run_ocr_default_method_is_tesseract(mock_tesseract: MagicMock) -> None:
    """run_ocr with default method uses Tesseract."""
    mock_tesseract.return_value = []
    run_ocr("img.png", method=OCR_METHOD_TESSERACT)
    mock_tesseract.assert_called_once()


@patch("src.core.ocr_engine._run_tesseract")
def test_run_ocr_empty_src_lang_uses_eng(mock_tesseract: MagicMock) -> None:
    """Empty src_lang falls back to 'eng' for Tesseract."""
    mock_tesseract.return_value = []
    run_ocr("img.png", method=OCR_METHOD_TESSERACT, src_lang="")
    mock_tesseract.assert_called_once_with("img.png", lang="eng")


@patch("src.core.ocr_engine._run_easyocr")
def test_run_ocr_easyocr_empty_src_lang(mock_easyocr: MagicMock) -> None:
    """Empty src_lang with EasyOCR falls back to ['en']."""
    mock_easyocr.return_value = []
    run_ocr("img.png", method=OCR_METHOD_EASYOCR, src_lang="")
    mock_easyocr.assert_called_once_with("img.png", languages=["en"])


@patch("src.core.ocr_engine._run_google_cloud")
def test_run_ocr_google_cloud_empty_src_lang(mock_gcloud: MagicMock) -> None:
    """Empty src_lang with Google Cloud passes None hints."""
    mock_gcloud.return_value = []
    run_ocr("img.png", method=OCR_METHOD_GOOGLE_CLOUD, src_lang="")
    mock_gcloud.assert_called_once_with("img.png", lang_hints=None)
