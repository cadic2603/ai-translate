---
description: Image और PDF text extraction के लिए OCR engines set करें — offline Tesseract या EasyOCR के बीच, या cloud-based Google Vision OCR चुनें।
---

# OCR Engines

OCR images से text पढ़ने के लिए उपयोग होता है — दोनों [Extract Text](../features/extract-text.md)
पेज पर और Document translation के अंदर एक fallback के रूप में जब
एक page scanned हो (कोई text layer नहीं) या जब आप **Translate
embedded images** turn on करते हैं।

आप तीन OCR engines में से चुन सकते हैं।

## Tesseract (recommended default)

Free, fast, offline। एक system install की आवश्यकता है।

=== "macOS"
    ```bash
    brew install tesseract tesseract-lang
    ```

=== "Ubuntu / Debian"
    ```bash
    sudo apt install tesseract-ocr tesseract-ocr-all
    ```

    `tesseract-ocr-all` हर supported language लाता है। Disk बचाने
    के लिए, केवल वही install करें जिसकी आपको आवश्यकता है (जैसे
    French के लिए `tesseract-ocr-fra`)।

=== "Fedora / RHEL"
    ```bash
    sudo dnf install tesseract tesseract-langpack-eng tesseract-langpack-fra
    ```

=== "Windows"
    [UB Mannheim's Tesseract releases](https://github.com/UB-Mannheim/tesseract/wiki)
    से installer download करें। इसे run करें, defaults accept
    करें — language packs bundled हैं।

Verify:

```bash
tesseract --version
tesseract --list-langs
```

Desktop ऐप में: **Settings → OCR → OCR method = Tesseract**। Done।

## EasyOCR

Free, offline। Non-Latin scripts (Chinese, Korean, Japanese, Thai)
के लिए बढ़िया। Models पहले उपयोग पर download होते हैं (~1 GB
total)।

```bash
uv sync --extra easyocr
```

Desktop ऐप में: **Settings → OCR → OCR method = EasyOCR**।

जब आप किसी language के लिए इसे पहली बार उपयोग करते हैं, relevant
model `~/.EasyOCR/` पर download होता है। बाद के runs instant होते
हैं।

## Google Cloud Vision

Cloud, paid (1,000 free requests / month)। Highest accuracy,
विशेष रूप से noisy / handwritten / mixed-script content पर।

1. [एक Google Cloud project बनाएँ](https://console.cloud.google.com/projectcreate)
2. [Vision API](https://console.cloud.google.com/apis/library/vision.googleapis.com)
   enable करें
3. [एक API key बनाएँ](https://console.cloud.google.com/apis/credentials)
4. Desktop ऐप में: **Settings → Service → Google Cloud API key**
   → paste
5. **Settings → OCR → OCR method = Google Cloud OCR**

यदि आप उन APIs को भी enable करते हैं, तो वही Google Cloud API key
Vision OCR, Speech-to-Text, और Text-to-Speech को powers देती है।

## Accuracy compare करना

**Settings → OCR** tab में एक small comparison table built in है
— language coverage, online/offline, cost, accuracy। जब भी आप
switch करने के लिए tempted हों इसे फिर से पढ़ें।

## OCR कब उपयोग होता है

| जगह | व्यवहार |
|---|---|
| **Extract Text page** (जब method = OCR) | Dropped images पर direct OCR |
| **Translate Document → PDF** | Scan-only pages पर OCR fallback (कोई text layer नहीं) |
| **Translate Document → Office** **Translate embedded images** on के साथ | हर embedded image पर OCR + LLM vision |

## Tips

!!! tip "Source language चुनें"
    अधिकांश OCR engines बहुत अधिक accurate होते हैं जब आप उन्हें
    बताते हैं कि कौन सी language expect करनी है। Subtitle /
    Document / Extract Text पेज सभी आपके **Source language**
    picker को OCR engine पर forward करते हैं।

!!! tip "Clean printed text के लिए Tesseract पर्याप्त है"
    Cloud OCR तक तब तक न पहुँचें जब तक Tesseract / EasyOCR वास्तव
    में आपके content पर fail न हो जाए। वे free, fast, और surprisingly
    अच्छे हैं।
