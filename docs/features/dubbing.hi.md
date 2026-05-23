---
description: "Videos को end-to-end dub करें: audio transcribe करें, subtitle translate करें, target language में speech synthesize करें, और इसे वापस original video में mix करें।"
---

# Video Dubbing

Full **STT → Translate → TTS → Mix** pipeline जो दूसरी भाषा में
voice track को बदलकर एक video file बनाती है। Original audio को छोड़
दिया जाता है; नया dub track subtitles के समय पर है।

## आपको क्या चाहिए

- `PATH` पर **FFmpeg** — देखें [FFmpeg setup](../setup/ffmpeg.md)।
- एक STT backend (local Whisper पर default, कोई setup नहीं)
- एक TTS backend — Edge TTS (default), ElevenLabs, Google Cloud
  TTS, Gemini TTS, या **Piper TTS** (पूरी तरह से offline;
  per-language voices एक बार **Settings → Voice → Piper TTS →
  Download voices now** के माध्यम से download)
- Translate step के लिए configured **LLM**

## Step-by-step

1. Sidebar में **Dubbing** क्लिक करें।
2. एक या अधिक video files drop करें (`.mp4`, `.webm`, `.mkv`,
   `.avi`, `.mov`, `.wmv`)।
3. **Source language** (video में *बोली जाने वाली* language) और
   जिसमें dub करना है वह **Target language** चुनें।
4. **Start Dubbing** क्लिक करें (`Ctrl+Enter`)।
5. History table में per-task progress देखें। यह चार phases से
   गुज़रती है:

| Phase | Range | क्या हो रहा है |
|---|---|---|
| **STT** | 5–25% | Source audio transcribe कर रहा है |
| **Translate** | 25–50% | LLM हर subtitle line translate कर रहा है |
| **TTS** | 50–90% | हर line के लिए target-language voice synthesize कर रहा है |
| **Mix** | 90–100% | FFmpeg audio track को बदल रहा है |

6. पूरा होने पर, dubbed video play करने के लिए row में **Open**
   क्लिक करें।

## Outputs

हर input video के लिए आपको output directory में चार files मिलती हैं:

```
movie.mp4
movie_dubbed_en_fr.mp4              ← dubbed video
movie_subtitle_en.srt               ← original-language subtitle
movie_subtitle_fr.srt               ← translated subtitle
movie_voice_fr.mp3                  ← synthesized voice track
```

## Paused / crashed run resume करना

Pipeline हर phase के बाद checkpoint करती है। यदि आप **Stop** दबाते
हैं, ऐप से quit करते हैं, या crash होता है, तो row पर **Continue**
दबाने से last completed phase से resume होता है — यदि STT या
translation पहले ही हो गया है तो आप उनके लिए फिर से payment नहीं
करते।

इन options के लिए एक Done / Failed entry पर right-click करें:

- **Continue** — फिर से prompting के बिना last checkpoint से resume
  करें।
- **Re-dub** — language picker फिर से खोलें; यदि आप एक नया target
  चुनते हैं, तो translate और TTS checkpoints drop हो जाते हैं
  (आप STT के लिए फिर से payment नहीं करते)। Same target चुनने से
  effectively last checkpoint से re-run होता है, Continue के समान।
- **Open** — dubbed video play करें।

## Caveats

!!! warning "Lip sync"
    Dubbing source audio के *timestamps* से match होती है, lip
    movements से नहीं। Translated lines जो original से बहुत लंबी हैं
    rushed sound करेंगी; बहुत छोटी lines silence छोड़ देंगी।
    Professional dubbing के लिए आप आमतौर पर इस pass के बाद manually
    re-time करते हैं — यह एक future feature है।

!!! tip "Pre-flight checks"
    Page शुरू करने से पहले FFmpeg + अपने TTS backend की keys
    validate करता है। Missing key → friendly dialog, कोई half-run
    dub नहीं। **Piper TTS** चुने जाने के साथ, यह यह भी जाँचता है
    कि per-language Piper voice disk पर है; missing voice → एक
    **Open Settings** बटन के साथ modal dialog जो आपको voice library
    में drop करता है, ताकि आप STT + translate time burn न करें केवल
    TTS step पर fail होने के लिए।

!!! tip "Target language बदलना"
    Re-target पर pipeline translate + TTS checkpoints drop करती है
    (उनकी content नई language के लिए valid नहीं रहती) लेकिन STT
    checkpoint रखती है — आप transcription cost बचाते हैं।

## Shortcuts

| Shortcut | Action |
|---|---|
| `Ctrl+Enter` | Start Dubbing |
| `Ctrl+O` | Browse |
| `Ctrl+F` | History search पर focus |
| `Ctrl+P` | Active queue को pause करें |
| `Ctrl+G` | Active queue को continue (resume) करें |

`Ctrl+P` / `Ctrl+G` text-input focused होने पर suppress होते हैं,
ताकि वे typing से collide न करें।
