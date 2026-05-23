# AI Translate

A cross-platform desktop application that translates files into 40+ languages — documents, PDFs, subtitles, images, audio, and live speech.

📖 **Full documentation: [cadic2603.github.io/ai-translate](https://cadic2603.github.io/ai-translate/)**

## Highlights

- **Documents** — DOCX / XLSX / PPTX / ODT / PDF / EPUB / HTML / Markdown / subtitles / localization files, with full formatting, hyperlinks, comments, headers/footers, footnotes, and embedded images preserved.
- **Multiple LLM providers** — Gemini (Developer API or Vertex AI) plus any OpenAI-compatible endpoint (OpenAI, Azure, Anthropic, DeepSeek, OpenRouter, Groq, vLLM, Ollama, LM Studio, …) via a 4-variant payload auto-fallback.
- **Speech** — Subtitle generation (Whisper / Google Cloud / Soniox), text-to-speech (Edge / Google Cloud / Gemini / Piper offline / ElevenLabs), end-to-end video dubbing, and real-time live translation with a floating subtitle overlay.
- **Headless** — `ait` CLI for terminal use and `ait-mcp` MCP server for AI agents (Claude Desktop, Claude Code, …).
- **Resumable** — Checkpoint system so paused or crashed tasks resume from the last completed stage; atomic output means partial files never appear in your output folder.

## Quickstart

Requires Python 3.12+ and [uv](https://github.com/astral-sh/uv).

```bash
git clone https://github.com/cadic2603/ai-translate.git
cd ai-translate
uv sync
uv run ai-translate
```

For CLI and MCP usage:

```bash
uv run ait report.docx --target French
uv run ait-mcp                                # stdio transport for Claude Desktop / Claude Code
```

See the [Getting Started](https://cadic2603.github.io/ai-translate/getting-started/) guide for installation details, provider setup, and per-feature walkthroughs.

## Tech stack

Python 3.12 · PySide6 · SQLite · uv · Ruff · pytest

## Contributing

Conventions for human and AI contributors live in [`AGENTS.md`](AGENTS.md). Bug reports and feature requests are welcome at [Issues](https://github.com/cadic2603/ai-translate/issues).

## License

[AGPL-3.0-or-later](LICENSE)
