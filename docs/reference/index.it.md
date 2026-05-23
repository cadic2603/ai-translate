---
description: Riferimento per sviluppatori dell'API Python di AI Translate — generato automaticamente dai docstring; copre i moduli core, utils, constants, CLI e server MCP.
---

# Riferimento per sviluppatori

Gli utenti finali probabilmente vogliono le
[pagine delle funzionalità](../index.md#headline-features) o le
[guide di configurazione](../setup/llm-providers.md), non questa sezione.

Questo è il **riferimento API generato automaticamente** — una pagina
per modulo Python in `src/`, renderizzato dai docstring del progetto.
È pensato per contributori e integratori che vogliono chiamare le
funzioni sottostanti dal proprio codice Python.

## Destinazione di build

`uv run mkdocs build` rigenera queste pagine da `src/` ad ogni build,
quindi riflettono sempre quanto c'è nel codice.

## Da dove iniziare

Il punto di ingresso di traduzione senza interfaccia è
[`run_translation_pipeline`](api/core/translator.md) — ogni
funzionalità dell'app desktop, il CLI e il server MCP finiscono per
passarci. Leggere questa funzione e il suo vicino
`TranslationConfig` è il modo più rapido di capire la pipeline.

## Struttura

- **[Constants](api/constants/index.md)** — chiavi di configurazione, codici di errore, tabelle di lingue, motori i18n / tema.
- **[Core](api/core/index.md)** — pipeline di traduzione, dispatch LLM, processori specifici per formato, motori OCR / STT / TTS, checkpoint, database.
- **[Utils](api/utils/index.md)** — helper trasversali.
- **[CLI](api/cli.md)** — punto di ingresso `ait`.
- **[MCP Server](api/mcp_server.md)** — punto di ingresso `ait-mcp`.
