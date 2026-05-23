---
description: FFmpeg install करें ताकि AI Translate subtitle generation, voice synthesis, और video dubbing के लिए audio और video decode कर सके — media features के लिए आवश्यक।
---

# FFmpeg

किसी भी audio / video workflow के लिए FFmpeg आवश्यक है:

- **Subtitle generate करें** — STT के लिए source audio decoding
- **Voice generate करें** — एक file में timed TTS clips combine
  करना
- **Dubbing** — STT → TTS → वापस video में mux
- **Live Translation** — जब system audio capture `parec` के
  माध्यम से जाती है

यह bundled नहीं है — इसे अपने system पर एक बार install करें।

## Install करें

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

    या, अधिक complete build के लिए, पहले
    [RPM Fusion](https://rpmfusion.org/Configuration) enable करें।

=== "Arch / Manjaro"
    ```bash
    sudo pacman -S ffmpeg
    ```

=== "Windows"
    <https://www.gyan.dev/ffmpeg/builds/> से एक static build
    download करें ("release essentials" build ठीक है), unzip करें,
    फिर `bin/` folder को अपने PATH में add करें:

    1. **Win + R** दबाएँ, `sysdm.cpl` type करें, **Enter** दबाएँ
    2. **Advanced → Environment Variables → System variables → Path → Edit**
    3. **New** → FFmpeg के `bin` folder का absolute path paste करें
    4. हर जगह **OK**, खुले terminals को restart करें

## Verify करें

```bash
ffmpeg -version
```

आपको configuration line में `--enable-libx264 --enable-libvpx` के
साथ एक version banner दिखना चाहिए। यदि आपको "command not found"
दिखता है, तो installation PATH पर नहीं पहुँची।

## In-app pre-flight check

Voice / Dubbing पेज काम शुरू करने से पहले `shutil.which("ffmpeg")`
call करते हैं। यदि FFmpeg नहीं मिलता है तो आपको half-run task के
बजाय यहाँ वापस link के साथ एक friendly error dialog दिखेगा।

## Common error

| Error | अर्थ |
|---|---|
| `FFMPEG_NOT_FOUND` | जब page ने इसे run करने की कोशिश की तब `ffmpeg` PATH पर नहीं था। इसे install करें (ऊपर) और ऐप restart करें। |

MCP server (`ait-mcp`) में, यही error एक human-readable message में
re-wrap किया जाता है:

> *"FFmpeg is required to decode this audio/video file but is not
> installed or not on PATH. Install FFmpeg and try again."*
