---
description: 設定用於圖像和 PDF 文本提取的 OCR 引擎 — 在離線 Tesseract 或 EasyOCR，或基於雲的 Google Vision OCR 之間選擇。
---

# OCR 引擎

OCR 用於從圖像中讀取文本 — 既在[提取文本](../features/extract-text.md)
頁面，也作為文件翻譯內的后備，当頁面被掃描（無文本層）或当你開啟
**翻譯嵌入圖像**時。

你可以從三個 OCR 引擎中選擇。

## Tesseract（推薦預設）

免費、快速、離線。需要系統安裝。

=== "macOS"
    ```bash
    brew install tesseract tesseract-lang
    ```

=== "Ubuntu / Debian"
    ```bash
    sudo apt install tesseract-ocr tesseract-ocr-all
    ```

    `tesseract-ocr-all` 帶來所有支援的語言。要節省磁盤空間，只安裝
    你需要的（例如 `tesseract-ocr-fra` 用於法語）。

=== "Fedora / RHEL"
    ```bash
    sudo dnf install tesseract tesseract-langpack-eng tesseract-langpack-fra
    ```

=== "Windows"
    從 [UB Mannheim 的 Tesseract 發布](https://github.com/UB-Mannheim/tesseract/wiki)
    下載安裝程式。執行它，接受預設值 — 語言套件已捆綁。

驗證：

```bash
tesseract --version
tesseract --list-langs
```

在桌面應用程式中：**設定 → OCR → OCR 方法 = Tesseract**。完成。

## EasyOCR

免費，離線。非常适合非拉丁文字（中文、韓文、日文、泰文）。模型在首次
使用時下載（總共約 1 GB）。

```bash
uv sync --extra easyocr
```

在桌面應用程式中：**設定 → OCR → OCR 方法 = EasyOCR**。

第一次為某語言使用它時，相關模型會下載到 `~/.EasyOCR/`。后續執行很快。

## Google Cloud Vision

雲端，付費（每月 1,000 次免費要求）。最高準確度，特別是在嘈雜 /
手寫 / 多指令稿內容上。

1. [創建 Google Cloud 專案](https://console.cloud.google.com/projectcreate)
2. 啟用 [Vision API](https://console.cloud.google.com/apis/library/vision.googleapis.com)
3. [創建 API 密鑰](https://console.cloud.google.com/apis/credentials)
4. 在桌面應用程式中：**設定 → 服務 → Google Cloud API 密鑰** → 貼上
5. **設定 → OCR → OCR 方法 = Google Cloud OCR**

如果你也啟用這些 API，相同的 Google Cloud API 密鑰可以驅動 Vision
OCR、Speech-to-Text 和 Text-to-Speech。

## 比較準確度

**設定 → OCR** 頁籤有一個內置的小比較表 — 語言覆蓋、線上/離線、
成本、準確度。每次想要切換時重新閱讀它。

## OCR 何時使用

| 地方 | 行為 |
|---|---|
| **提取文本頁面**（方法 = OCR 時） | 對放下的圖像進行直接 OCR |
| **翻譯文件 → PDF** | 在僅掃描頁面（無文本層）上的 OCR 后備 |
| **翻譯文件 → Office** 啟用**翻譯嵌入圖像**時 | 在每個嵌入圖像上進行 OCR + LLM 視覺 |

## 提示

!!! tip "選擇源語言"
    大多數 OCR 引擎在你告訴它們要期待什麼語言時準確得多。字幕 /
    文件 / 提取文本頁面都將你的**源語言**選擇器轉發到 OCR 引擎。

!!! tip "Tesseract 對清潔印刷文本足夠"
    在 Tesseract / EasyOCR 實際上在你的內容上失敗之前不要伸手去
    雲 OCR。它們是免費的、快速的，而且出奇地好。
