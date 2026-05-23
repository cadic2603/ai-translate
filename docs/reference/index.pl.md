---
description: Dokumentacja deweloperska Python API AI Translate — auto-generowana z docstringów; obejmuje moduły core, utils, constants, CLI i MCP server.
---

# Dokumentacja dla deweloperów

Użytkownicy końcowi prawdopodobnie chcą [stron funkcji](../index.md#headline-features)
lub [przewodników konfiguracji](../setup/llm-providers.md), a nie tej
sekcji.

To jest **auto-generowana dokumentacja API** — jedna strona na każdy
moduł Python w `src/`, renderowana z docstringów projektu.
Przeznaczona dla kontrybutorów i integratorów, którzy chcą wywoływać
podstawowe funkcje z własnego kodu Python.

## Cel budowania

`uv run mkdocs build` regeneruje te strony z `src/` przy każdym
buildzie, więc zawsze odzwierciedlają one to, co aktualnie znajduje
się w kodzie.

## Od czego zacząć

Bezgłowy punkt wejścia tłumaczenia to
[`run_translation_pipeline`](api/core/translator.md) — każda funkcja w
aplikacji desktopowej, CLI i serwerze MCP ostatecznie przechodzi przez
nią. Czytanie tej funkcji i jej sąsiada `TranslationConfig` to
najszybszy sposób, by zrozumieć potok.

## Układ

- **[Constants](api/constants/index.md)** — klucze ustawień, kody błędów, tablice języków, silniki i18n / theme.
- **[Core](api/core/index.md)** — potok tłumaczenia, dyspozycja LLM, procesory specyficzne dla formatu, silniki OCR / STT / TTS, punkty kontrolne, baza danych.
- **[Utils](api/utils/index.md)** — pomocnicy międzymodułowi.
- **[CLI](api/cli.md)** — punkt wejścia `ait`.
- **[MCP Server](api/mcp_server.md)** — punkt wejścia `ait-mcp`.
