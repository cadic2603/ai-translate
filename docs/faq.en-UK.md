---
description: "Common questions about AI Translate: supported file formats, free vs paid features, offline use, LLM provider choices, and OCR engine selection."
---

# Frequently Asked Questions

## General

### Does it work offline?

Mostly yes. Specifically:

- **Translation** needs an LLM. The free Gemini API is online; **local
  Ollama / LM Studio** through the Custom Provider settings is fully
  offline.
- **OCR** with **Tesseract** or **EasyOCR** is offline.
- **STT** with **Whisper** (default) is offline.
- **TTS** with **Edge TTS** (default) is online; **ElevenLabs** /
  **Google Cloud TTS** / **Gemini TTS** are online (free or paid);
  **Piper TTS** is fully offline neural TTS — no key, no network calls
  once you've downloaded the per-language voice (~25–60 MB ONNX file)
  via **Settings → Voice → Piper TTS → Download voices now**.

For a fully air-gapped setup: Custom Provider → local LLM, Tesseract or
EasyOCR for OCR, Whisper for STT, and Piper TTS for voice output.

### Where are my translated files saved?

Next to the original by default, with a `_translated_<src>_<tgt>` suffix
(e.g. `report_translated_en_fr.docx`). Override per-feature in
**Settings → General → Translation storage path**.

### Where are my settings stored?

INI file at:

| OS | Path |
|---|---|
| **Linux** | `~/.config/ai-translate/settings.ini` |
| **macOS** | `~/Library/Preferences/ai-translate/settings.ini` |
| **Windows** | `%APPDATA%\ai-translate\settings.ini` |

API keys live in the OS keychain (not in the INI). Translation history
lives in a SQLite DB in the data directory.

### How is my data handled?

- **Local-first** — text never leaves your machine unless you're calling
  a cloud LLM / OCR / STT / TTS service.
- **No telemetry** — the app doesn't phone home. The only outbound
  request the app itself makes is the optional GitHub-Releases update
  check (toggle in **Settings → General**); cloud backends only call
  their respective vendors.
- **API keys** — stored in your OS keychain. The desktop app's keychain
  fallback is a plaintext INI when no keychain daemon is available.

### Can I translate a Google Doc / Notion page?

Not directly. Export to `.docx` first, translate, then import the
translated file back. Same for Notion (export as Markdown / HTML),
Confluence (export as `.docx`), etc.

## Choosing models / engines

### Which LLM model should I use?

For most users:

- **Any Gemini Flash variant** — free tier, fast, surprisingly good. Use
  for everyday translations. Names look like `gemini-2.5-flash`,
  `gemini-3-flash-preview`, etc., depending on what's currently
  available.
- **Any Gemini Pro variant** — pay-per-token, higher quality. Use for
  important documents (legal, technical, customer-facing).
- **Local Ollama** with a 7B-13B model — when you need offline / privacy.

The per-feature model picker means you can use a fast model for
chat-style translation and reserve the expensive one for documents.

### Which OCR engine should I use?

- **Tesseract** for clean printed text in major scripts. Free, offline,
  fast.
- **EasyOCR** for non-Latin scripts (CJK especially) and noisier images.
- **Google Cloud Vision** for handwriting, mixed scripts, and the
  highest accuracy when you can pay.

### Which STT method should I use?

- **Whisper local** for offline / privacy.
- **Soniox** for multi-speaker recordings — speaker labels round-trip
  into your SRT.
- **Google Cloud STT** for telephony / medical audio (their domain
  models are good).
- **Gemini Live** for real-time speech-to-speech translation.

### Which TTS backend?

- **Edge TTS** for free, high-quality voices.
- **ElevenLabs** for premium / branded / cloned voices.
- **Google Cloud TTS** for WaveNet voices in long-tail languages where
  Edge has thin coverage.
- **Gemini TTS** for free natural prebuilt voices reusing your existing
  Gemini API key.
- **Piper TTS** when you need **offline / air-gapped** voice output.
  Trade-off: each language needs a one-time ~25–60 MB voice download
  via **Settings → Voice → Piper TTS → Download voices now**, and
  13 of the app's 45 languages have no Piper voice (those silently
  fall back to Edge TTS).

## Workflow

### How do I translate a whole folder?

Drop the folder into the **Translate Document** drop zone. Supported
files inside (recursively) get queued; everything else is silently
skipped. There's a 100-file drop cap; bigger batches → split into
multiple drops.

### Can I pause and resume translations?

Yes. Quit the app any time — Pending / Translating tasks resume on next
launch. Per-task checkpointing means PDF page 47 of 100 isn't redone
when you resume.

### Can I edit a translation by hand?

For **Translate Text** — yes, click the right pane and type. The
edit auto-saves to the entry's history record.

For **Translate Document** — open the translated file in your usual
editor (Word, LibreOffice, etc.) and edit there. The app doesn't
roundtrip the edits back into history.

### Can I bulk-translate a list of strings?

Use the CLI:

```bash
ait *.txt --target French
```

Or for in-process strings (e.g. UI strings extracted from code), call
the `translate_text` MCP tool with a list, or use the Python API
directly:

```python
from src.core.llm_engine import translate_text
out = translate_text(texts=["Hello", "World"], target_lang="French")
```

## Glossary

### Why isn't the LLM using my glossary?

Three things to check:

1. The set is **active** (checkbox checked).
2. The source term in your glossary actually appears in the source text
   (the per-call compression only sends the LLM entries that match the
   batch text — saves tokens, but means a typo'd source term is invisible).
3. The model is strong enough — `flash-lite` sometimes ignores hints
   that `flash` and `pro` honour.

### Glossary terms are matched accent-insensitively?

Yes. Both glossary lookup and the search box in the Glossary page use
a normalisation function that strips accents and case. So `cafe`,
`Café`, and `CAFE` all match an entry whose source is `Café`.

## Privacy

### Do you collect any usage data?

No. The app has no analytics SDK. The optional update check polls a
single GitHub Releases endpoint at startup; it's toggleable in
**Settings → General**.

### Are my API keys safe?

They're stored in your OS keychain (Keychain on macOS, Credential
Manager on Windows, Secret Service on Linux). Other processes can't
read them without your explicit permission. The fallback (when no
keychain daemon is available — typically headless Linux servers) is
a plaintext INI under your user's config directory; in that mode the
keys are file-permission-protected but not cryptographically encrypted.
