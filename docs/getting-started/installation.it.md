---
description: Installa AI Translate su Windows, macOS o Linux da binari precompilati o dal sorgente — copre Python, FFmpeg e configurazione opzionale di LibreOffice.
---

# Installazione

## Cosa ti serve

- **Python 3.12 o più recente** ([download](https://www.python.org/downloads/))
- **[uv](https://docs.astral.sh/uv/)** — gestore pacchetti Python veloce. Installa con:

    === "macOS / Linux"
        ```bash
        curl -LsSf https://astral.sh/uv/install.sh | sh
        ```

    === "Windows"
        ```powershell
        powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
        ```

- **Una chiave API LLM** — una di:
    - [Google Gemini](https://aistudio.google.com/apikey) (livello gratuito disponibile — consigliato per iniziare)
    - Qualsiasi endpoint compatibile OpenAI (OpenAI, Anthropic via proxy, Ollama / LM Studio locale, ecc.)

## Opzionale, ma sblocca più funzionalità

| Strumento | Usato da | Quando ti serve |
|---|---|---|
| **FFmpeg** ([download](https://ffmpeg.org/download.html)) | Sottotitolo, Voce, Doppiaggio, Live | Qualsiasi flusso audio/video |
| **LibreOffice** ([download](https://www.libreoffice.org/download/)) | Formati Office su Linux/macOS | Tradurre legacy `.doc` / `.xls` / `.ppt`, o qualsiasi file Office quando MS Office non è installato |
| **Tesseract** ([guida installazione](https://tesseract-ocr.github.io/tessdoc/Installation.html)) | Motore OCR (default) | Pagina Estrai testo, traduzione PDF scansionati, traduzione immagini incorporate |
| **MS Office** + **pywin32** | Office su Windows | Traduzione Office di massima fedeltà su Windows |

Puoi installare AI Translate senza nessuno di questi — le funzionalità
che ne hanno bisogno te lo dicono prima di fallire.

## Setup

```bash
git clone https://github.com/cadic2603/ai-translate.git
cd ai-translate
uv sync
```

Questo installa tutto il necessario per eseguire l'app desktop, il CLI
e il server MCP.

## Eseguilo

=== "App desktop"
    ```bash
    uv run python -m src.main
    ```

=== "Riga di comando"
    ```bash
    uv run ait --version
    ```

=== "Server MCP"
    ```bash
    uv run ait-mcp           # trasporto stdio (per Claude Desktop / Code)
    ```

## Aggiungi la tua chiave API

La prima volta che apri l'app desktop:

1. Clicca su **Impostazioni** nella barra laterale
2. Apri il tab **LLM**
3. Incolla la tua **chiave API Google Gemini** (o configura un provider
   personalizzato compatibile OpenAI). Gli utenti enterprise possono
   cambiare Gemini in **modalità Vertex AI** — puntalo a un progetto
   e regione GCP, opzionalmente fornisci un percorso JSON di service
   account; vedi [Provider LLM](../setup/llm-providers.md) per i dettagli.
4. Scegli un modello di default — qualsiasi variante Flash attuale (es.
   `gemini-2.5-flash`) è un solido punto di partenza gratuito. Le
   varianti Pro danno qualità migliore a costo più alto.
5. Chiudi le Impostazioni — hai finito

Le chiavi sono salvate nel **portachiavi del tuo OS** (Keychain macOS,
Credential Manager Windows, GNOME / KDE Secret Service su Linux), non
in chiaro su disco.

!!! tip "Installazione headless / server"
    Se non puoi eseguire l'app desktop per configurare le chiavi, vedi
    [Provider LLM](../setup/llm-providers.md) per i comandi CLI keychain.

## Avanti: provala

[Prima traduzione in 5 minuti →](first-translation.md){ .md-button .md-button--primary }
