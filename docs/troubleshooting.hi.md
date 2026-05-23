---
description: AI Translate की समस्याओं का diagnose करें — missing fonts, FFmpeg errors, LibreOffice converter problems, OCR setup failures, और LLM API authentication।
---

# समस्या निवारण

सामान्य errors, उनका क्या मतलब है, और उन्हें कैसे ठीक करें।

## सेटअप errors

### "LLM is not configured"

आपने अभी तक API key नहीं जोड़ी है। Desktop app खोलें →
**Settings → LLM** → एक key paste करें। पूरा गाइड के लिए
[LLM Providers](setup/llm-providers.md) देखें।

### `AUTH_ERROR`

LLM API key गलत या expired है।

- **Gemini** — <https://aistudio.google.com/apikey> पर एक नई key
  generate करें, **Settings → LLM** में फिर से paste करें।
- **Custom provider** — verify करें कि key valid है (समान
  `Authorization: Bearer …` header के साथ endpoint को manually
  curl करें)। यदि endpoint moved हो गया है, तो **API endpoint**
  field को भी update करें।

### `QUOTA_ERROR`

आप एक free-tier या paid-plan limit तक पहुँच गए हैं।

- **Gemini free tier** — daily request quota model के अनुसार
  भिन्न होता है (देखें
  <https://ai.google.dev/gemini-api/docs/rate-limits>)। एक दिन
  प्रतीक्षा करें, या paid में upgrade करें।
- **OpenAI / others** — अपना billing dashboard जाँचें। कई
  providers के पास "spend caps" होते हैं जो आपके उन तक पहुँचने पर
  requests को pause करते हैं।

### `MODEL_NOT_FOUND`

आपने जो model name चुना है वह उपलब्ध नहीं है।

- Custom providers — सुनिश्चित करें कि model **Settings → LLM**
  में **Models** comma-separated list में है।
- Built-in Gemini list — **Settings → LLM → Default Gemini model**
  में एक documented model पर switch करें।

### `VISION_NOT_SUPPORTED`

आपने एक non-vision model चुना और एक image / scanned PDF का अनुवाद
करने की कोशिश की। एक model पर switch करें जिसके name में `flash`,
`pro`, या `vision` हो (जैसे OpenAI के लिए `gpt-4o`, Gemini के लिए
कोई भी मौजूदा Gemini Flash या Pro variant)।

## Audio / video errors

### `FFMPEG_NOT_FOUND`

FFmpeg PATH पर नहीं है। अपने OS के लिए install command के लिए
[FFmpeg setup](setup/ffmpeg.md) देखें।

MCP server इसे इस रूप में re-wrap करता है: *"FFmpeg is required to
decode this audio/video file but is not installed or not on PATH."*

### Live page कोई captions नहीं दिखाता

- **Wrong audio source** — **Settings → Live → Audio source**
  खोलें और सुनिश्चित करें कि यह वही है जो आप वास्तव में चाहते हैं
  (Microphone / System / Both)।
- **Mic muted** — OS sound settings जाँचें; ऐप आपके default input
  device का उपयोग करता है।
- **System audio set up नहीं है** — macOS / Windows loopback steps
  के लिए [System audio capture](setup/system-audio.md) देखें।

### Voice output silent / empty है

- **ElevenLabs without key** — Voice page एक friendly dialog
  pre-flight दिखाता है; यदि यह slip हो गया, तो file empty bytes
  हो सकती है। **Settings → Service → ElevenLabs API key** जाँचें।
- **Edge TTS network error** — Edge TTS को internet चाहिए; यदि
  आपका firewall `speech.platform.bing.com` को block करता है, तो
  ElevenLabs, Google Cloud TTS, या **Piper TTS** (fully offline)
  पर switch करें।

### "Piper voice not installed" dialog

Voice / Dubbing / Translate Text पेज pre-flight करते हैं कि आपकी
target language के लिए Piper voice किसी भी worker शुरू होने से
पहले disk पर है। यदि नहीं है, तो आप **Open Settings** बटन के साथ
एक modal देखेंगे।

Voice download करने के लिए:

1. Dialog में **Open Settings** क्लिक करें (या **Settings → Voice**
   मैन्युअली खोलें)।
2. सुनिश्चित करें कि **TTS method** **Piper TTS** पर सेट है।
3. Voice library dialog खोलने के लिए **Download voices now** क्लिक
   करें।
4. अपनी target language की row खोजें, फिर इसके बगल में **Female
   voice** या **Male voice** क्लिक करें। Voices ~25–60 MB ONNX
   files हैं जो HuggingFace से download होती हैं; प्रति language
   एक बार।
5. Dialog बंद करें और अपना translation / voice / dub job फिर से
   चलाएँ।

यदि आपकी target language list में नहीं है, तो इसका Piper coverage
नहीं है — engine synthesis time पर silently Edge TTS पर fall back
करता है, इसलिए आपको वास्तव में कुछ download करने की आवश्यकता
नहीं है। आज Piper voices के बिना 13 languages: Belarusian,
Bengali, Chinese (Traditional), Croatian, Estonian, Hebrew,
Japanese, Khmer, Korean, Lithuanian, Malay, Mongolian, Thai।

**Live Translation** page एक ऐसी जगह है जो यह dialog *नहीं*
दिखाएगी — एक live stream को modal से interrupt करना fallback से
बदतर होगा, इसलिए वहाँ missing-voice cases silently Edge TTS पर
route होते हैं।

## Document translation errors

### PDF translation किसी specific पेज पर fail होता है

PDFs per-page checkpointing का उपयोग करते हैं — सफल pages फिर से
नहीं किए जाते। Failed page `app.log` पर एक stack log करता है;
सामान्य कारण:

- पेज एक **scan with no text layer** है और OCR configured नहीं है।
  **Settings → OCR** सेट करें (देखें
  [OCR engines](setup/ocr-engines.md))।
- पेज में **complex math layout** है जिसे LLM ने बिगाड़ दिया।
  एक stronger model आज़माएँ (Flash के बजाय Pro variant)।

### Office translation formatting तोड़ता है

- **Modern formats** (`.docx`, `.xlsx`, `.pptx`) — formatting को
  HTML round-trip के माध्यम से per-run preserve किया जाता है।
  यदि आप output में stray `<b>` tags देखते हैं, तो LLM ने उन्हें
  बंद नहीं किया — एक stronger model के साथ फिर से चलाएँ।
- **Legacy formats** (`.doc`, `.xls`, `.ppt`) — far better
  fidelity के लिए **Settings → Translation → Auto-convert legacy**
  चालू करें। Pipeline पहले `.docx` में convert करता है, अनुवाद
  करता है, वापस convert करता है।

### Translation queue mid-batch रुकती है

ऐप quit करें और database जाँचें:

```bash
sqlite3 ~/.local/share/ai-translate/translator.db \
  "SELECT id, status, error_code, file_name FROM history WHERE status NOT IN ('Done', 'Failed') ORDER BY created_at DESC LIMIT 10;"
```

`Translating` rows जो minutes में touched नहीं हुई हैं इसका मतलब
है कि एक worker silently crash हो गया। Desktop app को re-launch
करें — यह startup पर Pending / Translating tasks को auto-resume
करता है।

## Cross-cutting issues

### एक साथ कई files silently एक के रूप में अनुवादित होती हैं

एक समय में एक file drop करें, या queue header में **Files**
column जाँचें — इसे आपके drop किए हुए count को दिखाना चाहिए।
100-file cap exceed होने पर एक notification दिखाता है।

### Sidebar हमेशा spinner दिखाता है

संकेत देता है कि एक worker अभी भी running flagged है। ऐप को
cleanly quit करें (कोई SIGKILL नहीं) — autouse cleanup hooks flags
को reset करते हैं। यदि एक SIGKILL ने state stuck छोड़ दिया है,
तो DB workers को manually clear करें:

```bash
sqlite3 ~/.local/share/ai-translate/translator.db \
  "UPDATE history SET status='Failed', error_code=99 WHERE status IN ('Pending', 'Translating');"
```

### Logs कहाँ हैं? {: #where-are-the-logs }

| OS | Path |
|---|---|
| **Linux** | `~/.local/state/log/ai-translate/app.log` |
| **macOS** | `~/Library/Logs/ai-translate/app.log` |
| **Windows** | `%LOCALAPPDATA%\ai-translate\logs\app.log` |

Logs हमेशा DEBUG+ capture करते हैं चाहे console verbosity कुछ भी
हो। Console output by default INFO+ है; stdout पर full file log
mirror करने के लिए CLI को `--verbose` pass करें।

## अभी भी अटके हैं?

- Design-level प्रश्नों के लिए [FAQ](faq.md) देखें।
- <https://github.com/cadic2603/ai-translate/issues> पर एक issue
  file करें: OS, Python version, failing command, `app.log` का
  relevant slice, और आपने जो expected किया था उसका विवरण के साथ।
