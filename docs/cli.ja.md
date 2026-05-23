---
description: ait コマンドラインインターフェイスを使ってヘッドレスでファイルを翻訳 — スクリプトや CI ジョブから PDF、Office ドキュメント、字幕、45+ 言語をサポート。
---

# コマンドライン (`ait`)

ヘッドレス翻訳 — デスクトップアプリと同じパイプライン、ディスプレイ不要。
CI、バッチジョブ、サーバー、スクリプト化されたワークフローに役立ちます。

## クイックスタート

```bash
ait report.docx --target French
```

出力はソースの隣に `report_translated_<src>_<tgt>.docx` として配置されます。

## 一般的なレシピ

### 複数ファイル

```bash
ait *.pdf --target Japanese
```

Glob 展開はシェルの仕事(Unix)。Windows / `cmd.exe` では、
ファイルを明示的にリストするか PowerShell を使用:

```powershell
ait (Get-ChildItem *.pdf) --target Japanese
```

### カスタム出力ディレクトリ

```bash
ait report.docx --target French --output ./translated/
```

ディレクトリは存在しない場合作成されます。作成できない場合
(権限拒否など)、明確なエラーと終了コード 2 — 中途半端な実行はありません。

### ソース言語を指定

```bash
ait letter.txt --target German --source "English (US)"
```

ソースマッチングは大文字小文字を区別しません。"Chinese" だけだと
ヒントを表示:

```bash
ait letter.txt --target Chinese
# Error: unknown target language 'Chinese'.
# Did you mean one of: Chinese (Simplified), Chinese (Traditional)?
```

### 特定のモデルを選択

```bash
ait big-doc.pdf --target French --model "Gemini:gemini-2.5-pro"
# またはデスクトップアプリの LLM タブに登録された他の Provider:model_name。
```

フォーマットは厳密に `Provider:model_name`。コロン欠落 → デフォルト
Gemini モデルにサイレントにフォールバックする代わりに明確なメッセージで終了 2。

### Office オプション

```bash
ait deck.pptx --target Vietnamese \
    --translate-images \
    --translate-comments \
    --translate-shapes \
    --translate-notes
```

`--translate-images` には設定済み OCR が必要です(参照:
[OCR エンジン](setup/ocr-engines.md))。

### レガシーフォーマットの自動変換

```bash
ait old-doc.doc --target French --convert-legacy
```

パイプラインはまず `.doc` → `.docx` を変換(より良い忠実度)、
モダンなコピーを翻訳、再変換します。`--convert-odf` と
`.odt` / `.ods` / `.odp` も同様。

### 静か / 詳細

```bash
ait report.docx --target French --quiet      # エラーのみ
ait report.docx --target French --verbose    # 完全な DEBUG ストリーム
```

デフォルトモードはバナーとタスクごとの進捗を stderr に出力;
完全な詳細(HTTP body ダンプ、retry ログ)はコンソールの詳細度に
関係なくプラットフォームのアプリログディレクトリに入ります(あなたの
OS のパスは
[トラブルシューティング → ログはどこ?](troubleshooting.md#where-are-the-logs)
を参照)。

### サポートされている言語をリスト

```bash
ait --list-languages
```

サポートされている全 45 言語を出力。シェルループへのパイピングに便利。

### バージョン

```bash
ait --version
# ait 0.1.0
```

## 終了コード

| コード | 意味 |
|---|---|
| `0` | すべてのタスクが成功 |
| `2` | 引数エラー(未知の言語、ターゲット欠落、不正な形式のモデル、書き込み不可の出力、サポートされていないファイル拡張子) |
| `3` | LLM が設定されていない |
| `4` | 部分的な失敗(一部成功、一部失敗) |
| `5` | すべて失敗 |
| `130` | 中断 (`Ctrl+C`) |

## キャンセル

`Ctrl+C` 一回 — 協調的キャンセル。現在のタスクのチェックポイントが
保存され、パイプラインは次のポーリング境界でクリーンに終了します。

`Ctrl+C` もう一回 — ハード割り込み。控えめに使用;部分ファイルが
書きかけ状態で残る可能性があります。

## 完全なフラグリファレンス

```bash
ait --help
```

各フラグとそのデフォルトを表示。同じ内容をここに要約:

| フラグ | デフォルト | メモ |
|---|---|---|
| `--target / -t LANG` | _必須_ | 大文字小文字を区別しない |
| `--source / -s LANG` | 自動検出 | 大文字小文字を区別しない |
| `--output / -o DIR` | ソースの親 | 欠落時作成 |
| `--model / -m PROVIDER:MODEL` | デスクトップデフォルト | 厳密フォーマット |
| `--ocr-method METHOD` | `TesseractOCR` | `Tesseract`、`EasyOCR`、`Google Cloud OCR` |
| `--translate-images` | オフ | 設定済み OCR が必要 |
| `--translate-comments` | オフ | Office コメント |
| `--translate-shapes` | オフ | 図形 / テキストボックス |
| `--translate-notes` | オフ | PowerPoint 発表者ノート |
| `--translate-sheet-names` | オフ | Excel シートタブ |
| `--convert-legacy` | オフ | `.doc`/`.xls`/`.ppt` → モダンフォーマット |
| `--convert-odf` | オフ | `.odt`/`.ods`/`.odp` → OOXML |
| `--keep-history` | オフ | 完了後に履歴エントリを保持 |
| `--quiet / -q` | オフ | コンソールでエラーのみ |
| `--verbose / -v` | オフ | DEBUG ストリーム |
| `--list-languages` | — | 45 言語を出力して終了 |
| `--version` | — | バージョンを出力して終了 |

## ヒント

!!! tip "一度設定すれば、どこでも使用"
    CLI は API キーと設定をデスクトップアプリと共有 — GUI で一度
    すべて設定し、そこから `ait` で自動化。

!!! tip "コールドスタート endpoint キャッシュ"
    各 `(エンドポイント、モデル)` ペアについて、
    chat-vs-responses-API 選択と動作する payload バリアントは OS
    キャッシュディレクトリ内の `llm_endpoint_cache.json` に永続化
    されます(Linux では `~/.cache/ai-translate/`、
    macOS では `~/Library/Caches/ai-translate/`、
    Windows では `%LOCALAPPDATA%\ai-translate\cache\`)。
    コールドスタート CLI 呼び出しは最初の成功した呼び出しの後、
    自動検出プローブを完全にスキップします — プロバイダー固有の
    payload チューニングが必要な Azure / vLLM / OpenRouter /
    Anthropic / DeepSeek デプロイメントに対してスクリプトを書く際に
    便利。キャッシュはマルチプロセスとマルチスレッドに対して安全
    (アトミックな rename 付き RLock 下での read-merge-write)。

!!! tip "出力ストリーム"
    デフォルトモードはバナー、キューに入ったタスクのリスト、タスク
    ごとの進捗を **stdout** に出力(エラーと正しくインターリーブ
    するように行バッファード);エラーメッセージとログレコードは
    **stderr** に。クリーンなパイピングのために stdout を完全に
    抑制するには `--quiet` と組み合わせ:

    ```bash
    ait --list-languages | grep -i japanese    # stdout のデータ
    ait file.txt --target French --quiet 2> errors.log
    ```
