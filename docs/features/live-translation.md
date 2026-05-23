---
description: "Real-time speech translation: transcribe and translate microphone or system audio live with Whisper or Soniox backends."
---

# Live Translation

Real-time captions and translations from microphone, system audio, or
both — with an optional always-on-top overlay window so the captions
sit over whatever you're watching.

## What you can do with it

- **Live meeting captions** — caption a Zoom / Meet / Teams call in
  another language without joining as a translator bot.
- **Real-time language learning** — caption foreign-language content
  (films, podcasts, lectures) with your native language as the
  translation track.
- **System-wide subtitles** — capture system audio so you can subtitle
  YouTube / Netflix / anything that plays on your speakers.

## What you need

- **FFmpeg** on `PATH` — see [FFmpeg setup](../setup/ffmpeg.md).
- An STT backend, one of:
    - **faster-whisper** — local, offline, free, default
    - **Soniox** — cloud, paid, real-time speaker diarization. See [Soniox setup](../setup/soniox.md).

- For **system audio capture**, the right backend per OS is
  auto-selected: Linux uses `parec` (PulseAudio / PipeWire),
  Windows uses native WASAPI loopback (no extra software in most
  cases), macOS uses `ffmpeg -f avfoundation` against a virtual
  loopback device (BlackHole / Loopback / etc.).  An inline warning
  banner with clickable install links shows up if anything's
  missing.  See [Setup → System audio](../setup/system-audio.md) for
  full per-OS install instructions.

## Walkthrough

1. Click **Live Translation** in the sidebar.
2. Configure once in **Settings → Live**:

    - **Source language** (spoken language)
    - **Target language** (or leave blank for transcription only)
    - **Audio source**: Microphone / System audio / Both
    - **STT method**: Whisper / Soniox

3. Back on the Live page, click **Start** (`Ctrl+Enter`).
4. The transcript fills the main pane card-by-card. The floating
   **Overlay** window also shows captions (drag it to wherever you want).
5. Click **Stop** to end the session.

## The transcript view

Pick a layout in the toolbar:

- **Both stacked** — original + translation, one above the other
- **Both side-by-side** — original on the left, translation on the right
- **Original only** / **Translation only**

The toolbar buttons use **`ON`** / **`OFF`** suffixes for at-a-glance
state — e.g. `TTS ON`, `TTS OFF`, `Timestamps ON`, `Overlay OFF`.

Toggle **timestamps** on/off with the clock icon. Toggle **TTS playback**
of the translated lines with the speaker icon. Honours your **Settings →
Voice → TTS method** pick — Edge TTS (default), ElevenLabs, Google
Cloud TTS, Gemini TTS, or **Piper TTS** (fully offline). With Piper
selected, missing per-language voices **silently fall back to Edge TTS**
mid-stream — there's no modal pre-flight on this page, since blocking
the live flow on a download dialog would be worse than the fallback.

## The overlay window

A draggable, resizable, always-on-top tool window. Shortcuts:

| Shortcut | Action |
|---|---|
| `Ctrl+[` / `Ctrl+]` | Decrease / increase opacity |
| `Ctrl+Arrow` | Move the overlay |
| `Ctrl+0` / `Ctrl+9` | Grow / shrink |
| `+` / `-` | Increase / decrease transcript font size |

Position, size, opacity, and font size persist between sessions.

### Live-sync with Settings

Font size and opacity controls work in both directions: dragging the
**Font size** or **Opacity** slider in **Settings → Live → Overlay
Configuration** updates the open overlay in real time, and conversely,
pressing `+` / `-` / `Ctrl+[` / `Ctrl+]` inside the overlay updates the
sliders in Settings. No overlay restart required.

### Empty-state placeholder

Before any audio is captured the overlay shows a placeholder ("Press
Start..." idle / "Listening..." once Start is clicked) that mirrors the
main window's empty state — the swap stays in lockstep with the
running status pill. The placeholder scales with the overlay's
current width × height so it remains readable at any window size.

### Minimal-captions mode

The **Show minimal captions** checkbox in Settings → Live → Overlay
Configuration hides the timestamp + speaker chips on the overlay
while keeping them visible on the main window. Useful when the
overlay is shared with an audience (presenter mode / screen
sharing) but you still want full metadata in your working view. The
toggle is overlay-only — it doesn't change your "Speaker labels"
preference for the main window.

## Save the transcript

Click **Save Transcript** to export the session. Pick the format in
Settings → Live → Auto-save → Transcript format:

| Format | When to pick |
|---|---|
| **SRT** (default) | Subtitle alignment — load into a media player to caption your recording |
| **VTT** | Web-native subtitles (HTML5 `<track>`) |
| **ASS** / **SSA** | Subtitle styling for video editors (Aegisub-style) |
| **CSV** | Spreadsheet analysis — one row per cue with `start`, `end`, `speaker`, `original`, `translated` columns (RFC 4180 quoted) |

Each cue includes the speaker label (when Soniox diarization is on),
the original sentence, and the translation (when a target language is
set). The Save Transcript button also dispatches by the file
extension you type in the save dialog if it differs from the saved
default.

## Picking an STT backend

| Backend | Best for | Cost | Latency |
|---|---|---|---|
| **Whisper** (local) | Offline, privacy-sensitive | Free | Medium (~1 s after end-of-sentence) |
| **Soniox** | Multi-speaker meetings | Paid (~$0.005 / min) | Low (real-time) |

## Caveats

!!! warning "Microphone selection"
    The mic input always uses the **OS default device** — there's no
    in-app picker (sounddevice surfaces too many ALSA virtual plugins
    to be useful, and the OS already owns the default-mic UI). Set your
    preferred mic in your OS sound settings before starting.

!!! warning "TTS backpressure"
    The TTS queue is bounded to the most recent 3 sentences — older
    queued audio is dropped if synthesis falls behind. This keeps
    spoken playback near the on-screen captions.

!!! tip "ElevenLabs without a key"
    If you've set TTS method to ElevenLabs but no API key is configured,
    the Live page automatically falls back to Edge TTS and announces
    the fallback in the status label.

## Shortcuts

| Shortcut | Action |
|---|---|
| `Ctrl+Enter` | Start / Stop |
| `Ctrl+K` | Clear log (with confirmation) |
| `Ctrl+[` / `Ctrl+]` | Adjust overlay opacity |
