---
description: AI Translate ist ein kostenloser, plattformübergreifender Desktop-Übersetzer für Dokumente, PDFs, Untertitel, Audio und Live-Sprache in über 45 Sprachen.
---

# AI Translate

Ein kostenloser, plattformübergreifender Desktop-Übersetzer, der **45 Sprachen**
beherrscht und weit über reinen Text hinausgeht — er übersetzt Dokumente, Audio,
Video, Live-Sprache, Bildschirmaufnahmen und mehr, alles über eine einzige
LLM-gesteuerte Pipeline.

<div class="grid cards" markdown>

-   :material-cursor-default-click-outline:{ .lg .middle } **Desktop-App**

    ---

    Ziehen Sie eine Datei hinein, wählen Sie eine Zielsprache, erhalten
    Sie eine übersetzte Kopie zurück. Drag-and-Drop, Verlauf, Glossare,
    alles dabei.

    [:octicons-arrow-right-24: 5-Minuten-Walkthrough](getting-started/first-translation.md)

-   :material-console:{ .lg .middle } **Kommandozeile**

    ---

    `ait report.docx --target French` — dieselbe Pipeline, skriptfähig
    und headless. Nützlich für CI, Batch-Jobs, Server.

    [:octicons-arrow-right-24: CLI-Anleitung](cli.md)

-   :material-robot-outline:{ .lg .middle } **KI-Agenten (MCP)**

    ---

    Stellt Übersetzung als Model Context Protocol Tools bereit, sodass
    Claude Desktop, Claude Code und andere MCP-Clients sie direkt
    aufrufen können.

    [:octicons-arrow-right-24: MCP-Setup](mcp.md)

</div>

## Was Sie übersetzen können

| Art | Formate |
|---|---|
| **Office-Dokumente** | `.docx`, `.xlsx`, `.pptx`, `.odt`, `.ods`, `.odp`, plus Legacy `.doc` / `.xls` / `.ppt` |
| **PDFs** | Extract-Overlay-Übersetzung mit Layout-Erhaltung, Lesezeichen-/Formular-/Link-Übersetzung, OCR-Fallback für Scans |
| **Text & Web** | `.txt`, `.md`, `.rst`, `.html` / `.htm` / `.xhtml`, `.xml`, `.rtf`, `.json`, `.csv`, `.epub` |
| **Untertitel** | `.srt`, `.vtt`, `.ass`, `.ssa` |
| **Lokalisierung** | `.po`, `.pot`, `.xliff` / `.xlf`, `.yaml` / `.yml`, `.properties`, `.strings` |
| **Bilder** | `.png`, `.jpg`, `.jpeg`, `.bmp`, `.webp`, `.tiff`, `.tif` (OCR oder LLM-Vision) |
| **Audio** | `.mp3`, `.wav`, `.m4a`, `.flac`, `.ogg`, `.aac`, `.wma` |
| **Video** | `.mp4`, `.webm`, `.mkv`, `.avi`, `.mov`, `.wmv` (vollständige Synchronisations-Pipeline) |

## Hauptfunktionen {: #headline-features }

- **[Text übersetzen](features/translate-text.md)** — sofortige LLM-Übersetzung mit Auto-Erkennung, Vor-Ort-Bearbeitung, TTS-Wiedergabe. Rechts-nach-links-Sprachen (Arabisch, Hebräisch, Persisch) werden nativ gerendert.
- **[Dokument übersetzen](features/translate-document.md)** — Dateien fallen lassen, einen Fortschritts-Spinner pro Aufgabe beobachten, übersetzte Kopien Seite an Seite erhalten. RTL-Ziele erhalten ordentliches bidi-Markup; `Ctrl+P` / `Ctrl+G` pausieren und setzen die Warteschlange fort.
- **[Untertitel erzeugen (STT)](features/generate-subtitle.md)** — transkribiert Audio / Video in SRT / VTT / ASS / SSA.
- **[Stimme erzeugen (TTS)](features/generate-voice.md)** — synthetisiert Untertitel zu MP3 / WAV mit Timing.
- **[Video-Synchronisation](features/dubbing.md)** — vollständig STT → übersetzen → TTS → zurück in das Quellvideo mischen.
- **[Live-Übersetzung](features/live-translation.md)** — Echtzeit-Untertitel-Overlay vom Mikrofon oder System-Audio.
- **[Text extrahieren](features/extract-text.md)** — OCR oder LLM-Vision → `.txt` / `.docx`.
- **[Glossar](features/glossary.md)** — erzwingt einheitliche Terminologie über alle Übersetzungen hinweg.

!!! tip "Vertex-AI-Modus für Gemini"
    Enterprise-Nutzer können Gemini-Aufrufe von der Developer-API auf
    **Vertex AI** in **Einstellungen → LLM** umstellen — auf Ihr GCP-Projekt
    und Region zeigen, optional einen Pfad zu einer Service-Account-JSON
    angeben. Siehe
    [LLM-Anbieter](setup/llm-providers.md#google-gemini-recommended-for-first-time-setup).

!!! tip "Zum ersten Mal hier?"
    Beginnen Sie mit der [Installation](getting-started/installation.md), dann
    dem [5-Minuten-Walkthrough zur ersten Übersetzung](getting-started/first-translation.md).
    Sie haben in unter 10 Minuten ab einem frischen Clone ein übersetztes Dokument.
