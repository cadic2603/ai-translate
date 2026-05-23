---
description: AI Translate Python API 的开发者参考文档——根据 docstring 自动生成；涵盖 core、utils、constants、CLI 和 MCP 服务器模块。
---

# 开发者参考

终端用户可能想看[功能页面](../index.md#headline-features)或
[设置指南](../setup/llm-providers.md),而不是这一节。

这是**自动生成的 API 参考**——`src/` 中每个 Python 模块对应一个页面,
由项目的 docstring 渲染而成。它面向希望从自己的 Python 代码中调用底层函数的
贡献者和集成方。

## 构建目标

`uv run mkdocs build` 会在每次构建时从 `src/` 重新生成这些页面,
因此它们始终反映当前代码状态。

## 从哪里开始

无界面翻译的入口点是
[`run_translation_pipeline`](api/core/translator.md)——桌面应用的每个功能、
CLI 和 MCP 服务器最终都会经过它。阅读这个函数及其相邻的
`TranslationConfig` 是了解整个 pipeline 最快的方式。

## 布局

- **[Constants](api/constants/index.md)**——设置键、错误码、语言表、i18n / 主题引擎。
- **[Core](api/core/index.md)**——翻译 pipeline、LLM 分发、按格式的处理器、OCR / STT / TTS 引擎、检查点、数据库。
- **[Utils](api/utils/index.md)**——跨功能辅助工具。
- **[CLI](api/cli.md)**——`ait` 入口点。
- **[MCP Server](api/mcp_server.md)**——`ait-mcp` 入口点。
