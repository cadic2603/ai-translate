---
description: "Dub videos end-to-end: transcribe audio, translate the subtitle, synthesise speech in the target language, and mix it back into the original video."
---

# Video Dubbing

Full **STT → Translate → TTS → Mix** pipeline that produces a video file
in another language with the voice track replaced. The original audio
is dropped; the new dub track is timed to the subtitles.

## What you need

- **FFmpeg** on `PATH` — see [FFmpeg setup](../setup/ffmpeg.md).
- An STT backend (defaults to local Whisper, no setup needed)
- A TTS backend — Edge TTS (default), ElevenLabs, Google Cloud TTS,
  Gemini TTS, or **Piper TTS** (fully offline; per-language voices
  downloaded once via **Settings → Voice → Piper TTS → Download
  voices now**)
- A configured **LLM** for the translate step

## Walkthrough

1. Click **Dubbing** in the sidebar.
2. Drop one or more video files (`.mp4`, `.webm`, `.mkv`, `.avi`, `.mov`,
   `.wmv`).
3. Pick **Source language** (the language *spoken* in the video) and the
   **Target language** to dub into.
4. Click **Start Dubbing** (`Ctrl+Enter`).
5. Watch the per-task progress in the history table. It moves through
   four phases:

| Phase | Range | What's happening |
|---|---|---|
| **STT** | 5–25% | Transcribing the source audio |
| **Translate** | 25–50% | LLM translating each subtitle line |
| **TTS** | 50–90% | Synthesising target-language voice for each line |
| **Mix** | 90–100% | FFmpeg replaces the audio track |

6. When complete, **Open** the row to play the dubbed video.

## Outputs

For each input video you get four files in the output directory:

```
movie.mp4
movie_dubbed_en_fr.mp4              ← dubbed video
movie_subtitle_en.srt               ← original-language subtitle
movie_subtitle_fr.srt               ← translated subtitle
movie_voice_fr.mp3                  ← synthesised voice track
```

## Resuming a paused / crashed run

The pipeline checkpoints after each phase. If you hit **Stop**, quit
the app, or crash, hitting **Continue** on the row resumes from the last
completed phase — you don't re-pay for STT or translation if they were
already done.

Right-click a Done / Failed entry for these options:

- **Continue** — resume from the last checkpoint without re-prompting.
- **Re-dub** — re-open the language picker; if you pick a new target,
  the translate and TTS checkpoints are dropped (you don't re-pay for
  STT). Picking the same target effectively re-runs from the last
  checkpoint, same as Continue.
- **Open** — play the dubbed video.

## Caveats

!!! warning "Lip sync"
    Dubbing matches the *timestamps* of the source audio, not lip
    movements. Translated lines that are much longer than the original
    will sound rushed; much shorter lines will leave silence. For
    professional dubbing you'd usually re-time manually after this
    pass — that's a future feature.

!!! tip "Pre-flight checks"
    The page validates FFmpeg + your TTS backend's keys before starting.
    Missing key → friendly dialogue, no half-run dub. With **Piper TTS**
    selected, it also checks that the per-language Piper voice is on
    disk; missing voice → modal dialogue with an **Open Settings** button
    that drops you into the voice library, so you don't burn STT +
    translate time only to fail at the TTS step.

!!! tip "Changing target language"
    On a re-target the pipeline drops the translate + TTS checkpoints
    (their content is no longer valid for the new language) but keeps
    the STT checkpoint — you save the transcription cost.

## Shortcuts

| Shortcut | Action |
|---|---|
| `Ctrl+Enter` | Start Dubbing |
| `Ctrl+O` | Browse |
| `Ctrl+F` | Focus history search |
| `Ctrl+P` | Pause the active queue |
| `Ctrl+G` | Continue (resume) the active queue |

`Ctrl+P` / `Ctrl+G` are suppressed when a text-input has focus, so they
won't collide with typing.
