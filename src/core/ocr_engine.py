"""OCR Engine for extracting text and bounding boxes from images.

Provides standardized access to multiple OCR backends (Tesseract, EasyOCR,
and Google Cloud Vision) with built-in sentence/phrase merging.
"""

import base64
import builtins
import csv
import json
import logging
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

from src.constants.ocr import (
    EASYOCR_DEFAULT_LANGUAGES,
    GOOGLE_CLOUD_OCR_MAX_BYTES,
    GOOGLE_CLOUD_OCR_TIMEOUT,
    OCR_HORIZONTAL_GAP_RATIO,
    OCR_METHOD_EASYOCR,
    OCR_METHOD_GOOGLE_CLOUD,
    OCR_METHOD_TESSERACT,
    OCR_VERTICAL_OVERLAP_RATIO,
    TESSERACT_CONFIDENCE_SCALE,
    TESSERACT_WORD_LEVEL,
    get_easyocr_langs,
    get_google_lang_hints,
    get_tesseract_lang,
)
from src.utils.config_manager import load_google_cloud_api_key

logger = logging.getLogger("ocr_engine")


class OCRResult:
    """Standardized OCR result for a single block of text."""

    def __init__(self, text: str, x: int, y: int, w: int, h: int, confidence: float):  # noqa: PLR0913
        """Initializes the OCRResult.

        Args:
            text (str): The extracted text fragment.
            x (int): X-coordinate of top-left corner.
            y (int): Y-coordinate of top-left corner.
            w (int): Width of the bounding box.
            h (int): Height of the bounding box.
            confidence (float): Recognition confidence score (0.0 to 1.0).
        """
        self.text = text
        self.x = x
        self.y = y
        self.w = w
        self.h = h
        self.confidence = confidence
        self.color = "#000000"  # Default text color (hex string)
        self.is_bold = False
        self.is_italic = False
        self.is_underline = False
        self.translated_text = ""
        self.translated_html = ""
        self.alignment = None  # Qt.AlignmentFlag
        self.original_text_height = h
        self.line_height_ratio = 1.2  # Default standard leading
        self.is_single_line = False

    def to_dict(self) -> dict[str, Any]:
        """Converts the result to a dictionary for serialization or debugging.

        Returns:
            dict: Dictionary representation of the OCR result.
        """
        return {
            "text": self.text,
            "translated_text": self.translated_text,
            "box": [self.x, self.y, self.w, self.h],
            "confidence": self.confidence,
            "color": self.color,
            "is_bold": self.is_bold,
            "is_italic": self.is_italic,
            "is_underline": self.is_underline,
            "alignment": str(self.alignment) if self.alignment else None,
        }


def run_ocr(
    image_path: str,
    method: str = OCR_METHOD_TESSERACT,
    src_lang: str = "",
) -> list[OCRResult]:
    """Runs OCR on an image and returns standardized merged results.

    Coordinates backend execution, samples text colors, and applies spatial merging.

    Args:
        image_path: Path to the image file.
        method: OCR method to use.
        src_lang: Source language label (e.g. ``"French"``). When provided,
            the appropriate language model is used for more accurate recognition.

    Returns:
        list[OCRResult]: List of merged OCR results with color info.
    """
    results = []
    if method == OCR_METHOD_TESSERACT:
        results = _run_tesseract(image_path, lang=get_tesseract_lang(src_lang))
    elif method == OCR_METHOD_EASYOCR:
        results = _run_easyocr(image_path, languages=get_easyocr_langs(src_lang))
    elif method == OCR_METHOD_GOOGLE_CLOUD:
        results = _run_google_cloud(
            image_path,
            lang_hints=get_google_lang_hints(src_lang),
        )

    # Merge individual word detections into cohesive sentences/phrases
    return merge_ocr_results(results)


def merge_ocr_results(results: list[OCRResult]) -> list[OCRResult]:
    """Groups OCR fragments into sentences based on spatial proximity.

    Uses vertical overlap to identify lines and horizontal gaps to identify
    sentence breaks.

    Args:
        results (list[OCRResult]): Raw fragments from OCR engine.

    Returns:
        list[OCRResult]: Cohesive text blocks.
    """
    if not results:
        return []

    results = [r for r in results if r.text.strip()]
    if not results:
        return []

    # 1. Group fragments into horizontal lines
    results.sort(key=lambda r: r.y)

    lines = []
    current_line = [results[0]]

    for i in range(1, len(results)):
        prev = current_line[-1]
        curr = results[i]

        overlap = min(prev.y + prev.h, curr.y + curr.h) - max(prev.y, curr.y)
        min_h = min(prev.h, curr.h)

        if overlap > min_h * OCR_VERTICAL_OVERLAP_RATIO:
            current_line.append(curr)
        else:
            lines.append(current_line)
            current_line = [curr]
    lines.append(current_line)

    # 2. Merge within each line based on horizontal distance
    final_results = []
    for line in lines:
        line.sort(key=lambda r: r.x)

        current_block = line[0]
        for i in range(1, len(line)):
            prev = current_block
            curr = line[i]

            gap = curr.x - (prev.x + prev.w)
            dist_threshold = prev.h * OCR_HORIZONTAL_GAP_RATIO

            if gap < dist_threshold:
                new_x = min(prev.x, curr.x)
                new_y = min(prev.y, curr.y)
                new_w = max(prev.x + prev.w, curr.x + curr.w) - new_x
                new_h = max(prev.y + prev.h, curr.y + curr.h) - new_y
                new_text = prev.text + " " + curr.text
                new_conf = (prev.confidence + curr.confidence) / 2.0

                # Create merged block
                current_block = OCRResult(
                    new_text,
                    new_x,
                    new_y,
                    new_w,
                    new_h,
                    new_conf,
                )
                # Keep the color of the first fragment in the sentence
                current_block.color = prev.color
                # If any part is bold/italic, mark the whole merged block
                current_block.is_bold = prev.is_bold or curr.is_bold
                current_block.is_italic = prev.is_italic or curr.is_italic
            else:
                final_results.append(current_block)
                current_block = curr
        final_results.append(current_block)

    return final_results


def _run_tesseract(image_path: str, lang: str = "eng") -> list[OCRResult]:
    """Runs Tesseract OCR using subprocess and returns parsed word-level results.

    If the requested language pack is not installed, automatically retries
    with English (``eng``) as a fallback.

    Args:
        image_path: Path to the image file.
        lang: Tesseract language code (e.g. ``"fra"``, ``"jpn"``).
    """
    results = []
    with tempfile.TemporaryDirectory() as tmp_dir:
        output_base = Path(tmp_dir) / "out"
        try:
            cmd = ["tesseract", image_path, str(output_base), "-l", lang, "tsv"]
            try:
                subprocess.run(cmd, check=True, capture_output=True)
            except subprocess.CalledProcessError:
                if lang != "eng":
                    # Language pack likely not installed — retry with English
                    logger.warning(
                        "Tesseract language '%s' unavailable, falling back to 'eng'",
                        lang,
                    )
                    cmd = [
                        "tesseract",
                        image_path,
                        str(output_base),
                        "-l",
                        "eng",
                        "tsv",
                    ]
                    subprocess.run(cmd, check=True, capture_output=True)
                else:
                    raise

            tsv_path = output_base.with_suffix(".tsv")
            if not tsv_path.exists():
                raise RuntimeError("Tesseract failed to create output file.")

            with tsv_path.open(encoding="utf-8") as f:
                reader = csv.DictReader(f, delimiter="\t", quoting=csv.QUOTE_NONE)
                for row in reader:
                    level = int(row.get("level", TESSERACT_WORD_LEVEL))
                    text = row.get("text", "").strip()

                    if level != TESSERACT_WORD_LEVEL or not text:
                        continue

                    conf = float(row["conf"])
                    if conf > 0:
                        res = OCRResult(
                            text=text,
                            x=int(row["left"]),
                            y=int(row["top"]),
                            w=int(row["width"]),
                            h=int(row["height"]),
                            confidence=conf / TESSERACT_CONFIDENCE_SCALE,
                        )
                        # Tesseract TSV sometimes has italic/bold
                        # info depending on config/version
                        if row.get("italic") == "1":
                            res.is_italic = True
                        if row.get("bold") == "1":
                            res.is_bold = True
                        results.append(res)
        except (subprocess.CalledProcessError, ValueError, KeyError) as e:
            logger.error("Tesseract OCR error: %s", e)

    return results


# Module-level cache for EasyOCR Reader instances (keyed by language tuple).
# Re-creating a Reader on every call reloads models from disk and triggers
# the deprecated torch.quantization API, which is unreliable on torch ≥ 2.10.
_easyocr_readers: dict[tuple[str, ...], object] = {}


def _bypass_uno_import() -> Callable[..., Any] | None:
    """Temporarily restores Python's original import if UNO's hook is active.

    LibreOffice UNO replaces ``builtins.__import__`` with ``_uno_import``,
    which crashes on C-extension wildcard imports (e.g.
    ``from _elementtree import *``) because it accesses ``mod.__dict__``
    without guarding against ``mod`` being ``None``.

    Returns:
        The UNO import hook that was replaced, or ``None`` if no swap
        was needed.  The caller must restore it via
        ``builtins.__import__ = returned_value`` in a ``finally`` block.
    """
    uno_mod = sys.modules.get("uno")
    if uno_mod is None:
        return None
    original = getattr(uno_mod, "_builtin_import", None)
    if original is None or builtins.__import__ is original:
        # UNO not active, or already using the real import
        return None
    # Swap: put Python's real import back, return UNO's hook for later restore
    uno_hook = builtins.__import__
    builtins.__import__ = original
    return uno_hook


def _get_easyocr_reader(langs: list[str]) -> object:
    """Returns a cached EasyOCR Reader for the given languages.

    Creates a new Reader on first call for each language set, then reuses it.
    Disables GPU (no accelerator available) and quantization (deprecated in
    torch 2.10) to avoid intermittent failures.

    Args:
        langs: EasyOCR language codes (e.g. ``["en"]``, ``["ja", "en"]``).

    Returns:
        An ``easyocr.Reader`` instance.
    """
    # Bypass UNO's broken import hook while loading easyocr's dependency tree
    saved_hook = _bypass_uno_import()
    try:
        import easyocr  # noqa: PLC0415
    finally:
        if saved_hook is not None:
            builtins.__import__ = saved_hook

    key = tuple(sorted(langs))
    if key not in _easyocr_readers:
        _easyocr_readers[key] = easyocr.Reader(
            langs,
            gpu=False,
            quantize=False,
            verbose=False,
        )
    return _easyocr_readers[key]


def _run_easyocr(
    image_path: str,
    languages: list[str] | None = None,
) -> list[OCRResult]:
    """Runs EasyOCR backend.

    If the requested language is not supported by EasyOCR, automatically
    retries with English (``["en"]``) as a fallback.

    Args:
        image_path: Path to the image file.
        languages: EasyOCR language codes (e.g. ``["ja", "en"]``).
    """
    try:
        langs = languages or EASYOCR_DEFAULT_LANGUAGES
        try:
            reader = _get_easyocr_reader(langs)
        except Exception:
            if langs != EASYOCR_DEFAULT_LANGUAGES:
                # Language likely not supported — retry with English
                logger.warning(
                    "EasyOCR languages %s unavailable, falling back to %s",
                    langs,
                    EASYOCR_DEFAULT_LANGUAGES,
                )
                reader = _get_easyocr_reader(EASYOCR_DEFAULT_LANGUAGES)
            else:
                raise

        results = reader.readtext(image_path)

        standardized = []
        for bbox, text, conf in results:
            xs = [p[0] for p in bbox]
            ys = [p[1] for p in bbox]
            x, y = int(min(xs)), int(min(ys))
            w, h = int(max(xs) - x), int(max(ys) - y)
            standardized.append(OCRResult(text, x, y, w, h, float(conf)))
        return standardized
    except ImportError:
        raise ImportError("EasyOCR not installed.") from None
    except Exception as e:
        logger.error("EasyOCR error: %s", e, exc_info=True)
        raise


def _run_google_cloud(  # noqa: PLR0912, PLR0915
    image_path: str,
    lang_hints: list[str] | None = None,
) -> list[OCRResult]:
    """Runs Google Cloud Vision OCR backend via REST API.

    Args:
        image_path: Path to the image file.
        lang_hints: Optional BCP-47 language hint codes (e.g. ``["fr"]``).
    """
    api_key = load_google_cloud_api_key()
    if not api_key:
        raise ValueError("AUTH_ERROR:Google Cloud")

    # Pre-flight size check.  Cloud Vision documents two size limits
    # for inline (base64) requests: 20 MB raw image AND a 10 MB JSON
    # body.  Base64 adds ~33 % overhead, so the JSON limit hits first
    # for files larger than ~7.5 MB.  ``GOOGLE_CLOUD_OCR_MAX_BYTES``
    # is sized for the JSON limit so users get our typed sentinel
    # with a clear "downscale first" message instead of the opaque
    # HTTP 400 the server would otherwise return.
    file_size = Path(image_path).stat().st_size
    if file_size > GOOGLE_CLOUD_OCR_MAX_BYTES:
        raise ValueError("IMAGE_TOO_LARGE")

    try:
        with Path(image_path).open("rb") as image_file:
            content = base64.b64encode(image_file.read()).decode("utf-8")

        url = f"https://vision.googleapis.com/v1/images:annotate?key={api_key}"
        # ``DOCUMENT_TEXT_DETECTION`` (not ``TEXT_DETECTION``) is the
        # Google-recommended feature for dense text + documents:
        # PDF pages, screenshots of articles, scanned book pages —
        # all of which are this app's primary OCR inputs.  It also
        # produces hierarchical reading order (page → block →
        # paragraph → word → symbol), so the OCR result reflects
        # how a human would read the page.  ``TEXT_DETECTION`` is
        # optimised for short text in photos (signs, labels) and
        # tends to miss / mis-order text in document-style inputs.
        # Both features still populate ``textAnnotations[]`` for
        # response compatibility, so the downstream parser below
        # is unchanged.
        request_body: dict = {
            "image": {"content": content},
            "features": [{"type": "DOCUMENT_TEXT_DETECTION"}],
        }
        # Add language hints to improve detection accuracy
        if lang_hints:
            request_body["imageContext"] = {"languageHints": lang_hints}

        payload = {"requests": [request_body]}

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )

        with urllib.request.urlopen(req, timeout=GOOGLE_CLOUD_OCR_TIMEOUT) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            annotations = res_data["responses"][0].get("textAnnotations", [])
            if not annotations:
                return []

            standardized = []
            for ann in annotations[1:]:
                text = ann.get("description", "")
                vertices = ann.get("boundingPoly", {}).get("vertices", [])
                if not vertices:
                    continue
                xs = [v.get("x", 0) for v in vertices]
                ys = [v.get("y", 0) for v in vertices]
                x, y = min(xs), min(ys)
                w, h = max(xs) - x, max(ys) - y
                standardized.append(OCRResult(text, x, y, w, h, 1.0))
            return standardized
    except urllib.error.HTTPError as exc:
        # Map Google Cloud Vision's HTTP status codes to the typed
        # sentinels our error UI already knows how to render — same
        # contract as ``llm_engine._handle_api_error``.  Without this
        # mapping the user sees "Google Cloud OCR error: HTTP Error
        # 429: Too Many Requests" with no actionable guidance; with
        # it, the OCR pipeline routes to a clear "rate limit hit,
        # try again later" toast and the test suite can pin the
        # per-status behaviour.
        if exc.code in {401, 403}:
            logger.error("Google Cloud OCR auth/forbidden: %s", exc)
            raise ValueError("AUTH_ERROR:Google Cloud") from exc
        if exc.code == 429:  # noqa: PLR2004
            logger.error("Google Cloud OCR quota exhausted: %s", exc)
            raise ValueError("QUOTA_ERROR") from exc
        if exc.code == 413:  # noqa: PLR2004
            # Server saw an oversize payload despite our pre-flight —
            # typically means the JSON body limit was tighter than
            # expected.  Surface the same sentinel as the pre-flight.
            logger.error("Google Cloud OCR payload too large: %s", exc)
            raise ValueError("IMAGE_TOO_LARGE") from exc
        if 500 <= exc.code < 600:  # noqa: PLR2004
            logger.error("Google Cloud OCR service unavailable: %s", exc)
            raise ValueError("SERVICE_UNAVAILABLE_ERROR") from exc
        logger.error("Google Cloud OCR HTTP error: %s", exc)
        raise
    except urllib.error.URLError as exc:
        # Network-level failures (DNS, refused connection).  Map to
        # CONNECTION_ERROR so the UI shows "offline / network down".
        logger.error("Google Cloud OCR connection error: %s", exc)
        raise ValueError("CONNECTION_ERROR") from exc
    except TimeoutError as exc:
        logger.error("Google Cloud OCR timeout: %s", exc)
        raise ValueError("TIMEOUT_ERROR") from exc
    except Exception as e:
        logger.error("Google Cloud OCR error: %s", e)
        raise
