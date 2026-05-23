---
description: ライブ翻訳のためのクロスプラットフォーム・マイク音声キャプチャ。
---

# PortAudio のセットアップ (マイク)

[ライブ翻訳](../features/live-translation.md) 機能は Python パッケージの `sounddevice` を使用します。これは、すべてのオペレーティングシステムでマイクデバイスにアクセスするために PortAudio C ライブラリに依存しています。ほとんどのユーザーは、このシステムレベルの依存関係をインストールする必要があります。

## Windows
`sounddevice` や `PyAudio` 用のコンパイル済み wheel は、通常 Windows 上で PortAudio バイナリをバンドルしています。通常、手動でのシステム全体のインストールは必要ありません。エラーが発生する場合は、オーディオドライバーが最新であることを確認してください。

## macOS
Homebrew を使用して PortAudio をインストールします:

```bash
brew install portaudio
```

## Linux
パッケージ名はディストリビューションによって異なります。コンパイル済みの wheel が利用できない場合、Python が C バインディングを構築できるように、開発パッケージ (通常は `-dev` または `-devel` で終わる) をインストールする必要があります。

=== "Ubuntu / Debian / Mint"

    ```bash
    sudo apt-get install portaudio19-dev
    ```

=== "Fedora / RHEL"

    ```bash
    sudo dnf install portaudio-devel
    ```

=== "Arch Linux"

    ```bash
    sudo pacman -S portaudio
    ```

## トラブルシューティング

インストール後もアプリケーションがマイクにアクセスできないと報告し続ける場合:

1. ターミナルアプリケーション (またはデスクトップ環境) にマイクへのアクセス権限があることを確認してください (特に macOS の場合)。
2. 新しいライブラリパスを取得できるように、アプリケーション (またはターミナル/MCP サーバー) を再起動します。
