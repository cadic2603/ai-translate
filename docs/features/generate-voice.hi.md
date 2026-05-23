---
description: Edge TTS, ElevenLabs, Google Cloud TTS, Gemini TTS, या offline Piper TTS के साथ subtitles को spoken audio में convert करें — dubbing-quality voice generation के लिए SRT timing preserves करता है।
---

# Voice बनाएँ (TTS)

Subtitle files (timing के साथ) या arbitrary text को MP3 / WAV
audio में synthesize करें। पाँच TTS backends: Edge TTS (free),
ElevenLabs (high quality), Google Cloud TTS, Gemini TTS (free
tier), और Piper TTS (offline)।

## आपको क्या चाहिए

- `PATH` पर **FFmpeg** — देखें [FFmpeg setup](../setup/ffmpeg.md)।
- एक TTS backend, इनमें से एक:
    - **Edge TTS** — free, no key, default। Microsoft Edge की
      cloud voices उपयोग करता है।
    - **ElevenLabs** — paid, highest quality। देखें
      [ElevenLabs setup](../setup/elevenlabs.md)।
    - **Google Cloud TTS** — paid, very good। देखें
      [Google Cloud setup](../setup/google-cloud.md)।
    - **Gemini TTS** — free tier, natural prebuilt voices। LLM tab
      से अपनी मौजूदा Gemini API key reuses करता है — कोई extra
      setup नहीं।
    - **Piper TTS** — पूरी तरह से offline neural TTS। कोई API key
      नहीं, कोई network calls नहीं — voices ~25–60 MB ONNX files
      हैं जो **Settings → Voice → Piper TTS → Download voices now**
      के माध्यम से एक बार download होती हैं। आज ऐप की 45 languages
      में से 32 के पास Piper voice है; Piper coverage के बिना
      languages synthesis time पर silently Edge TTS पर fall back
      करती हैं।

## Step-by-step

1. Sidebar में **Voice बनाएँ** क्लिक करें।
2. एक या अधिक `.srt` / `.vtt` / `.ass` / `.ssa` subtitle files
   drop करें।
3. **Language** चुनें (जब possible हो subtitle filename से
   auto-detected — जैसे `_translated_en_fr.srt` को French के रूप
   में detect किया जाता है)।
4. **Voice gender** चुनें — `Female` या `Male`।
5. **Output format** चुनें — `.mp3` (default) या `.wav`।
6. **Generate** क्लिक करें (या `Ctrl+Enter`)।
7. Done होने पर row पर **Open** क्लिक करें — यह आपके default
   audio app में play होता है।

## Output

आपको एक single audio file मिलती है जिसमें voice tracks हर subtitle
के timestamp पर रखे होते हैं। Silent gaps cues के बीच का समय भरते
हैं ताकि audio original timing के साथ sync में रहे।

## TTS backend चुनना

| Backend | Cost | Voices | Notes |
|---|---|---|---|
| **Edge TTS** | Free | सैकड़ों, सभी प्रमुख languages | Default। कोई setup नहीं। |
| **ElevenLabs** | Paid (~$5/mo entry tier) | Premium neural voices, voice cloning | Highest quality। Voice ID Settings → Service में set होती है। |
| **Google Cloud TTS** | Paid (~$4/M chars; 1 M free / month) | 50+ languages में WaveNet / Studio voices | European languages के लिए strong WaveNet voices। Default रूप से server language + gender के आधार पर voice चुनता है। |
| **Gemini TTS** | Free tier (Developer API quotas apply) | 24+ languages में natural prebuilt voices — `Kore` (female default) / `Puck` (male default) | LLM tab से आपकी Gemini API key reuses करता है। Per-call output ~30 s तक capped; long text सीमाओं पर automatically chunks होता है। |
| **Piper TTS** | Free, **offline** | ऐप की 45 languages में से 32 में neural voices | कोई key नहीं, कोई network नहीं। Per-language voice **Settings → Voice → Piper TTS → Download voices now** से on demand download (प्रत्येक ~25–60 MB)। Pre-flight काम शुरू होने से पहले missing voice catch करता है। |

**Settings → Voice → TTS method** में switch करें।

## Piper TTS specifics

Piper ऐप में एकमात्र पूरी तरह से offline TTS backend है। कुछ चीजें
जानने योग्य:

- **Voice library dialog** — **Settings → Voice → Piper TTS →
  Download voices now** के माध्यम से खोलें। हर language row एक
  `Female voice` और / या `Male voice` download button दिखाता है
  (कुछ languages single-gender हैं)। Voices
  [rhasspy/piper-voices](https://huggingface.co/rhasspy/piper-voices)
  HuggingFace catalogue से आती हैं।
- **Coverage** — ऐप की 45 languages में से 32 के पास Piper voice
  है। Coverage के बिना 13 (Belarusian, Bengali, Chinese
  (Traditional), Croatian, Estonian, Hebrew, Japanese, Khmer,
  Korean, Lithuanian, Malay, Mongolian, Thai) synthesis time पर
  silently Edge TTS पर fall back करते हैं ताकि synthesis missing
  voice पर hard fail कभी न हो।
- **Gender resolution** — जब आप `Female` चुनते हैं, engine पहले
  उस language के लिए female voice आज़माता है; यदि केवल एक male
  voice exists है, तो वह उसका उपयोग करता है (और vice versa)।
  INFO level पर logged।
- **Pre-flight gate** — Voice run शुरू होने से पहले, page check
  करता है कि per-language Piper voice disk पर है। यदि missing है,
  आपको एक **Open Settings** बटन के साथ modal dialog मिलता है जो
  आपको सीधे voice library में ले जाता है ताकि आप अपनी queue खोए
  बिना इसे download कर सकें।

## Gemini TTS specifics

Gemini TTS Developer API के माध्यम से
`gemini-2.5-flash-preview-tts` का उपयोग करता है। कुछ चीजें जानने
योग्य:

- **Voice selection** आज gender द्वारा है — Female `Kore` पर map
  करता है, Male `Puck` पर। दोनों clear, neutral voices हैं जो
  languages में बहुत character-y sound किए बिना काम करती हैं।
- **Output length cap** — हर Gemini API call अधिकतम ~30 s of
  speech लौटाता है। ऐप input text को `_GEMINI_TTS_MAX_BYTES`
  (~2000 bytes ≈ 30 s) के नीचे sentence boundaries पर chunks
  करता है, फिर FFmpeg के माध्यम से chunks concatenate करता है।
  आप normal subtitle text पर truncation hit नहीं करेंगे।
- **Audio format** — Gemini 24 kHz mono s16le पर raw PCM emit
  करता है; ऐप per-chunk MP3 (या यदि आपने चुना तो WAV) में transcode
  करता है ताकि final file आपके selected output format से match हो।
- **Vertex AI अभी TTS के लिए support नहीं है** — भले ही आपका LLM
  tab Vertex के लिए configured हो, Gemini TTS को अभी भी एक
  Developer API key चाहिए। Missing होने पर ऐप पहले से `AUTH_ERROR`
  raise करता है।

## ElevenLabs models

तीन models exposed हैं:

| Model | Latency | Quality | Use for |
|---|---|---|---|
| `eleven_multilingual_v2` (default) | Medium | High | General TTS |
| `eleven_v3` | Medium | Highest | Studio / production |
| `eleven_flash_v2_5` | Low | Good | Real-time / Live mode |

**Settings → Voice → ElevenLabs model** में configure करें।

## Tips

!!! tip "Re-generate"
    Translation को फिर से चलाए बिना voice gender / TTS method /
    format swap करने के लिए row पर right-click → **Re-generate**।

!!! tip "Pre-flight checks"
    Page शुरू करने से पहले ElevenLabs API key (जब selected) और
    FFmpeg availability validate करता है। यदि कुछ missing है तो
    आपको एक friendly dialog दिखेगा।

!!! warning "Stop atomic है"
    Synthesis के दौरान **Stop** दबाएँ और आपको output directory में
    एक half-written MP3 नहीं मिलेगा — file पहले एक temp location
    पर लिखी जाती है, फिर केवल success पर place में move होती है।

## Shortcuts

| Shortcut | Action |
|---|---|
| `Ctrl+Enter` | Generate |
| `Ctrl+O` | Browse |
| `Ctrl+F` | History search पर focus |
