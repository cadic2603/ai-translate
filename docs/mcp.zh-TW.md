---
description: 將 AI Translate 公開為 Model Context Protocol 工具,以便 Claude Desktop、Claude Code 和其他 MCP 用戶端可以翻譯文本、檔案和音訊。
---

# MCP 伺服器 (`ait-mcp`)

將翻譯管道公開為 **Model Context Protocol** 工具,以便 Claude Desktop
和 Claude Code 等 AI 智能體可以直接驅動它——"將這個 PDF 翻譯成法語"
變成一次工具調用,而不是複製貼上。

## 公開內容

九個工具:

| 工具 | 用途 |
|---|---|
| `translate_text` | 翻譯字串清單 |
| `translate_document` | 排隊檔案翻譯任務(返回任務 ID) |
| `get_task_status` | 輪詢任務狀態 |
| `cancel_task` | 協作式取消正在執行的任務 |
| `extract_image_text` | OCR 或 LLM 視覺 |
| `transcribe_audio` | 音訊 → SRT |
| `synthesize_speech` | 文本 → MP3 / WAV |
| `query_glossary` | 列出術語集 / 條目 |
| `list_languages` | 全部 45 種支援的語言 |

## 執行伺服器

```bash
ait-mcp                       # stdio 傳輸(桌面智能體的預設)
ait-mcp --transport sse       # 用於 Web 用戶端的 Server-Sent Events
ait-mcp --transport sse --port 9000
```

`stdio` 是任何 MCP 用戶端的預期,除非您已顯式設定 SSE。

## 添加到 Claude Desktop

1. 開啟 Claude Desktop → **Settings → Developer → Edit Config**
2. 在 `mcpServers` 下添加此條目:

    ```json
    {
      "mcpServers": {
        "ai-translate": {
          "command": "uv",
          "args": ["run", "--project", "/absolute/path/to/ai-translate", "ait-mcp"]
        }
      }
    }
    ```

    將 `/absolute/path/to/ai-translate` 取代為克隆的 repo 路徑。

3. 結束並重新開啟 Claude Desktop。錘子圖标現在應顯示帶有所有 9 個工具的
   "ai-translate"。試試:

    > "將這個 PDF (`/home/me/report.pdf`) 翻譯成法語——把輸出儲存在源檔案旁邊。"

## 添加到 Claude Code

`~/.config/claude-code/mcp_servers.json`(或從 Claude Code 內部
`claude mcp add`):

```json
{
  "ai-translate": {
    "command": "uv",
    "args": ["run", "--project", "/absolute/path/to/ai-translate", "ait-mcp"]
  }
}
```

重新啟動 Claude Code。同樣的 9 個工具變得可調用。

## 添加到其他 MCP 用戶端

任何 MCP 兼容的用戶端采用類別似的形式:

- **Command** — `uv run --project /path/to/ai-translate ait-mcp`
- **Transport** — stdio(預設)

對於基於 HTTP / SSE 的用戶端,執行
`ait-mcp --transport sse --port 9000` 並將用戶端指向
`http://localhost:9000`。

## 驗證保證

每個工具在錯誤時返回相同的形狀,以便智能體可以一致地處理失敗:

| 錯誤輸入 | 工具回應 |
|---|---|
| 未知語言 | `ValueError: Unknown … language '<input>'. Call list_languages to see supported values.` |
| LLM 未設定 | `RuntimeError: LLM is not configured. Run the desktop app and set up your API key…` |
| 不支援的檔案類別型 | 列出允許擴充名的 `ValueError` |
| 格式錯誤的 `model="…"` (無 `:`) | `ValueError`,而不是悄悄使用預設值 |
| `cancel_task` 中未知的任務 ID | 在 `unknown` 陣列中返回——無錯誤 |
| `transcribe_audio` 中缺少 FFmpeg | `RuntimeError: FFmpeg is required…`(從引擎的原始 `FFMPEG_NOT_FOUND` 標籤重新套件裝) |

調用這些工具的智能體可以相依這些契約。

## 並行

`translate_document` 在守護執行緒中執行管道。每個批次獲得自己的取消事件,
因此取消一個批次不會干擾另一個。MCP 伺服器在處理程序本地映射中跟蹤活動管道
(管道結束時自動清理)。

## 用例

- **"將這個程式碼库的文件翻譯成越南語"** ——將智能體指向 docs 檔案夾,
  它會批處理 `translate_document` 調用,並輪詢 `get_task_status`
  直到每一個完成。
- **"你支援哪些語言?"** ——智能體調用 `list_languages`,讀取回應。
- **"翻譯這張日語收據"** ——智能體在照片上調用 `extract_image_text`,
  然後在結果上調用 `translate_text`。
- **"為這個 Zoom 錄影生成越南語字幕"** ——智能體調用 `transcribe_audio`
  以獲取源語言的 SRT,然後在每個 cue 上調用 `translate_text` 進行本地化,
  再重新組裝 SRT。

!!! note "影片配音不是 MCP 工具"
    完整的 STT → 翻譯 → TTS → mux 管道(桌面應用程式的**配音**頁面)
    目前僅透過 GUI 可用。從 MCP 您可以自己組合等效的:
    `transcribe_audio` + `translate_text` + `synthesize_speech`,
    但您需要在外部處理時序敏感的 mux 步驟(FFmpeg)。

## 技巧

!!! tip "設定一次,智能體在任何地方工作"
    MCP 伺服器與桌面應用程式和 CLI 共享 API 密鑰和設定。在 GUI 中一次性
    設定 LLM / OCR / TTS,然後任何與 `ait-mcp` 通信的智能體都繼承
    相同的設定。

!!! tip "冷啟動 endpoint 快取"
    對於每個 `(endpoint, 模型)` 對,chat-vs-responses-API 選擇和
    有效的 payload 變體被持久化到 OS 快取目錄中的
    `llm_endpoint_cache.json`(Linux 上 `~/.cache/ai-translate/`,
    macOS 上 `~/Library/Caches/ai-translate/`,
    Windows 上 `%LOCALAPPDATA%\ai-translate\cache\`)。新的 `ait-mcp`
    處理程序在第一次成功調用后完全跳過自動檢測探測——按需啟動伺服器的
    智能體不會在每次調用時支付變體檢測往返。快取是多處理程序和多執行緒
    安全的(在 RLock 下進行 read-merge-write,帶原子 rename)。

!!! tip "每個工具的模型選擇器"
    `translate_text` 和 `translate_document` 工具接受選用的 `model`
    參數——智能體可以為快速回合選擇快速模型,為生產輸出選擇更重的
    模型,而不需要使用者重新設定桌面應用程式。

!!! warning "長時間執行的管道"
    `translate_document` 立即返回任務 ID。期望智能體輪詢
    `get_task_status` 直到每個任務達到 `Done` 或 `Failed`。不要在
    工具調用內部同步等待;那會冒 MCP 用戶端超時觸發的風險。
