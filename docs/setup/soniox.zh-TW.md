---
description: 在 AI Translate 的 Live 頁面設定 Soniox 用於即時語音轉文字 — 支援說話人分離、術語表條目和即時翻譯。
---

# Soniox (STT)

透過 Soniox WebSocket API 進行即時語音轉文字。当你選擇 Soniox 作為
STT 方法時，由**[字幕](../features/generate-subtitle.md)**和
**[即時翻譯](../features/live-translation.md)**頁面使用。

## 為什麼選擇 Soniox

- **即時** — 在說話人還在說話時令牌就已到達。
- **說話人分離** — 每個令牌的說話人標籤（例如 _說話人 1：你好…_）。
- **流內翻譯** — Soniox 可以在轉錄的同時翻譯，節省額外的 LLM 往返。
- **多語言** — 即使在流中也能自動檢測源語言。

## 獲取 API 密鑰

1. 在 <https://console.soniox.com> 註冊
2. 開啟 **API keys** → **Create new API key**
3. 複製（看起來像 `Bearer ...`；只複製 token，不帶 `Bearer ` 前綴）。

定價按音訊分鐘計費（撰寫時約 $0.005 / 分鐘）— 見
<https://soniox.com/pricing>。

## 在應用中設定

在**設定 → 服務**中：

1. 將密鑰貼上到 **Soniox API 密鑰** → **儲存**

在**設定 → Live**（用於即時翻譯）或**設定 → 字幕**（用於字幕生成）中：

1. 將 **STT 方法**設為 **Soniox**

## 它支援什麼

| 頁面 | 何時使用 Soniox |
|---|---|
| **字幕** | 多說話人錄音（采訪、小組討論、會議），你希望在 SRT 中有說話人標籤 |
| **即時翻譯** | 即時會議字幕，特別是有多個說話人時 |

## 術語表條目

Soniox WebSocket 接受一個術語表來偏置識別。應用自動轉發你的活動術語
表條目 — 品牌名 / 專有名詞 / 行話能更可靠地被識別。

## 注意事项

!!! warning "僅線上"
    Soniox 僅雲端；如果你的音訊敏感（醫療、法律），請改用 Whisper
    （本地）。

!!! info "重連"
    WebSocket 在瞬時故障時會以指數退避自動重連。長會話能在短暫網路
    波動中保持連接。

## 常見錯誤

| 錯誤 | 可能原因 |
|---|---|
| `AUTH_ERROR` | API 密鑰錯誤 / 過期。在設定 → 服務中重新貼上。 |
| `QUOTA_ERROR` | 套餐限額超出。 |
| `CONNECTION_ERROR` | 網路被阻止 / 防火牆。從不同網路重試。 |
