---
description: AI Translate Python API 的開發者參考文件——根據 docstring 自動生成；涵蓋 core、utils、constants、CLI 和 MCP 伺服器模組。
---

# 開發者參考

終端機使用者可能想看[功能頁面](../index.md#headline-features)或
[設定指南](../setup/llm-providers.md),而不是這一節。

這是**自動生成的 API 參考**——`src/` 中每個 Python 模組對應一個頁面,
由專案的 docstring 渲染而成。它面向希望從自己的 Python 程式碼中調用底層函式的
貢獻者和集成方。

## 構建目标

`uv run mkdocs build` 會在每次構建時從 `src/` 重新生成這些頁面,
因此它們始終反映目前程式碼狀態。

## 從哪裡開始

無介面翻譯的入口點是
[`run_translation_pipeline`](api/core/translator.md)——桌面應用程式的每個功能、
CLI 和 MCP 伺服器最終都會經過它。閱讀這個函式及其相鄰的
`TranslationConfig` 是了解整個 pipeline 最快的方式。

## 布局

- **[Constants](api/constants/index.md)**——設定鍵、錯誤碼、語言表、i18n / 主題引擎。
- **[Core](api/core/index.md)**——翻譯 pipeline、LLM 分發、按格式的處理器、OCR / STT / TTS 引擎、檢查點、資料庫。
- **[Utils](api/utils/index.md)**——跨功能輔助工具。
- **[CLI](api/cli.md)**——`ait` 入口點。
- **[MCP Server](api/mcp_server.md)**——`ait-mcp` 入口點。
