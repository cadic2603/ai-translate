---
description: 使用 Edge TTS、ElevenLabs、Google Cloud TTS、Gemini TTS 或離線 Piper TTS 將字幕轉換為口語音訊 — 保留 SRT 時間以生成配音品質的語音。
---

# 生成語音 (TTS)

將字幕檔案（帶時間）或任意文本合成為 MP3 / WAV 音訊。五種 TTS 后端：
Edge TTS（免費）、ElevenLabs（高品質）、Google Cloud TTS、Gemini TTS
（免費層）和 Piper TTS（離線）。

## 你需要什麼

- `PATH` 中的 **FFmpeg** — 見 [FFmpeg 設定](../setup/ffmpeg.md)。
- 一個 TTS 后端，以下之一：
    - **Edge TTS** — 免費，無密鑰，預設。使用 Microsoft Edge 的雲端
      語音。
    - **ElevenLabs** — 付費，最高品質。見 [ElevenLabs 設定](../setup/elevenlabs.md)。
    - **Google Cloud TTS** — 付費，非常好。見 [Google Cloud 設定](../setup/google-cloud.md)。
    - **Gemini TTS** — 免費層，自然預設語音。復用你 LLM 頁籤中
      現有的 Gemini API 密鑰 — 無需額外設定。
    - **Piper TTS** — 完全離線的神經網路 TTS。無 API 密鑰，無網路
      調用 — 語音是約 25–60 MB 的 ONNX 檔案，透過**設定 → 語音 →
      Piper TTS → 立即下載語音**一次性下載。應用 45 種語言中的 32
      種今天有 Piper 語音；沒有 Piper 覆蓋的語言在合成時會靜默回到
      Edge TTS。

## 操作步驟

1. 在側欄點擊**生成語音**。
2. 拖放一個或多個 `.srt` / `.vtt` / `.ass` / `.ssa` 字幕檔案。
3. 選擇**語言**（尽可能從字幕檔案名自動檢測 — 例如
   `_translated_en_zh.srt` 被檢測為中文）。
4. 選擇**語音性別** — `女` 或 `男`。
5. 選擇**輸出格式** — `.mp3`（預設）或 `.wav`。
6. 點擊**生成**（或 `Ctrl+Enter`）。
7. 完成后**開啟**該行 — 在你的預設音訊應用中播放。

## 輸出

你會得到一個單一的音訊檔案，其中語音軌道放置在每個字幕的時間戳上。
靜音間隙填充提示之間的時間，以便音訊與原始時間保持同步。

## 選擇 TTS 后端

| 后端 | 成本 | 語音 | 備註 |
|---|---|---|---|
| **Edge TTS** | 免費 | 數百，所有主要語言 | 預設。無設定。 |
| **ElevenLabs** | 付費（約 $5/月入門級） | 進階神經語音，語音克隆 | 最高品質。語音 ID 在設定 → 服務中設定。 |
| **Google Cloud TTS** | 付費（約 $4/M 字元；每月免費 1 M） | 50+ 種語言的 WaveNet / Studio 語音 | 強大的歐洲語言 WaveNet 語音。預設情況下，伺服器根據語言 + 性別選擇語音。 |
| **Gemini TTS** | 免費層（适用 Developer API 配額） | 24+ 種語言的自然預設語音 — `Kore`（女預設）/ `Puck`（男預設） | 復用你 LLM 頁籤中的 Gemini API 密鑰。每次調用輸出限制約 30 秒；長文本自動在句子邊界分塊。 |
| **Piper TTS** | 免費，**離線** | 應用 45 種語言中 32 種的神經語音 | 無密鑰，無網路。每語言語音從**設定 → 語音 → Piper TTS → 立即下載語音**按需下載（每個約 25–60 MB）。預檢查在工作開始前捕獲缺失的語音。 |

在**設定 → 語音 → TTS 方法**中切換。

## Piper TTS 細節

Piper 是應用中唯一完全離線的 TTS 后端。需要了解的幾件事：

- **語音库對話方塊** — 透過**設定 → 語音 → Piper TTS → 立即下載語音**
  開啟。每個語言行顯示一個`女聲`和/或`男聲`下載按鈕（某些語言是
  單一性別）。語音來自
  [rhasspy/piper-voices](https://huggingface.co/rhasspy/piper-voices)
  HuggingFace 目錄。
- **覆蓋范圍** — 應用 45 種語言中的 32 種有 Piper 語音。沒有覆蓋的
  13 種（白俄羅斯語、孟加拉語、中文（繁體）、克羅地亞語、愛沙尼亞語、
  希伯來語、日語、高棉語、韓語、立陶宛語、馬來語、蒙古語、泰語）在
  合成時靜默回到 Edge TTS，所以合成永遠不會因為缺失語音而硬失敗。
- **性別解析** — 当你選擇`女`時，引擎首先嘗試該語言的女聲；如果只有
  男聲，它會改用那個（反之亦然）。在 INFO 級別記錄。
- **預檢查門** — 在語音執行開始之前，頁面會檢查每語言的 Piper 語音
  是否在磁盤上。如果缺失，你會得到一個帶有**開啟設定**按鈕的模態
  對話方塊，它直接帶你到語音库，這樣你可以在不丟失佇列的情況下下載它。

## Gemini TTS 細節

Gemini TTS 透過 Developer API 使用 `gemini-2.5-flash-preview-tts`。
需要了解的幾件事：

- **語音選擇**今天按性別 — 女映射到 `Kore`，男映射到 `Puck`。兩者
  都是清晰、中性的語音，跨語言工作而不會聽起來太具特征性。
- **輸出長度上限** — 每次 Gemini API 調用最多返回約 30 秒的語音。
  應用在句子邊界處將輸入文本分塊到 `_GEMINI_TTS_MAX_BYTES`
  （約 2000 字節 ≈ 30 秒）以下，然後透過 FFmpeg 連接塊。在正常字幕
  文本上你不會遇到截斷。
- **音訊格式** — Gemini 輸出 24 kHz 單聲道 s16le 的原始 PCM；應用
  按塊轉碼為 MP3（或如果你選擇則為 WAV），以便最終檔案與你選擇的
  輸出格式匹配。
- **Vertex AI 尚未支援 TTS** — 即使你的 LLM 頁籤設定為 Vertex，
  Gemini TTS 仍然需要 Developer API 密鑰。如果缺失，應用會預先拋出
  `AUTH_ERROR`。

## ElevenLabs 模型

公開了三個模型：

| 模型 | 延遲 | 品質 | 用於 |
|---|---|---|---|
| `eleven_multilingual_v2`（預設） | 中等 | 高 | 通用 TTS |
| `eleven_v3` | 中等 | 最高 | 錄音室 / 制作 |
| `eleven_flash_v2_5` | 低 | 良好 | 即時 / Live 模式 |

在**設定 → 語音 → ElevenLabs 模型**中設定。

## 提示

!!! tip "重新生成"
    右鍵點擊行 → **重新生成**以交換語音性別 / TTS 方法 / 格式，無需
    重新執行翻譯。

!!! tip "預檢查"
    頁面在開始前驗證 ElevenLabs API 密鑰（選擇時）和 FFmpeg 可用性。
    如果缺少什麼，你會看到一個友好的對話方塊。

!!! warning "Stop 是原子的"
    在合成期間按**Stop**，你不會在輸出目錄中得到一個寫到一半的 MP3
    — 檔案首先被寫入臨時位置，然後只在成功時移到位置。

## 快速鍵

| 快速鍵 | 操作 |
|---|---|
| `Ctrl+Enter` | 生成 |
| `Ctrl+O` | 瀏覽 |
| `Ctrl+F` | 聚焦歷史搜尋 |
