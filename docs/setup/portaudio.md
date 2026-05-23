---
description: Install PortAudio so AI Translate can capture your microphone for Live Translation — required when the Live page can't find the audio system.
---

# PortAudio

PortAudio is the cross-platform audio I/O library that powers AI
Translate's microphone capture in the
**[Live Translation](../features/live-translation.md)** page.

If the Live page shows the banner:

> ⚠️ Microphone capture needs PortAudio.

…then PortAudio isn't installed (or isn't on the standard library path).
Most users never see this banner because PortAudio ships with the
`sounddevice` Python wheel; it only surfaces in stripped-down Python
distributions, custom builds, or some container images.

## Install

=== "macOS"
    ```bash
    brew install portaudio
    ```

=== "Ubuntu / Debian"
    ```bash
    sudo apt install libportaudio2
    ```

=== "Fedora / RHEL"
    ```bash
    sudo dnf install portaudio
    ```

=== "Arch / Manjaro"
    ```bash
    sudo pacman -S portaudio
    ```

=== "Alpine"
    ```bash
    sudo apk add portaudio
    ```

=== "Windows"
    PortAudio ships bundled inside the `sounddevice` Python wheel —
    no separate install needed.  If the banner still appears, force-
    reinstall the wheel:

    ```pwsh
    pip install --force-reinstall sounddevice
    ```

## Verify

After installing, restart AI Translate (or switch tabs once) and the
Live page should no longer show the PortAudio banner.  If it still
does:

1. Confirm a real microphone is plugged in / enabled in your OS.
2. On Linux, check that your user is in the `audio` group:
   ```bash
   groups | grep audio
   ```
   If not, `sudo usermod -aG audio $USER` and log out / back in.
3. Open the Live page and pick **Microphone** as the audio source —
   the banner re-evaluates on every show, so the moment PortAudio
   becomes available the warning clears without an app restart.

## See also

- [System Audio Capture](system-audio.md) — separate guide for
  capturing system audio (PulseAudio / PipeWire / BlackHole /
  VB-Audio) on the Live page.
- [Live Translation feature](../features/live-translation.md)
