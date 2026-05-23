---
description: AI Translate が字幕生成、音声合成、ビデオダビングのためにオーディオとビデオをデコードできるよう FFmpeg をインストール — メディア機能に必要。
---

# FFmpeg

FFmpeg はあらゆるオーディオ / ビデオワークフローに必要です：

- **字幕を生成** — STT 用にソースオーディオをデコード
- **音声を生成** — タイミングのある TTS クリップを 1 つのファイルに結合
- **ダビング** — STT → TTS → ビデオに mux back
- **ライブ翻訳** — システムオーディオキャプチャが `parec` を経由する
  とき

バンドルされていません — システムに 1 回インストールしてください。

## インストール

=== "macOS"
    ```bash
    brew install ffmpeg
    ```

=== "Ubuntu / Debian"
    ```bash
    sudo apt update && sudo apt install ffmpeg
    ```

=== "Fedora / RHEL"
    ```bash
    sudo dnf install ffmpeg
    ```

    または、より完全なビルドには、最初に
    [RPM Fusion](https://rpmfusion.org/Configuration)を有効に
    してください。

=== "Arch / Manjaro"
    ```bash
    sudo pacman -S ffmpeg
    ```

=== "Windows"
    <https://www.gyan.dev/ffmpeg/builds/> から静的ビルドをダウンロード
    （"release essentials" ビルドで OK）、解凍し、`bin/` フォルダを
    PATH に追加：

    1. **Win + R** を押し、`sysdm.cpl` と入力、**Enter** を押す
    2. **詳細 → 環境変数 → システム変数 → Path → 編集**
    3. **新規** → FFmpeg の `bin` フォルダの絶対パスを貼り付け
    4. すべて **OK**、開いているターミナルを再起動

## 検証

```bash
ffmpeg -version
```

設定行に `--enable-libx264 --enable-libvpx` を含むバージョンバナーが
表示されるはずです。"command not found" が表示される場合、インス
トールが PATH に至っていません。

## アプリ内プリフライトチェック

音声 / ダビングページは作業開始前に `shutil.which("ffmpeg")` を呼び
出します。FFmpeg が見つからない場合、半分実行されたタスクではなく、
ここに戻るリンクのあるフレンドリーなエラーダイアログが表示されます。

## よくあるエラー

| エラー | 意味 |
|---|---|
| `FFMPEG_NOT_FOUND` | ページが実行を試みた時点で `ffmpeg` が PATH にありません。インストール（上記）してアプリを再起動してください。 |

MCP サーバー（`ait-mcp`）では、同じエラーが人間が読めるメッセージに
再ラップされます：

> *「このオーディオ/ビデオファイルをデコードするには FFmpeg が
> 必要ですが、インストールされていないか PATH にありません。FFmpeg
> をインストールして再試行してください。」*
