---
description: Developer reference for AI Translate's Python API — auto-generated from docstrings; covers core, utils, constants, CLI, and MCP server modules.
---

# Developer Reference

End users probably want the [feature pages](../index.md#headline-features)
or the [setup guides](../setup/llm-providers.md), not this section.

This is the **auto-generated API reference** — one page per Python
module in `src/`, rendered from the project's docstrings. It's intended
for contributors and integrators who want to call the underlying
functions from their own Python code.

## Build target

`uv run mkdocs build` regenerates these pages from `src/` on every
build, so they always reflect what's currently in the code.

## Where to start

The headless translation entry point is
[`run_translation_pipeline`](api/core/translator.md) — every feature
in the desktop app, the CLI, and the MCP server eventually routes
through it. Reading that function and its `TranslationConfig` neighbour
is the fastest way to understand the pipeline.

## Layout

- **[Constants](api/constants/index.md)** — settings keys, error codes, language tables, i18n / theme engines.
- **[Core](api/core/index.md)** — the translation pipeline, LLM dispatch, format-specific processors, OCR / STT / TTS engines, checkpoints, database.
- **[Utils](api/utils/index.md)** — cross-cutting helpers.
- **[CLI](api/cli.md)** — `ait` entry point.
- **[MCP Server](api/mcp_server.md)** — `ait-mcp` entry point.
