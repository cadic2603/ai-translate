---
description: AI Translate is a free, cross-platform desktop translator for documents, PDFs, subtitles, audio, and live speech across 45+ languages.
---

# AI Translate

A free, cross-platform desktop translator that handles **45 languages** and
goes far beyond plain text — it translates documents, audio, video, live
speech, screen captures, and more, all with a single LLM-powered pipeline.

<div class="grid cards" markdown>

-   :material-cursor-default-click-outline:{ .lg .middle } **Desktop app**

    ---

    Drag a file in, pick a target language, get a translated copy back.
    Drag-and-drop, history, glossaries, the works.

    [:octicons-arrow-right-24: 5-minute walkthrough](getting-started/first-translation.md)

-   :material-console:{ .lg .middle } **Command line**

    ---

    `ait report.docx --target French` — the same pipeline, scriptable
    and headless.  Useful for CI, batch jobs, servers.

    [:octicons-arrow-right-24: CLI guide](cli.md)

-   :material-robot-outline:{ .lg .middle } **AI agents (MCP)**

    ---

    Expose translation as Model Context Protocol tools so Claude Desktop,
    Claude Code, and other MCP clients can call them directly.

    [:octicons-arrow-right-24: MCP setup](mcp.md)

</div>

## What you can translate

| Kind | Formats |
|---|---|
| **Office docs** | `.docx`, `.xlsx`, `.pptx`, `.odt`, `.ods`, `.odp`, plus legacy `.doc` / `.xls` / `.ppt` |
| **PDFs** | extract-overlay translation with layout preservation, bookmark / form / link translation, OCR fallback for scans |
| **Text & web** | `.txt`, `.md`, `.rst`, `.html` / `.htm` / `.xhtml`, `.xml`, `.rtf`, `.json`, `.csv`, `.epub` |
| **Subtitles** | `.srt`, `.vtt`, `.ass`, `.ssa` |
| **Localization** | `.po`, `.pot`, `.xliff` / `.xlf`, `.yaml` / `.yml`, `.properties`, `.strings` |
| **Images** | `.png`, `.jpg`, `.jpeg`, `.bmp`, `.webp`, `.tiff`, `.tif` (OCR or LLM vision) |
| **Audio** | `.mp3`, `.wav`, `.m4a`, `.flac`, `.ogg`, `.aac`, `.wma` |
| **Video** | `.mp4`, `.webm`, `.mkv`, `.avi`, `.mov`, `.wmv` (full dubbing pipeline) |

## Headline features

- **[Translate Text](features/translate-text.md)** — instant LLM translation with auto-detection, edit-in-place, TTS playback. Right-to-left languages (Arabic, Hebrew, Persian) render natively.
- **[Translate Document](features/translate-document.md)** — drop files, watch a per-task progress spinner, get translated copies side-by-side. RTL targets get proper bidi markup; `Ctrl+P` / `Ctrl+G` pause and continue the queue.
- **[Generate Subtitle (STT)](features/generate-subtitle.md)** — transcribe audio / video into SRT / VTT / ASS / SSA.
- **[Generate Voice (TTS)](features/generate-voice.md)** — synthesize subtitles into MP3 / WAV with timing.
- **[Video Dubbing](features/dubbing.md)** — full STT → translate → TTS → mix back into the source video.
- **[Live Translation](features/live-translation.md)** — real-time microphone or system-audio subtitle overlay.
- **[Extract Text](features/extract-text.md)** — OCR or LLM vision → `.txt` / `.docx`.
- **[Glossary](features/glossary.md)** — enforce consistent terminology across translations.

!!! tip "Vertex AI mode for Gemini"
    Enterprise users can flip Gemini calls from the Developer API to
    **Vertex AI** in **Settings → LLM** — point it at your GCP project
    and region, optionally supply a service-account JSON path. See
    [LLM Providers](setup/llm-providers.md#google-gemini-recommended-for-first-time-setup).

!!! tip "First time here?"
    Start with [Installation](getting-started/installation.md), then the
    [5-minute first-translation walkthrough](getting-started/first-translation.md).
    You'll have a translated document in under 10 minutes from a fresh clone.
