---
description: AI Translate が macOS と Linux でレガシー Office 形式（.doc、.xls、.ppt）と ODF ファイル（.odt、.ods、.odp）を翻訳できるよう LibreOffice をインストール。
---

# LibreOffice（Office 形式）

Office 翻訳パイプラインは、次の順序で利用可能な最高のバックエンドを
選択します：

1. **win32com**（Windows + MS Office インストール済み）— 最高の忠実度
2. **LibreOffice UNO**（クロスプラットフォーム）— win32com がない
   ときのフォールバック
3. **python-docx / openpyxl / python-pptx**（モダン形式のみ）—
   上記のいずれも使用できないときのピュア Python フォールバック

LibreOffice は Linux と macOS でのレガシー `.doc` / `.xls` / `.ppt`
の**唯一の方法**であり、それらのプラットフォームでモダン Office 形式
にも推奨される方法です（ピュア Python バックエンドより優れた忠実度、
特にテーブルと埋め込みオブジェクト用）。

## インストール

=== "macOS"
    ```bash
    brew install --cask libreoffice
    ```

    または <https://www.libreoffice.org/download/download/> から
    ダウンロード。

=== "Ubuntu / Debian"
    ```bash
    sudo apt install libreoffice
    ```

=== "Fedora / RHEL"
    ```bash
    sudo dnf install libreoffice
    ```

=== "Windows"
    Windows のデスクトップアプリは通常、MS Office インストール済み
    の **win32com** を使用します — LibreOffice は MS Office が
    ないときの*フォールバック*です。
    <https://www.libreoffice.org/download/download/> からインストール。

## 検証

```bash
soffice --version
```

macOS で "command not found" が表示される場合、バイナリは
`/Applications/LibreOffice.app/Contents/MacOS/soffice` にあります。
アプリは一般的なインストールパスを通じて自動検出しますが、必要に
応じて **設定 → 一般 → LibreOffice パス** で上書きできます。

## 何を強化するか

LibreOffice がアクティブなバックエンドの場合：

| 機能 | 注 |
|---|---|
| **モダン Office**（`.docx`、`.xlsx`、`.pptx`） | win32com が使用できないときにフォールバックとして使用 |
| **レガシー Office**（`.doc`、`.xls`、`.ppt`） | 必須 — 純粋な Python はこれらを読めません |
| **ODF**（`.odt`、`.ods`、`.odp`） | **ODF を自動変換**がオンのときラウンドトリップ変換に使用 |
| **レガシー / ODF → OOXML 自動変換** | 必須 |

## バックグラウンドプロセス

LibreOffice が初めて必要になると、アプリはヘッドレスモードで
`soffice` プロセスを生成し、翻訳全体で生かしておきます
（`office_lifecycle.py`）。アプリ終了時に自動的にシャットダウンし
ます。

## 注意事項

!!! warning "初回起動時間"
    LibreOffice にヒットする最初の翻訳は、`soffice` が起動するまで
    ~5-10 秒待ちます。後続の翻訳は同じプロセスを再利用し、高速です。

!!! info "JVM クラッシュログ"
    LibreOffice の Java コンポーネントは、segfault 時に時々
    `hs_err_pid*.log` ファイルを生成します。アプリは、プロジェクト
    フォルダを汚染しないよう、それらを一時ディレクトリにルーティング
    します。

!!! tip "レガシー / ODF 自動変換"
    日常的に `.doc` / `.xls` / `.ppt` を翻訳する場合は、**設定 →
    翻訳 → レガシーを自動変換**を有効にします。パイプラインはまず
    それらを `.docx` / `.xlsx` / `.pptx` に変換（`convert_to_modern_format`
    経由）、モダンコピーを翻訳、次に変換し戻します。忠実度はレガシー
    形式を直接翻訳するよりもはるかに高いです。
