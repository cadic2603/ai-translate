---
description: AI Translate 是一款免费的跨平台桌面翻译器,支持 45 多种语言的文档、PDF、字幕、音频和实时语音翻译。
---

# AI Translate

一款免费的跨平台桌面翻译器,支持 **45 种语言**,远不止纯文本——它通过单一的 LLM 驱动管道翻译文档、音频、视频、实时语音、屏幕截图等等。

<div class="grid cards" markdown>

-   :material-cursor-default-click-outline:{ .lg .middle } **桌面应用**

    ---

    拖入文件,选择目标语言,获得翻译副本。拖放、历史记录、术语表,应有尽有。

    [:octicons-arrow-right-24: 5 分钟教程](getting-started/first-translation.md)

-   :material-console:{ .lg .middle } **命令行**

    ---

    `ait report.docx --target French`——同样的管道,可脚本化、无界面。
    适用于 CI、批处理任务、服务器。

    [:octicons-arrow-right-24: CLI 指南](cli.md)

-   :material-robot-outline:{ .lg .middle } **AI 智能体 (MCP)**

    ---

    将翻译公开为 Model Context Protocol 工具,以便 Claude Desktop、
    Claude Code 和其他 MCP 客户端可以直接调用。

    [:octicons-arrow-right-24: MCP 设置](mcp.md)

</div>

## 您可以翻译什么

| 类型 | 格式 |
|---|---|
| **Office 文档** | `.docx`、`.xlsx`、`.pptx`、`.odt`、`.ods`、`.odp`,加上旧版 `.doc` / `.xls` / `.ppt` |
| **PDF** | 保留布局的 extract-overlay 翻译,书签 / 表单 / 链接翻译,扫描件 OCR 回退 |
| **文本和网页** | `.txt`、`.md`、`.rst`、`.html` / `.htm` / `.xhtml`、`.xml`、`.rtf`、`.json`、`.csv`、`.epub` |
| **字幕** | `.srt`、`.vtt`、`.ass`、`.ssa` |
| **本地化** | `.po`、`.pot`、`.xliff` / `.xlf`、`.yaml` / `.yml`、`.properties`、`.strings` |
| **图像** | `.png`、`.jpg`、`.jpeg`、`.bmp`、`.webp`、`.tiff`、`.tif`(OCR 或 LLM 视觉) |
| **音频** | `.mp3`、`.wav`、`.m4a`、`.flac`、`.ogg`、`.aac`、`.wma` |
| **视频** | `.mp4`、`.webm`、`.mkv`、`.avi`、`.mov`、`.wmv`(完整配音管道) |

## 主要功能 {: #headline-features }

- **[翻译文本](features/translate-text.md)**——即时 LLM 翻译,自动检测、原地编辑、TTS 播放。从右到左语言(阿拉伯语、希伯来语、波斯语)原生渲染。
- **[翻译文档](features/translate-document.md)**——拖入文件,观察每任务进度旋转器,获得并排的翻译副本。RTL 目标获得正确的 bidi 标记;`Ctrl+P` / `Ctrl+G` 暂停和继续队列。
- **[生成字幕 (STT)](features/generate-subtitle.md)**——将音频/视频转录为 SRT / VTT / ASS / SSA。
- **[生成语音 (TTS)](features/generate-voice.md)**——将字幕合成为带时序的 MP3 / WAV。
- **[视频配音](features/dubbing.md)**——完整的 STT → 翻译 → TTS → 混合回源视频。
- **[实时翻译](features/live-translation.md)**——来自麦克风或系统音频的实时字幕叠加。
- **[提取文本](features/extract-text.md)**——OCR 或 LLM 视觉 → `.txt` / `.docx`。
- **[术语表](features/glossary.md)**——在所有翻译中强制执行一致的术语。

!!! tip "Gemini 的 Vertex AI 模式"
    企业用户可以在**设置 → LLM** 中将 Gemini 调用从 Developer API 切换到
    **Vertex AI**——指向您的 GCP 项目和区域,可选地提供 service-account JSON 路径。
    参见 [LLM 提供商](setup/llm-providers.md#google-gemini-recommended-for-first-time-setup)。

!!! tip "第一次来?"
    从[安装](getting-started/installation.md)开始,然后是
    [5 分钟首次翻译教程](getting-started/first-translation.md)。
    您将在不到 10 分钟内从全新克隆获得翻译文档。
