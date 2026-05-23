---
description: Connect ElevenLabs to AI Translate for high-quality neural TTS — generate voiceovers in 30+ languages with realistic, expressive speech.
---

# ElevenLabs (TTS)

Premium neural text-to-speech. Used by the **[Generate Voice](../features/generate-voice.md)**,
**[Dubbing](../features/dubbing.md)**, and **[Live Translation](../features/live-translation.md)**
pages when you pick ElevenLabs as the TTS method.

## Get an API key

1. Sign up at <https://elevenlabs.io>
2. Open <https://elevenlabs.io/app/settings/api-keys>
3. Click **+ Create New Key**, name it (e.g. "ai-translate"), copy the key
   (looks like `sk_...`)

The free tier gives you ~10,000 characters / month, enough to test.
Production usage starts around $5/month.

## Configure in the app

In **Settings → Service**:

1. Paste the key into **ElevenLabs API key** → **Save**
2. Enter your preferred **Voice ID** in **Voice ID** (find IDs at
   <https://elevenlabs.io/app/voice-lab>; copy the ID from a voice's URL).
   Leave blank for ElevenLabs to pick a default.

In **Settings → Voice**:

1. Set **TTS method** to **ElevenLabs**
2. Pick the **ElevenLabs model**:

    | Model | Best for |
    |---|---|
    | `eleven_multilingual_v2` (default) | General use, balanced latency/quality |
    | `eleven_v3` | Highest quality (use for production dubs) |
    | `eleven_flash_v2_5` | Lowest latency (use for Live Translation) |

## What it powers

| Page | Use ElevenLabs when |
|---|---|
| **Generate Voice** | You want premium-quality voiceovers from subtitle files |
| **Dubbing** | You want a high-quality dub track on a translated video |
| **Live Translation** | You want spoken playback of translated captions in real time |

## Voice cloning

ElevenLabs supports custom voice cloning (paid plan). Once you've cloned
a voice on the ElevenLabs site, paste its Voice ID into **Settings → Service →
Voice ID** and the dubbing / voice-generation pipeline will use it.

## Caveats

!!! warning "Pre-flight check"
    The Voice / Dubbing pages check that your ElevenLabs API key is set
    *before* starting work. If it's missing you'll get a friendly dialog
    pointing you to Settings, not a half-run task.

!!! tip "Live mode falls back automatically"
    On the **Live Translation** page, if you've selected ElevenLabs but
    haven't configured a key, the app falls back to **Edge TTS** (free)
    and announces the fallback in the status label so you can fix it
    when convenient.

!!! info "FFmpeg still required"
    ElevenLabs returns audio bytes; the app still uses FFmpeg to convert
    between formats and to combine timed clips into one file. See
    [FFmpeg setup](ffmpeg.md).

## Common errors

| Error | Likely cause |
|---|---|
| `AUTH_ERROR` | Wrong / expired API key. Re-paste in Settings → Service. |
| `QUOTA_ERROR` | Free-tier character limit hit, or paid plan exhausted. |
| `MODEL_NOT_FOUND` | The selected ElevenLabs model is no longer available; pick another in Settings → Voice. |
