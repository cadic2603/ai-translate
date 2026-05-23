---
description: Vision OCR、Speech-to-Text、Text-to-Speech のために Google Cloud を AI Translate に接続 — API キーをセットアップし、関連サービスを有効化。
---

# Google Cloud（Vision OCR / Speech-to-Text / Text-to-Speech）

1 つの Google Cloud API キーで 3 つのオプションバックエンドを駆動：

- **Vision OCR** — 有料 OCR エンジン（月 1,000 回無料）
- **Speech-to-Text v1** — 有料 STT（月 60 分無料）
- **Text-to-Speech v1** — 有料 TTS（WaveNet で月 1 M 文字無料）

実際に使用する API のみを有効化する必要があります。

## API キーを取得

1. [Google Cloud プロジェクトを作成](https://console.cloud.google.com/projectcreate)
2. API ライブラリを開く：<https://console.cloud.google.com/apis/library>
3. いずれかを有効化：
    - [Vision API](https://console.cloud.google.com/apis/library/vision.googleapis.com)
    - [Speech-to-Text API](https://console.cloud.google.com/apis/library/speech.googleapis.com)
    - [Text-to-Speech API](https://console.cloud.google.com/apis/library/texttospeech.googleapis.com)
4. [API キーを作成](https://console.cloud.google.com/apis/credentials)：
   **+ Create Credentials → API key** をクリック
5. キーをコピー（`AIza...` のように見える）。

!!! tip "キーを制限"
    API キーの詳細ページで、**API restrictions** の下で、有効化した
    API のみにキーを制限します。そうすれば、漏洩したキーが、使用する
    意図がなかったサービスで請求を蓄積することはできません。

## アプリで構成

**設定 → サービス**で：

1. **Google Cloud API キー** に貼り付け → **保存**

この 1 つのキーが今、3 つのすべての Google サービスで利用可能になり
ました。

## 各サービスを有効化

### Vision OCR

**設定 → OCR → OCR メソッド = Google Cloud OCR**で。

これだけです — サービスからの同じキーを使用します。

### Speech-to-Text

**設定 → 字幕 → STT メソッド = Google Cloud**（字幕 / 音声ページ用）
または**設定 → Live → STT メソッド = Google Cloud**（Live ページ用）
で。

**設定 → 字幕 → Google STT モデル**で、認識モデルを選択：

| モデル | 最適 |
|---|---|
| `latest_long`（デフォルト） | 長尺オーディオ（インタビュー、講義） |
| `latest_short` | 音声コマンド、短いフレーズ |
| `phone_call` | 電話オーディオ（8 kHz） |
| `medical_dictation` / `medical_conversation` | 医療ドメインのオーディオ |

### Text-to-Speech

**設定 → 音声 → TTS メソッド = Google Cloud TTS**で。

デフォルトでは、サーバーが言語と性別に基づいて音声を選択します — それ
がほとんどのユーザーが必要とするすべてです。特定の Google 音声を
固定すること（例：`en-US-Chirp3-HD-Charon`、`vi-VN-Wavenet-A`）は
エンジンによってサポートされていますが、まだ設定フィールドとして
公開されていません；`voice/google_tts_voice_name` を `settings.ini`
で直接編集して設定できます。音声 ID は
<https://cloud.google.com/text-to-speech/docs/voices> にリスト
されています。

## よくあるエラー

| エラー | 考えられる原因 |
|---|---|
| `AUTH_ERROR` | 間違った / 期限切れのキー。設定 → サービスで再貼り付け。 |
| `API not enabled` | この Cloud プロジェクトで特定の API（Vision / Speech / TTS）を有効化していません。 |
| `QUOTA_ERROR` | この API の無料層制限に達しました。待つか、課金をアップグレードしてください。 |
| `INVALID_ARGUMENT_ERROR` | 選択した言語に音声名が存在しません。 |

## コストガード

!!! warning
    3 つの Google API はすべてポストペイドです — 無料層を超えると、
    停止せずに請求が始まります。大量作業を行う前に、Cloud プロジェクト
    で[予算アラート](https://console.cloud.google.com/billing/budgets)
    を設定してください。
