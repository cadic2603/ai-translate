---
description: Set up OCR engines for image and PDF text extraction — choose between offline Tesseract or EasyOCR, or cloud-based Google Vision OCR.
---

# OCR Engines

OCR is used to read text out of images — both on the [Extract Text](../features/extract-text.md)
page and as a fallback inside Document translation when a page is
scanned (no text layer) or when you turn on **Translate embedded images**.

You can pick from three OCR engines.

## Tesseract (recommended default)

Free, fast, offline. Needs a system install.

=== "macOS"
    ```bash
    brew install tesseract tesseract-lang
    ```

=== "Ubuntu / Debian"
    ```bash
    sudo apt install tesseract-ocr tesseract-ocr-all
    ```

    `tesseract-ocr-all` brings every supported language. To save disk,
    install only what you need (e.g. `tesseract-ocr-fra` for French).

=== "Fedora / RHEL"
    ```bash
    sudo dnf install tesseract tesseract-langpack-eng tesseract-langpack-fra
    ```

=== "Windows"
    Download the installer from
    [UB Mannheim's Tesseract releases](https://github.com/UB-Mannheim/tesseract/wiki).
    Run it, accept the defaults — language packs are bundled.

Verify:

```bash
tesseract --version
tesseract --list-langs
```

In the desktop app: **Settings → OCR → OCR method = Tesseract**. Done.

## EasyOCR

Free, offline. Great for non-Latin scripts (Chinese, Korean, Japanese,
Thai). Models download on first use (~1 GB total).

```bash
uv sync --extra easyocr
```

In the desktop app: **Settings → OCR → OCR method = EasyOCR**.

The first time you use it for a language, the relevant model downloads
to `~/.EasyOCR/`. Subsequent runs are instant.

## Google Cloud Vision

Cloud, paid (1,000 free requests / month). Highest accuracy, especially
on noisy / handwritten / mixed-script content.

1. [Create a Google Cloud project](https://console.cloud.google.com/projectcreate)
2. Enable the [Vision API](https://console.cloud.google.com/apis/library/vision.googleapis.com)
3. [Create an API key](https://console.cloud.google.com/apis/credentials)
4. In the desktop app: **Settings → Service → Google Cloud API key** → paste
5. **Settings → OCR → OCR method = Google Cloud OCR**

The same Google Cloud API key powers Vision OCR, Speech-to-Text, and
Text-to-Speech if you also enable those APIs.

## Comparing accuracy

The **Settings → OCR** tab has a small comparison table built in —
language coverage, online/offline, cost, accuracy. Re-read it any time
you're tempted to switch.

## When OCR is used

| Place | Behaviour |
|---|---|
| **Extract Text page** (when method = OCR) | Direct OCR on the dropped images |
| **Translate Document → PDF** | OCR fallback on scan-only pages (no text layer) |
| **Translate Document → Office** with **Translate embedded images** on | OCR + LLM vision on every embedded image |

## Tips

!!! tip "Pick the source language"
    Most OCR engines are much more accurate when you tell them what
    language to expect. The Subtitle / Document / Extract Text pages all
    forward your **Source language** picker to the OCR engine.

!!! tip "Tesseract is enough for clean printed text"
    Don't reach for cloud OCR until Tesseract / EasyOCR has actually
    failed on your content. They're free, fast, and surprisingly good.
