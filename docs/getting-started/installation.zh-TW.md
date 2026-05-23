---
description: 在 Windows、macOS 或 Linux 上從預編譯二進制檔案或源程式碼安裝 AI Translate——涵蓋 Python、FFmpeg 和選用的 LibreOffice 設定。
---

# 安裝

## 您需要什麼

- **Python 3.12 或更新版本**([下載](https://www.python.org/downloads/))
- **[uv](https://docs.astral.sh/uv/)**——快速的 Python 套件管理員。安裝方式:

    === "macOS / Linux"
        ```bash
        curl -LsSf https://astral.sh/uv/install.sh | sh
        ```

    === "Windows"
        ```powershell
        powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
        ```

- **一個 LLM API 密鑰**——以下任一:
    - [Google Gemini](https://aistudio.google.com/apikey)(免費層可用——推薦入門使用)
    - 任何 OpenAI 兼容的 endpoint(OpenAI、透過代理的 Anthropic、本地 Ollama / LM Studio 等)

## 選用,但解鎖更多功能

| 工具 | 被以下使用 | 何時需要 |
|---|---|---|
| **FFmpeg**([下載](https://ffmpeg.org/download.html)) | 字幕、語音、配音、Live | 任何音訊/影片工作流 |
| **LibreOffice**([下載](https://www.libreoffice.org/download/)) | Linux/macOS 上的 Office 格式 | 翻譯舊版 `.doc` / `.xls` / `.ppt`,或 MS Office 未安裝時翻譯任何 Office 檔案 |
| **Tesseract**([安裝指南](https://tesseract-ocr.github.io/tessdoc/Installation.html)) | OCR 引擎(預設) | 提取文本頁面、掃描 PDF 翻譯、嵌入圖像翻譯 |
| **MS Office** + **pywin32** | Windows 上的 Office | Windows 上最高保真度的 Office 翻譯 |

您可以在沒有任何這些工具的情況下安裝 AI Translate——需要它們的功能會在失敗前告訴您。

## 設定

```bash
git clone https://github.com/cadic2603/ai-translate.git
cd ai-translate
uv sync
```

這會安裝執行桌面應用程式、CLI 和 MCP 伺服器所需的一切。

## 執行

=== "桌面應用程式"
    ```bash
    uv run python -m src.main
    ```

=== "命令列"
    ```bash
    uv run ait --version
    ```

=== "MCP 伺服器"
    ```bash
    uv run ait-mcp           # stdio 傳輸(用於 Claude Desktop / Code)
    ```

## 添加您的 API 密鑰

第一次開啟桌面應用程式時:

1. 在側欄點擊**設定**
2. 開啟 **LLM** 分頁
3. 貼上您的 **Google Gemini API 密鑰**(或設定 OpenAI 兼容的自定義提供商)。
   企業使用者可以將 Gemini 切換到 **Vertex AI 模式**——指向 GCP 專案和區域,
   選用地提供 service-account JSON 路徑;詳情見
   [LLM 提供商](../setup/llm-providers.md)。
4. 選擇預設模型——任何目前的 Flash 變體(例如 `gemini-2.5-flash`)
   都是穩健的免費起點。Pro 變體以更高成本提供更好品質。
5. 關閉設定——完成

密鑰儲存在您的 **OS 鑰匙串**中(macOS Keychain、Windows Credential Manager、
Linux 上的 GNOME / KDE Secret Service),而不是磁盤上的明文。

!!! tip "Headless / 伺服器安裝"
    如果您無法執行桌面應用程式來設定密鑰,請參見
    [LLM 提供商](../setup/llm-providers.md)了解 keychain CLI 命令。

## 接下來:試試看

[5 分鐘首次翻譯 →](first-translation.md){ .md-button .md-button--primary }
