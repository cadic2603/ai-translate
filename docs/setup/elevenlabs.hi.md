---
description: उच्च-quality neural TTS के लिए AI Translate को ElevenLabs से connect करें — realistic, expressive speech के साथ 30+ languages में voiceovers बनाएँ।
---

# ElevenLabs (TTS)

Premium neural text-to-speech। **[Generate Voice](../features/generate-voice.md)**,
**[Dubbing](../features/dubbing.md)**, और **[Live Translation](../features/live-translation.md)**
पेज जब आप ElevenLabs को TTS method के रूप में चुनते हैं तब उपयोग
करते हैं।

## API key प्राप्त करें

1. <https://elevenlabs.io> पर sign up करें
2. <https://elevenlabs.io/app/settings/api-keys> खोलें
3. **+ Create New Key** क्लिक करें, इसे name दें (जैसे "ai-translate"),
   key copy करें (ऐसा दिखता है `sk_...`)

Free tier आपको ~10,000 characters / month देती है, test के लिए
पर्याप्त। Production usage लगभग $5/month से शुरू होती है।

## ऐप में configure करें

**Settings → Service** में:

1. Key को **ElevenLabs API key** में paste करें → **Save**
2. **Voice ID** में अपना preferred **Voice ID** डालें (IDs को
   <https://elevenlabs.io/app/voice-lab> पर ढूंढें; एक voice के
   URL से ID copy करें)। ElevenLabs को default चुनने देने के लिए
   blank छोड़ दें।

**Settings → Voice** में:

1. **TTS method** को **ElevenLabs** पर set करें
2. **ElevenLabs model** चुनें:

    | Model | सबसे अच्छा |
    |---|---|
    | `eleven_multilingual_v2` (default) | General use, balanced latency/quality |
    | `eleven_v3` | उच्चतम quality (production dubs के लिए use) |
    | `eleven_flash_v2_5` | सबसे कम latency (Live Translation के लिए use) |

## यह क्या powers देता है

| Page | कब ElevenLabs use करें |
|---|---|
| **Generate Voice** | जब आप subtitle files से premium-quality voiceovers चाहते हैं |
| **Dubbing** | जब आप एक translated video पर एक उच्च-quality dub track चाहते हैं |
| **Live Translation** | जब आप real time में translated captions का spoken playback चाहते हैं |

## Voice cloning

ElevenLabs custom voice cloning support करता है (paid plan)। एक
बार जब आप ElevenLabs site पर एक voice clone कर लेते हैं, तो इसकी
Voice ID को **Settings → Service → Voice ID** में paste करें और
dubbing / voice-generation pipeline इसका उपयोग करेगा।

## Caveats

!!! warning "Pre-flight check"
    Voice / Dubbing पेज काम शुरू करने से *पहले* check करते हैं कि
    आपकी ElevenLabs API key set है। यदि यह missing है तो आपको
    half-run task के बजाय Settings की ओर इशारा करता एक friendly
    dialog मिलेगा।

!!! tip "Live mode automatically falls back करता है"
    **Live Translation** पेज पर, यदि आपने ElevenLabs select किया
    है लेकिन एक key configured नहीं की है, तो ऐप **Edge TTS**
    (free) पर fall back करता है और status label में fallback
    announce करता है ताकि आप convenient होने पर इसे fix कर सकें।

!!! info "FFmpeg अभी भी आवश्यक है"
    ElevenLabs audio bytes return करता है; ऐप अभी भी formats के
    बीच convert करने के लिए और timed clips को एक file में
    combine करने के लिए FFmpeg का उपयोग करता है। देखें
    [FFmpeg setup](ffmpeg.md)।

## Common errors

| Error | Likely cause |
|---|---|
| `AUTH_ERROR` | गलत / expired API key। Settings → Service में फिर से paste करें। |
| `QUOTA_ERROR` | Free-tier character limit hit, या paid plan exhausted। |
| `MODEL_NOT_FOUND` | Selected ElevenLabs model अब उपलब्ध नहीं है; Settings → Voice में दूसरा चुनें। |
