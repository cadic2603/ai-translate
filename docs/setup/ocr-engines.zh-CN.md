---
description: 设置用于图像和 PDF 文本提取的 OCR 引擎 — 在离线 Tesseract 或 EasyOCR，或基于云的 Google Vision OCR 之间选择。
---

# OCR 引擎

OCR 用于从图像中读取文本 — 既在[提取文本](../features/extract-text.md)
页面，也作为文档翻译内的后备，当页面被扫描（无文本层）或当你打开
**翻译嵌入图像**时。

你可以从三个 OCR 引擎中选择。

## Tesseract（推荐默认）

免费、快速、离线。需要系统安装。

=== "macOS"
    ```bash
    brew install tesseract tesseract-lang
    ```

=== "Ubuntu / Debian"
    ```bash
    sudo apt install tesseract-ocr tesseract-ocr-all
    ```

    `tesseract-ocr-all` 带来所有支持的语言。要节省磁盘空间，只安装
    你需要的（例如 `tesseract-ocr-fra` 用于法语）。

=== "Fedora / RHEL"
    ```bash
    sudo dnf install tesseract tesseract-langpack-eng tesseract-langpack-fra
    ```

=== "Windows"
    从 [UB Mannheim 的 Tesseract 发布](https://github.com/UB-Mannheim/tesseract/wiki)
    下载安装程序。运行它，接受默认值 — 语言包已捆绑。

验证：

```bash
tesseract --version
tesseract --list-langs
```

在桌面应用中：**设置 → OCR → OCR 方法 = Tesseract**。完成。

## EasyOCR

免费，离线。非常适合非拉丁文字（中文、韩文、日文、泰文）。模型在首次
使用时下载（总共约 1 GB）。

```bash
uv sync --extra easyocr
```

在桌面应用中：**设置 → OCR → OCR 方法 = EasyOCR**。

第一次为某语言使用它时，相关模型会下载到 `~/.EasyOCR/`。后续运行很快。

## Google Cloud Vision

云端，付费（每月 1,000 次免费请求）。最高准确度，特别是在嘈杂 /
手写 / 多脚本内容上。

1. [创建 Google Cloud 项目](https://console.cloud.google.com/projectcreate)
2. 启用 [Vision API](https://console.cloud.google.com/apis/library/vision.googleapis.com)
3. [创建 API 密钥](https://console.cloud.google.com/apis/credentials)
4. 在桌面应用中：**设置 → 服务 → Google Cloud API 密钥** → 粘贴
5. **设置 → OCR → OCR 方法 = Google Cloud OCR**

如果你也启用这些 API，相同的 Google Cloud API 密钥可以驱动 Vision
OCR、Speech-to-Text 和 Text-to-Speech。

## 比较准确度

**设置 → OCR** 选项卡有一个内置的小比较表 — 语言覆盖、在线/离线、
成本、准确度。每次想要切换时重新阅读它。

## OCR 何时使用

| 地方 | 行为 |
|---|---|
| **提取文本页面**（方法 = OCR 时） | 对放下的图像进行直接 OCR |
| **翻译文档 → PDF** | 在仅扫描页面（无文本层）上的 OCR 后备 |
| **翻译文档 → Office** 启用**翻译嵌入图像**时 | 在每个嵌入图像上进行 OCR + LLM 视觉 |

## 提示

!!! tip "选择源语言"
    大多数 OCR 引擎在你告诉它们要期待什么语言时准确得多。字幕 /
    文档 / 提取文本页面都将你的**源语言**选择器转发到 OCR 引擎。

!!! tip "Tesseract 对清洁印刷文本足够"
    在 Tesseract / EasyOCR 实际上在你的内容上失败之前不要伸手去
    云 OCR。它们是免费的、快速的，而且出奇地好。
