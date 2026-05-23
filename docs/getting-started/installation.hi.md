---
description: Windows, macOS, या Linux पर prebuilt binaries या source से AI Translate install करें — Python, FFmpeg, और optional LibreOffice setup शामिल।
---

# इंस्टॉलेशन

## आपको क्या चाहिए

- **Python 3.12 या नया** ([download](https://www.python.org/downloads/))
- **[uv](https://docs.astral.sh/uv/)** — fast Python package manager. इसके साथ install करें:

    === "macOS / Linux"
        ```bash
        curl -LsSf https://astral.sh/uv/install.sh | sh
        ```

    === "Windows"
        ```powershell
        powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
        ```

- **एक LLM API key** — इनमें से कोई एक:
    - [Google Gemini](https://aistudio.google.com/apikey) (free tier उपलब्ध — शुरुआत के लिए अनुशंसित)
    - कोई भी OpenAI-compatible endpoint (OpenAI, proxy via Anthropic, local Ollama / LM Studio, आदि)

## वैकल्पिक, लेकिन अधिक features अनलॉक करता है

| Tool | किसके द्वारा उपयोग | कब आवश्यक है |
|---|---|---|
| **FFmpeg** ([download](https://ffmpeg.org/download.html)) | Subtitle, Voice, Dubbing, Live | कोई भी audio/video workflow |
| **LibreOffice** ([download](https://www.libreoffice.org/download/)) | Linux/macOS पर Office formats | legacy `.doc` / `.xls` / `.ppt` का अनुवाद, या जब MS Office इंस्टॉल नहीं हो तो कोई भी Office file |
| **Tesseract** ([install guide](https://tesseract-ocr.github.io/tessdoc/Installation.html)) | OCR engine (default) | Extract Text पेज, scanned-PDF translation, embedded-image translation |
| **MS Office** + **pywin32** | Windows पर Office | Windows पर उच्चतम fidelity Office translation |

आप इनमें से किसी के बिना AI Translate install कर सकते हैं — जिन
features को इनकी आवश्यकता है वे fail होने से पहले आपको बताएँगी।

## सेटअप करें

```bash
git clone https://github.com/cadic2603/ai-translate.git
cd ai-translate
uv sync
```

यह desktop app, CLI, और MCP server चलाने के लिए जो कुछ भी आवश्यक है
वह install करता है।

## इसे चलाएँ

=== "Desktop app"
    ```bash
    uv run python -m src.main
    ```

=== "Command line"
    ```bash
    uv run ait --version
    ```

=== "MCP server"
    ```bash
    uv run ait-mcp           # stdio transport (Claude Desktop / Code के लिए)
    ```

## अपनी API key जोड़ें

पहली बार जब आप desktop app खोलते हैं:

1. Sidebar में **Settings** क्लिक करें
2. **LLM** tab खोलें
3. अपनी **Google Gemini API key** paste करें (या एक custom
   OpenAI-compatible provider configure करें)। Enterprise users इसके
   बजाय Gemini को **Vertex AI mode** में switch कर सकते हैं — इसे
   एक GCP project और region पर इंगित करें, वैकल्पिक रूप से एक
   service-account JSON path प्रदान करें; details के लिए
   [LLM Providers](../setup/llm-providers.md) देखें।
4. एक default model चुनें — कोई भी मौजूदा Flash variant (जैसे
   `gemini-2.5-flash`) एक solid free starting point है। Pro variants
   उच्च लागत पर बेहतर quality देते हैं।
5. Settings बंद करें — आप तैयार हैं

Keys आपके **OS keychain** में store की जाती हैं (macOS Keychain,
Windows Credential Manager, Linux पर GNOME / KDE Secret Service),
disk पर plain text में नहीं।

!!! tip "Headless / server install"
    यदि आप keys सेट करने के लिए desktop app नहीं चला सकते हैं, तो
    keychain CLI commands के लिए
    [LLM Providers](../setup/llm-providers.md) देखें।

## अगला: इसे आज़माएँ

[5-मिनट पहला अनुवाद →](first-translation.md){ .md-button .md-button--primary }
