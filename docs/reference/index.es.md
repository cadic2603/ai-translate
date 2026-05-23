---
description: Referencia para desarrolladores de la API Python de AI Translate — autogenerada desde los docstrings; cubre los módulos core, utils, constants, CLI y servidor MCP.
---

# Referencia para desarrolladores

Probablemente los usuarios finales quieran las
[páginas de funcionalidades](../index.md#headline-features) o las
[guías de configuración](../setup/llm-providers.md), no esta sección.

Esta es la **referencia de API autogenerada** — una página por módulo
Python en `src/`, renderizada desde los docstrings del proyecto. Está
pensada para colaboradores e integradores que quieren llamar a las
funciones subyacentes desde su propio código Python.

## Destino de build

`uv run mkdocs build` regenera estas páginas desde `src/` en cada
build, así que siempre reflejan lo que hay en el código.

## Por dónde empezar

El punto de entrada de traducción sin interfaz es
[`run_translation_pipeline`](api/core/translator.md) — cada
funcionalidad de la aplicación de escritorio, el CLI y el servidor MCP
acaban pasando por ahí. Leer esa función y su vecina
`TranslationConfig` es la forma más rápida de entender el pipeline.

## Organización

- **[Constants](api/constants/index.md)** — claves de configuración, códigos de error, tablas de idiomas, motores i18n / tema.
- **[Core](api/core/index.md)** — pipeline de traducción, dispatch LLM, procesadores específicos por formato, motores OCR / STT / TTS, checkpoints, base de datos.
- **[Utils](api/utils/index.md)** — utilidades transversales.
- **[CLI](api/cli.md)** — punto de entrada `ait`.
- **[MCP Server](api/mcp_server.md)** — punto de entrada `ait-mcp`.
