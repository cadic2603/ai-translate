---
description: AI Translate के Live पेज के लिए Linux, macOS, और Windows पर system audio capture करें — अपने computer पर play होने वाले किसी भी sound को real time में translate करें।
---

# System Audio Capture (Live)

**[Live Translation](../features/live-translation.md)** पेज
**system audio** (आपके speakers पर play होने वाला सब कुछ) capture
कर सकता है ताकि आप किसी भी media को subtitle / translate कर सकें
— Zoom calls, YouTube, Netflix, games, system sounds।

**Settings → Live → Audio source** (या Live पेज के top पर combo)
में चुनें:

- **Microphone** — केवल आपका mic
- **System audio** — केवल जो भी आपके speakers पर play हो रहा है
- **Both** — दोनों mixed (media पर narrate करने या hybrid meetings
  capture करने के लिए अच्छा)

जब आप **System audio** या **Both** चुनते हैं, ऐप आपके OS के लिए
सही capture backend पर dispatch करती है। यदि OS prerequisites
पूरे नहीं होते हैं तो clickable install links के साथ एक inline
warning banner दिखाई देता है, ताकि आपको session start करके यह
पता न चलाना पड़े कि कुछ missing है।

## Linux (PulseAudio / PipeWire)

हर modern distro पर out of the box काम करता है।

ऐप `parec` (PulseAudio Recorder) का उपयोग करता है ताकि आपके default
sink के **monitor source** को tap किया जा सके। PipeWire का
PulseAudio compatibility shim इसे transparent बनाता है — आपको
raw PulseAudio की आवश्यकता नहीं है।

```bash
parec --version    # कुछ print करना चाहिए
```

यदि `parec` missing है, warning banner आपके distro का package
manager detect करता है और exact install command inline करता है —
उदाहरण के लिए:

> System audio capture को PulseAudio या PipeWire चाहिए — `sudo apt-get install pulseaudio` run करें।

apt-get / dnf / pacman / zypper / apk पर detected; आप command को
सीधे terminal में copy-paste कर सकते हैं।

## macOS

CoreAudio system audio को natively expose नहीं करता, इसलिए आपको
एक **virtual loopback device** की आवश्यकता है — इनमें से एक
install करें:

- **[BlackHole](https://existential.audio/blackhole/)** — free, open source
- **[Loopback](https://rogueamoeba.com/loopback/)** — paid, polished GUI
- **[Soundflower](https://github.com/mattingalls/Soundflower)** — legacy free option
- **[iShowU Audio Capture](https://shinywhitebox.com/audio-capture)** — paid

ऐप इनमें से किसी को `ffmpeg -f avfoundation -list_devices` के
माध्यम से auto-detect करती है और first match का उपयोग करती है।
Loopback को अपना default output / input set करने की आवश्यकता
नहीं है — capture `ffmpeg` के avfoundation backend के माध्यम से
सीधे होता है।

Install करने के बाद, बस Live पेज combo में **System audio** चुनें
और warning banner गायब हो जाता है।

## Windows

Native — अधिकांश मामलों में **कोई extra software आवश्यक नहीं**।

ऐप Python package
[`soundcard`](https://github.com/bastibe/SoundCard) के माध्यम से
सीधे **WASAPI loopback** से बात करता है (Windows पर ऐप के साथ
automatically installed)। यह वही native loopback API है जो
Tauri / Rust desktop apps उपयोग करते हैं; यह virtual cable के
बिना default speaker output capture करता है।

यदि किसी कारण से WASAPI loopback available नहीं है (older Windows
versions, unusual audio driver), ऐप एक virtual-loopback DirectShow
device के विरुद्ध `ffmpeg -f dshow` पर fall back करता है। इनमें
से एक चुनें:

- **[Screen Capture Recorder](https://github.com/rdp/screen-capture-recorder-to-video-windows-free)** — free, `virtual-audio-capturer` provide करता है
- **[VB-Audio Virtual Cable](https://vb-audio.com/Cable/)** — free, `CABLE Output (VB-Audio Virtual Cable)` के रूप में आता है
- **Stereo Mix (Realtek Audio)** — legacy on-board option, अक्सर default रूप से disabled

ऐप इनके लिए order में probe करता है और first present का उपयोग
करता है।

## "Both" क्यों आपकी voice AND system audio दोनों pickup करता है

**Both** mode में, ऐप parallel में दो capture streams खोलता है —
आपका mic `sounddevice` के माध्यम से, system audio ऊपर के OS-specific
backend के माध्यम से — और sample-block granularity पर उन्हें mix
करता है। एक video पर narrate करने के लिए, या एक hybrid meeting
के दोनों sides capture करने के लिए (आपकी voice plus speakers पर
participants) यह सही mode है।

> **Tip:** यदि आप एक echo सुनते हैं या duplicate captions मिलते
> हैं, तो आपके microphone के माध्यम से system audio आ रहा है
> (loud speakers → mic उन्हें pick up करता है)। केवल **System
> audio** पर switch करें, या headphones use करें।

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| Live page start होता है लेकिन कोई captions नहीं | गलत audio source selected, या आपका default mic muted है |
| आपकी voice के लिए captions लेकिन YouTube video के लिए नहीं | System audio prerequisite installed नहीं है (banner को install instructions दिखाने चाहिए) |
| Captions दो बार (echo) | "Both" mode system audio को दो बार pickup करता है — एक बार speakers से mic के माध्यम से, एक बार loopback के माध्यम से। केवल System audio पर switch करें या headphones use करें |
| Missing software install करने के बाद भी banner visible रहता है | Tabs switch करें और वापस आएँ — banner page show पर re-checks करता है |
| macOS: BlackHole installed है लेकिन banner अभी भी ऊपर है | Confirm करें कि BlackHole `ffmpeg -f avfoundation -list_devices true -i ""` audio devices list में है; ऐप को इसे वहाँ देखने की आवश्यकता है |
| Windows: कोई error न होने के बावजूद WASAPI loopback fail होता है | Fallback के रूप में VB-Audio Virtual Cable install करने का प्रयास करें; older Windows versions या कुछ audio drivers `soundcard` के माध्यम से loopback expose नहीं करते |
