---
description: "翻訳のための LLM プロバイダーを構成：Google Gemini（推奨）、OpenAI 互換エンドポイント、または API キーを持つ任意のカスタムプロバイダー。"
---

# LLM プロバイダー

翻訳パイプラインは実際の翻訳のために Large Language Model を呼び出し
ます。1 つまたは複数を構成できます；機能ごとのモデルピッカーにより、
各ページが異なるものを使用できます。

## Google Gemini（初回設定に推奨） {: #google-gemini-recommended-for-first-time-setup }

無料層は寛大で、ほとんどの個人使用に十分です。

1. <https://aistudio.google.com/apikey> に移動
2. **Create API key** をクリック（Google アカウントでサインイン）
3. キーをコピー（`AIza...` のように見える）
4. デスクトップアプリで：**設定 → LLM → Gemini API キー** → 貼り付け
   → **保存**
5. **デフォルト Gemini モデル**ドロップダウンでデフォルトモデルを
   選択。Google のラインアップは次のようになる傾向があります：

    - **Flash** バリアント（例：`gemini-2.5-flash`）— 高速、寛大な
      無料層、良い品質。推奨される開始点。
    - **Pro** バリアント — 遅め、高品質、より高価。
    - **Flash-lite** — 最速、最も安く、低品質。

    利用可能な正確なモデル名は、Google があなたのアカウントに展開
    したものに依存します；バランスの取れたデフォルトのために名前
    に `flash` を含むものを選んでください。

完了。キーは OS のキーチェーンに保存され、平文ではありません。

### Vertex AI モード（エンタープライズ）

Gemini 構成ブロック内で、ラジオペアにより **Developer API** から
**Vertex AI** に切り替えることができます — 同じ Gemini モデル、
GCP アカウント経由で課金、組織レベルのコントロール（VPC-SC、監査
ログ、地域データレジデンシー）。

1. **設定 → LLM** で Gemini ラジオを **Developer API** から
   **Vertex AI** に切り替え
2. 入力：
    - **Project** — GCP プロジェクト ID
    - **Location** — Vertex リージョン（デフォルト `us-central1`）
    - **Credentials path** *（オプション）* — サービスアカウント
      JSON キーファイルへのパス。Application Default Credentials
      を使用するには空白のままにしてください
      （`gcloud auth application-default login`）
3. **保存**。プロジェクトが設定されると、モデルのドロップダウンが
   Vertex から再入力されます。

OAuth リフレッシュは `google-genai` によって自動的に処理されます。
サービスアカウント JSON パスは意図的に平文で保存されます（*パス*
は秘密ではない — ファイルの内容がそうであり、Google が文書化した
ベストプラクティスがそれらを保持するディスクに残ります）。

## OpenAI / OpenAI 互換

OpenAI 互換の REST API を公開する任意のものが動作します — OpenAI
自体、[LiteLLM プロキシ](https://docs.litellm.ai)経由の Anthropic、
ローカル Ollama、LM Studio、vLLM、Together.ai、Groq など。

**設定 → LLM**で：

1. **Add Custom Provider** をクリック
2. 入力：
    - **Name** — "OpenAI" / "Local Ollama" / "Anthropic" のような
      ラベル
    - **API endpoint** — ベース URL（例：`https://api.openai.com/v1`
      または Ollama 用の `http://localhost:11434/v1`）
    - **API key** — 認証されていないローカルエンドポイントには空白
      にしてください
    - **Models** — カンマ区切りリスト（例：`gpt-4o-mini, gpt-4o,
      gpt-3.5-turbo`）
3. **Save** をクリック。

カスタムプロバイダーは OS キーチェーンに JSON blob として保存され
ます（API キー含む）。

## デフォルトモデルを切り替え

**設定 → LLM** の **デフォルト Gemini モデル**ドロップダウンは、
独自のピッカーを持たないすべての機能ページで使用されるフォール
バックを設定します。

独自のモデルピッカーを持つページ：

- **テキストを翻訳** — `テキストを翻訳設定タブ → デフォルトモデル`
- **ドキュメントを翻訳** — タスクごとに選択；デフォルトに戻る
- **字幕 / 音声 / ダビング / Live / テキスト抽出** — それぞれ独自
  の設定タブに機能ごとのデフォルトがあります

これにより、混在させることができます：live 用の無料 Flash、大きな
ドキュメント用の Pro、機密データ用のローカル Ollama。

## キーが保存される場所

| OS | ストレージ |
|---|---|
| **macOS** | キーチェーン（ログインキーチェーン） |
| **Windows** | 資格情報マネージャー |
| **Linux (GNOME)** | Secret Service（gnome-keyring / KWallet） |
| **Linux（デーモンなし）** | `~/.config/ai-translate/settings.ini` の平文 INI にフォールバック |

フォールバック INI 値は、キーチェーンが利用可能になるたびに最初の
読み取り時にキーチェーンに移行されます — 手動ステップなし。

## ヘッドレス / サーバーインストール

デスクトップセッションなしでも、Python の `keyring` CLI（`uv sync`
後）でキーを設定できます：

```bash
# Gemini
uv run keyring set ai-translate llm/gemini_api_key

# カスタムプロバイダー（JSON blob を貼り付け — スキーマは設定 UI を参照）
uv run keyring set ai-translate llm/custom_providers
```

または、同じ INI キーを `settings.ini` に直接設定 — アプリは最初の
読み取りでそれらをキーチェーンに移行します。ファイルは次の場所に
あります：

- **Linux** — `~/.config/ai-translate/settings.ini`
- **macOS** — `~/Library/Preferences/ai-translate/settings.ini`
- **Windows** — `%APPDATA%\ai-translate\settings.ini`

## セットアップのテスト

最速の健全性チェック：

```bash
uv run ait --version
echo "Hello world." > /tmp/x.txt
uv run ait /tmp/x.txt --target Japanese --quiet
cat /tmp/x_translated__ja.txt
```

「こんにちは世界。」が表示されたら — 完了です。

## よくあるエラー

| エラー | 考えられる原因 |
|---|---|
| `AUTH_ERROR` | 間違った / 期限切れの API キー。設定で再貼り付け。 |
| `QUOTA_ERROR` | 無料層の 1 日あたりリクエストを超過。待つか、支払う。 |
| `MODEL_NOT_FOUND` | カスタムプロバイダーの `models` リストに要求されたモデルが含まれていません。 |
| `VISION_NOT_SUPPORTED` | 選んだモデルは画像入力できません。`flash` / `pro` / `vision` バリアントを使用。 |

詳細は [トラブルシューティング](../troubleshooting.md)を参照。
