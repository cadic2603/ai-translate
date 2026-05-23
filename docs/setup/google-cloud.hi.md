---
description: Vision OCR, Speech-to-Text, और Text-to-Speech के लिए Google Cloud को AI Translate से connect करें — एक API key set करें और relevant services enable करें।
---

# Google Cloud (Vision OCR / Speech-to-Text / Text-to-Speech)

एक single Google Cloud API key तीन optional backends को powers
देती है:

- **Vision OCR** — paid OCR engine (1,000 free / month)
- **Speech-to-Text v1** — paid STT (60 minutes / month free)
- **Text-to-Speech v1** — paid TTS (1 M characters / month free for
  WaveNet)

आपको केवल वही APIs enable करने की आवश्यकता है जिनका आप वास्तव में
उपयोग करते हैं।

## API key प्राप्त करें

1. [एक Google Cloud project बनाएँ](https://console.cloud.google.com/projectcreate)
2. API library खोलें: <https://console.cloud.google.com/apis/library>
3. इनमें से किसी को enable करें:
    - [Vision API](https://console.cloud.google.com/apis/library/vision.googleapis.com)
    - [Speech-to-Text API](https://console.cloud.google.com/apis/library/speech.googleapis.com)
    - [Text-to-Speech API](https://console.cloud.google.com/apis/library/texttospeech.googleapis.com)
4. [एक API key बनाएँ](https://console.cloud.google.com/apis/credentials):
   **+ Create Credentials → API key** क्लिक करें
5. Key copy करें (ऐसा दिखता है `AIza...`)।

!!! tip "Key को restrict करें"
    API-key detail page पर, **API restrictions** के तहत, key को
    केवल उन APIs पर restrict करें जिन्हें आपने enable किया है।
    इस तरह leaked key उन services पर bills nहीं चढ़ा सकती जिन्हें
    आप उपयोग नहीं करना चाहते थे।

## ऐप में configure करें

**Settings → Service** में:

1. **Google Cloud API key** में paste करें → **Save**

यह single key अब सभी तीन Google services के लिए available है।

## हर service enable करें

### Vision OCR

**Settings → OCR → OCR method = Google Cloud OCR** में।

बस इतना ही — यह Service से वही key उपयोग करेगा।

### Speech-to-Text

**Settings → Subtitle → STT method = Google Cloud** (Subtitle /
Voice पेज के लिए) या **Settings → Live → STT method = Google
Cloud** (Live पेज के लिए) में।

**Settings → Subtitle → Google STT model** में, recognition model
चुनें:

| Model | सबसे अच्छा |
|---|---|
| `latest_long` (default) | Long-form audio (interviews, lectures) |
| `latest_short` | Voice commands, short phrases |
| `phone_call` | Telephony audio (8 kHz) |
| `medical_dictation` / `medical_conversation` | Medical-domain audio |

### Text-to-Speech

**Settings → Voice → TTS method = Google Cloud TTS** में।

Default रूप से server language और gender के आधार पर एक voice
चुनता है — यह जो अधिकांश users को चाहिए। Specific Google voice
को pin करना (जैसे `en-US-Chirp3-HD-Charon`, `vi-VN-Wavenet-A`)
engine द्वारा supported है लेकिन अभी एक Settings field के रूप में
exposed नहीं है; इसे `settings.ini` में सीधे
`voice/google_tts_voice_name` edit करके set किया जा सकता है। Voice
IDs की list <https://cloud.google.com/text-to-speech/docs/voices>
पर है।

## Common errors

| Error | Likely cause |
|---|---|
| `AUTH_ERROR` | गलत / expired key। Settings → Service में फिर से paste करें। |
| `API not enabled` | आपने इस Cloud project पर specific API (Vision / Speech / TTS) enable नहीं की है। |
| `QUOTA_ERROR` | इस API के लिए free-tier limit reached। Wait, या billing upgrade करें। |
| `INVALID_ARGUMENT_ERROR` | Voice name आपके चुने हुए language में मौजूद नहीं है। |

## Cost guard

!!! warning
    सभी तीन Google APIs post-paid हैं — एक बार जब आप free tier
    exceed कर देते हैं, बिना stop के bill आना शुरू हो जाता है।
    High-volume work करने से पहले Cloud project पर एक
    [budget alert](https://console.cloud.google.com/billing/budgets)
    set करें।
