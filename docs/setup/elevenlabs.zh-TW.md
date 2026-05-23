---
description: 將 ElevenLabs 連接到 AI Translate 以獲得高品質神經 TTS — 用逼真、富有表現力的語音生成 30+ 種語言的配音。
---

# ElevenLabs (TTS)

進階神經文本轉語音。当你選擇 ElevenLabs 作為 TTS 方法時，由
**[生成語音](../features/generate-voice.md)**、
**[配音](../features/dubbing.md)**和
**[即時翻譯](../features/live-translation.md)**頁面使用。

## 獲取 API 密鑰

1. 在 <https://elevenlabs.io> 註冊
2. 開啟 <https://elevenlabs.io/app/settings/api-keys>
3. 點擊 **+ Create New Key**，命名（例如 "ai-translate"），複製密鑰
   （看起來像 `sk_...`）

免費層每月給你約 10,000 個字元，足夠測試。生產使用從約 $5/月開始。

## 在應用中設定

在**設定 → 服務**中：

1. 將密鑰貼上到 **ElevenLabs API 密鑰** → **儲存**
2. 在**語音 ID** 中輸入你偏好的**語音 ID**（在
   <https://elevenlabs.io/app/voice-lab> 找到 ID；從語音的 URL 中
   複製 ID）。留空讓 ElevenLabs 選擇預設。

在**設定 → 語音**中：

1. 將 **TTS 方法**設為 **ElevenLabs**
2. 選擇 **ElevenLabs 模型**：

    | 模型 | 最适合 |
    |---|---|
    | `eleven_multilingual_v2`（預設） | 通用使用，延遲/品質平衡 |
    | `eleven_v3` | 最高品質（用於生產配音） |
    | `eleven_flash_v2_5` | 最低延遲（用於即時翻譯） |

## 它支援什麼

| 頁面 | 何時使用 ElevenLabs |
|---|---|
| **生成語音** | 你想從字幕檔案獲得進階品質配音 |
| **配音** | 你想在翻譯影片上獲得高品質的配音軌 |
| **即時翻譯** | 你想即時播放翻譯字幕的語音 |

## 語音克隆

ElevenLabs 支援自定義語音克隆（付費計劃）。在 ElevenLabs 網站上克隆
語音后，將其語音 ID 貼上到**設定 → 服務 → 語音 ID** 中，配音 / 語音
生成管道將使用它。

## 注意事项

!!! warning "預檢查"
    語音 / 配音頁面在開始工作*之前*檢查你的 ElevenLabs API 密鑰已
    設定。如果缺失，你會得到一個友好的對話方塊指向設定，而不是半執行
    的任務。

!!! tip "Live 模式自動回退"
    在**即時翻譯**頁面，如果你選擇了 ElevenLabs 但沒有設定密鑰，
    應用會自動回到 **Edge TTS**（免費）並在狀態標籤中宣布回退，
    以便你方便時修復。

!!! info "仍需要 FFmpeg"
    ElevenLabs 返回音訊字節；應用仍使用 FFmpeg 在格式之間轉換並將
    定時片段組合成一個檔案。見 [FFmpeg 設定](ffmpeg.md)。

## 常見錯誤

| 錯誤 | 可能原因 |
|---|---|
| `AUTH_ERROR` | API 密鑰錯誤 / 過期。在設定 → 服務中重新貼上。 |
| `QUOTA_ERROR` | 免費層字元限制達到，或付費計劃耗尽。 |
| `MODEL_NOT_FOUND` | 所選 ElevenLabs 模型不再可用；在設定 → 語音中選擇另一個。 |
