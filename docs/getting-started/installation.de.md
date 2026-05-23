---
description: Installieren Sie AI Translate auf Windows, macOS oder Linux aus vorgefertigten Binärdateien oder dem Quellcode — behandelt Python, FFmpeg und optionale LibreOffice-Einrichtung.
---

# Installation

## Was Sie brauchen

- **Python 3.12 oder neuer** ([Download](https://www.python.org/downloads/))
- **[uv](https://docs.astral.sh/uv/)** — schneller Python-Paketmanager. Installation:

    === "macOS / Linux"
        ```bash
        curl -LsSf https://astral.sh/uv/install.sh | sh
        ```

    === "Windows"
        ```powershell
        powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
        ```

- **Ein LLM-API-Schlüssel** — eines von:
    - [Google Gemini](https://aistudio.google.com/apikey) (kostenlose Stufe verfügbar — empfohlen für den Einstieg)
    - Jeder OpenAI-kompatible Endpunkt (OpenAI, Anthropic via Proxy, lokales Ollama / LM Studio, etc.)

## Optional, aber schaltet mehr Funktionen frei

| Tool | Verwendet von | Wann benötigt |
|---|---|---|
| **FFmpeg** ([Download](https://ffmpeg.org/download.html)) | Untertitel, Stimme, Synchronisation, Live | Jeder Audio-/Video-Workflow |
| **LibreOffice** ([Download](https://www.libreoffice.org/download/)) | Office-Formate auf Linux/macOS | Übersetzen von Legacy `.doc` / `.xls` / `.ppt`, oder jeder Office-Datei wenn MS Office nicht installiert ist |
| **Tesseract** ([Installationsanleitung](https://tesseract-ocr.github.io/tessdoc/Installation.html)) | OCR-Engine (Standard) | Seite Text extrahieren, Übersetzung gescannter PDFs, Übersetzung eingebetteter Bilder |
| **MS Office** + **pywin32** | Office unter Windows | Höchste Office-Übersetzungsgenauigkeit auf Windows |

Sie können AI Translate ohne diese installieren — Funktionen, die sie
brauchen, sagen es Ihnen, bevor sie fehlschlagen.

## Einrichten

```bash
git clone https://github.com/cadic2603/ai-translate.git
cd ai-translate
uv sync
```

Das installiert alles, was zum Ausführen der Desktop-App, des CLI und
des MCP-Servers benötigt wird.

## Ausführen

=== "Desktop-App"
    ```bash
    uv run python -m src.main
    ```

=== "Kommandozeile"
    ```bash
    uv run ait --version
    ```

=== "MCP-Server"
    ```bash
    uv run ait-mcp           # stdio-Transport (für Claude Desktop / Code)
    ```

## API-Schlüssel hinzufügen

Wenn Sie die Desktop-App zum ersten Mal öffnen:

1. Klicken Sie in der Seitenleiste auf **Einstellungen**
2. Öffnen Sie den Tab **LLM**
3. Fügen Sie Ihren **Google Gemini API-Schlüssel** ein (oder konfigurieren
   Sie einen benutzerdefinierten OpenAI-kompatiblen Anbieter).
   Enterprise-Benutzer können Gemini stattdessen in den **Vertex-AI-Modus**
   umschalten — auf ein GCP-Projekt und Region zeigen, optional einen
   Service-Account-JSON-Pfad angeben; siehe
   [LLM-Anbieter](../setup/llm-providers.md) für Details.
4. Wählen Sie ein Standardmodell — jede aktuelle Flash-Variante (z. B.
   `gemini-2.5-flash`) ist ein solider kostenloser Ausgangspunkt.
   Pro-Varianten bieten bessere Qualität zu höheren Kosten.
5. Schließen Sie die Einstellungen — fertig

Die Schlüssel werden im **OS-Schlüsselbund** Ihres Systems gespeichert
(macOS Keychain, Windows Credential Manager, GNOME / KDE Secret Service
auf Linux), nicht im Klartext auf der Festplatte.

!!! tip "Headless-/Server-Installation"
    Wenn Sie die Desktop-App nicht ausführen können, um Schlüssel
    einzurichten, siehe [LLM-Anbieter](../setup/llm-providers.md) für
    die Keychain-CLI-Befehle.

## Weiter: Probieren Sie es aus

[Erste Übersetzung in 5 Minuten →](first-translation.md){ .md-button .md-button--primary }
