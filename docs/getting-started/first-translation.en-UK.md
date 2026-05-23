---
description: Translate your first document with AI Translate in 5 minutes — drag-and-drop a PDF, pick a target language, and download the translated copy.
---

# Your first translation

A quick end-to-end run — under 5 minutes once setup is done.

!!! abstract "Before you start"
    You need [installation](installation.md) finished and an LLM API key
    configured. The free Google Gemini tier is enough for a first try.

## Translate a Word document

1. Launch the desktop app:

    ```bash
    uv run python -m src.main
    ```

2. Click **Translate Document** in the left sidebar.

3. Drag any `.docx` file into the drop zone — or click **Browse** to pick one.

4. The file appears in the queue. Pick a target language at the top:

    - Source: `Auto-detect` (default — usually correct)
    - Target: e.g. `French`, `Vietnamese`, `Japanese`, `Chinese (Simplified)`

5. Click **Translate** (or press `Ctrl+Enter`).

6. Watch the progress bar in the history table at the bottom of the page.
   When it reaches 100%, click **Open** on the row to open the translated
   file — saved next to the original with a `_translated_<src>_<tgt>` suffix.

## What just happened

- Your `.docx` got cloned into a per-task storage folder so the original
  is untouched.
- The text was extracted, batched into LLM-friendly chunks, translated,
  then re-injected into the document with all formatting preserved (bold,
  italic, fonts, colours, headers, footnotes, hyperlinks…).
- A history entry was written to a SQLite database so you can re-open,
  re-run, or re-translate the file later.

## Try the quick wins next

=== "Translate plain text"

    Pop into **Translate Text** in the sidebar. Paste anything, pick a
    target, hit Enter. Streaming output, language-swap (`Ctrl+L`), edit
    mode, TTS playback.

=== "Generate subtitles"

    **Generate Subtitle** — drop an `.mp4`. You'll get an `.srt` back
    in the source language. (To translate _and_ dub the video, use the
    Dubbing page instead.)

=== "Live mic translation"

    **Live Translation** — pick microphone or system audio, pick a target,
    Start. A floating overlay window shows captions in real time.

## Where to next

- See the [feature index](../index.md#headline-features) for what each page does.
- Wire up [more providers](../setup/llm-providers.md) (custom endpoints, ElevenLabs, Soniox, Google Cloud).
- Try the [CLI](../cli.md) for batch / scripted runs.
