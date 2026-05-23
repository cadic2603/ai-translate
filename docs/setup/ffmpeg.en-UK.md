---
description: Install FFmpeg so AI Translate can decode audio and video for subtitle generation, voice synthesis, and video dubbing — required for media features.
---

# FFmpeg

FFmpeg is required for any audio / video workflow:

- **Generate Subtitle** — decoding source audio for STT
- **Generate Voice** — combining timed TTS clips into one file
- **Dubbing** — STT → TTS → mux back into video
- **Live Translation** — when system audio capture goes through `parec`

It's not bundled — install it once on your system.

## Install

=== "macOS"
    ```bash
    brew install ffmpeg
    ```

=== "Ubuntu / Debian"
    ```bash
    sudo apt update && sudo apt install ffmpeg
    ```

=== "Fedora / RHEL"
    ```bash
    sudo dnf install ffmpeg
    ```

    Or, for a more complete build, enable [RPM Fusion](https://rpmfusion.org/Configuration)
    first.

=== "Arch / Manjaro"
    ```bash
    sudo pacman -S ffmpeg
    ```

=== "Windows"
    Download a static build from <https://www.gyan.dev/ffmpeg/builds/>
    (the "release essentials" build is fine), unzip, then add the `bin/`
    folder to your PATH:

    1. Press **Win + R**, type `sysdm.cpl`, press **Enter**
    2. **Advanced → Environment Variables → System variables → Path → Edit**
    3. **New** → paste the absolute path to FFmpeg's `bin` folder
    4. **OK** all the way out, restart any open terminals

## Verify

```bash
ffmpeg -version
```

You should see a version banner with `--enable-libx264 --enable-libvpx`
in the configuration line. If you see "command not found", the
installation didn't end up on PATH.

## In-app pre-flight check

The Voice / Dubbing pages call `shutil.which("ffmpeg")` before starting
work. If FFmpeg isn't found you'll see a friendly error dialogue with a
link back here, not a half-run task.

## Common error

| Error | Meaning |
|---|---|
| `FFMPEG_NOT_FOUND` | `ffmpeg` isn't on PATH at the time the page tried to run it. Install it (above) and restart the app. |

In the MCP server (`ait-mcp`), the same error is re-wrapped into a
human-readable message:

> *"FFmpeg is required to decode this audio/video file but is not
> installed or not on PATH. Install FFmpeg and try again."*
