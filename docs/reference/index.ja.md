---
description: AI Translate の Python API 開発者向けリファレンス — docstring から自動生成。core、utils、constants、CLI、MCP サーバーモジュールを網羅。
---

# 開発者リファレンス

エンドユーザーはこのセクションではなく、
[機能ページ](../index.md#headline-features)または
[セットアップガイド](../setup/llm-providers.md)を見たいはずです。

これは**自動生成された API リファレンス**です — `src/` 内の各 Python
モジュールごとに 1 ページ、プロジェクトの docstring から描画されます。
独自の Python コードから基盤関数を呼びたいコントリビュータや
インテグレータ向けに作成されています。

## ビルド対象

`uv run mkdocs build` はビルドのたびに `src/` からこれらのページを
再生成するため、常に最新のコードを反映します。

## どこから始めるか

ヘッドレス翻訳のエントリポイントは
[`run_translation_pipeline`](api/core/translator.md) です — デスクトップ
アプリ、CLI、MCP サーバーのすべての機能は最終的にここを通ります。
この関数と隣接する `TranslationConfig` を読むのが、パイプラインを理解する
最速の方法です。

## レイアウト

- **[Constants](api/constants/index.md)** — 設定キー、エラーコード、言語テーブル、i18n / テーマエンジン。
- **[Core](api/core/index.md)** — 翻訳パイプライン、LLM ディスパッチ、フォーマット別プロセッサ、OCR / STT / TTS エンジン、チェックポイント、データベース。
- **[Utils](api/utils/index.md)** — 横断的なヘルパー。
- **[CLI](api/cli.md)** — `ait` エントリポイント。
- **[MCP Server](api/mcp_server.md)** — `ait-mcp` エントリポイント。
