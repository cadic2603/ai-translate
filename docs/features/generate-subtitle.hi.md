---
description: किसी भी audio या video से SRT, VTT, ASS, या SSA subtitles generate करें — उच्च-quality transcription के लिए Whisper या Google Cloud Speech-to-Text का उपयोग करता है।
---

# Subtitle बनाएँ (STT)

Audio या video को timed subtitles में transcribe करें। Speech पकड़ता
है और SRT / VTT / ASS / SSA emit करता है — same pass में optional
translation के साथ।

## आपको क्या चाहिए

- Audio/video decoding के लिए `PATH` पर **FFmpeg** — देखें
  [FFmpeg setup](../setup/ffmpeg.md)।
- एक transcription backend, इनमें से एक:
    - **faster-whisper** — local, offline, free (default; कोई setup
      आवश्यक नहीं)
    - **Google Cloud Speech-to-Text** — cloud, paid, noisy audio
      पर अधिक accurate। देखें
      [Google Cloud setup](../setup/google-cloud.md)।
    - **Soniox** — cloud, paid, real-time और speaker diarization।
      देखें [Soniox setup](../setup/soniox.md)।

## Step-by-step

1. Sidebar में **Subtitle बनाएँ** क्लिक करें।
2. एक या अधिक audio / video files drop करें (`.mp3`, `.wav`, `.m4a`,
   `.flac`, `.ogg`, `.aac`, `.wma`, `.mp4`, `.webm`, `.mkv`, `.avi`,
   `.mov`, `.wmv`)।
3. **Source language** चुनें (audio में *बोली जाने वाली* language)
   — Whisper को figure out करने देने के लिए `Auto-detect` पर छोड़ें।
4. एक **Target language** चुनें — plain transcript के लिए `No
   translation` चुनें, या same pass में transcript को translated
   पाने के लिए 45 supported languages में से कोई भी।
5. **Output format** चुनें (SRT / VTT / ASS / SSA)।
6. **Generate** क्लिक करें (या `Ctrl+Enter`)।
7. Queue देखें। Done होने पर row में **Open** क्लिक करें।

## Format choice

| Format | सबसे अच्छा |
|---|---|
| **SRT** | Universal — लगभग हर player इसे support करता है |
| **VTT** | HTML5 `<video>` `<track>` elements |
| **ASS / SSA** | Karaoke, styled subtitles, fansub workflows |

चार formats same parser के माध्यम से round-trip करते हैं, इसलिए
आप timing खोए बिना re-translate पर output format switch कर सकते
हैं।

## Whisper model size

**Settings → Subtitle** में switch करें:

| Model | Size | Speed | Accuracy |
|---|---|---|---|
| `tiny` | ~75 MB | very fast | कम |
| `base` (default) | ~150 MB | fast | decent |
| `small` | ~500 MB | medium | good |
| `medium` | ~1.5 GB | slow | high |
| `large` | ~3 GB | very slow | सबसे अच्छा |

Models पहले उपयोग पर download होते हैं और locally cache होते हैं।
Slow connection पर first run लंबा लगता है; बाद के runs तेज़ होते हैं।

## STT method comparison

| Backend | Cost | Online? | Speaker diarization | Languages |
|---|---|---|---|---|
| **Whisper** (local) | Free | No | No | 99 |
| **Google Cloud STT** | Paid | Yes | Yes (`latest_long` model) | 125+ |
| **Soniox** | Paid | Yes | Yes (per-token speaker labels) | 60+ |

**Settings → Subtitle → STT method** में switch करें।

## टिप्स

- **Stop button** — एक in-flight batch को interrupt करें। Active
  एक के पीछे queued files queued रहती हैं; आप बाद में resume कर
  सकते हैं।
- **Re-generate** — एक different format / language / STT method के
  साथ फिर से चलाने के लिए एक Done entry पर right-click करें।
- **Long-form audio** — Whisper hours of audio को ठीक से handle
  करता है; एक CPU `base` model पर audio के per minute प्रसंस्करण
  के ~1 minute का budget रखें।

## Shortcuts

| Shortcut | Action |
|---|---|
| `Ctrl+Enter` | Generate |
| `Ctrl+O` | Browse |
| `Ctrl+F` | History search पर focus |
