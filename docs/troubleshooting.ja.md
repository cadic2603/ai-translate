---
description: AI Translate の問題を診断 — 不足しているフォント、FFmpeg エラー、LibreOffice コンバーターの問題、OCR セットアップの失敗、LLM API 認証。
---

# トラブルシューティング

一般的なエラー、その意味、修正方法。

## セットアップエラー

### "LLM is not configured"

API キーをまだ追加していません。デスクトップアプリを開く →
**設定 → LLM** → キーを貼り付け。完全なガイドは
[LLM プロバイダー](setup/llm-providers.md) を参照。

### `AUTH_ERROR`

LLM API キーが間違っているか期限切れ。

- **Gemini** — <https://aistudio.google.com/apikey> で新しいキーを
  生成、**設定 → LLM** に再貼り付け。
- **カスタムプロバイダー** — キーが有効か確認(同じ
  `Authorization: Bearer …` ヘッダーで手動でエンドポイントに curl)。
  エンドポイントが移動した場合、**API endpoint** フィールドも更新。

### `QUOTA_ERROR`

無料枠または有料プランの制限に達しました。

- **Gemini 無料枠** — 1 日のリクエストクォータはモデルによって
  異なります(<https://ai.google.dev/gemini-api/docs/rate-limits> 参照)。
  1 日待つか、有料にアップグレード。
- **OpenAI / その他** — 課金ダッシュボードを確認。多くのプロバイダーは
  到達するとリクエストを一時停止する "spend cap" を持っています。

### `MODEL_NOT_FOUND`

選択したモデル名が利用できません。

- カスタムプロバイダー — モデルが **設定 → LLM** のカンマ区切りの
  **Models** リストに含まれていることを確認。
- 組み込み Gemini リスト — **設定 → LLM → デフォルト Gemini モデル**
  でドキュメント化されたモデルに切り替え。

### `VISION_NOT_SUPPORTED`

非ビジョンモデルを選択して、画像 / スキャン PDF を翻訳しようと
しました。名前に `flash`、`pro`、または `vision` を含むモデルに
切り替え(例:OpenAI の `gpt-4o`、Gemini の任意の現行 Gemini
Flash または Pro バリアント)。

## 音声 / 動画エラー

### `FFMPEG_NOT_FOUND`

FFmpeg が PATH にありません。あなたの OS のインストールコマンドは
[FFmpeg セットアップ](setup/ffmpeg.md) を参照。

MCP サーバーはこれを次のように再ラップします:*"FFmpeg is required
to decode this audio/video file but is not installed or not on PATH."*

### Live ページに字幕が表示されない

- **間違った音声ソース** — **設定 → Live → 音声ソース** を開いて、
  実際に欲しいもの(マイク / システム / 両方)と一致することを確認。
- **マイクミュート** — OS のサウンド設定を確認;アプリはデフォルト
  入力デバイスを使用。
- **システム音声未設定** — macOS / Windows ループバック手順は
  [システム音声キャプチャ](setup/system-audio.md) を参照。

### 音声出力が無音 / 空

- **キーなしの ElevenLabs** — Voice ページがフレンドリーな pre-flight
  ダイアログを表示;すり抜けた場合、ファイルは空バイトかも。
  **設定 → Service → ElevenLabs API key** を確認。
- **Edge TTS ネットワークエラー** — Edge TTS にはインターネットが必要;
  ファイアウォールが `speech.platform.bing.com` をブロックしている場合、
  ElevenLabs、Google Cloud TTS、または **Piper TTS**(完全オフライン)
  に切り替え。

### "Piper voice not installed" ダイアログ

Voice / Dubbing / Translate Text ページは、worker が起動する前に
ターゲット言語の Piper 音声がディスク上にあるか pre-flight で
チェックします。ない場合、**設定を開く** ボタン付きのモーダルが
表示されます。

音声をダウンロード:

1. ダイアログの **設定を開く** をクリック(または **設定 → 音声**
   を手動で開く)。
2. **TTS 方法** が **Piper TTS** に設定されていることを確認。
3. **今すぐ音声をダウンロード** をクリックして音声ライブラリ
   ダイアログを開く。
4. ターゲット言語の行を見つけ、隣の **Female voice** または
   **Male voice** をクリック。音声は HuggingFace からダウンロードされる
   ~25–60 MB の ONNX ファイル;言語ごとに 1 回。
5. ダイアログを閉じて、翻訳 / voice / dub ジョブを再実行。

ターゲット言語がリストにない場合、Piper カバレッジがありません —
エンジンは合成時に静かに Edge TTS にフォールバックするので、
実際には何もダウンロードする必要はありません。今日 Piper 音声がない
13 言語:ベラルーシ語、ベンガル語、中国語(繁体)、クロアチア語、
エストニア語、ヘブライ語、日本語、クメール語、韓国語、リトアニア語、
マレー語、モンゴル語、タイ語。

**ライブ翻訳** ページはこのダイアログを *表示しない* 唯一の場所 —
モーダルでライブストリームを中断するのはフォールバックよりも悪いので、
そこでの音声欠落のケースは静かに Edge TTS に向かいます。

## ドキュメント翻訳エラー

### PDF 翻訳が特定のページで失敗

PDF はページごとのチェックポイントを使用 — 成功したページは
やり直されません。失敗したページは `app.log` にスタックを記録;
よくある犯人:

- ページが **テキストレイヤーのないスキャン** で OCR が未設定。
  **設定 → OCR** をセットアップ(参照:
  [OCR エンジン](setup/ocr-engines.md))。
- ページが LLM が壊した **複雑な数学レイアウト** を含む。より強い
  モデルを試す(Flash ではなく Pro バリアント)。

### Office 翻訳がフォーマットを破壊

- **モダンフォーマット**(`.docx`、`.xlsx`、`.pptx`)— フォーマットは
  HTML ラウンドトリップ経由で run ごとに保持。出力に迷子の `<b>`
  タグがある場合、LLM がそれらを閉じませんでした — より強いモデルで
  再実行。
- **レガシーフォーマット**(`.doc`、`.xls`、`.ppt`)— はるかに
  良い忠実度のために **設定 → 翻訳 → Auto-convert legacy** を有効化。
  パイプラインはまず `.docx` に変換、翻訳、再変換します。

### 翻訳キューがバッチの途中で停止

アプリを終了してデータベースを確認:

```bash
sqlite3 ~/.local/share/ai-translate/translator.db \
  "SELECT id, status, error_code, file_name FROM history WHERE status NOT IN ('Done', 'Failed') ORDER BY created_at DESC LIMIT 10;"
```

数分間タッチされていない `Translating` 行は worker が静かに
クラッシュしたことを意味します。デスクトップアプリを再起動 —
起動時に Pending / Translating タスクを自動再開します。

## 横断的な問題

### 一度に複数のファイルが静かに 1 つとして翻訳される

一度に 1 つのファイルをドロップ、または、キューヘッダーの
**Files** 列を確認 — ドロップした数を表示するはず。
100 ファイルキャップは超過時に通知を表示。

### サイドバーがスピナーを永遠に表示

worker がまだ実行中とフラグされていることを示します。アプリを
クリーンに終了(SIGKILL なし)— autouse クリーンアップフックが
フラグをリセット。SIGKILL が状態をスタックさせた場合、DB worker
を手動でクリア:

```bash
sqlite3 ~/.local/share/ai-translate/translator.db \
  "UPDATE history SET status='Failed', error_code=99 WHERE status IN ('Pending', 'Translating');"
```

### ログはどこ? {: #where-are-the-logs }

| OS | パス |
|---|---|
| **Linux** | `~/.local/state/log/ai-translate/app.log` |
| **macOS** | `~/Library/Logs/ai-translate/app.log` |
| **Windows** | `%LOCALAPPDATA%\ai-translate\logs\app.log` |

ログはコンソールの詳細度に関係なく常に DEBUG+ をキャプチャ。
コンソール出力はデフォルトで INFO+;完全なファイルログを stdout に
ミラーするには CLI に `--verbose` を渡す。

## まだスタック?

- 設計レベルの質問は [FAQ](faq.md) を参照。
- <https://github.com/cadic2603/ai-translate/issues> で issue を
  ファイル:OS、Python バージョン、失敗したコマンド、`app.log` の
  関連スライス、期待していたものの説明。
