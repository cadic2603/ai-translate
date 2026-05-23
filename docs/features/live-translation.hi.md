---
description: "Real-time speech translation: Whisper या Soniox backends के साथ microphone या system audio को live transcribe और translate करें।"
---

# Live अनुवाद

Microphone, system audio, या दोनों से real-time captions और
translations — एक optional always-on-top overlay window के साथ ताकि
captions उस चीज़ पर बैठें जो भी आप देख रहे हैं।

## आप इसके साथ क्या कर सकते हैं

- **Live meeting captions** — एक translator bot के रूप में join किए
  बिना दूसरी language में Zoom / Meet / Teams call को caption करें।
- **Real-time language learning** — अपनी native language को
  translation track के रूप में foreign-language content (films,
  podcasts, lectures) caption करें।
- **System-wide subtitles** — system audio capture करें ताकि आप
  YouTube / Netflix / आपके speakers पर play होने वाला कुछ भी
  subtitle कर सकें।

## आपको क्या चाहिए

- `PATH` पर **FFmpeg** — देखें [FFmpeg setup](../setup/ffmpeg.md)।
- एक STT backend, इनमें से एक:
    - **faster-whisper** — local, offline, free, default
    - **Soniox** — cloud, paid, real-time speaker diarization। देखें [Soniox setup](../setup/soniox.md)।

- **System audio capture** के लिए, OS के अनुसार सही backend
  auto-selected है: Linux `parec` (PulseAudio / PipeWire) उपयोग
  करता है, Windows native WASAPI loopback (अधिकांश मामलों में कोई
  extra software नहीं) उपयोग करता है, macOS एक virtual loopback
  device (BlackHole / Loopback / etc.) के विरुद्ध
  `ffmpeg -f avfoundation` उपयोग करता है। यदि कुछ missing है तो
  clickable install links के साथ एक inline warning banner दिखाई
  देता है। पूरी per-OS install instructions के लिए देखें
  [Setup → System audio](../setup/system-audio.md)।

## Step-by-step

1. Sidebar में **Live अनुवाद** क्लिक करें।
2. **Settings → Live** में एक बार configure करें:

    - **Source language** (बोली जाने वाली language)
    - **Target language** (या केवल transcription के लिए blank छोड़ें)
    - **Audio source**: Microphone / System audio / Both
    - **STT method**: Whisper / Soniox

3. Live पेज पर वापस, **Start** क्लिक करें (`Ctrl+Enter`)।
4. Transcript main pane को card-by-card भरता है। Floating **Overlay**
   window भी captions दिखाती है (इसे जहाँ चाहें drag करें)।
5. Session समाप्त करने के लिए **Stop** क्लिक करें।

## Transcript view

Toolbar में एक layout चुनें:

- **Both stacked** — original + translation, एक के ऊपर दूसरा
- **Both side-by-side** — original बाईं ओर, translation दाईं ओर
- **Original only** / **Translation only**

Toolbar buttons at-a-glance state के लिए **`ON`** / **`OFF`**
suffixes का उपयोग करते हैं — जैसे `TTS ON`, `TTS OFF`,
`Timestamps ON`, `Overlay OFF`।

Clock icon से **timestamps** on/off toggle करें। Speaker icon से
translated lines की **TTS playback** toggle करें। आपकी **Settings
→ Voice → TTS method** चुनाव का सम्मान करता है — Edge TTS (default),
ElevenLabs, Google Cloud TTS, Gemini TTS, या **Piper TTS** (पूरी
तरह से offline)। Piper selected के साथ, missing per-language voices
mid-stream **silently Edge TTS पर fall back** करती हैं — इस पेज पर
modal pre-flight नहीं है, क्योंकि download dialog के साथ live flow
को block करना fallback से बदतर होगा।

## Overlay window

एक draggable, resizable, always-on-top tool window। Shortcuts:

| Shortcut | Action |
|---|---|
| `Ctrl+[` / `Ctrl+]` | Opacity कम करें / बढ़ाएँ |
| `Ctrl+Arrow` | Overlay को move करें |
| `Ctrl+0` / `Ctrl+9` | Grow / shrink |

Position, size, opacity, और font size sessions के बीच persist
रहते हैं।

### सेटिंग्स के साथ लाइव-सिंक

फ़ॉन्ट आकार और अपारदर्शिता दोनों दिशाओं में काम करते हैं:
**सेटिंग्स → लाइव ट्रांसलेशन → ओवरले कॉन्फ़िगरेशन** में
**फ़ॉन्ट आकार** या **अपारदर्शिता** स्लाइडर खींचने पर खुले हुए
ओवरले को रीयल टाइम में अपडेट करता है, और इसके विपरीत,
ओवरले के अंदर `+` / `-` / `Ctrl+[` / `Ctrl+]` दबाने पर
सेटिंग्स के स्लाइडर अपडेट हो जाते हैं। ओवरले को पुनरारंभ करने
की आवश्यकता नहीं।

### खाली अवस्था का प्लेसहोल्डर

ऑडियो कैप्चर होने से पहले ओवरले एक प्लेसहोल्डर दिखाता है
("Start दबाएँ..." निष्क्रिय / "सुन रहा है..." Start क्लिक होने
के बाद) जो मुख्य विंडो की खाली अवस्था को दर्शाता है — यह
चालू स्टेटस पिल के साथ सिंक रहता है। प्लेसहोल्डर ओवरले की
वर्तमान चौड़ाई × ऊँचाई के साथ स्केल होता है ताकि किसी भी
विंडो आकार पर पठनीय बना रहे।

### न्यूनतम कैप्शन मोड

सेटिंग्स → लाइव ट्रांसलेशन → ओवरले कॉन्फ़िगरेशन में
**न्यूनतम कैप्शन दिखाएँ** चेकबॉक्स ओवरले पर टाइमस्टैम्प और
वक्ता टैग छिपा देता है जबकि उन्हें मुख्य विंडो पर दिखाई
देता है। ओवरले को दर्शकों के साथ साझा करते समय उपयोगी
(प्रस्तुतकर्ता मोड / स्क्रीन शेयरिंग) लेकिन फिर भी आप अपने
कार्य दृश्य में पूर्ण मेटाडेटा रखना चाहते हैं। यह टॉगल
केवल ओवरले के लिए है — यह मुख्य विंडो की "वक्ता टैग"
प्राथमिकता को नहीं बदलता।

## Transcript save करें

Session को timestamps, speakers, original lines, और translated lines
के साथ एक `.txt` file में export करने के लिए **Save Transcript**
क्लिक करें।

## STT backend चुनना

| Backend | सबसे अच्छा | Cost | Latency |
|---|---|---|---|
| **Whisper** (local) | Offline, privacy-sensitive | Free | Medium (~1 s after end-of-sentence) |
| **Soniox** | Multi-speaker meetings | Paid (~$0.005 / min) | Low (real-time) |

## Caveats

!!! warning "Microphone selection"
    Mic input हमेशा **OS default device** का उपयोग करता है — कोई
    in-app picker नहीं (sounddevice उपयोगी होने के लिए बहुत सारे
    virtual ALSA plugins surface करता है, और OS पहले से ही default-
    mic UI का मालिक है)। शुरू करने से पहले अपने OS sound settings
    में अपना preferred mic set करें।

!!! warning "TTS backpressure"
    TTS queue सबसे recent 3 sentences तक bounded है — यदि synthesis
    पीछे पड़ जाता है तो older queued audio drop हो जाता है। यह
    spoken playback को on-screen captions के पास रखता है।

!!! tip "ElevenLabs बिना key के"
    यदि आपने TTS method को ElevenLabs पर set किया है लेकिन कोई API
    key configured नहीं है, Live page automatically Edge TTS पर
    fall back करता है और status label में fallback की घोषणा करता
    है।

## Shortcuts

| Shortcut | Action |
|---|---|
| `Ctrl+Enter` | Start / Stop |
| `Ctrl+K` | Log clear करें (confirmation के साथ) |
| `Ctrl+[` / `Ctrl+]` | Overlay opacity adjust करें |
