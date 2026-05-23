---
description: Referência para desenvolvedores da API Python do AI Translate — gerada automaticamente a partir das docstrings; cobre módulos core, utils, constants, CLI e servidor MCP.
---

# Referência para desenvolvedores

Utilizadors finais provavelmente querem as
[páginas de funcionalidades](../index.md#headline-features) ou os
[guias de definição](../setup/llm-providers.md), não esta seção.

Esta é a **referência de API gerada automaticamente** — uma página
por módulo Python em `src/`, renderizada a partir das docstrings do
projeto. É destinada a contribuidores e integradores que querem chamar
as funções subjacentes a partir do próprio código Python.

## Alvo de build

`uv run mkdocs build` regenera estas páginas a partir de `src/` a cada
build, então sempre refletem o que está no código.

## Por onde começar

O ponto de entrada de tradução sem interface é
[`run_translation_pipeline`](api/core/translator.md) — cada
funcionalidade da aplicação desktop, o CLI e o servidor MCP acabam
passando por ele. Ler essa função e seu vizinho `TranslationConfig`
é a forma mais rápida de entender o pipeline.

## Organização

- **[Constants](api/constants/index.md)** — chaves de definição, códigos de erro, tabelas de idiomas, motores i18n / tema.
- **[Core](api/core/index.md)** — pipeline de tradução, dispatch LLM, processadores específicos por formato, motores OCR / STT / TTS, checkpoints, banco de dados.
- **[Utils](api/utils/index.md)** — utilitários transversais.
- **[CLI](api/cli.md)** — ponto de entrada `ait`.
- **[MCP Server](api/mcp_server.md)** — ponto de entrada `ait-mcp`.
