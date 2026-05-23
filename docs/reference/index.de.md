---
description: Entwicklerreferenz für die Python-API von AI Translate — automatisch aus Docstrings generiert; deckt core-, utils-, constants-, CLI- und MCP-Server-Module ab.
---

# Entwicklerreferenz

Endbenutzer wollen wahrscheinlich die
[Funktionsseiten](../index.md#headline-features) oder die
[Einrichtungsanleitungen](../setup/llm-providers.md), nicht diesen Abschnitt.

Dies ist die **automatisch generierte API-Referenz** — eine Seite pro
Python-Modul in `src/`, gerendert aus den Docstrings des Projekts. Sie
ist für Mitwirkende und Integratoren gedacht, die die zugrunde
liegenden Funktionen aus eigenem Python-Code aufrufen wollen.

## Build-Ziel

`uv run mkdocs build` erzeugt diese Seiten bei jedem Build neu aus
`src/`, sodass sie stets den aktuellen Code widerspiegeln.

## Wo anfangen

Der Headless-Translation-Einstiegspunkt ist
[`run_translation_pipeline`](api/core/translator.md) — jede
Funktion der Desktop-App, das CLI und der MCP-Server laufen
letztlich darüber. Diese Funktion und ihren Nachbarn
`TranslationConfig` zu lesen ist der schnellste Weg, die Pipeline
zu verstehen.

## Aufbau

- **[Constants](api/constants/index.md)** — Einstellungsschlüssel, Fehlercodes, Sprachtabellen, i18n- / Theme-Engines.
- **[Core](api/core/index.md)** — Übersetzungspipeline, LLM-Dispatch, formatspezifische Prozessoren, OCR- / STT- / TTS-Engines, Checkpoints, Datenbank.
- **[Utils](api/utils/index.md)** — übergreifende Helfer.
- **[CLI](api/cli.md)** — `ait`-Einstiegspunkt.
- **[MCP Server](api/mcp_server.md)** — `ait-mcp`-Einstiegspunkt.
