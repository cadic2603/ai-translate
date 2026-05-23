---
description: 將 Google Cloud 連接到 AI Translate 用於 Vision OCR、Speech-to-Text 和 Text-to-Speech — 設定 API 密鑰並啟用相關服務。
---

# Google Cloud（Vision OCR / Speech-to-Text / Text-to-Speech）

一個 Google Cloud API 密鑰支援三個選用的后端：

- **Vision OCR** — 付費 OCR 引擎（每月 1,000 次免費）
- **Speech-to-Text v1** — 付費 STT（每月 60 分鐘免費）
- **Text-to-Speech v1** — 付費 TTS（WaveNet 每月 1 M 字元免費）

你只需要啟用你實際使用的 API。

## 獲取 API 密鑰

1. [創建 Google Cloud 專案](https://console.cloud.google.com/projectcreate)
2. 開啟 API 库：<https://console.cloud.google.com/apis/library>
3. 啟用以下任一：
    - [Vision API](https://console.cloud.google.com/apis/library/vision.googleapis.com)
    - [Speech-to-Text API](https://console.cloud.google.com/apis/library/speech.googleapis.com)
    - [Text-to-Speech API](https://console.cloud.google.com/apis/library/texttospeech.googleapis.com)
4. [創建 API 密鑰](https://console.cloud.google.com/apis/credentials)：
   點擊 **+ Create Credentials → API key**
5. 複製密鑰（看起來像 `AIza...`）。

!!! tip "限制密鑰"
    在 API 密鑰詳細資訊頁面，在 **API restrictions** 下，將密鑰限制
    為僅你已啟用的 API。這樣泄漏的密鑰不能在你不想使用的服務上累積
    賬單。

## 在應用中設定

在**設定 → 服務**中：

1. 貼上到 **Google Cloud API 密鑰** → **儲存**

這個單一密鑰現在對所有三個 Google 服務可用。

## 啟用每個服務

### Vision OCR

在**設定 → OCR → OCR 方法 = Google Cloud OCR**。

就是這樣 — 它將使用服務中的相同密鑰。

### Speech-to-Text

在**設定 → 字幕 → STT 方法 = Google Cloud**（用於字幕 / 語音頁面）或
**設定 → Live → STT 方法 = Google Cloud**（用於 Live 頁面）。

在**設定 → 字幕 → Google STT 模型**中，選擇識別模型：

| 模型 | 最适合 |
|---|---|
| `latest_long`（預設） | 長格式音訊（采訪、講座） |
| `latest_short` | 語音命令、短句 |
| `phone_call` | 電話音訊（8 kHz） |
| `medical_dictation` / `medical_conversation` | 醫療領域音訊 |

### Text-to-Speech

在**設定 → 語音 → TTS 方法 = Google Cloud TTS**。

預設情況下，伺服器根據語言和性別選擇語音 — 這是大多數使用者所需的全部。
固定特定 Google 語音（例如 `en-US-Chirp3-HD-Charon`、
`vi-VN-Wavenet-A`）由引擎支援，但尚未作為設定字段公開；可以透過直接
在 `settings.ini` 中編輯 `voice/google_tts_voice_name` 來設定。語音
ID 在 <https://cloud.google.com/text-to-speech/docs/voices> 列出。

## 常見錯誤

| 錯誤 | 可能原因 |
|---|---|
| `AUTH_ERROR` | 密鑰錯誤 / 過期。在設定 → 服務中重新貼上。 |
| `API not enabled` | 你尚未在此 Cloud 專案上啟用特定 API（Vision / Speech / TTS）。 |
| `QUOTA_ERROR` | 此 API 的免費層限額達到。等待，或升級賬單。 |
| `INVALID_ARGUMENT_ERROR` | 你選擇的語言中不存在該語音名稱。 |

## 成本守衛

!!! warning
    所有三個 Google API 都是后付費的 — 一旦你超過免費層，就會開始
    被無限制地計費。在做大量工作之前，在 Cloud 專案上設定
    [預算警報](https://console.cloud.google.com/billing/budgets)。
