---
description: 画像と PDF テキスト抽出のための OCR エンジンをセットアップ — オフライン Tesseract または EasyOCR、あるいはクラウドベースの Google Vision OCR から選択。
---

# OCR エンジン

OCR は画像からテキストを読むために使用されます — [テキスト抽出](../features/extract-text.md)
ページと、ページがスキャンされている（テキストレイヤーがない）または
**埋め込み画像を翻訳**をオンにしたときの Document 翻訳内の
フォールバックの両方で。

3 つの OCR エンジンから選択できます。

## Tesseract（推奨デフォルト）

無料、高速、オフライン。システムインストールが必要。

=== "macOS"
    ```bash
    brew install tesseract tesseract-lang
    ```

=== "Ubuntu / Debian"
    ```bash
    sudo apt install tesseract-ocr tesseract-ocr-all
    ```

    `tesseract-ocr-all` は、サポートされているすべての言語をもた
    らします。ディスクを節約するには、必要なものだけをインストール
    してください（例：フランス語用の `tesseract-ocr-fra`）。

=== "Fedora / RHEL"
    ```bash
    sudo dnf install tesseract tesseract-langpack-eng tesseract-langpack-fra
    ```

=== "Windows"
    [UB Mannheim の Tesseract リリース](https://github.com/UB-Mannheim/tesseract/wiki)
    からインストーラーをダウンロード。実行し、デフォルトを受け入れ
    る — 言語パックがバンドルされています。

検証：

```bash
tesseract --version
tesseract --list-langs
```

デスクトップアプリで：**設定 → OCR → OCR メソッド = Tesseract**。
完了。

## EasyOCR

無料、オフライン。非ラテン文字（中国語、韓国語、日本語、タイ語）に
最適。モデルは初回使用時にダウンロード（合計~1 GB）。

```bash
uv sync --extra easyocr
```

デスクトップアプリで：**設定 → OCR → OCR メソッド = EasyOCR**。

ある言語で初めて使用する時、関連するモデルが `~/.EasyOCR/` に
ダウンロードされます。以降の実行は瞬時です。

## Google Cloud Vision

クラウド、有料（月 1,000 件の無料リクエスト）。最高精度、特にノイズの
多い / 手書き / 多書式コンテンツで。

1. [Google Cloud プロジェクトを作成](https://console.cloud.google.com/projectcreate)
2. [Vision API](https://console.cloud.google.com/apis/library/vision.googleapis.com) を有効化
3. [API キーを作成](https://console.cloud.google.com/apis/credentials)
4. デスクトップアプリで：**設定 → サービス → Google Cloud API キー** → 貼り付け
5. **設定 → OCR → OCR メソッド = Google Cloud OCR**

それらの API も有効にすれば、同じ Google Cloud API キーが Vision
OCR、Speech-to-Text、Text-to-Speech を駆動します。

## 精度の比較

**設定 → OCR** タブには小さな比較テーブルが組み込まれています —
言語カバレッジ、オンライン/オフライン、コスト、精度。切り替えたい
誘惑にかられるたびに再読してください。

## OCR が使われる時

| 場所 | 動作 |
|---|---|
| **テキスト抽出ページ**（メソッド = OCR の時） | ドロップされた画像での直接 OCR |
| **ドキュメントを翻訳 → PDF** | スキャンのみのページ（テキストレイヤーなし）での OCR フォールバック |
| **ドキュメントを翻訳 → Office** で **埋め込み画像を翻訳** がオン | すべての埋め込み画像での OCR + LLM ビジョン |

## ヒント

!!! tip "ソース言語を選ぶ"
    ほとんどの OCR エンジンは、何の言語を期待するか伝えたときに
    はるかに正確です。字幕 / ドキュメント / テキスト抽出ページは、
    あなたの**ソース言語**ピッカーを OCR エンジンに転送します。

!!! tip "きれいに印刷されたテキストには Tesseract で十分"
    Tesseract / EasyOCR があなたのコンテンツで実際に失敗するまで
    クラウド OCR に手を伸ばさないでください。それらは無料で、高速
    で、驚くほど良いです。
