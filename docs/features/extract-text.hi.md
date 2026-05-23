---
description: OCR engines (Tesseract, EasyOCR, Google Vision) या vision LLMs का उपयोग करके images और screenshots से text निकालें — TXT या DOCX में output।
---

# Text निकालें

Images से text प्राप्त करें — receipts, screenshots, photographed
documents, scanned pages, कुछ भी। `.txt` (plain) या `.docx`
(formatted paragraphs) output करता है।

यह पेज **अनुवाद नहीं करता** — यह केवल extract करता है। Output को
Translate Document में pipe करें यदि आप अनुवाद भी चाहते हैं।

## दो extraction methods

| Method | सबसे अच्छा |
|---|---|
| **OCR** | High-volume / batch / cost-sensitive (free या near-free per image) |
| **LLM vision** | Layout preservation, mixed scripts, low-quality images, handwriting |

Default को **Settings → Extract Text → Extraction method** में चुनें।

## OCR engines (OCR method)

| Engine | Cost | Offline | Languages | Notes |
|---|---|---|---|---|
| **Tesseract** | Free | Yes | 100+ | Default। System install की आवश्यकता है। |
| **EasyOCR** | Free | Yes (model download के बाद) | 80+ | Non-Latin scripts के लिए सबसे अच्छा। ~1 GB models। |
| **Google Cloud Vision** | Paid (1,000 free / month) | No | 60+ | Highest accuracy। |

**Settings → OCR** में configure करें।

## Step-by-step

1. Sidebar में **Text निकालें** क्लिक करें।
2. एक या अधिक image files drop करें (`.png`, `.jpg`, `.jpeg`,
   `.bmp`, `.webp`, `.tiff`, `.tif`)।
3. **Source language** चुनें (OCR को सही model चुनने में मदद करता
   है)।
4. **Output format** चुनें — `.txt` या `.docx`।
5. **Extract** क्लिक करें (या `Ctrl+Enter`)।
6. Done होने पर row में **Open** क्लिक करें।

## कब किसका उपयोग करें

- **Text-heavy receipt / invoice** → Tesseract तेज़ और accurate है।
- **Photographed handwritten notes** → LLM vision बहुत आगे जीतता है।
- **Manga / comic panels** → EasyOCR (vertical CJK text को अच्छी
  तरह handle करता है)।
- **छोटे fields वाले Form** → Google Cloud Vision field boundaries
  को दूसरों की तुलना में बेहतर preserve करता है।

## टिप्स

!!! tip "OCR या LLM, दोनों नहीं"
    पेज एक method चुनता है और इसे चलाता है। Outputs की तुलना करने
    के लिए, अलग-अलग methods के साथ same image को दो बार चलाएँ।

!!! tip "Setup-required dialog"
    यदि आप OCR चुनते हैं लेकिन कोई OCR engine configured नहीं है
    (या LLM लेकिन कोई LLM key configured नहीं है), तो पेज एक single
    "Setup Required" dialog दिखाता है जो सीधे relevant Settings
    tab से link करता है।

## Shortcuts

| Shortcut | Action |
|---|---|
| `Ctrl+Enter` | Extract |
| `Ctrl+O` | Browse |
| `Ctrl+F` | History search पर focus |
