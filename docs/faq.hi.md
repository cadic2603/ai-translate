---
description: "AI Translate के बारे में सामान्य प्रश्न: supported file formats, free vs paid features, offline use, LLM provider choices, और OCR engine selection।"
---

# अक्सर पूछे जाने वाले प्रश्न

## सामान्य

### क्या यह offline काम करता है?

ज्यादातर हाँ। विशेष रूप से:

- **Translation** को LLM की आवश्यकता है। Free Gemini API online है;
  Custom Provider settings के माध्यम से **local Ollama / LM Studio**
  पूरी तरह से offline है।
- **Tesseract** या **EasyOCR** के साथ **OCR** offline है।
- **Whisper** (default) के साथ **STT** offline है।
- **Edge TTS** (default) के साथ **TTS** online है; **ElevenLabs** /
  **Google Cloud TTS** / **Gemini TTS** online हैं (free या paid);
  **Piper TTS** पूरी तरह से offline neural TTS है — कोई key नहीं,
  कोई network calls नहीं जब आपने **Settings → Voice → Piper TTS →
  Download voices now** के माध्यम से per-language voice (~25–60 MB
  ONNX file) download कर लिया हो।

पूरी तरह से air-gapped setup के लिए: Custom Provider → local LLM,
OCR के लिए Tesseract या EasyOCR, STT के लिए Whisper, और voice
output के लिए Piper TTS।

### मेरी translated files कहाँ saved होती हैं?

Default रूप से original के बगल में, `_translated_<src>_<tgt>` suffix
के साथ (जैसे `report_translated_en_fr.docx`)। **Settings → General
→ Translation storage path** में per-feature override करें।

### मेरी settings कहाँ store होती हैं?

INI file पर:

| OS | Path |
|---|---|
| **Linux** | `~/.config/ai-translate/settings.ini` |
| **macOS** | `~/Library/Preferences/ai-translate/settings.ini` |
| **Windows** | `%APPDATA%\ai-translate\settings.ini` |

API keys OS keychain में रहती हैं (INI में नहीं)। Translation
history data directory में SQLite DB में रहती है।

### मेरा data कैसे संभाला जाता है?

- **Local-first** — text आपकी मशीन को कभी नहीं छोड़ता जब तक कि आप
  एक cloud LLM / OCR / STT / TTS service कॉल नहीं कर रहे हैं।
- **No telemetry** — ऐप phone home नहीं करता। ऐप द्वारा किया जाने
  वाला एकमात्र outbound request optional GitHub-Releases update
  check है (**Settings → General** में toggle); cloud backends केवल
  अपने respective vendors को कॉल करते हैं।
- **API keys** — आपके OS keychain में store होती हैं। Desktop ऐप का
  keychain fallback एक plaintext INI है जब कोई keychain daemon
  उपलब्ध नहीं हो।

### क्या मैं एक Google Doc / Notion page का अनुवाद कर सकता हूँ?

सीधे नहीं। पहले `.docx` में export करें, अनुवाद करें, फिर translated
file को वापस import करें। Notion (Markdown / HTML के रूप में
export), Confluence (`.docx` के रूप में export), आदि के लिए भी ऐसा
ही।

## Models / engines चुनना

### मुझे कौन सा LLM model उपयोग करना चाहिए?

अधिकांश users के लिए:

- **कोई भी Gemini Flash variant** — free tier, fast, surprisingly
  good। रोज़मर्रा के translations के लिए उपयोग करें। Names ऐसे
  दिखते हैं `gemini-2.5-flash`, `gemini-3-flash-preview`, आदि,
  वर्तमान में जो उपलब्ध है उस पर निर्भर करता है।
- **कोई भी Gemini Pro variant** — pay-per-token, उच्च quality।
  महत्वपूर्ण documents (legal, technical, customer-facing) के लिए
  उपयोग करें।
- **Local Ollama** एक 7B-13B model के साथ — जब आपको offline /
  privacy की आवश्यकता हो।

Per-feature model picker का अर्थ है कि आप chat-style translation के
लिए एक fast model का उपयोग कर सकते हैं और expensive एक को documents
के लिए reserve कर सकते हैं।

### मुझे कौन सा OCR engine उपयोग करना चाहिए?

- **Tesseract** major scripts में clean printed text के लिए। Free,
  offline, fast।
- **EasyOCR** non-Latin scripts (विशेष रूप से CJK) और noisier images
  के लिए।
- **Google Cloud Vision** handwriting, mixed scripts, और highest
  accuracy के लिए जब आप भुगतान कर सकते हैं।

### मुझे कौन सा STT method उपयोग करना चाहिए?

- **Whisper local** offline / privacy के लिए।
- **Soniox** multi-speaker recordings के लिए — speaker labels आपके
  SRT में round-trip करते हैं।
- **Google Cloud STT** telephony / medical audio के लिए (उनके domain
  models अच्छे हैं)।
- **Gemini Live** real-time speech-to-speech translation के लिए।

### कौन सा TTS backend?

- **Edge TTS** free, उच्च-quality voices के लिए।
- **ElevenLabs** premium / branded / cloned voices के लिए।
- **Google Cloud TTS** long-tail languages में WaveNet voices के लिए
  जहाँ Edge की coverage कम है।
- **Gemini TTS** अपनी existing Gemini API key को reuse करते हुए free
  natural prebuilt voices के लिए।
- **Piper TTS** जब आपको **offline / air-gapped** voice output की
  आवश्यकता हो। Trade-off: हर language को **Settings → Voice → Piper
  TTS → Download voices now** के माध्यम से एक one-time ~25–60 MB
  voice download की आवश्यकता होती है, और ऐप की 45 languages में से
  13 के पास Piper voice नहीं है (वे silently Edge TTS पर fall back
  करते हैं)।

## Workflow

### मैं एक पूरे folder का अनुवाद कैसे करूँ?

Folder को **Translate Document** drop zone में drop करें। अंदर
(recursively) supported files queue हो जाती हैं; बाकी सब कुछ
silently skip होता है। एक 100-file drop cap है; bigger batches →
multiple drops में split करें।

### क्या मैं translations को pause और resume कर सकता हूँ?

हाँ। ऐप को कभी भी quit करें — Pending / Translating tasks अगले launch
पर resume होते हैं। Per-task checkpointing का अर्थ है कि 100 में से
PDF पेज 47 redone नहीं होगा जब आप resume करते हैं।

### क्या मैं हाथ से एक translation edit कर सकता हूँ?

**Translate Text** के लिए — हाँ, right pane पर क्लिक करें और टाइप
करें। Edit entry के history record में auto-save होता है।

**Translate Document** के लिए — translated file को अपने सामान्य
editor (Word, LibreOffice, आदि) में खोलें और वहाँ edit करें। ऐप
edits को history में वापस roundtrip नहीं करता।

### क्या मैं strings की एक list को bulk-translate कर सकता हूँ?

CLI का उपयोग करें:

```bash
ait *.txt --target French
```

या in-process strings (जैसे code से extracted UI strings) के लिए,
list के साथ `translate_text` MCP tool को कॉल करें, या Python API को
सीधे उपयोग करें:

```python
from src.core.llm_engine import translate_text
out = translate_text(texts=["Hello", "World"], target_lang="French")
```

## शब्दावली

### LLM मेरी glossary का उपयोग क्यों नहीं कर रहा है?

जाँचने के लिए तीन चीजें:

1. Set **active** है (checkbox checked)।
2. आपकी glossary में source term वास्तव में source text में आता है
   (per-call compression LLM को केवल वे entries भेजता है जो batch
   text से match करती हैं — tokens बचाता है, लेकिन इसका मतलब है कि
   एक typo'd source term invisible है)।
3. Model पर्याप्त strong है — `flash-lite` कभी-कभी उन hints को
   ignore करता है जिन्हें `flash` और `pro` honor करते हैं।

### Glossary terms accent-insensitively match होते हैं?

हाँ। Glossary lookup और Glossary page में search box दोनों एक
normalisation function का उपयोग करते हैं जो accents और case को strip
करता है। तो `cafe`, `Café`, और `CAFE` सभी एक entry से match करते हैं
जिसका source `Café` है।

## Privacy

### क्या आप कोई usage data collect करते हैं?

नहीं। ऐप के पास कोई analytics SDK नहीं है। Optional update check
startup पर एक single GitHub Releases endpoint poll करता है; यह
**Settings → General** में toggleable है।

### क्या मेरी API keys safe हैं?

वे आपके OS keychain में store की जाती हैं (macOS पर Keychain, Windows
पर Credential Manager, Linux पर Secret Service)। अन्य processes
उन्हें आपकी explicit permission के बिना नहीं पढ़ सकती हैं। Fallback
(जब कोई keychain daemon उपलब्ध नहीं हो — typically headless Linux
servers) आपके user की config directory के तहत एक plaintext INI है;
उस mode में keys file-permission-protected हैं लेकिन
cryptographically encrypted नहीं हैं।
