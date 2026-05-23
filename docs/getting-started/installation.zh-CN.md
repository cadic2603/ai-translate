---
description: 在 Windows、macOS 或 Linux 上从预编译二进制文件或源代码安装 AI Translate——涵盖 Python、FFmpeg 和可选的 LibreOffice 设置。
---

# 安装

## 您需要什么

- **Python 3.12 或更新版本**([下载](https://www.python.org/downloads/))
- **[uv](https://docs.astral.sh/uv/)**——快速的 Python 包管理器。安装方式:

    === "macOS / Linux"
        ```bash
        curl -LsSf https://astral.sh/uv/install.sh | sh
        ```

    === "Windows"
        ```powershell
        powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
        ```

- **一个 LLM API 密钥**——以下任一:
    - [Google Gemini](https://aistudio.google.com/apikey)(免费层可用——推荐入门使用)
    - 任何 OpenAI 兼容的 endpoint(OpenAI、通过代理的 Anthropic、本地 Ollama / LM Studio 等)

## 可选,但解锁更多功能

| 工具 | 被以下使用 | 何时需要 |
|---|---|---|
| **FFmpeg**([下载](https://ffmpeg.org/download.html)) | 字幕、语音、配音、Live | 任何音频/视频工作流 |
| **LibreOffice**([下载](https://www.libreoffice.org/download/)) | Linux/macOS 上的 Office 格式 | 翻译旧版 `.doc` / `.xls` / `.ppt`,或 MS Office 未安装时翻译任何 Office 文件 |
| **Tesseract**([安装指南](https://tesseract-ocr.github.io/tessdoc/Installation.html)) | OCR 引擎(默认) | 提取文本页面、扫描 PDF 翻译、嵌入图像翻译 |
| **MS Office** + **pywin32** | Windows 上的 Office | Windows 上最高保真度的 Office 翻译 |

您可以在没有任何这些工具的情况下安装 AI Translate——需要它们的功能会在失败前告诉您。

## 设置

```bash
git clone https://github.com/cadic2603/ai-translate.git
cd ai-translate
uv sync
```

这会安装运行桌面应用、CLI 和 MCP 服务器所需的一切。

## 运行

=== "桌面应用"
    ```bash
    uv run python -m src.main
    ```

=== "命令行"
    ```bash
    uv run ait --version
    ```

=== "MCP 服务器"
    ```bash
    uv run ait-mcp           # stdio 传输(用于 Claude Desktop / Code)
    ```

## 添加您的 API 密钥

第一次打开桌面应用时:

1. 在侧边栏点击**设置**
2. 打开 **LLM** 标签页
3. 粘贴您的 **Google Gemini API 密钥**(或配置 OpenAI 兼容的自定义提供商)。
   企业用户可以将 Gemini 切换到 **Vertex AI 模式**——指向 GCP 项目和区域,
   可选地提供 service-account JSON 路径;详情见
   [LLM 提供商](../setup/llm-providers.md)。
4. 选择默认模型——任何当前的 Flash 变体(例如 `gemini-2.5-flash`)
   都是稳健的免费起点。Pro 变体以更高成本提供更好质量。
5. 关闭设置——完成

密钥存储在您的 **OS 钥匙串**中(macOS Keychain、Windows Credential Manager、
Linux 上的 GNOME / KDE Secret Service),而不是磁盘上的明文。

!!! tip "Headless / 服务器安装"
    如果您无法运行桌面应用来设置密钥,请参见
    [LLM 提供商](../setup/llm-providers.md)了解 keychain CLI 命令。

## 接下来:试试看

[5 分钟首次翻译 →](first-translation.md){ .md-button .md-button--primary }
