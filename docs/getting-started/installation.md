---
description: Install AI Translate on Windows, macOS, or Linux from prebuilt binaries or source — covers Python, FFmpeg, and optional LibreOffice setup.
---

# Installation

## What you need

- **Python 3.12 or newer** ([download](https://www.python.org/downloads/))
- **[uv](https://docs.astral.sh/uv/)** — fast Python package manager. Install with:

    === "macOS / Linux"
        ```bash
        curl -LsSf https://astral.sh/uv/install.sh | sh
        ```

    === "Windows"
        ```powershell
        powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
        ```

- **An LLM API key** — any of:
    - [Google Gemini](https://aistudio.google.com/apikey) (free tier available — recommended for getting started)
    - Any OpenAI-compatible endpoint (OpenAI, Anthropic via proxy, local Ollama / LM Studio, etc.)

## Optional, but unlocks more features

| Tool | Used by | When you need it |
|---|---|---|
| **FFmpeg** ([download](https://ffmpeg.org/download.html)) | Subtitle, Voice, Dubbing, Live | Any audio/video workflow |
| **LibreOffice** ([download](https://www.libreoffice.org/download/)) | Office formats on Linux/macOS | Translating legacy `.doc` / `.xls` / `.ppt`, or any Office file when MS Office isn't installed |
| **Tesseract** ([install guide](https://tesseract-ocr.github.io/tessdoc/Installation.html)) | OCR engine (default) | Extract Text page, scanned-PDF translation, embedded-image translation |
| **MS Office** + **pywin32** | Office on Windows | Highest fidelity Office translation on Windows |

You can install AI Translate without any of these — features that need them
will tell you so before they fail.

## Set it up

```bash
git clone https://github.com/cadic2603/ai-translate.git
cd ai-translate
uv sync
```

That installs everything needed to run the desktop app, the CLI, and the
MCP server.

## Run it

=== "Desktop app"
    ```bash
    uv run python -m src.main
    ```

=== "Command line"
    ```bash
    uv run ait --version
    ```

=== "MCP server"
    ```bash
    uv run ait-mcp           # stdio transport (for Claude Desktop / Code)
    ```

## Add your API key

The first time you open the desktop app:

1. Click **Settings** in the sidebar
2. Open the **LLM** tab
3. Paste your **Google Gemini API key** (or configure a custom OpenAI-compatible
   provider). Enterprise users can flip Gemini to **Vertex AI mode** instead —
   point it at a GCP project and region, optionally supply a service-account
   JSON path; see [LLM Providers](../setup/llm-providers.md) for the details.
4. Pick a default model — any current Flash variant (e.g. `gemini-2.5-flash`)
   is a solid free starting point. Pro variants give better quality at higher
   cost.
5. Close Settings — you're done

Keys are stored in your **OS keychain** (macOS Keychain, Windows Credential Manager,
GNOME / KDE Secret Service on Linux), not in plain text on disk.

!!! tip "Headless / server install"
    If you can't run the desktop app to set up keys, see
    [LLM Providers](../setup/llm-providers.md) for the keychain CLI commands.

## Next: take it for a spin

[5-minute first translation →](first-translation.md){ .md-button .md-button--primary }
