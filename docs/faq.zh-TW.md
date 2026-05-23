---
description: "關於 AI Translate 的常見問題:支援的檔案格式、免費 vs 付費功能、離線使用、LLM 提供商選擇和 OCR 引擎選擇。"
---

# 常見問題

## 一般

### 它能離線工作嗎?

大部分可以。具體而言:

- **翻譯**需要 LLM。免費 Gemini API 線上;透過 Custom Provider 設定的
  **本地 Ollama / LM Studio** 完全離線。
- **OCR** 使用 **Tesseract** 或 **EasyOCR** 離線。
- **STT** 使用 **Whisper**(預設)離線。
- **TTS** 使用 **Edge TTS**(預設)線上;**ElevenLabs** /
  **Google Cloud TTS** / **Gemini TTS** 線上(免費或付費);
  **Piper TTS** 是完全離線的神經 TTS——透過**設定 → 語音 → Piper TTS
  → 立即下載語音**下載每語言語音(~25–60 MB ONNX 檔案)后,
  無密鑰、無網路調用。

完全 air-gapped 設定:Custom Provider → 本地 LLM,Tesseract 或 EasyOCR
用於 OCR,Whisper 用於 STT,Piper TTS 用於語音輸出。

### 我翻譯的檔案儲存在哪裡?

預設在原檔案旁邊,帶有 `_translated_<src>_<tgt>` 后綴
(例如 `report_translated_en_fr.docx`)。在
**設定 → 通用 → 翻譯儲存路徑**中按功能覆蓋。

### 我的設定儲存在哪裡?

INI 檔案位於:

| OS | 路徑 |
|---|---|
| **Linux** | `~/.config/ai-translate/settings.ini` |
| **macOS** | `~/Library/Preferences/ai-translate/settings.ini` |
| **Windows** | `%APPDATA%\ai-translate\settings.ini` |

API 密鑰存放在 OS 鑰匙串中(不在 INI 中)。
翻譯歷史存放在資料目錄中的 SQLite DB 中。

### 我的資料如何處理?

- **本地優先**——除非您在調用雲 LLM / OCR / STT / TTS 服務,
  否則文本永遠不會離開您的機器。
- **無遥測**——應用不會"打電話回家"。應用本身唯一發出的出站要求是
  選用的 GitHub Releases 更新檢查(在**設定 → 通用**中切換);
  雲后端僅調用各自的供應商。
- **API 密鑰**——儲存在您的 OS 鑰匙串中。当沒有鑰匙串守護處理程序可用時,
  桌面應用程式的鑰匙串回退是明文 INI。

### 我可以翻譯 Google Doc / Notion 頁面嗎?

不能直接。先匯出為 `.docx`,翻譯,然後將翻譯后的檔案匯入回來。
Notion 同理(匯出為 Markdown / HTML)、Confluence(匯出為 `.docx`)等。

## 選擇模型 / 引擎

### 我應該使用哪個 LLM 模型?

對於大多數使用者:

- **任何 Gemini Flash 變體**——免費層、快速、出乎意料地好。
  用於日常翻譯。名稱看起來像 `gemini-2.5-flash`、
  `gemini-3-flash-preview` 等,取決於目前可用情況。
- **任何 Gemini Pro 變體**——按 token 付費,更高品質。
  用於重要文件(法律、技術、面向客戶)。
- **本地 Ollama** 配 7B-13B 模型——当您需要離線 / 隱私時。

每功能模型選擇器意味着您可以為聊天式翻譯使用快速模型,
將昂貴的留給文件。

### 我應該使用哪個 OCR 引擎?

- **Tesseract** 用於主要指令稿中的清晰打印文本。免費、離線、快速。
- **EasyOCR** 用於非拉丁指令稿(尤其是 CJK)和較嘈雜的圖像。
- **Google Cloud Vision** 用於手寫、混合指令稿和您可以付費時的最高準確性。

### 我應該使用哪個 STT 方法?

- **Whisper local** 用於離線 / 隱私。
- **Soniox** 用於多說話者錄音——說話者標籤往返進入您的 SRT。
- **Google Cloud STT** 用於電話 / 醫療音訊(他們的領域模型很好)。
- **Gemini Live** 用於即時語音到語音翻譯。

### 哪個 TTS 后端?

- **Edge TTS** 用於免費的高品質語音。
- **ElevenLabs** 用於進階 / 品牌 / 克隆語音。
- **Google Cloud TTS** 用於 Edge 覆蓋薄弱的長尾語言中的 WaveNet 語音。
- **Gemini TTS** 用於復用現有 Gemini API 密鑰的免費自然 prebuilt 語音。
- **Piper TTS** 当您需要**離線 / air-gapped** 語音輸出時。
  權衡:每種語言透過**設定 → 語音 → Piper TTS → 立即下載語音**
  需要一次性 ~25–60 MB 語音下載,且應用 45 種語言中的 13 種沒有
  Piper 語音(那些會悄悄回到 Edge TTS)。

## 工作流

### 我如何翻譯整個檔案夾?

將檔案夾拖到**翻譯文件**的拖放區。其中(遞歸地)支援的檔案被排隊;
其他一切都被靜默跳過。每次拖放有 100 個檔案的上限;更大的批次 →
分成多次拖放。

### 我可以暫停和恢復翻譯嗎?

可以。隨時結束應用——Pending / Translating 任務在下次啟動時恢復。
每任務檢查點意味着 PDF 100 页中的第 47 页在恢復時不會重做。

### 我可以手動編輯翻譯嗎?

對於**翻譯文本**——可以,點擊右側面板並輸入。編輯會自動儲存到
條目的歷史記錄。

對於**翻譯文件**——在您常用的編輯器中開啟翻譯后的檔案
(Word、LibreOffice 等)並在那裡編輯。應用不會將編輯往返回歷史記錄。

### 我可以批量翻譯字串清單嗎?

使用 CLI:

```bash
ait *.txt --target French
```

或對於處理程序內字串(例如從程式碼中提取的 UI 字串),用清單調用
MCP `translate_text` 工具,或直接使用 Python API:

```python
from src.core.llm_engine import translate_text
out = translate_text(texts=["Hello", "World"], target_lang="French")
```

## 術語表

### 為什麼 LLM 不使用我的術語表?

要檢查的三件事:

1. 集合**激活**(復選框已勾選)。
2. 您術語表中的源術語實際上出現在源文本中(每次調用壓縮僅向 LLM
   發送與批次文本匹配的條目——節省 token,但意味着源術語中的拼寫
   錯誤是不可見的)。
3. 模型足夠強——`flash-lite` 有時忽略 `flash` 和 `pro` 尊重的提示。

### 術語表條目是否獨立於重音匹配?

是的。術語表尋找和術語表頁面中的搜尋欄都使用一個去除重音和
大小寫的歸一化函式。所以 `cafe`、`Café` 和 `CAFE` 都匹配源為
`Café` 的條目。

## 隱私

### 您是否收集任何使用資料?

不。應用沒有 analytics SDK。選用的更新檢查在啟動時輪詢單個
GitHub Releases endpoint;在**設定 → 通用**中可切換。

### 我的 API 密鑰安全嗎?

它們儲存在您的 OS 鑰匙串中(macOS 上的 Keychain、Windows 上的
Credential Manager、Linux 上的 Secret Service)。其他處理程序沒有
您的明確許可無法讀取它們。回退(当沒有鑰匙串守護處理程序可用時——
通常是無介面 Linux 伺服器)是您使用者設定目錄下的明文 INI;
在該模式下密鑰受檔案權限保護但未經過加密。
