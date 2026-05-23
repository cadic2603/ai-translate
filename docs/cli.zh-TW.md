---
description: 使用 ait 命令列介面無介面地翻譯檔案——支援 PDF、Office 文件、字幕和 45 多種語言,可從指令稿或 CI 任務執行。
---

# 命令列 (`ait`)

無介面翻譯——與桌面應用程式相同的管道,無需顯示器。适用於 CI、批處理任務、
伺服器和指令稿化的工作流。

## 快速開始

```bash
ait report.docx --target French
```

輸出落在源檔案旁邊,命名為 `report_translated_<src>_<tgt>.docx`。

## 常見用法

### 多個檔案

```bash
ait *.pdf --target Japanese
```

Glob 展開是 shell 的工作(Unix)。在 Windows / `cmd.exe` 上,
顯式列出檔案或使用 PowerShell:

```powershell
ait (Get-ChildItem *.pdf) --target Japanese
```

### 自定義輸出目錄

```bash
ait report.docx --target French --output ./translated/
```

如果目錄不存在則創建。如果無法創建(權限被拒絕等),
您會收到清晰的錯誤和結束碼 2——不會有半執行狀態。

### 指定源語言

```bash
ait letter.txt --target German --source "English (US)"
```

源匹配不區分大小寫。"Chinese" 單獨使用會打印提示:

```bash
ait letter.txt --target Chinese
# Error: unknown target language 'Chinese'.
# Did you mean one of: Chinese (Simplified), Chinese (Traditional)?
```

### 選擇特定模型

```bash
ait big-doc.pdf --target French --model "Gemini:gemini-2.5-pro"
# 或桌面應用程式 LLM 分頁中註冊的任何其他 Provider:model_name。
```

格式嚴格為 `Provider:model_name`。缺少冒號 → 結束 2 並顯示清晰消息,
而不是悄悄回到預設 Gemini 模型。

### Office 選項

```bash
ait deck.pptx --target Vietnamese \
    --translate-images \
    --translate-comments \
    --translate-shapes \
    --translate-notes
```

`--translate-images` 需要設定 OCR(參見
[OCR 引擎](setup/ocr-engines.md))。

### 舊格式自動轉換

```bash
ait old-doc.doc --target French --convert-legacy
```

管道首先將 `.doc` → `.docx` 轉換(更好的保真度),翻譯現代副本,
再轉換回來。`--convert-odf` 和 `.odt` / `.ods` / `.odp` 同理。

### 靜默 / 詳細

```bash
ait report.docx --target French --quiet      # 僅錯誤
ait report.docx --target French --verbose    # 完整 DEBUG 流
```

預設模式將橫幅和每任務進度打印到 stderr;完整詳情(HTTP body 轉儲、
重試記錄檔)無論控制台詳細程度如何都會進入平台的應用記錄檔目錄(參見
[故障排除 → 記錄檔在哪裡?](troubleshooting.md#where-are-the-logs)
查看您的 OS 上的路徑)。

### 列出支援的語言

```bash
ait --list-languages
```

打印所有 45 種支援的語言。便於透過管道傳遞到 shell 循環。

### 版本

```bash
ait --version
# ait 0.1.0
```

## 結束碼

| 碼 | 含義 |
|---|---|
| `0` | 所有任務成功 |
| `2` | 參數錯誤(未知語言、缺失目标、格式錯誤的模型、不可寫的輸出、不支援的檔案擴充名) |
| `3` | LLM 未設定 |
| `4` | 部分失敗(部分成功,部分失敗) |
| `5` | 全部失敗 |
| `130` | 中斷 (`Ctrl+C`) |

## 取消

`Ctrl+C` 一次——協作式取消。目前任務的檢查點被儲存,
管道在下一個輪詢邊界干淨結束。

`Ctrl+C` 再次——硬中斷。謹慎使用;部分檔案可能保留半寫狀態。

## 完整标志參考

```bash
ait --help
```

顯示每個标志及其預設值。同樣的內容在這裡總結:

| 标志 | 預設 | 說明 |
|---|---|---|
| `--target / -t LANG` | _必需_ | 不區分大小寫 |
| `--source / -s LANG` | 自動檢測 | 不區分大小寫 |
| `--output / -o DIR` | 源的父目錄 | 缺失時創建 |
| `--model / -m PROVIDER:MODEL` | 桌面預設 | 嚴格格式 |
| `--ocr-method METHOD` | `TesseractOCR` | `Tesseract`、`EasyOCR`、`Google Cloud OCR` |
| `--translate-images` | 關 | 需要設定 OCR |
| `--translate-comments` | 關 | Office 註解 |
| `--translate-shapes` | 關 | 形狀 / 文本框 |
| `--translate-notes` | 關 | PowerPoint 演講者備註 |
| `--translate-sheet-names` | 關 | Excel 工作表標籤 |
| `--convert-legacy` | 關 | `.doc`/`.xls`/`.ppt` → 現代格式 |
| `--convert-odf` | 關 | `.odt`/`.ods`/`.odp` → OOXML |
| `--keep-history` | 關 | 完成后保留歷史條目 |
| `--quiet / -q` | 關 | 控制台僅顯示錯誤 |
| `--verbose / -v` | 關 | DEBUG 流 |
| `--list-languages` | — | 打印 45 種語言並結束 |
| `--version` | — | 打印版本並結束 |

## 提示

!!! tip "一次設定,處處使用"
    CLI 與桌面應用程式共享 API 密鑰和設定——在 GUI 中一次性設定好,
    然後從那裡用 `ait` 自動化。

!!! tip "冷啟動 endpoint 快取"
    對於每個 `(endpoint, 模型)` 對,chat-vs-responses-API 選擇
    和有效的 payload 變體被持久化到 OS 快取目錄中的
    `llm_endpoint_cache.json`(Linux 上 `~/.cache/ai-translate/`,
    macOS 上 `~/Library/Caches/ai-translate/`,
    Windows 上 `%LOCALAPPDATA%\ai-translate\cache\`)。冷啟動 CLI
    調用在第一次成功調用后完全跳過自動檢測探測——
    在指令稿化對接需要供應商特定 payload 調優的 Azure / vLLM /
    OpenRouter / Anthropic / DeepSeek 部署時很有用。
    快取是多處理程序和多執行緒安全的(在 RLock 下進行 read-merge-write,
    帶原子 rename)。

!!! tip "輸出流"
    預設模式將橫幅、排隊任務清單和每任務進度打印到 **stdout**
    (按行緩衝,以便與錯誤正確交錯);錯誤消息和記錄檔記錄進入
    **stderr**。結合 `--quiet` 完全抑制 stdout 以進行干淨的管道:

    ```bash
    ait --list-languages | grep -i japanese    # 資料在 stdout
    ait file.txt --target French --quiet 2> errors.log
    ```
