---
description: Files को headlessly अनुवाद करने के लिए ait command-line interface का उपयोग करें — script या CI job से PDFs, Office docs, subtitles, और 45+ languages को support करता है।
---

# Command Line (`ait`)

Headless translation — desktop app के समान pipeline, कोई display
आवश्यक नहीं। CI, batch jobs, servers, और scripted workflows के लिए
उपयोगी।

## Quick start

```bash
ait report.docx --target French
```

Output source के बगल में `report_translated_<src>_<tgt>.docx` के रूप
में आता है।

## सामान्य recipes

### कई files

```bash
ait *.pdf --target Japanese
```

Glob expansion shell का काम है (Unix)। Windows / `cmd.exe` पर,
files को explicitly list करें या PowerShell का उपयोग करें:

```powershell
ait (Get-ChildItem *.pdf) --target Japanese
```

### Custom output directory

```bash
ait report.docx --target French --output ./translated/
```

Directory create की जाती है यदि वह मौजूद नहीं है। यदि यह create
नहीं हो सकती (permission denied, आदि) तो आपको एक स्पष्ट error
मिलता है और exit code 2 — कोई half-run नहीं।

### Source language निर्दिष्ट करें

```bash
ait letter.txt --target German --source "English (US)"
```

Source matching case-insensitive है। बेयर "Chinese" एक hint print
करता है:

```bash
ait letter.txt --target Chinese
# Error: unknown target language 'Chinese'.
# Did you mean one of: Chinese (Simplified), Chinese (Traditional)?
```

### एक specific model चुनें

```bash
ait big-doc.pdf --target French --model "Gemini:gemini-2.5-pro"
# या desktop app के LLM tab में registered कोई भी अन्य Provider:model_name।
```

Format सख्ती से `Provider:model_name` है। Missing colon → exit 2
के साथ silently default Gemini model पर fall back होने के बजाय एक
स्पष्ट message।

### Office options

```bash
ait deck.pptx --target Vietnamese \
    --translate-images \
    --translate-comments \
    --translate-shapes \
    --translate-notes
```

`--translate-images` को OCR configured की आवश्यकता है (देखें
[OCR engines](setup/ocr-engines.md))।

### Auto-convert legacy formats

```bash
ait old-doc.doc --target French --convert-legacy
```

Pipeline पहले `.doc` → `.docx` convert करता है (better fidelity),
modern copy का अनुवाद करता है, वापस convert करता है। `--convert-odf`
और `.odt` / `.ods` / `.odp` के लिए वही।

### Quiet / verbose

```bash
ait report.docx --target French --quiet      # only errors
ait report.docx --target French --verbose    # full DEBUG firehose
```

Default mode एक banner और per-task progress को stderr पर print
करता है; full detail (HTTP body dumps, retry logs) console
verbosity की परवाह किए बिना platform की app-log directory में जाता
है (अपने OS पर path के लिए
[Troubleshooting → Where are the logs?](troubleshooting.md#where-are-the-logs)
देखें)।

### Supported languages list करें

```bash
ait --list-languages
```

सभी 45 supported languages print करता है। Shell loops में piping के
लिए उपयोगी।

### Version

```bash
ait --version
# ait 0.1.0
```

## Exit codes

| Code | अर्थ |
|---|---|
| `0` | सभी tasks succeeded |
| `2` | Argument error (unknown language, missing target, malformed model, unwritable output, unsupported file extension) |
| `3` | LLM configured नहीं है |
| `4` | Partial failure (कुछ succeeded, कुछ नहीं) |
| `5` | सभी failed |
| `130` | Interrupted (`Ctrl+C`) |

## Cancellation

`Ctrl+C` एक बार — cooperative cancel। वर्तमान task का checkpoint
save किया जाता है, pipeline अगले polling boundary पर cleanly
exit करती है।

`Ctrl+C` फिर से — hard interrupt। Sparingly उपयोग करें; partial
files half-written state में छूट सकती हैं।

## Full flag reference

```bash
ait --help
```

हर flag को इसके default के साथ दिखाता है। यहाँ वही content
सारांशित है:

| Flag | Default | Notes |
|---|---|---|
| `--target / -t LANG` | _required_ | Case-insensitive |
| `--source / -s LANG` | auto-detect | Case-insensitive |
| `--output / -o DIR` | source's parent | Missing होने पर create |
| `--model / -m PROVIDER:MODEL` | desktop default | Strict format |
| `--ocr-method METHOD` | `TesseractOCR` | `Tesseract`, `EasyOCR`, `Google Cloud OCR` |
| `--translate-images` | off | OCR configured की आवश्यकता है |
| `--translate-comments` | off | Office comments |
| `--translate-shapes` | off | Shapes / text boxes |
| `--translate-notes` | off | PowerPoint speaker notes |
| `--translate-sheet-names` | off | Excel sheet tabs |
| `--convert-legacy` | off | `.doc`/`.xls`/`.ppt` → modern format |
| `--convert-odf` | off | `.odt`/`.ods`/`.odp` → OOXML |
| `--keep-history` | off | Completion के बाद history entries रखें |
| `--quiet / -q` | off | Console पर केवल errors |
| `--verbose / -v` | off | DEBUG firehose |
| `--list-languages` | — | 45 languages print करें और exit |
| `--version` | — | Version print करें और exit |

## टिप्स

!!! tip "एक बार setup करें, हर जगह उपयोग करें"
    CLI desktop app के साथ अपनी API keys और settings साझा करता है
    — सब कुछ GUI में एक बार सेट करें, फिर वहाँ से `ait` के साथ
    automate करें।

!!! tip "Cold-start endpoint cache"
    प्रत्येक `(endpoint, model)` pair के लिए, chat-vs-responses-API
    choice और working payload variant OS cache directory में
    `llm_endpoint_cache.json` में persist किए जाते हैं (Linux पर
    `~/.cache/ai-translate/`, macOS पर
    `~/Library/Caches/ai-translate/`, Windows पर
    `%LOCALAPPDATA%\ai-translate\cache\`)। पहले successful call के
    बाद Cold-start CLI invocations auto-detection probe को पूरी तरह
    skip करते हैं — provider-specific payload tuning की आवश्यकता
    वाले Azure / vLLM / OpenRouter / Anthropic / DeepSeek
    deployments के खिलाफ scripting करते समय उपयोगी। Cache
    multi-process और multi-thread safe है (atomic rename के साथ
    RLock के तहत read-merge-write)।

!!! tip "Output streams"
    Default mode banner, queued-task list, और per-task progress को
    **stdout** पर print करता है (line-buffered ताकि errors के साथ
    सही ढंग से interleave हो); error messages और log records
    **stderr** पर जाते हैं। Clean piping के लिए stdout को पूरी तरह
    suppress करने के लिए `--quiet` के साथ combine करें:

    ```bash
    ait --list-languages | grep -i japanese    # stdout पर data
    ait file.txt --target French --quiet 2> errors.log
    ```
