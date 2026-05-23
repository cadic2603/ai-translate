---
description: Use the ait command-line interface to translate files headlessly — supports PDFs, Office docs, subtitles, and 45+ languages from a script or CI job.
---

# Command Line (`ait`)

Headless translation — same pipeline as the desktop app, no display
required. Useful for CI, batch jobs, servers, and scripted workflows.

## Quick start

```bash
ait report.docx --target French
```

Output lands next to the source as `report_translated_<src>_<tgt>.docx`.

## Common recipes

### Multiple files

```bash
ait *.pdf --target Japanese
```

Glob expansion is the shell's job (Unix). On Windows / `cmd.exe`, list
files explicitly or use PowerShell:

```powershell
ait (Get-ChildItem *.pdf) --target Japanese
```

### Custom output directory

```bash
ait report.docx --target French --output ./translated/
```

The directory is created if it doesn't exist. If it can't be created
(permission denied, etc.) you get a clear error and exit code 2 — no
half-run.

### Specify source language

```bash
ait letter.txt --target German --source "English (US)"
```

Source matching is case-insensitive. Bare "Chinese" prints a hint:

```bash
ait letter.txt --target Chinese
# Error: unknown target language 'Chinese'.
# Did you mean one of: Chinese (Simplified), Chinese (Traditional)?
```

### Pick a specific model

```bash
ait big-doc.pdf --target French --model "Gemini:gemini-2.5-pro"
# Or any other Provider:model_name registered in the desktop app's LLM tab.
```

Format is strictly `Provider:model_name`. Missing colon → exit 2 with
a clear message instead of silently falling back to the default Gemini
model.

### Office options

```bash
ait deck.pptx --target Vietnamese \
    --translate-images \
    --translate-comments \
    --translate-shapes \
    --translate-notes
```

`--translate-images` requires OCR configured (see
[OCR engines](setup/ocr-engines.md)).

### Auto-convert legacy formats

```bash
ait old-doc.doc --target French --convert-legacy
```

The pipeline converts `.doc` → `.docx` first (better fidelity), translates
the modern copy, converts back. Same for `--convert-odf` and `.odt` /
`.ods` / `.odp`.

### Quiet / verbose

```bash
ait report.docx --target French --quiet      # errors only
ait report.docx --target French --verbose    # full DEBUG firehose
```

The default mode prints a banner and per-task progress to stderr; full
detail (HTTP body dumps, retry logs) lands in the platform's app-log
directory regardless of console verbosity (see
[Troubleshooting → Where are the logs?](troubleshooting.md#where-are-the-logs)
for the path on your OS).

### List supported languages

```bash
ait --list-languages
```

Prints all 45 supported languages. Useful for piping into shell loops.

### Version

```bash
ait --version
# ait 0.1.0
```

## Exit codes

| Code | Meaning |
|---|---|
| `0` | All tasks succeeded |
| `2` | Argument error (unknown language, missing target, malformed model, unwritable output, unsupported file extension) |
| `3` | LLM not configured |
| `4` | Partial failure (some succeeded, some didn't) |
| `5` | All failed |
| `130` | Interrupted (`Ctrl+C`) |

## Cancellation

`Ctrl+C` once — cooperative cancel. The current task's checkpoint is
saved, the pipeline exits cleanly at the next polling boundary.

`Ctrl+C` again — hard interrupt. Use sparingly; partial files may be
left in a half-written state.

## Full flag reference

```bash
ait --help
```

Shows every flag with its default. The same content is summarised here:

| Flag | Default | Notes |
|---|---|---|
| `--target / -t LANG` | _required_ | Case-insensitive |
| `--source / -s LANG` | auto-detect | Case-insensitive |
| `--output / -o DIR` | source's parent | Created if missing |
| `--model / -m PROVIDER:MODEL` | desktop default | Strict format |
| `--ocr-method METHOD` | `TesseractOCR` | `Tesseract`, `EasyOCR`, `Google Cloud OCR` |
| `--translate-images` | off | Requires OCR configured |
| `--translate-comments` | off | Office comments |
| `--translate-shapes` | off | Shapes / text boxes |
| `--translate-notes` | off | PowerPoint speaker notes |
| `--translate-sheet-names` | off | Excel sheet tabs |
| `--convert-legacy` | off | `.doc`/`.xls`/`.ppt` → modern format |
| `--convert-odf` | off | `.odt`/`.ods`/`.odp` → OOXML |
| `--keep-history` | off | Keep history entries after completion |
| `--quiet / -q` | off | Errors only on console |
| `--verbose / -v` | off | DEBUG firehose |
| `--list-languages` | — | Print 45 languages and exit |
| `--version` | — | Print version and exit |

## Tips

!!! tip "Setup once, use everywhere"
    The CLI shares its API keys and settings with the desktop app — set
    everything up once in the GUI, then automate with `ait` from there.

!!! tip "Cold-start endpoint cache"
    For each `(endpoint, model)` pair, the chat-vs-responses-API choice
    and the working payload variant are persisted to
    `llm_endpoint_cache.json` in the OS cache directory
    (`~/.cache/ai-translate/` on Linux,
    `~/Library/Caches/ai-translate/` on macOS,
    `%LOCALAPPDATA%\ai-translate\cache\` on Windows). Cold-start CLI
    invocations skip the auto-detection probe entirely after the first
    successful call — useful when scripting against Azure / vLLM /
    OpenRouter / Anthropic / DeepSeek deployments that need
    provider-specific payload tuning. The cache is multi-process and
    multi-thread safe (read-merge-write under RLock with atomic rename).

!!! tip "Output streams"
    Default mode prints the banner, queued-task list, and per-task
    progress to **stdout** (line-buffered so it interleaves correctly
    with errors); error messages and log records go to **stderr**.
    Combine with `--quiet` to suppress stdout entirely for clean
    piping:

    ```bash
    ait --list-languages | grep -i japanese    # data on stdout
    ait file.txt --target French --quiet 2> errors.log
    ```
