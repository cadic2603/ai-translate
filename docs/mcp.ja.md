---
description: AI Translate を Model Context Protocol ツールとして公開し、Claude Desktop、Claude Code、その他の MCP クライアントがテキスト、ファイル、音声を翻訳できるようにします。
---

# MCP サーバー (`ait-mcp`)

翻訳パイプラインを **Model Context Protocol** ツールとして公開し、
Claude Desktop や Claude Code のような AI エージェントが直接駆動できる
ようにします — 「この PDF をフランス語に翻訳して」がコピー&ペースト
ではなくツール呼び出しになります。

## 公開されるもの

9 つのツール:

| ツール | 目的 |
|---|---|
| `translate_text` | 文字列のリストを翻訳 |
| `translate_document` | ファイル翻訳タスクをキューイング(タスク ID を返す) |
| `get_task_status` | タスクのステータスをポーリング |
| `cancel_task` | 実行中タスクの協調的キャンセル |
| `extract_image_text` | OCR または LLM ビジョン |
| `transcribe_audio` | 音声 → SRT |
| `synthesize_speech` | テキスト → MP3 / WAV |
| `query_glossary` | 用語集セット / エントリのリスト |
| `list_languages` | サポートされる全 45 言語 |

## サーバーを実行

```bash
ait-mcp                       # stdio トランスポート(デスクトップエージェントのデフォルト)
ait-mcp --transport sse       # Web クライアント用の Server-Sent Events
ait-mcp --transport sse --port 9000
```

`stdio` は SSE を明示的に配線していない限り、すべての MCP
クライアントが期待するものです。

## Claude Desktop に追加

1. Claude Desktop を開く → **Settings → Developer → Edit Config**
2. `mcpServers` の下にこのエントリを追加:

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

    `/absolute/path/to/ai-translate` をクローンしたリポジトリのパスに置き換えてください。

3. Claude Desktop を終了して再度開きます。ハンマーアイコンには
   「ai-translate」がすべての 9 ツールと共に表示されるはずです。試してみる:

    > 「この PDF (`/home/me/report.pdf`) をフランス語に翻訳して — 出力をソースの隣に保存して。」

## Claude Code に追加

`~/.config/claude-code/mcp_servers.json`(または Claude Code 内から
`claude mcp add`):

```json
{
  "ai-translate": {
    "command": "uv",
    "args": ["run", "--project", "/absolute/path/to/ai-translate", "ait-mcp"]
  }
}
```

Claude Code を再起動。同じ 9 ツールが呼び出し可能になります。

## 他の MCP クライアントに追加

MCP 互換のクライアントは類似の形を取ります:

- **Command** — `uv run --project /path/to/ai-translate ait-mcp`
- **Transport** — stdio(デフォルト)

HTTP / SSE ベースのクライアントの場合、
`ait-mcp --transport sse --port 9000` を実行し、クライアントを
`http://localhost:9000` に向けます。

## 検証保証

各ツールはエラー時に同じ形を返すので、エージェントは失敗を一貫して
処理できます:

| 不正な入力 | ツール応答 |
|---|---|
| 未知の言語 | `ValueError: Unknown … language '<input>'. Call list_languages to see supported values.` |
| LLM 未設定 | `RuntimeError: LLM is not configured. Run the desktop app and set up your API key…` |
| サポートされないファイルタイプ | 許可された拡張子をリストする `ValueError` |
| 不正な形式の `model="…"` (`:` なし) | デフォルトを暗黙的に使用する代わりに `ValueError` |
| `cancel_task` の未知のタスク ID | `unknown` 配列で返される — エラーなし |
| `transcribe_audio` で FFmpeg がない | `RuntimeError: FFmpeg is required…`(エンジンの生の `FFMPEG_NOT_FOUND` タグから再ラップ) |

これらのツールを呼び出すエージェントは、これらの契約に頼ることができます。

## 並行性

`translate_document` はパイプラインをデーモンスレッドで実行します。
各バッチは独自のキャンセルイベントを取得するので、1 つのバッチを
キャンセルしても他のバッチには影響しません。MCP サーバーはプロセス
ローカルマップでアクティブなパイプラインを追跡します(パイプライン
終了時に自動クリーンアップ)。

## ユースケース

- **「このコードベースのドキュメントをベトナム語に翻訳して」** —
  エージェントを docs フォルダに向けると、`translate_document` 呼び出し
  をバッチ化し、それぞれが終了するまで `get_task_status` をポーリング
  します。
- **「どの言語をサポートしていますか?」** — エージェントは
  `list_languages` を呼び出し、応答を読みます。
- **「この日本語のレシートを翻訳して」** — エージェントは写真に対して
  `extract_image_text` を呼び出し、結果に対して `translate_text` を呼び出します。
- **「この Zoom 録画用のベトナム語字幕を生成して」** — エージェントは
  ソース言語の SRT を取得するために `transcribe_audio` を呼び出し、
  ローカライズするために各 cue に対して `translate_text` を呼び出し、
  SRT を再構築します。

!!! note "ビデオダビングは MCP ツールではない"
    完全な STT → 翻訳 → TTS → mux パイプライン(デスクトップアプリの
    **ダビング** ページ)は現在 GUI 経由でのみ利用可能です。MCP からは、
    `transcribe_audio` + `translate_text` + `synthesize_speech` で
    自分で同等のものを構成できますが、タイミングを意識した mux ステップ
    (FFmpeg)を外部で処理する必要があります。

## ヒント

!!! tip "一度設定すれば、エージェントはどこでも動作"
    MCP サーバーは API キーと設定をデスクトップアプリと CLI と共有
    します。GUI で LLM / OCR / TTS を一度設定すれば、`ait-mcp` と
    通信するエージェントは同じセットアップを継承します。

!!! tip "コールドスタート endpoint キャッシュ"
    各 `(エンドポイント、モデル)` ペアについて、chat-vs-responses-API
    の選択と動作する payload バリアントは OS キャッシュディレクトリ
    内の `llm_endpoint_cache.json` に永続化されます
    (Linux では `~/.cache/ai-translate/`、
    macOS では `~/Library/Caches/ai-translate/`、
    Windows では `%LOCALAPPDATA%\ai-translate\cache\`)。新しい
    `ait-mcp` プロセスは、最初の成功した呼び出し後、自動検出プローブを
    完全にスキップします — オンデマンドでサーバーをスポーンする
    エージェントは、各呼び出しでバリアント検出のラウンドトリップを
    支払いません。キャッシュはマルチプロセスとマルチスレッドに対して
    安全です(アトミックな rename を伴う RLock 下での
    read-merge-write)。

!!! tip "ツールごとのモデルピッカー"
    `translate_text` と `translate_document` ツールはオプションの
    `model` パラメーターを受け入れます — エージェントはユーザーが
    デスクトップアプリを再構成する必要なく、クイックターン用の高速
    モデルとプロダクション出力用のより重いモデルを選択できます。

!!! warning "長時間実行されるパイプライン"
    `translate_document` はタスク ID と共にすぐに返ります。エージェント
    は各タスクが `Done` または `Failed` に達するまで `get_task_status`
    をポーリングすることが期待されます。ツール呼び出し内で同期的に
    待機しないでください;それは MCP クライアントのタイムアウトが
    発火するリスクがあります。
