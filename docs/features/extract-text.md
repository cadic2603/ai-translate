---
description: Extract text from images and screenshots using OCR engines (Tesseract, EasyOCR, Google Vision) or vision LLMs — output to TXT or DOCX.
---

# Extract Text

Get the text out of images — receipts, screenshots, photographed
documents, scanned pages, anything. Outputs `.txt` (plain) or `.docx`
(formatted paragraphs).

This page **does not translate** — it just extracts. Pipe the output
into Translate Document if you also want translation.

## Two extraction methods

| Method | Best for |
|---|---|
| **OCR** | High-volume / batch / cost-sensitive (free or near-free per image) |
| **LLM vision** | Layout preservation, mixed scripts, low-quality images, handwriting |

Pick the default in **Settings → Extract Text → Extraction method**.

## OCR engines (OCR method)

| Engine | Cost | Offline | Languages | Notes |
|---|---|---|---|---|
| **Tesseract** | Free | Yes | 100+ | Default. Needs a system install. |
| **EasyOCR** | Free | Yes (after model download) | 80+ | Best for non-Latin scripts. ~1 GB models. |
| **Google Cloud Vision** | Paid (1,000 free / month) | No | 60+ | Highest accuracy. |

Configure in **Settings → OCR**.

## Walkthrough

1. Click **Extract Text** in the sidebar.
2. Drop one or more image files (`.png`, `.jpg`, `.jpeg`, `.bmp`, `.webp`,
   `.tiff`, `.tif`).
3. Pick the **Source language** (helps OCR pick the right model).
4. Pick the **Output format** — `.txt` or `.docx`.
5. Click **Extract** (or `Ctrl+Enter`).
6. **Open** the row when done.

## When to use which

- **Text-heavy receipt / invoice** → Tesseract is fast and accurate.
- **Photographed handwritten notes** → LLM vision wins by a lot.
- **Manga / comic panels** → EasyOCR (handles vertical CJK text well).
- **Form with lots of small fields** → Google Cloud Vision tends to
  preserve field boundaries better than the others.

## Tips

!!! tip "OCR or LLM, not both"
    The page picks one method and runs it. To compare outputs, run the
    same image twice with different methods.

!!! tip "Setup-required dialog"
    If you pick OCR but no OCR engine is configured (or LLM but no LLM
    key is configured), the page surfaces a single "Setup Required"
    dialog that links straight to the relevant Settings tab.

## Shortcuts

| Shortcut | Action |
|---|---|
| `Ctrl+Enter` | Extract |
| `Ctrl+O` | Browse |
| `Ctrl+F` | Focus history search |
