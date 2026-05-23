---
description: "為翻譯設定 LLM 提供商：Google Gemini（推薦）、與 OpenAI 兼容的端點，或任何帶有 API 密鑰的自定義提供商。"
---

# LLM 提供商

翻譯管道調用大型語言模型進行實際翻譯。你可以設定一個或多個；每個功能
的模型選擇器允許每個頁面使用不同的。

## Google Gemini（建議首次設定使用） {: #google-gemini-recommended-for-first-time-setup }

免費層很慷慨，對大多數個人使用足夠好。

1. 前往 <https://aistudio.google.com/apikey>
2. 點擊 **Create API key**（用你的 Google 賬戶登入）
3. 複製密鑰（看起來像 `AIza...`）
4. 在桌面應用程式中：**設定 → LLM → Gemini API 密鑰** → 貼上 → **儲存**
5. 在**預設 Gemini 模型**下拉選單中選擇預設模型。Google 的陣容往往
   看起來像：

    - **Flash** 變體（例如 `gemini-2.5-flash`）— 快速、慷慨的免費層、
      品質好。推薦起點。
    - **Pro** 變體 — 較慢、品質更高、更貴。
    - **Flash-lite** — 最快、最便宜、品質較低。

    可用的具體模型名取決於 Google 推送給你賬戶的內容；選擇名稱套件含
    `flash` 的以獲得平衡的預設值。

完成。密鑰儲存在你的 OS 鑰匙串中，而不是明文。

### Vertex AI 模式（企業）

在 Gemini 設定塊內，一對單選按鈕讓你從 **Developer API** 切換到
**Vertex AI** — 相同的 Gemini 模型，透過你的 GCP 賬戶計費，具有組織
級別控制（VPC-SC、審計記錄檔、區域資料駐留）。

1. 在**設定 → LLM** 中將 Gemini 單選按鈕從 **Developer API** 切換到
   **Vertex AI**
2. 填寫：
    - **Project** — 你的 GCP 專案 ID
    - **Location** — Vertex 區域（預設 `us-central1`）
    - **Credentials path** *(選用)* — 服務賬戶 JSON 密鑰檔案的路徑。
      留空使用 Application Default Credentials
      （`gcloud auth application-default login`）
3. **儲存**。模型下拉選單在專案設定好后從 Vertex 重新填充。

OAuth 重新整理由 `google-genai` 自動處理。服務賬戶 JSON 路徑故意以明文
儲存（*路徑*不是秘密 — 檔案的內容才是，並且它們留在磁盤上，這是
Google 文件化的最佳實踐所保留它們的位置）。

## OpenAI / OpenAI 兼容

任何暴露 OpenAI 兼容 REST API 的東西都有效 — OpenAI 自己、透過
[LiteLLM 代理](https://docs.litellm.ai)的 Anthropic、本地 Ollama、
LM Studio、vLLM、Together.ai、Groq 等等。

在**設定 → LLM**中：

1. 點擊 **Add Custom Provider**
2. 填寫：
    - **Name** — 像 "OpenAI" / "Local Ollama" / "Anthropic" 的標籤
    - **API endpoint** — 基礎 URL（例如 `https://api.openai.com/v1`
      或 `http://localhost:11434/v1` 用於 Ollama）
    - **API key** — 對未驗證的本地端點留空
    - **Models** — 逗號分隔的清單（例如 `gpt-4o-mini, gpt-4o,
      gpt-3.5-turbo`）
3. 點擊 **Save**。

自定義提供商作為 JSON blob 儲存在 OS 鑰匙串中（套件括 API 密鑰）。

## 切換預設模型

**設定 → LLM** 中的**預設 Gemini 模型**下拉選單設定一個后備，由沒有
自己選擇器的每個功能頁面使用。

具有自己模型選擇器的頁面：

- **翻譯文本** — `翻譯文本設定頁籤 → 預設模型`
- **翻譯文件** — 按任務選擇；回到預設
- **字幕 / 語音 / 配音 / Live / 提取文本** — 每個在其設定頁籤中
  都有自己的每功能預設值

這讓你混合搭配：免費 Flash 用於 live、Pro 用於大文件、本地 Ollama
用於敏感資料。

## 密鑰儲存位置

| OS | 儲存 |
|---|---|
| **macOS** | 鑰匙串（登入鑰匙串） |
| **Windows** | 認證資料管理器 |
| **Linux (GNOME)** | Secret Service（gnome-keyring / KWallet） |
| **Linux（無守護處理程序）** | 回到 `~/.config/ai-translate/settings.ini` 中的明文 INI |

回退 INI 值在鑰匙串可用時的首次讀取時遷移到鑰匙串 — 無手動步驟。

## 無頭 / 伺服器安裝

沒有桌面會話，你仍然可以透過 Python 的 `keyring` CLI 設定密鑰
（在 `uv sync` 之後）：

```bash
# Gemini
uv run keyring set ai-translate llm/gemini_api_key

# 自定義提供商（貼上 JSON blob — 見設定 UI 了解 schema）
uv run keyring set ai-translate llm/custom_providers
```

或直接在 `settings.ini` 中設定相同的 INI 密鑰 — 應用在首次讀取時
將它們遷移到鑰匙串。檔案位於：

- **Linux** — `~/.config/ai-translate/settings.ini`
- **macOS** — `~/Library/Preferences/ai-translate/settings.ini`
- **Windows** — `%APPDATA%\ai-translate\settings.ini`

## 測試你的設定

最快的健全性檢查：

```bash
uv run ait --version
echo "Hello world." > /tmp/x.txt
uv run ait /tmp/x.txt --target Chinese --quiet
cat /tmp/x_translated__zh.txt
```

如果你看到 "你好世界。" — 你完成了。

## 常見錯誤

| 錯誤 | 可能原因 |
|---|---|
| `AUTH_ERROR` | API 密鑰錯誤 / 過期。在設定中重新貼上。 |
| `QUOTA_ERROR` | 免費層每日要求超出。等待或付費。 |
| `MODEL_NOT_FOUND` | 自定義提供商的 `models` 清單不套件含要求的模型。 |
| `VISION_NOT_SUPPORTED` | 你選擇的模型不能進行圖像輸入。使用 `flash` / `pro` / `vision` 變體。 |

更多見[故障排除](../troubleshooting.md)。
