---
description: PDFs, Word, Excel, PowerPoint, ODF, EPUB, HTML, JSON, YAML, SRT और 30+ अन्य file formats को formatting और layout preserve करते हुए translate करें।
---

# दस्तावेज़ अनुवाद

पूरी files अनुवाद करें — Office, PDF, EPUB, plain text, subtitles,
localization formats, और बहुत कुछ — formatting preserved के साथ।

## Supported formats

| Category | Extensions |
|---|---|
| Office | `.docx`, `.xlsx`, `.pptx`, `.odt`, `.ods`, `.odp`, `.doc`, `.xls`, `.ppt` |
| PDF | `.pdf` |
| Text & web | `.txt`, `.md`, `.rst`, `.html`, `.htm`, `.xhtml`, `.xml`, `.rtf`, `.json`, `.csv` |
| eBooks | `.epub` |
| Subtitles | `.srt`, `.vtt`, `.ass`, `.ssa` |
| Localization | `.po`, `.pot`, `.xliff`, `.xlf`, `.yaml`, `.yml`, `.properties`, `.strings` |

## Step-by-step

1. Sidebar में **दस्तावेज़ अनुवाद** क्लिक करें।
2. Files drag करें (या **Browse** क्लिक करें)। Folders भी काम करते
   हैं — अंदर supported files recursively pick होती हैं।
3. **Source** चुनें (या `Auto-detect` पर छोड़ें) और **Target** चुनें।
4. **अनुवाद** क्लिक करें — या `Ctrl+Enter` दबाएँ।
5. नीचे history table per-file progress दिखाती है (Pending →
   Translating → Done / Failed)। Sidebar एक spinner दिखाता है जब
   तक कोई task active है।
6. एक row पर **Open** क्लिक करें ताकि translated file खुले।
   Right-click करने पर options: re-translate, pause, retry, delete।

## Files कहाँ पहुँचती हैं

Default रूप से, translated files original के बगल में
`_translated_<src>_<tgt>` suffix के साथ save होती हैं:

```
~/Documents/report.docx
~/Documents/report_translated_en_fr.docx     ← यहाँ
```

इसे **Settings → General → Translation storage path** में एक custom
directory में बदलें।

## Limits और guards

- **100-file drop cap** — अधिक drop करें और आपको एक notification
  मिलेगी। Batches में अनुवाद करें।
- **Duplicate detection** — पहले से queue में एक file drop करें और
  आपको एक notification दिखेगी (duplicate dropped होती है, दो बार
  add नहीं होती)।
- **Auto-resume** — translations चलते समय ऐप quit करें और वे अगले
  launch पर resume होंगी (Pending / Translating tasks)।

## Office-specific options

**Settings** में Translation tab Office files के लिए ये toggles
expose करता है:

| Option | यह क्या करता है |
|---|---|
| **Translate embedded images** | `.docx` / `.xlsx` / `.pptx` के अंदर images पर OCR + LLM vision चलाता है और translated image फिर से insert करता है। OCR configured की आवश्यकता है। |
| **Translate comments** | Comments / review notes body text के साथ अनुवादित होते हैं। |
| **Translate shapes & text boxes** | Shapes, callouts, और floating text boxes में रहने वाले text को catch करता है। |
| **Translate speaker notes** | PowerPoint speaker notes अनुवादित होते हैं। |
| **Translate sheet names** | Excel sheet tab labels अनुवादित होते हैं। |
| **Auto-convert legacy** | `.doc` / `.xls` / `.ppt` अनुवाद से पहले modern OOXML में convert होते हैं (better fidelity)। |
| **Auto-convert ODF** | `.odt` / `.ods` / `.odp` अनुवाद से पहले OOXML में convert होते हैं। |

सभी Office translation per-run formatting preserve करती है: bold,
italic, underline, strikethrough, font size, colour, hyperlinks,
headers, footers, footnotes, endnotes, सब कुछ।

### एम्बेडेड छवि अनुवाद: चेतावनी के साथ छोड़ें + कैश

जब **एम्बेडेड छवियाँ अनुवाद करें** चालू होता है, हर एम्बेडेड
छवि OCR → LLM विज़न → रेंडर किए गए पुनः-इंजेक्शन से गुज़रती
है। दो व्यवहार जानने योग्य हैं:

- **चेतावनी के साथ छोड़ें**: यदि एक छवि का अनुवाद विफल हो
  जाता है (बहुत बड़ी, क्षतिग्रस्त, विज़न मॉडल स्वरूप
  अस्वीकार करता है, आदि) तो दस्तावेज़ फिर भी पूरा हो जाता है
  — टूटी हुई छवि मूल भाषा में बनी रहती है, `app.log` में एक
  चेतावनी लॉग की जाती है, और लूप अगली छवि के साथ जारी रहता
  है। केवल घातक LLM त्रुटियाँ (`AUTH_ERROR`, `QUOTA_ERROR`,
  `VISION_NOT_SUPPORTED`) पाइपलाइन को तुरंत रोकती हैं क्योंकि
  वे शेष सभी छवियों को भी रोक देती हैं। **एम्बेडेड छवियाँ
  अनुवाद करें** चेकबॉक्स के ऊपर की जानकारी पट्टी इस नीति को
  इनलाइन दस्तावेज़ करती है।
- **प्रति-छवि कैश**: सफल छवि अनुवाद कार्य के आंतरिक स्टोरेज
  निर्देशिका में SHA256 बाइट कुंजी के तहत संरक्षित किए जाते
  हैं। पुनः प्रयास पर, पहले से अनुवादित छवियाँ OCR + LLM को
  पुनः चलाने के बजाय कैश हिट करती हैं — भुगतान किया गया काम
  दोबारा नहीं किया जाता। डुप्लिकेट छवियाँ (हर स्लाइड पर एक
  कंपनी लोगो) एक बार अनुवादित होती हैं और N − 1 बार पुनः
  उपयोग होती हैं।

आउटपुट फ़ाइल केवल **सफलता** पर आपके चुने हुए आउटपुट फ़ोल्डर
में दिखाई देती है — रद्द किए गए या विफल रन से आंशिक अनुवाद
कार्य की आंतरिक स्टोरेज निर्देशिका तक सीमित रहते हैं, इसलिए
आपका आउटपुट फ़ोल्डर कभी भी अनाथ आधे-अनुवादित दस्तावेज़ एकत्र
नहीं करता।

## PDF specifics

PDFs एक extract-overlay engine का उपयोग करते हैं: original text
in place redact होता है और translated text उन्हीं boxes में
overlaid होता है, visual layout रखते हुए। Per-page checkpointing का
मतलब है कि एक paused / crashed run वहीं resume होता है जहाँ रुका
था, page 1 से नहीं।

क्या translated होता है:

- Body text (alignment detection के साथ — left / center / right /
  justify)
- Bookmarks / outlines (TOC entries)
- Form fields (text inputs, dropdowns, list boxes)
- Hyperlinks (link rect को नए text को wrap करने के लिए update
  किया जाता है)
- Embedded images (जब **Translate embedded images** on हो)
- PDF comments / annotations

Scanned PDFs (कोई embedded text layer नहीं) के लिए, OCR per page
automatically चलता है। **Settings → OCR** में अपना OCR engine
configure करें।

## Right-to-left output

**Arabic**, **Hebrew**, या **Persian** में translations हर output
format में natively RTL render होते हैं — `dir="rtl"` PDF
overlays, HTML, और EPUB chapters में inject होता है (EPUB OPF में
`page-progression-direction="rtl"` के साथ ताकि Apple Books और
Kindle सही दिशा में page-turn करें); DOCX `<w:bidi/>` + `<w:rtl/>`,
PPTX `rtl="1"`, XLSX right-to-left sheet view, ODT/ODS/ODP
`style:writing-mode="rl-tb"`, RTF `\rtldoc`, और ASS/SSA alignment-
code mirroring (`\an1` ↔ `\an3`, `\an4` ↔ `\an6`, etc.)। Centre
alignments untouched हैं।

## Shortcuts

| Shortcut | Action |
|---|---|
| `Ctrl+Enter` | Translation शुरू करें |
| `Ctrl+O` | Files के लिए browse |
| `Ctrl+F` | History search पर focus |
| `Ctrl+P` | Active queue को pause करें |
| `Ctrl+G` | Active queue को continue (resume) करें |
| `Delete` | Selected history entries delete करें |

`Ctrl+P` / `Ctrl+G` text-input focused होने पर suppress होते हैं
ताकि वे typing से collide न करें।

## जब चीजें fail होती हैं

एक failed task एक error code और एक localized message के साथ red
status दिखाता है — सामान्य के लिए
[troubleshooting guide](../troubleshooting.md) देखें (`AUTH_ERROR`,
`QUOTA_ERROR`, `FFMPEG_NOT_FOUND`, etc.)।
