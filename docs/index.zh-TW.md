---
description: AI Translate 是一款免費的跨平台桌面翻譯器,支援 45 多種語言的文件、PDF、字幕、音訊和即時語音翻譯。
---

# AI Translate

一款免費的跨平台桌面翻譯器,支援 **45 種語言**,遠不止純文本——它透過單一的 LLM 驅動管道翻譯文件、音訊、影片、即時語音、螢幕截圖等等。

<div class="grid cards" markdown>

-   :material-cursor-default-click-outline:{ .lg .middle } **桌面應用程式**

    ---

    拖入檔案,選擇目标語言,獲得翻譯副本。拖放、歷史記錄、術語表,應有尽有。

    [:octicons-arrow-right-24: 5 分鐘教學](getting-started/first-translation.md)

-   :material-console:{ .lg .middle } **命令列**

    ---

    `ait report.docx --target French`——同樣的管道,可指令稿化、無介面。
    适用於 CI、批處理任務、伺服器。

    [:octicons-arrow-right-24: CLI 指南](cli.md)

-   :material-robot-outline:{ .lg .middle } **AI 智能體 (MCP)**

    ---

    將翻譯公開為 Model Context Protocol 工具,以便 Claude Desktop、
    Claude Code 和其他 MCP 用戶端可以直接調用。

    [:octicons-arrow-right-24: MCP 設定](mcp.md)

</div>

## 您可以翻譯什麼

| 類別型 | 格式 |
|---|---|
| **Office 文件** | `.docx`、`.xlsx`、`.pptx`、`.odt`、`.ods`、`.odp`,加上舊版 `.doc` / `.xls` / `.ppt` |
| **PDF** | 保留布局的 extract-overlay 翻譯,書簽 / 表單 / 鏈接翻譯,掃描件 OCR 回退 |
| **文本和網页** | `.txt`、`.md`、`.rst`、`.html` / `.htm` / `.xhtml`、`.xml`、`.rtf`、`.json`、`.csv`、`.epub` |
| **字幕** | `.srt`、`.vtt`、`.ass`、`.ssa` |
| **本地化** | `.po`、`.pot`、`.xliff` / `.xlf`、`.yaml` / `.yml`、`.properties`、`.strings` |
| **圖像** | `.png`、`.jpg`、`.jpeg`、`.bmp`、`.webp`、`.tiff`、`.tif`(OCR 或 LLM 視覺) |
| **音訊** | `.mp3`、`.wav`、`.m4a`、`.flac`、`.ogg`、`.aac`、`.wma` |
| **影片** | `.mp4`、`.webm`、`.mkv`、`.avi`、`.mov`、`.wmv`(完整配音管道) |

## 主要功能 {: #headline-features }

- **[翻譯文本](features/translate-text.md)**——即時 LLM 翻譯,自動檢測、原地編輯、TTS 播放。從右到左語言(阿拉伯語、希伯來語、波斯語)原生渲染。
- **[翻譯文件](features/translate-document.md)**——拖入檔案,觀察每任務進度旋轉器,獲得並排的翻譯副本。RTL 目标獲得正確的 bidi 标記;`Ctrl+P` / `Ctrl+G` 暫停和繼續佇列。
- **[生成字幕 (STT)](features/generate-subtitle.md)**——將音訊/影片轉錄為 SRT / VTT / ASS / SSA。
- **[生成語音 (TTS)](features/generate-voice.md)**——將字幕合成為帶時序的 MP3 / WAV。
- **[影片配音](features/dubbing.md)**——完整的 STT → 翻譯 → TTS → 混合回源影片。
- **[即時翻譯](features/live-translation.md)**——來自麥克風或系統音訊的即時字幕疊加。
- **[提取文本](features/extract-text.md)**——OCR 或 LLM 視覺 → `.txt` / `.docx`。
- **[術語表](features/glossary.md)**——在所有翻譯中強制執行一致的術語。

!!! tip "Gemini 的 Vertex AI 模式"
    企業使用者可以在**設定 → LLM** 中將 Gemini 調用從 Developer API 切換到
    **Vertex AI**——指向您的 GCP 專案和區域,選用地提供 service-account JSON 路徑。
    參見 [LLM 提供商](setup/llm-providers.md#google-gemini-recommended-for-first-time-setup)。

!!! tip "第一次來?"
    從[安裝](getting-started/installation.md)開始,然後是
    [5 分鐘首次翻譯教學](getting-started/first-translation.md)。
    您將在不到 10 分鐘內從全新克隆獲得翻譯文件。
