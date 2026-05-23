---
description: Diagnose AI Translate issues — missing fonts, FFmpeg errors, LibreOffice converter problems, OCR setup failures, and LLM API authentication.
---

# Troubleshooting

Common errors, what they mean, and how to fix them.

## Setup errors

### "LLM is not configured"

You haven't added an API key yet. Open the desktop app → **Settings →
LLM** → paste a key. See [LLM Providers](setup/llm-providers.md) for
the full guide.

### `AUTH_ERROR`

The LLM API key is wrong or expired.

- **Gemini** — generate a new key at <https://aistudio.google.com/apikey>,
  re-paste in **Settings → LLM**.
- **Custom provider** — verify the key is valid (curl the endpoint
  manually with the same `Authorization: Bearer …` header). If the
  endpoint moved, update the **API endpoint** field too.

### `QUOTA_ERROR`

You've hit a free-tier or paid-plan limit.

- **Gemini free tier** — daily request quota varies per model
  (see <https://ai.google.dev/gemini-api/docs/rate-limits>).
  Wait a day, or upgrade to paid.
- **OpenAI / others** — check your billing dashboard. Many providers
  have "spend caps" that pause requests when you hit them.

### `MODEL_NOT_FOUND`

The model name you picked isn't available.

- Custom providers — make sure the model is in the **Models**
  comma-separated list in **Settings → LLM**.
- Built-in Gemini list — switch to a documented model in **Settings →
  LLM → Default Gemini model**.

### `VISION_NOT_SUPPORTED`

You picked a non-vision model and tried to translate an image / scanned
PDF. Switch to a model whose name contains `flash`,
`pro`, or `vision` (e.g. `gpt-4o` for OpenAI, any current Gemini Flash
or Pro variant for Gemini).

## Audio / video errors

### `FFMPEG_NOT_FOUND`

FFmpeg isn't on PATH. See [FFmpeg setup](setup/ffmpeg.md) for the
install command for your OS.

The MCP server re-wraps this as: *"FFmpeg is required to decode this
audio/video file but is not installed or not on PATH."*

### Live page shows no captions

- **Wrong audio source** — open **Settings → Live → Audio source** and
  make sure it matches what you actually want (Microphone / System /
  Both).
- **Mic muted** — check OS sound settings; the app uses your default
  input device.
- **System audio not set up** — see [System audio capture](setup/system-audio.md)
  for the macOS / Windows loopback steps.

### Voice output is silent / empty

- **ElevenLabs without key** — the Voice page shows a friendly dialog
  pre-flight; if it slipped through, the file may be empty bytes.
  Check **Settings → Service → ElevenLabs API key**.
- **Edge TTS network error** — Edge TTS requires internet; if your
  firewall blocks `speech.platform.bing.com`, switch to ElevenLabs,
  Google Cloud TTS, or **Piper TTS** (fully offline).

### "Piper voice not installed" dialog

The Voice / Dubbing / Translate Text pages pre-flight that the Piper
voice for your target language is on disk before any worker starts.
If it isn't, you'll see a modal with an **Open Settings** button.

To download the voice:

1. Click **Open Settings** in the dialog (or open **Settings →
   Voice** manually).
2. Make sure **TTS method** is set to **Piper TTS**.
3. Click **Download voices now** to open the voice library dialog.
4. Find your target language's row, then click **Female voice** or
   **Male voice** next to it. Voices are ~25–60 MB ONNX files
   downloaded from HuggingFace; one-time per language.
5. Close the dialog and re-run your translation / voice / dub job.

If your target language isn't in the list, it has no Piper coverage —
the engine silently falls back to Edge TTS at synthesis time, so you
don't actually need to download anything. The 13 languages without
Piper voices today: Belarusian, Bengali, Chinese (Traditional),
Croatian, Estonian, Hebrew, Japanese, Khmer, Korean, Lithuanian,
Malay, Mongolian, Thai.

The **Live Translation** page is the one place that *won't* show this
dialog — interrupting a live stream with a modal would be worse than
the fallback, so missing-voice cases there silently route to Edge TTS.

## Document translation errors

### PDF translation fails on a specific page

PDFs use per-page checkpointing — successful pages aren't redone. The
failed page logs a stack to `app.log`; common culprits:

- Page is a **scan with no text layer** and OCR isn't configured. Set
  up **Settings → OCR** (see [OCR engines](setup/ocr-engines.md)).
- Page contains **complex math layout** the LLM mangled. Try a stronger
  model (a Pro variant rather than Flash).

### Office translation breaks formatting

- **Modern formats** (`.docx`, `.xlsx`, `.pptx`) — formatting is
  preserved per-run via HTML round-trip. If you see stray `<b>` tags
  in the output, the LLM didn't close them — re-run with a stronger
  model.
- **Legacy formats** (`.doc`, `.xls`, `.ppt`) — turn on **Settings →
  Translation → Auto-convert legacy** for far better fidelity. The
  pipeline converts to `.docx` first, translates, converts back.

### Translation queue stops mid-batch

Quit the app and check the database:

```bash
sqlite3 ~/.local/share/ai-translate/translator.db \
  "SELECT id, status, error_code, file_name FROM history WHERE status NOT IN ('Done', 'Failed') ORDER BY created_at DESC LIMIT 10;"
```

`Translating` rows that haven't been touched in minutes mean a worker
crashed silently. Re-launch the desktop app — it auto-resumes Pending
/ Translating tasks on startup.

## Cross-cutting issues

### Multiple files at once silently translate as one

Drop one file at a time, OR check the **Files** column in the queue
header — it should show the count you dropped. The 100-file cap shows
a notification when exceeded.

### Sidebar shows a spinner forever

Indicates a worker is still flagged as running. Quit the app cleanly
(no SIGKILL) — the autouse cleanup hooks reset the flags. If a SIGKILL
left state stuck, clear the DB workers manually:

```bash
sqlite3 ~/.local/share/ai-translate/translator.db \
  "UPDATE history SET status='Failed', error_code=99 WHERE status IN ('Pending', 'Translating');"
```

### Where are the logs?

| OS | Path |
|---|---|
| **Linux** | `~/.local/state/log/ai-translate/app.log` |
| **macOS** | `~/Library/Logs/ai-translate/app.log` |
| **Windows** | `%LOCALAPPDATA%\ai-translate\logs\app.log` |

Logs always capture DEBUG+ regardless of console verbosity. Console
output is INFO+ by default; pass `--verbose` to the CLI to mirror the
full file log on stdout.

## Still stuck?

- See the [FAQ](faq.md) for design-level questions.
- File an issue at <https://github.com/cadic2603/ai-translate/issues>
  with: OS, Python version, the failing command, the relevant slice of
  `app.log`, and a description of what you expected.
