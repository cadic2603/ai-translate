---
description: AI Translate के साथ 45+ भाषाओं में तुरंत text snippets अनुवाद करें — paste करें, type करें, या बोलें; edit mode, TTS playback, और language swap का support।
---

# Text अनुवाद

Auto-detection, language swap, streaming output, और TTS playback के
साथ instant LLM translation। Short snippets, chat-style उपयोग, और
अपने LLM setup को testing करने के लिए सबसे अच्छा।

## Step-by-step

1. Sidebar में **Text अनुवाद** क्लिक करें।
2. अपना source text बाएँ pane में type या paste करें।
3. जैसे ही आप type करते हैं, **Source** language auto-detect हो
   जाती है (`langdetect` द्वारा powered)।
4. Right-side dropdown से एक **Target** language चुनें।
5. **अनुवाद** क्लिक करें (या `Ctrl+Enter` दबाएँ)।
6. Translation token-by-token right pane में stream होता है।

## आपको क्या मिलता है

- **Streaming output** — जैसे ही LLM generate करता है translation
  दिखाई देता है, पूरे response का इंतज़ार नहीं।
- **Auto-detect source** — source picker real time में update होता
  है। Override करने के लिए इसे क्लिक करें।
- **Edit mode** — translation को manually edit करने के लिए right
  pane पर क्लिक करें। In-flight translation को cancel करने के लिए
  `Escape` दबाएँ; edit mode से बाहर निकलने के लिए इसे फिर से दबाएँ।
- **History reuse** — हर translation save होता है। नीचे Text
  Translation History panel में एक entry क्लिक करें ताकि दोनों
  panes को re-load कर सकें; edits एक duplicate बनाने के बजाय
  original entry को update करते हैं।
- **TTS playback** — किसी भी pane के बगल में **Listen** बटन क्लिक
  करें ताकि इसे जोर से पढ़ा जा सके। **Settings → Voice → TTS
  method** चुनाव का सम्मान करता है — Edge TTS (default), ElevenLabs,
  Google Cloud TTS, Gemini TTS, या **Piper TTS** (पूरी तरह से
  offline)। Piper selected के साथ, Listen button वही pre-flight
  चलाता है जो Voice पेज: एक missing per-language voice **Open
  Settings** बटन के साथ एक modal dialog दिखाता है ताकि आप इसे
  download कर सकें। Cache hits pre-flight को पूरी तरह से skip करते
  हैं।
- **Per-feature model picker** — जब एक से अधिक LLM configured हो,
  तो एक dropdown आपको speed के लिए एक fast Flash model या quality
  के लिए एक heavier Pro model चुनने देता है, केवल इस पेज के लिए।

## Shortcuts

| Shortcut | Action |
|---|---|
| `Ctrl+Enter` | अनुवाद |
| `Ctrl+L` | Source ↔ target swap |
| `Escape` | In-flight translation cancel करें, या edit mode से बाहर निकलें |
| `Ctrl+F` | History search पर focus |

## टिप्स

!!! tip "RTL languages"
    **Arabic**, **Hebrew**, या **Persian** में translations
    automatically output pane में right-to-left render होते हैं।
    वही RTL handling [Translate Document](translate-document.md)
    पेज पर हर format में file output तक पहुँचती है (PDF, DOCX,
    PPTX, XLSX, ODF, RTF, HTML, EPUB, ASS/SSA), और Persian को Edge
    TTS playback के लिए एक native `fa-IR` voice मिलती है।

!!! tip "Listen-button cache"
    जब आप किसी (text, language) pair पर पहली बार Listen दबाते हैं,
    तो audio synthesize और disk पर cache किया जाता है। बाद के plays
    instant होते हैं। Cache app startup पर मिटा दिया जाता है, इसलिए
    हर session fresh शुरू होती है।

!!! tip "Keys कहाँ जाती हैं"
    Translate Text page बाकी ऐप के समान keychain entries पढ़ता है
    — [LLM Providers](../setup/llm-providers.md) देखें।
