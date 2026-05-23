---
description: Instantly translate text snippets in 45+ languages with AI Translate — paste, type, or speak; supports edit mode, TTS playback, and language swap.
---

# Translate Text

Instant LLM translation with auto-detection, language swap, streaming
output, and TTS playback. Best for short snippets, chat-style use, and
testing your LLM setup.

## Walkthrough

1. Click **Translate Text** in the sidebar.
2. Type or paste your source text into the left pane.
3. The **Source** language auto-detects as you type (powered by `langdetect`).
4. Pick a **Target** language from the right-side dropdown.
5. Click **Translate** (or press `Ctrl+Enter`).
6. The translation streams into the right pane token-by-token.

## What you get

- **Streaming output** — translation appears as the LLM generates it, no
  waiting for the whole response.
- **Auto-detect source** — the source picker updates in real time. Click it
  to override.
- **Edit mode** — click the right pane to edit the translation manually.
  Press `Escape` to cancel an in-flight translation; press it again to
  exit edit mode.
- **History reuse** — every translation is saved. Click an entry in the
  Text Translation History panel below to re-load both panes; edits update
  the original entry instead of creating a duplicate.
- **TTS playback** — click the **Listen** button next to either pane to
  hear it read aloud. Honours your **Settings → Voice → TTS method**
  pick — Edge TTS (default), ElevenLabs, Google Cloud TTS, Gemini TTS,
  or **Piper TTS** (fully offline). With Piper selected, the Listen
  button runs the same pre-flight as the Voice page: a missing per-
  language voice surfaces a modal dialogue with an **Open Settings**
  button so you can download it. Cache hits skip the pre-flight
  entirely.
- **Per-feature model picker** — when more than one LLM is configured, a
  dropdown lets you pick a fast Flash model for speed or a heavier Pro
  model for quality, just for this page.

## Shortcuts

| Shortcut | Action |
|---|---|
| `Ctrl+Enter` | Translate |
| `Ctrl+L` | Swap source ↔ target |
| `Escape` | Cancel in-flight translation, or exit edit mode |
| `Ctrl+F` | Focus the history search |

## Tips

!!! tip "RTL languages"
    Translations into **Arabic**, **Hebrew**, or **Persian** automatically
    render right-to-left in the output pane. The same RTL handling carries
    through to file output across every format on the
    [Translate Document](translate-document.md) page (PDF, DOCX, PPTX,
    XLSX, ODF, RTF, HTML, EPUB, ASS/SSA), and Persian gets a native
    `fa-IR` voice for Edge TTS playback.

!!! tip "Listen-button cache"
    The first time you hit Listen on a given (text, language) pair the
    audio is synthesised and cached on disk. Subsequent plays are instant.
    The cache is wiped at app startup, so each session starts fresh.

!!! tip "Where the keys go"
    The Translate Text page reads the same keychain entries as the rest
    of the app — see [LLM Providers](../setup/llm-providers.md).
