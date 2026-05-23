---
description: 診斷 AI Translate 問題——缺失字型、FFmpeg 錯誤、LibreOffice 轉換器問題、OCR 設定失敗和 LLM API 身份驗證。
---

# 故障排除

常見錯誤、它們的含義,以及如何修復。

## 設定錯誤

### "LLM is not configured"

您還沒有添加 API 密鑰。開啟桌面應用程式 → **設定 → LLM** → 貼上一個密鑰。
完整指南見 [LLM 提供商](setup/llm-providers.md)。

### `AUTH_ERROR`

LLM API 密鑰錯誤或已過期。

- **Gemini**——在 <https://aistudio.google.com/apikey> 生成新密鑰,
  在**設定 → LLM** 中重新貼上。
- **自定義提供商**——驗證密鑰有效(用相同的
  `Authorization: Bearer …` 頭手動 curl endpoint)。
  如果 endpoint 移動了,也更新 **API endpoint** 字段。

### `QUOTA_ERROR`

您達到了免費層或付費方案的限制。

- **Gemini 免費層**——每個模型的每日要求配額不同
  (見 <https://ai.google.dev/gemini-api/docs/rate-limits>)。
  等一天,或升級到付費。
- **OpenAI / 其他**——查看您的賬單儀表板。許多提供商有"消費上限",
  達到時會暫停要求。

### `MODEL_NOT_FOUND`

您選擇的模型名稱不可用。

- 自定義提供商——確保模型在**設定 → LLM** 中以逗號分隔的 **Models** 清單中。
- 內置 Gemini 清單——切換到**設定 → LLM → 預設 Gemini 模型**中
  記錄的模型。

### `VISION_NOT_SUPPORTED`

您選擇了非視覺模型並嘗試翻譯圖像 / 掃描 PDF。切換到名稱套件含
`flash`、`pro` 或 `vision` 的模型(例如 OpenAI 的 `gpt-4o`、
Gemini 的任何目前 Gemini Flash 或 Pro 變體)。

## 音訊 / 影片錯誤

### `FFMPEG_NOT_FOUND`

FFmpeg 不在 PATH 中。您的 OS 的安裝命令見
[FFmpeg 設定](setup/ffmpeg.md)。

MCP 伺服器將其重新套件裝為:*"FFmpeg is required to decode this
audio/video file but is not installed or not on PATH."*

### Live 頁面不顯示字幕

- **錯誤的音訊源**——開啟**設定 → Live → 音訊源**並確保它與
  您實際想要的匹配(麥克風 / 系統 / 兩者)。
- **麥克風靜音**——檢查 OS 聲音設定;應用使用您的預設輸入設備。
- **系統音訊未設定**——見
  [系統音訊捕獲](setup/system-audio.md) 了解 macOS / Windows
  loopback 步驟。

### 語音輸出靜音 / 空

- **沒有密鑰的 ElevenLabs**——Voice 頁面在飛行前顯示友好對話方塊;
  如果它溜過了,檔案可能是空字節。檢查
  **設定 → Service → ElevenLabs API key**。
- **Edge TTS 網路錯誤**——Edge TTS 需要互聯網;如果您的防火牆
  阻止 `speech.platform.bing.com`,切換到 ElevenLabs、
  Google Cloud TTS 或 **Piper TTS**(完全離線)。

### "Piper voice not installed" 對話方塊

Voice / Dubbing / Translate Text 頁面在任何 worker 啟動前
飛行前檢查您的目标語言的 Piper 語音是否在磁盤上。如果不在,
您將看到一個帶**開啟設定**按鈕的模態。

下載語音:

1. 在對話方塊中點擊**開啟設定**(或手動開啟**設定 → 語音**)。
2. 確保 **TTS 方法**設定為 **Piper TTS**。
3. 點擊**立即下載語音**開啟語音库對話方塊。
4. 找到您目标語言的行,然後點擊旁邊的 **Female voice** 或
   **Male voice**。語音是從 HuggingFace 下載的 ~25–60 MB ONNX 檔案;
   每種語言一次。
5. 關閉對話方塊並重新執行您的翻譯 / voice / dub 任務。

如果您的目标語言不在清單中,它沒有 Piper 覆蓋——引擎在合成時
悄悄回到 Edge TTS,所以您實際上不需要下載任何東西。
今天沒有 Piper 語音的 13 種語言:白俄羅斯語、孟加拉語、
中文(繁體)、克羅地亞語、愛沙尼亞語、希伯來語、日語、
高棉語、韓語、立陶宛語、馬來語、蒙古語、泰語。

**即時翻譯**頁面是*不會*顯示此對話方塊的唯一地方——
用模態打斷即時流會比回退更糟,所以那裡語音缺失的情況
悄悄走向 Edge TTS。

## 文件翻譯錯誤

### PDF 翻譯在特定頁面失敗

PDF 使用每页檢查點——成功的頁面不會重做。失敗的頁面將堆棧記錄檔記錄
到 `app.log`;常見罪魁禍首:

- 頁面是**沒有文本層的掃描**且 OCR 未設定。設定**設定 → OCR**
  (見 [OCR 引擎](setup/ocr-engines.md))。
- 頁面套件含 LLM 弄亂的**復雜數學布局**。嘗試更強的模型
  (Pro 變體而不是 Flash)。

### Office 翻譯破壞格式

- **現代格式**(`.docx`、`.xlsx`、`.pptx`)——透過 HTML 往返
  逐 run 保留格式。如果您在輸出中看到流浪的 `<b>` 標籤,LLM 沒有
  關閉它們——用更強的模型重新執行。
- **舊格式**(`.doc`、`.xls`、`.ppt`)——開啟**設定 → 翻譯 →
  Auto-convert legacy** 以獲得更好的保真度。管道首先轉換為 `.docx`,
  翻譯,再轉換回來。

### 翻譯佇列在批次中間停止

結束應用並檢查資料庫:

```bash
sqlite3 ~/.local/share/ai-translate/translator.db \
  "SELECT id, status, error_code, file_name FROM history WHERE status NOT IN ('Done', 'Failed') ORDER BY created_at DESC LIMIT 10;"
```

數分鐘未觸及的 `Translating` 行意味着 worker 靜默崩潰。
重新啟動桌面應用程式——它在啟動時自動恢復 Pending / Translating 任務。

## 跨界問題

### 一次多個檔案被靜默地翻譯為一個

一次拖放一個檔案,或檢查佇列标題中的 **Files** 列——
它應顯示您拖放的數量。100 檔案上限在超過時顯示通知。

### 側欄永遠顯示旋轉器

表示 worker 仍被标記為執行中。干淨結束應用(無 SIGKILL)——
autouse 清理掛鉤重置标志。如果 SIGKILL 留下了卡住的狀態,
手動清除 DB worker:

```bash
sqlite3 ~/.local/share/ai-translate/translator.db \
  "UPDATE history SET status='Failed', error_code=99 WHERE status IN ('Pending', 'Translating');"
```

### 記錄檔在哪裡? {: #where-are-the-logs }

| OS | 路徑 |
|---|---|
| **Linux** | `~/.local/state/log/ai-translate/app.log` |
| **macOS** | `~/Library/Logs/ai-translate/app.log` |
| **Windows** | `%LOCALAPPDATA%\ai-translate\logs\app.log` |

無論控制台詳細程度如何,記錄檔總是捕獲 DEBUG+。控制台輸出
預設是 INFO+;向 CLI 傳遞 `--verbose` 以在 stdout 上鏡像
完整的檔案記錄檔。

## 仍然卡住?

- 設計層面的問題見 [FAQ](faq.md)。
- 在 <https://github.com/cadic2603/ai-translate/issues>
  提交 issue,套件含:OS、Python 版本、失敗的命令、`app.log` 的
  相關切片以及您期望的內容描述。
