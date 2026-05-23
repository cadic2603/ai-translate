---
description: AI Translate के साथ अपने पहले दस्तावेज़ का अनुवाद 5 मिनट में करें — एक PDF को drag-and-drop करें, target language चुनें, और translated copy डाउनलोड करें।
---

# आपका पहला अनुवाद

एक त्वरित end-to-end run — सेटअप पूरा होने के बाद 5 मिनट से कम।

!!! abstract "शुरू करने से पहले"
    आपके पास [installation](installation.md) पूरी होनी चाहिए और एक
    LLM API key कॉन्फ़िगर होनी चाहिए। पहले प्रयास के लिए free Google
    Gemini tier पर्याप्त है।

## Word document का अनुवाद करें

1. Desktop ऐप लॉन्च करें:

    ```bash
    uv run python -m src.main
    ```

2. बाएँ sidebar में **दस्तावेज़ अनुवाद** क्लिक करें।

3. किसी भी `.docx` file को drop zone में drag करें — या **Browse**
   क्लिक करके एक चुनें।

4. File queue में दिखाई देती है। ऊपर एक target language चुनें:

    - Source: `Auto-detect` (default — आमतौर पर सही)
    - Target: जैसे `French`, `Vietnamese`, `Japanese`,
      `Chinese (Simplified)`

5. **अनुवाद करें** क्लिक करें (या `Ctrl+Enter` दबाएँ)।

6. पेज के नीचे history table में progress bar देखें। जब यह 100% तक
   पहुँच जाए, पंक्ति पर **खोलें** क्लिक करके translated file खोलें
   — original के बगल में `_translated_<src>_<tgt>` suffix के साथ
   सहेजी गई।

## अभी क्या हुआ

- आपकी `.docx` को per-task storage folder में clone किया गया ताकि
  original अछूती रहे।
- Text निकाला गया, LLM-friendly chunks में batch किया गया, अनुवादित
  किया गया, फिर सभी formatting को संरक्षित करते हुए document में
  वापस इंजेक्ट किया गया (bold, italic, fonts, colours, headers,
  footnotes, hyperlinks…)।
- एक history entry SQLite database में लिखी गई ताकि आप बाद में file
  को फिर से खोल, फिर से चला, या फिर से अनुवाद कर सकें।

## अगले quick wins आज़माएँ

=== "सादा text अनुवाद करें"

    Sidebar में **टेक्स्ट अनुवाद** में जाएँ। कुछ भी paste करें, एक
    target चुनें, Enter दबाएँ। Streaming output, language-swap
    (`Ctrl+L`), edit mode, TTS playback।

=== "Subtitles बनाएँ"

    **सबटाइटल बनाएँ** — एक `.mp4` drop करें। आपको source language
    में एक `.srt` मिलेगा। (वीडियो को _अनुवाद और_ dub करने के लिए,
    इसके बजाय Dubbing page का उपयोग करें।)

=== "Live mic अनुवाद"

    **लाइव अनुवाद** — microphone या system audio चुनें, एक target
    चुनें, Start करें। एक floating overlay window real time में
    captions दिखाती है।

## अगला कहाँ

- हर page क्या करती है देखने के लिए [feature index](../index.md#headline-features)
  देखें।
- [और providers](../setup/llm-providers.md) wire करें (custom
  endpoints, ElevenLabs, Soniox, Google Cloud)।
- Batch / scripted runs के लिए [CLI](../cli.md) आज़माएँ।
