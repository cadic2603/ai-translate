---
description: Windows、macOS、Linux でビルド済みバイナリまたはソースから AI Translate をインストール — Python、FFmpeg、オプションの LibreOffice セットアップを網羅。
---

# インストール

## 必要なもの

- **Python 3.12 以降** ([ダウンロード](https://www.python.org/downloads/))
- **[uv](https://docs.astral.sh/uv/)** — 高速な Python パッケージマネージャ。インストール:

    === "macOS / Linux"
        ```bash
        curl -LsSf https://astral.sh/uv/install.sh | sh
        ```

    === "Windows"
        ```powershell
        powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
        ```

- **LLM API キー** — 以下のいずれか:
    - [Google Gemini](https://aistudio.google.com/apikey)(無料枠あり — 始めるのに推奨)
    - 任意の OpenAI 互換エンドポイント(OpenAI、プロキシ経由の Anthropic、ローカル Ollama / LM Studio など)

## オプション、ただしより多くの機能を解放

| ツール | 使用場所 | 必要な時 |
|---|---|---|
| **FFmpeg** ([ダウンロード](https://ffmpeg.org/download.html)) | 字幕、音声、吹き替え、ライブ | 任意の音声/動画ワークフロー |
| **LibreOffice** ([ダウンロード](https://www.libreoffice.org/download/)) | Linux/macOS の Office フォーマット | レガシー `.doc` / `.xls` / `.ppt` の翻訳、または MS Office がインストールされていない時の任意の Office ファイル |
| **Tesseract** ([インストールガイド](https://tesseract-ocr.github.io/tessdoc/Installation.html)) | OCR エンジン(デフォルト) | テキスト抽出ページ、スキャン PDF 翻訳、埋め込み画像翻訳 |
| **MS Office** + **pywin32** | Windows の Office | Windows での最高忠実度の Office 翻訳 |

これらなしでも AI Translate をインストールできます — 必要な機能は
失敗する前に通知してくれます。

## セットアップ

```bash
git clone https://github.com/cadic2603/ai-translate.git
cd ai-translate
uv sync
```

これでデスクトップアプリ、CLI、MCP サーバーを実行するのに必要なすべてが
インストールされます。

## 実行

=== "デスクトップアプリ"
    ```bash
    uv run python -m src.main
    ```

=== "コマンドライン"
    ```bash
    uv run ait --version
    ```

=== "MCP サーバー"
    ```bash
    uv run ait-mcp           # stdio トランスポート(Claude Desktop / Code 用)
    ```

## API キーを追加

デスクトップアプリを最初に開いた時:

1. サイドバーの **設定** をクリック
2. **LLM** タブを開く
3. **Google Gemini API キー** を貼り付け(または OpenAI 互換のカスタム
   プロバイダーを設定)。エンタープライズユーザーは Gemini を
   **Vertex AI モード** に切り替えられます — GCP プロジェクトと
   リージョンを指定し、オプションでサービスアカウント JSON パスを提供;
   詳細は [LLM プロバイダー](../setup/llm-providers.md) を参照。
4. デフォルトモデルを選択 — 任意の現行 Flash バリアント
   (例: `gemini-2.5-flash`)が手堅い無料の出発点。Pro バリアントは
   高コストでより良い品質を提供。
5. 設定を閉じる — 完了

キーはディスク上のプレーンテキストではなく **OS キーチェーン**
(macOS Keychain、Windows Credential Manager、Linux の GNOME / KDE
Secret Service)に保存されます。

!!! tip "ヘッドレス / サーバーインストール"
    キーをセットアップするのにデスクトップアプリを実行できない場合、
    keychain CLI コマンドについて
    [LLM プロバイダー](../setup/llm-providers.md) を参照。

## 次へ:試してみる

[5 分の最初の翻訳 →](first-translation.md){ .md-button .md-button--primary }
