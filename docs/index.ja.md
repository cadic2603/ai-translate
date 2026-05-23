---
description: AI Translate は、45 以上の言語でドキュメント、PDF、字幕、音声、ライブ音声に対応する無料のクロスプラットフォームデスクトップ翻訳ツールです。
---

# AI Translate

**45 言語**を扱う無料のクロスプラットフォームデスクトップ翻訳ツール。
プレーンテキストをはるかに超えて — ドキュメント、音声、動画、ライブ音声、
スクリーンショットなどを、すべて単一の LLM 駆動パイプラインで翻訳します。

<div class="grid cards" markdown>

-   :material-cursor-default-click-outline:{ .lg .middle } **デスクトップアプリ**

    ---

    ファイルをドラッグ、ターゲット言語を選び、翻訳されたコピーを取得。
    ドラッグアンドドロップ、履歴、用語集、すべて。

    [:octicons-arrow-right-24: 5 分のウォークスルー](getting-started/first-translation.md)

-   :material-console:{ .lg .middle } **コマンドライン**

    ---

    `ait report.docx --target French` — 同じパイプライン、スクリプト化可能で
    ヘッドレス。CI、バッチジョブ、サーバーに役立ちます。

    [:octicons-arrow-right-24: CLI ガイド](cli.md)

-   :material-robot-outline:{ .lg .middle } **AI エージェント (MCP)**

    ---

    翻訳を Model Context Protocol ツールとして公開し、Claude Desktop、
    Claude Code、その他の MCP クライアントが直接呼び出せます。

    [:octicons-arrow-right-24: MCP セットアップ](mcp.md)

</div>

## 翻訳できるもの

| 種類 | フォーマット |
|---|---|
| **Office ドキュメント** | `.docx`、`.xlsx`、`.pptx`、`.odt`、`.ods`、`.odp`、レガシーの `.doc` / `.xls` / `.ppt` も |
| **PDF** | レイアウト保持の extract-overlay 翻訳、ブックマーク / フォーム / リンクの翻訳、スキャン用 OCR フォールバック |
| **テキスト & ウェブ** | `.txt`、`.md`、`.rst`、`.html` / `.htm` / `.xhtml`、`.xml`、`.rtf`、`.json`、`.csv`、`.epub` |
| **字幕** | `.srt`、`.vtt`、`.ass`、`.ssa` |
| **ローカライゼーション** | `.po`、`.pot`、`.xliff` / `.xlf`、`.yaml` / `.yml`、`.properties`、`.strings` |
| **画像** | `.png`、`.jpg`、`.jpeg`、`.bmp`、`.webp`、`.tiff`、`.tif`(OCR または LLM ビジョン) |
| **音声** | `.mp3`、`.wav`、`.m4a`、`.flac`、`.ogg`、`.aac`、`.wma` |
| **動画** | `.mp4`、`.webm`、`.mkv`、`.avi`、`.mov`、`.wmv`(完全な吹き替えパイプライン) |

## 主な機能 {: #headline-features }

- **[テキスト翻訳](features/translate-text.md)** — 自動検出、その場での編集、TTS 再生による即時 LLM 翻訳。右から左の言語(アラビア語、ヘブライ語、ペルシア語)はネイティブにレンダリングされます。
- **[ドキュメント翻訳](features/translate-document.md)** — ファイルをドロップし、タスクごとの進捗スピナーを観察し、翻訳されたコピーを並べて取得。RTL ターゲットは適切な bidi マークアップを取得;`Ctrl+P` / `Ctrl+G` でキューを一時停止・継続。
- **[字幕生成 (STT)](features/generate-subtitle.md)** — 音声 / 動画を SRT / VTT / ASS / SSA に文字起こし。
- **[音声生成 (TTS)](features/generate-voice.md)** — タイミング付きで字幕を MP3 / WAV に合成。
- **[動画吹き替え](features/dubbing.md)** — 完全な STT → 翻訳 → TTS → ソース動画へのミックスバック。
- **[ライブ翻訳](features/live-translation.md)** — マイクまたはシステム音声からのリアルタイム字幕オーバーレイ。
- **[テキスト抽出](features/extract-text.md)** — OCR または LLM ビジョン → `.txt` / `.docx`。
- **[用語集](features/glossary.md)** — 翻訳全体で一貫した用語を強制。

!!! tip "Gemini の Vertex AI モード"
    エンタープライズユーザーは **設定 → LLM** で Gemini 呼び出しを
    Developer API から **Vertex AI** に切り替えられます — GCP プロジェクトと
    リージョンを指定し、オプションでサービスアカウント JSON パスを提供。
    [LLM プロバイダー](setup/llm-providers.md#google-gemini-recommended-for-first-time-setup)
    を参照。

!!! tip "初めてですか?"
    [インストール](getting-started/installation.md) から始めて、次に
    [5 分の最初の翻訳ウォークスルー](getting-started/first-translation.md)。
    新規クローンから 10 分以内に翻訳ドキュメントが手に入ります。
