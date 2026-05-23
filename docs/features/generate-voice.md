---
description: Convert subtitles to spoken audio with Edge TTS, ElevenLabs, Google Cloud TTS, Gemini TTS, or offline Piper TTS — preserves SRT timing for dubbing-quality voice generation.
---

# Generate Voice (TTS)

Synthesize subtitle files (with timing) or arbitrary text into MP3 / WAV
audio. Five TTS backends: Edge TTS (free), ElevenLabs (high quality),
Google Cloud TTS, Gemini TTS (free tier), and Piper TTS (offline).

## What you need

- **FFmpeg** on `PATH` — see [FFmpeg setup](../setup/ffmpeg.md).
- A TTS backend, one of:
    - **Edge TTS** — free, no key, default. Uses Microsoft Edge's
      cloud voices.
    - **ElevenLabs** — paid, highest quality. See [ElevenLabs setup](../setup/elevenlabs.md).
    - **Google Cloud TTS** — paid, very good. See [Google Cloud setup](../setup/google-cloud.md).
    - **Gemini TTS** — free tier, natural prebuilt voices. Reuses your
      existing Gemini API key from the LLM tab — no extra setup.
    - **Piper TTS** — fully offline neural TTS. No API key, no network
      calls — voices are ~25–60 MB ONNX files downloaded once via
      **Settings → Voice → Piper TTS → Download voices now**. 32 of
      the app's 45 languages have a Piper voice today; languages
      without Piper coverage silently fall back to Edge TTS at
      synthesis time.

## Walkthrough

1. Click **Generate Voice** in the sidebar.
2. Drop one or more `.srt` / `.vtt` / `.ass` / `.ssa` subtitle files.
3. Pick the **Language** (auto-detected from the subtitle filename when
   possible — e.g. `_translated_en_fr.srt` is detected as French).
4. Pick **Voice gender** — `Female` or `Male`.
5. Pick **Output format** — `.mp3` (default) or `.wav`.
6. Click **Generate** (or `Ctrl+Enter`).
7. **Open** the row when done — it plays in your default audio app.

## Output

You get a single audio file with the voice tracks placed at each
subtitle's timestamp. Silent gaps fill the time between cues so the
audio stays in sync with the original timing.

## Picking a TTS backend

| Backend | Cost | Voices | Notes |
|---|---|---|---|
| **Edge TTS** | Free | Hundreds, all major languages | Default. No setup. |
| **ElevenLabs** | Paid (~$5/mo entry tier) | Premium neural voices, voice cloning | Highest quality. Voice ID is set in Settings → Service. |
| **Google Cloud TTS** | Paid (~$4/M chars; 1 M free / month) | WaveNet / Studio voices in 50+ languages | Strong WaveNet voices for European languages. By default the server picks a voice based on language + gender. |
| **Gemini TTS** | Free tier (Developer API quotas apply) | Natural prebuilt voices in 24+ languages — `Kore` (female default) / `Puck` (male default) | Reuses your Gemini API key from the LLM tab. Per-call output capped at ~30 s; long text chunks at sentence boundaries automatically. |
| **Piper TTS** | Free, **offline** | Neural voices in 32 of the app's 45 languages | No key, no network. Per-language voice downloaded on demand from **Settings → Voice → Piper TTS → Download voices now** (~25–60 MB each). Pre-flight catches a missing voice before work starts. |

Switch in **Settings → Voice → TTS method**.

## Piper TTS specifics

Piper is the only fully-offline TTS backend in the app. A few things
to know:

- **Voice library dialog** — open via **Settings → Voice → Piper TTS
  → Download voices now**. Each language row shows a `Female voice`
  and / or `Male voice` download button (some languages are
  single-gender). Voices come from the
  [rhasspy/piper-voices](https://huggingface.co/rhasspy/piper-voices)
  HuggingFace catalogue.
- **Coverage** — 32 of the app's 45 languages have a Piper voice.
  The 13 without coverage (Belarusian, Bengali, Chinese (Traditional),
  Croatian, Estonian, Hebrew, Japanese, Khmer, Korean, Lithuanian,
  Malay, Mongolian, Thai) silently fall back to Edge TTS at synthesis
  time so synthesis never hard-fails on a missing voice.
- **Gender resolution** — when you pick `Female`, the engine first
  tries the female voice for that language; if only a male voice exists,
  it uses that instead (and vice versa). Logged at INFO level.
- **Pre-flight gate** — before a Voice run starts, the page checks
  that the per-language Piper voice is on disk. If missing, you get
  a modal dialog with an **Open Settings** button that takes you
  straight to the voice library so you can download it without
  losing your queue.

## Gemini TTS specifics

Gemini TTS uses `gemini-2.5-flash-preview-tts` via the Developer API.
A few things to know:

- **Voice selection** is by gender today — Female maps to `Kore`,
  Male to `Puck`. Both are clear, neutral voices that work across
  languages without sounding too character-y.
- **Output length cap** — each Gemini API call returns at most ~30 s
  of speech. The app chunks input text under `_GEMINI_TTS_MAX_BYTES`
  (~2000 bytes ≈ 30 s) at sentence boundaries, then concatenates the
  chunks via FFmpeg. You won't hit truncation on normal subtitle text.
- **Audio format** — Gemini emits raw PCM at 24 kHz mono s16le; the
  app transcodes per-chunk to MP3 (or WAV if you picked it) so the
  final file matches your selected output format.
- **Vertex AI is not yet supported for TTS** — even if your LLM tab
  is configured for Vertex, Gemini TTS still needs a Developer API
  key. The app raises `AUTH_ERROR` upfront if missing.

## ElevenLabs models

Three models are exposed:

| Model | Latency | Quality | Use for |
|---|---|---|---|
| `eleven_multilingual_v2` (default) | Medium | High | General TTS |
| `eleven_v3` | Medium | Highest | Studio / production |
| `eleven_flash_v2_5` | Low | Good | Real-time / Live mode |

Configure in **Settings → Voice → ElevenLabs model**.

## Tips

!!! tip "Re-generate"
    Right-click a row → **Re-generate** to swap voice gender / TTS method
    / format without re-running translation.

!!! tip "Pre-flight checks"
    The page validates ElevenLabs API key (when selected) and FFmpeg
    availability before starting. You'll see a friendly dialog if anything
    is missing.

!!! warning "Stop is atomic"
    Hit **Stop** during synthesis and you won't get a half-written MP3
    in the output directory — the file is written to a temp location
    first, then moved into place only on success.

## Shortcuts

| Shortcut | Action |
|---|---|
| `Ctrl+Enter` | Generate |
| `Ctrl+O` | Browse |
| `Ctrl+F` | Focus history search |
