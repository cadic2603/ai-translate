---
description: Translate PDFs, Word, Excel, PowerPoint, ODF, EPUB, HTML, JSON, YAML, SRT, and 30+ other file formats while preserving formatting and layout.
---

# Translate Document

Translate full files — Office, PDF, EPUB, plain text, subtitles,
localisation formats, and more — with formatting preserved.

## Supported formats

| Category | Extensions |
|---|---|
| Office | `.docx`, `.xlsx`, `.pptx`, `.odt`, `.ods`, `.odp`, `.doc`, `.xls`, `.ppt` |
| PDF | `.pdf` |
| Text & web | `.txt`, `.md`, `.rst`, `.html`, `.htm`, `.xhtml`, `.xml`, `.rtf`, `.json`, `.csv` |
| eBooks | `.epub` |
| Subtitles | `.srt`, `.vtt`, `.ass`, `.ssa` |
| Localisation | `.po`, `.pot`, `.xliff`, `.xlf`, `.yaml`, `.yml`, `.properties`, `.strings` |

## Walkthrough

1. Click **Translate Document** in the sidebar.
2. Drag files in (or click **Browse**). Folders work too — supported files
   inside are picked up recursively.
3. Pick **Source** (or leave on `Auto-detect`) and **Target**.
4. Click **Translate** — or press `Ctrl+Enter`.
5. The history table below shows per-file progress (Pending → Translating
   → Done / Failed). The sidebar shows a spinner while any task is active.
6. Click **Open** on a row to open the translated file. Right-click for
   options: re-translate, pause, retry, delete.

## Where files end up

By default, translated files are saved next to the original with a
`_translated_<src>_<tgt>` suffix:

```
~/Documents/report.docx
~/Documents/report_translated_en_fr.docx     ← here
```

Change this in **Settings → General → Translation storage path** to a
custom directory.

## Limits and guards

- **100-file drop cap** — drop more and you'll get a notification. Translate
  in batches.
- **Duplicate detection** — drop a file already in the queue and you'll see
  a notification (the duplicate is dropped, not added twice).
- **Auto-resume** — quit the app while translations are running and they'll
  resume on next launch (Pending / Translating tasks).

## Office-specific options

The Translation tab in **Settings** exposes these toggles for Office files:

| Option | What it does |
|---|---|
| **Translate embedded images** | Runs OCR + LLM vision on images inside `.docx` / `.xlsx` / `.pptx` and re-inserts the translated image. Requires OCR configured. |
| **Translate comments** | Comments / review notes get translated alongside body text. |
| **Translate shapes & text boxes** | Catches text that lives in shapes, callouts, and floating text boxes. |
| **Translate speaker notes** | PowerPoint speaker notes are translated. |
| **Translate sheet names** | Excel sheet tab labels are translated. |
| **Auto-convert legacy** | `.doc` / `.xls` / `.ppt` are converted to modern OOXML before translation (better fidelity). |
| **Auto-convert ODF** | `.odt` / `.ods` / `.odp` are converted to OOXML before translation. |

All Office translation preserves per-run formatting: bold, italic,
underline, strikethrough, font size, colour, hyperlinks, headers,
footers, footnotes, endnotes, all of it.

### Embedded image translation: skip-with-warning + cache

When **Translate embedded images** is on, each embedded image goes
through OCR → LLM vision → rendered re-injection. Two behaviours
worth knowing about:

- **Skip-with-warning**: if one image fails to translate (too
  large, corrupt, vision model rejects the format, etc.) the
  document still completes — the broken image stays in the
  original language, a warning is logged to `app.log`, and the
  loop continues with the next image. Only fatal LLM errors
  (`AUTH_ERROR`, `QUOTA_ERROR`, `VISION_NOT_SUPPORTED`) stop the
  pipeline immediately, because they block every remaining image
  too. The info banner above the **Translate embedded images**
  checkbox documents the policy inline.
- **Per-image cache**: successful image translations are
  persisted under the task's internal storage directory keyed by
  SHA256 of the source bytes. On retry, already-translated images
  hit the cache instead of re-running OCR + LLM — paid work isn't
  redone. Duplicate images (a company logo on every slide)
  translate once and reuse N − 1 times.

The output file only appears in your chosen output folder on
**success** — partial translations from cancelled or failed runs
stay confined to the task's internal storage directory, so your
output folder never collects orphan half-translated docs.

## PDF specifics

PDFs use an extract-overlay engine: the original text is redacted in
place and translated text overlaid into the same boxes, keeping the
visual layout. Per-page checkpointing means a paused / crashed run
resumes from where it left off, not page 1.

What gets translated:

- Body text (with alignment detection — left / centre / right / justify)
- Bookmarks / outlines (TOC entries)
- Form fields (text inputs, dropdowns, list boxes)
- Hyperlinks (link rect updated to wrap the new text)
- Embedded images (when **Translate embedded images** is on)
- PDF comments / annotations

For scanned PDFs (no embedded text layer), OCR runs automatically per
page. Configure your OCR engine in **Settings → OCR**.

## Right-to-left output

Translations into **Arabic**, **Hebrew**, or **Persian** render as RTL
natively in every output format — `dir="rtl"` injected into PDF
overlays, HTML, and EPUB chapters (with `page-progression-direction="rtl"`
in the EPUB OPF so Apple Books and Kindle page-turn the right way);
DOCX `<w:bidi/>` + `<w:rtl/>`, PPTX `rtl="1"`, XLSX right-to-left sheet
view, ODT/ODS/ODP `style:writing-mode="rl-tb"`, RTF `\rtldoc`, and
ASS/SSA alignment-code mirroring (`\an1` ↔ `\an3`, `\an4` ↔ `\an6`,
etc.). Centre alignments are untouched.

## Shortcuts

| Shortcut | Action |
|---|---|
| `Ctrl+Enter` | Start translation |
| `Ctrl+O` | Browse for files |
| `Ctrl+F` | Focus history search |
| `Ctrl+P` | Pause the active queue |
| `Ctrl+G` | Continue (resume) the active queue |
| `Delete` | Delete selected history entries |

`Ctrl+P` / `Ctrl+G` are suppressed when a text-input has focus, so they
won't collide with typing.

## When things fail

A failed task shows a red status with an error code and a localised
message — see the [troubleshooting guide](../troubleshooting.md) for
common ones (`AUTH_ERROR`, `QUOTA_ERROR`, `FFMPEG_NOT_FOUND`, etc.).
