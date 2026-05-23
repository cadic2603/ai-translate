---
description: AI Translate è un traduttore desktop gratuito e multipiattaforma per documenti, PDF, sottotitoli, audio e parlato in tempo reale in oltre 45 lingue.
---

# AI Translate

Un traduttore desktop gratuito e multipiattaforma che gestisce **45 lingue**
e va ben oltre il testo semplice — traduce documenti, audio, video, parlato
in tempo reale, screenshot e altro, tutto attraverso una singola pipeline
basata su LLM.

<div class="grid cards" markdown>

-   :material-cursor-default-click-outline:{ .lg .middle } **App desktop**

    ---

    Trascina dentro un file, scegli una lingua di destinazione, ricevi una
    copia tradotta. Drag-and-drop, cronologia, glossari, tutto.

    [:octicons-arrow-right-24: Tutorial di 5 minuti](getting-started/first-translation.md)

-   :material-console:{ .lg .middle } **Riga di comando**

    ---

    `ait report.docx --target French` — la stessa pipeline, scriptabile e
    senza interfaccia. Utile per CI, job batch, server.

    [:octicons-arrow-right-24: Guida CLI](cli.md)

-   :material-robot-outline:{ .lg .middle } **Agenti AI (MCP)**

    ---

    Espone la traduzione come strumenti Model Context Protocol affinché
    Claude Desktop, Claude Code e altri client MCP possano chiamarli
    direttamente.

    [:octicons-arrow-right-24: Configurazione MCP](mcp.md)

</div>

## Cosa puoi tradurre

| Tipo | Formati |
|---|---|
| **Documenti Office** | `.docx`, `.xlsx`, `.pptx`, `.odt`, `.ods`, `.odp`, più legacy `.doc` / `.xls` / `.ppt` |
| **PDF** | traduzione extract-overlay con preservazione del layout, traduzione di segnalibri / form / link, fallback OCR per scansioni |
| **Testo & web** | `.txt`, `.md`, `.rst`, `.html` / `.htm` / `.xhtml`, `.xml`, `.rtf`, `.json`, `.csv`, `.epub` |
| **Sottotitoli** | `.srt`, `.vtt`, `.ass`, `.ssa` |
| **Localizzazione** | `.po`, `.pot`, `.xliff` / `.xlf`, `.yaml` / `.yml`, `.properties`, `.strings` |
| **Immagini** | `.png`, `.jpg`, `.jpeg`, `.bmp`, `.webp`, `.tiff`, `.tif` (OCR o LLM vision) |
| **Audio** | `.mp3`, `.wav`, `.m4a`, `.flac`, `.ogg`, `.aac`, `.wma` |
| **Video** | `.mp4`, `.webm`, `.mkv`, `.avi`, `.mov`, `.wmv` (pipeline di doppiaggio completa) |

## Funzionalità principali {: #headline-features }

- **[Traduci testo](features/translate-text.md)** — traduzione LLM istantanea con auto-rilevamento, modifica in loco, riproduzione TTS. Le lingue da destra a sinistra (arabo, ebraico, persiano) si renderizzano nativamente.
- **[Traduci documento](features/translate-document.md)** — rilascia file, osserva uno spinner di progresso per task, ricevi copie tradotte affiancate. I target RTL ricevono markup bidi appropriato; `Ctrl+P` / `Ctrl+G` mettono in pausa e continuano la coda.
- **[Genera sottotitolo (STT)](features/generate-subtitle.md)** — trascrive audio / video in SRT / VTT / ASS / SSA.
- **[Genera voce (TTS)](features/generate-voice.md)** — sintetizza sottotitoli in MP3 / WAV con timing.
- **[Doppiaggio video](features/dubbing.md)** — STT → traduci → TTS → mix completo nel video sorgente.
- **[Traduzione live](features/live-translation.md)** — overlay di sottotitoli in tempo reale da microfono o audio di sistema.
- **[Estrai testo](features/extract-text.md)** — OCR o LLM vision → `.txt` / `.docx`.
- **[Glossario](features/glossary.md)** — applica terminologia coerente attraverso le traduzioni.

!!! tip "Modalità Vertex AI per Gemini"
    Gli utenti enterprise possono cambiare le chiamate Gemini dalla
    Developer API a **Vertex AI** in **Impostazioni → LLM** —
    puntalo al tuo progetto e regione GCP, opzionalmente fornisci un
    percorso JSON di service account. Vedi
    [Provider LLM](setup/llm-providers.md#google-gemini-recommended-for-first-time-setup).

!!! tip "Prima volta qui?"
    Inizia con [Installazione](getting-started/installation.md), poi il
    [tutorial della prima traduzione di 5 minuti](getting-started/first-translation.md).
    Avrai un documento tradotto in meno di 10 minuti da un clone fresco.
