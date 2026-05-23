---
description: Capture system audio on Linux, macOS, and Windows for AI Translate's Live page — translate any sound playing on your computer in real time.
---

# System Audio Capture (Live)

The **[Live Translation](../features/live-translation.md)** page can
capture **system audio** (everything playing on your speakers) so you
can subtitle / translate any media — Zoom calls, YouTube, Netflix,
games, system sounds.

In **Settings → Live → Audio source** (or the combo at the top of the
Live page), pick:

- **Microphone** — just your mic
- **System audio** — just whatever's playing on your speakers
- **Both** — both mixed (good for narrating over media or capturing
  hybrid meetings)

When you pick **System audio** or **Both**, the app dispatches to the
right capture backend for your OS.  An inline warning banner with
clickable install links appears if the OS prerequisites aren't met,
so you don't have to start a session to find out something's missing.

## Linux (PulseAudio / PipeWire)

Works out of the box on every modern distro.

The app uses `parec` (PulseAudio Recorder) to tap the **monitor source**
of your default sink.  PipeWire's PulseAudio compatibility shim makes
this transparent — you don't need raw PulseAudio.

```bash
parec --version    # should print something
```

If `parec` is missing, the warning banner detects your distro's
package manager and inlines the exact install command — for example:

> System audio capture needs PulseAudio or PipeWire — run `sudo apt-get install pulseaudio`.

Detected on apt-get / dnf / pacman / zypper / apk; you can copy-paste
the command straight into a terminal.

## macOS

CoreAudio doesn't expose system audio natively, so you need a
**virtual loopback device** — install one of:

- **[BlackHole](https://existential.audio/blackhole/)** — free, open source
- **[Loopback](https://rogueamoeba.com/loopback/)** — paid, polished GUI
- **[Soundflower](https://github.com/mattingalls/Soundflower)** — legacy free option
- **[iShowU Audio Capture](https://shinywhitebox.com/audio-capture)** — paid

The app auto-detects any of these via `ffmpeg -f avfoundation -list_devices`
and uses the first match.  No need to set the loopback as your default
output / input — the capture happens directly through `ffmpeg`'s
avfoundation backend.

After installing, just pick **System audio** in the Live-page combo
and the warning banner disappears.

## Windows

Native — **no extra software needed** in most cases.

The app talks directly to **WASAPI loopback** via the
[`soundcard`](https://github.com/bastibe/SoundCard) Python package
(installed automatically with the app on Windows).  This is the same
native loopback API Tauri / Rust desktop apps use; it captures the
default speaker output without a virtual cable.

If for some reason WASAPI loopback isn't available (older Windows
versions, unusual audio driver), the app falls back to
`ffmpeg -f dshow` against a virtual-loopback DirectShow device.  Pick
one of:

- **[Screen Capture Recorder](https://github.com/rdp/screen-capture-recorder-to-video-windows-free)** — free, provides `virtual-audio-capturer`
- **[VB-Audio Virtual Cable](https://vb-audio.com/Cable/)** — free, ships as `CABLE Output (VB-Audio Virtual Cable)`
- **Stereo Mix (Realtek Audio)** — legacy on-board option, often disabled by default

The app probes for these in order and uses the first one present.

## Why "Both" picks up your voice AND system audio

In **Both** mode, the app opens TWO capture streams in parallel —
your mic via `sounddevice`, system audio via the OS-specific backend
above — and mixes them at sample-block granularity.  This is the
right mode for narrating over a video, or for capturing both sides
of a hybrid meeting (your voice plus the participants on speakers).

> **Tip:** if you hear an echo or get duplicate captions, you've got
> system audio coming through your microphone (speakers loud → mic
> picks them up).  Switch to **System audio** only, or use headphones.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| Live page starts but no captions | Wrong audio source selected, or your default mic is muted |
| Captions for your voice but not the YouTube video | System audio prerequisite isn't installed (banner should show install instructions) |
| Captions twice (echo) | "Both" mode picks up system audio twice — once from speakers via mic, once via loopback. Switch to System audio only or use headphones |
| Banner stays visible after installing the missing software | Switch tabs and come back — the banner re-checks on page show |
| macOS: BlackHole installed but banner still up | Confirm BlackHole is in `ffmpeg -f avfoundation -list_devices true -i ""` audio devices list; the app needs to see it there |
| Windows: WASAPI loopback fails despite no error | Try installing VB-Audio Virtual Cable as a fallback; older Windows versions or some audio drivers don't expose loopback through `soundcard` |
