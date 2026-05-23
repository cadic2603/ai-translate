---
description: Generate SRT, VTT, ASS, or SSA subtitles from any audio or video — uses Whisper or Google Cloud Speech-to-Text for high-quality transcription.
---

# Generate Subtitle (STT)

Transcribe audio or video into timed subtitles. Picks up speech and
emits SRT / VTT / ASS / SSA — with optional translation in the same
pass.

## What you need

- **FFmpeg** on `PATH` for audio/video decoding — see [FFmpeg setup](../setup/ffmpeg.md).
- A transcription backend, one of:
    - **faster-whisper** — local, offline, free (default; no setup needed)
    - **Google Cloud Speech-to-Text** — cloud, paid, more accurate on noisy
      audio. See [Google Cloud setup](../setup/google-cloud.md).
    - **Soniox** — cloud, paid, real-time and speaker diarization.
      See [Soniox setup](../setup/soniox.md).

## Walkthrough

1. Click **Generate Subtitle** in the sidebar.
2. Drop one or more audio / video files (`.mp3`, `.wav`, `.m4a`, `.flac`,
   `.ogg`, `.aac`, `.wma`, `.mp4`, `.webm`, `.mkv`, `.avi`, `.mov`, `.wmv`).
3. Pick the **Source language** (the language *spoken* in the audio) — leave
   on `Auto-detect` for Whisper to figure it out.
4. Pick a **Target language** — pick `No translation` for a plain
   transcript, or any of the 45 supported languages to get the
   transcript translated in the same pass.
5. Pick the **Output format** (SRT / VTT / ASS / SSA).
6. Click **Generate** (or `Ctrl+Enter`).
7. Watch the queue. **Open** the row when done.

## Format choice

| Format | Best for |
|---|---|
| **SRT** | Universal — almost every player supports it |
| **VTT** | HTML5 `<video>` `<track>` elements |
| **ASS / SSA** | Karaoke, styled subtitles, fansub workflows |

The four formats round-trip through the same parser, so you can switch
output format on a re-translate without losing timing.

## Whisper model size

Switch in **Settings → Subtitle**:

| Model | Size | Speed | Accuracy |
|---|---|---|---|
| `tiny` | ~75 MB | very fast | low |
| `base` (default) | ~150 MB | fast | decent |
| `small` | ~500 MB | medium | good |
| `medium` | ~1.5 GB | slow | high |
| `large` | ~3 GB | very slow | best |

Models download on first use and cache locally. On a slow connection
the first run feels long; subsequent runs are fast.

## STT method comparison

| Backend | Cost | Online? | Speaker diarization | Languages |
|---|---|---|---|---|
| **Whisper** (local) | Free | No | No | 99 |
| **Google Cloud STT** | Paid | Yes | Yes (`latest_long` model) | 125+ |
| **Soniox** | Paid | Yes | Yes (per-token speaker labels) | 60+ |

Switch in **Settings → Subtitle → STT method**.

## Tips

- **Stop button** — interrupt an in-flight batch. Files queued behind
  the active one stay queued; you can resume later.
- **Re-generate** — right-click a Done entry to re-run with a different
  format / language / STT method.
- **Long-form audio** — Whisper handles hours of audio fine; budget ~1
  minute of processing per minute of audio on a CPU `base` model.

## Shortcuts

| Shortcut | Action |
|---|---|
| `Ctrl+Enter` | Generate |
| `Ctrl+O` | Browse |
| `Ctrl+F` | Focus history search |
