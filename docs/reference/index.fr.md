---
description: Référence développeur pour l'API Python d'AI Translate — auto-générée depuis les docstrings ; couvre les modules core, utils, constants, CLI et serveur MCP.
---

# Référence développeur

Les utilisateurs finaux préféreront probablement les
[pages des fonctionnalités](../index.md#headline-features) ou les
[guides de configuration](../setup/llm-providers.md), pas cette section.

Ceci est la **référence d'API auto-générée** — une page par module
Python dans `src/`, rendue depuis les docstrings du projet. Elle est
destinée aux contributeurs et aux intégrateurs qui veulent appeler les
fonctions sous-jacentes depuis leur propre code Python.

## Cible de build

`uv run mkdocs build` régénère ces pages depuis `src/` à chaque build,
elles reflètent donc toujours ce qui est dans le code.

## Par où commencer

Le point d'entrée de traduction sans interface est
[`run_translation_pipeline`](api/core/translator.md) — chaque
fonctionnalité de l'application desktop, le CLI, et le serveur MCP
finissent par y passer. Lire cette fonction et son voisin
`TranslationConfig` est la façon la plus rapide de comprendre le pipeline.

## Organisation

- **[Constants](api/constants/index.md)** — clés de paramètres, codes d'erreur, tables de langues, moteurs i18n / thème.
- **[Core](api/core/index.md)** — pipeline de traduction, dispatch LLM, processeurs spécifiques aux formats, moteurs OCR / STT / TTS, checkpoints, base de données.
- **[Utils](api/utils/index.md)** — utilitaires transversaux.
- **[CLI](api/cli.md)** — point d'entrée `ait`.
- **[MCP Server](api/mcp_server.md)** — point d'entrée `ait-mcp`.
