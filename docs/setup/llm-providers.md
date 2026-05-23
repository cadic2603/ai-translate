---
description: "Configure LLM providers for translation: Google Gemini (recommended), OpenAI-compatible endpoints, or any custom provider with an API key."
---

# LLM Providers

The translation pipeline calls a Large Language Model for actual
translation. You can configure one or many; the per-feature model
picker lets each page use a different one.

## Google Gemini (recommended for first-time setup)

Free tier is generous and good enough for most personal use.

1. Go to <https://aistudio.google.com/apikey>
2. Click **Create API key** (sign in with your Google account)
3. Copy the key (looks like `AIza...`)
4. In the desktop app: **Settings → LLM → Gemini API key** → paste → **Save**
5. Pick a default model in the **Default Gemini model** dropdown.
   Google's lineup tends to look like:

    - **Flash** variants (e.g. `gemini-2.5-flash`) — fast, generous free tier,
      good quality. Recommended starting point.
    - **Pro** variants — slower, higher quality, more expensive.
    - **Flash-lite** — fastest, cheapest, lower quality.

    The exact model names available depend on what Google has rolled out
    to your account; pick one whose name contains `flash` for a balanced
    default.

Done. The key is stored in your OS keychain, not in plain text.

### Vertex AI mode (enterprise)

Inside the Gemini configuration block, a radio pair lets you flip from
**Developer API** to **Vertex AI** — same Gemini models, billed through
your GCP account, with org-level controls (VPC-SC, audit logs, regional
data residency).

1. In **Settings → LLM**, switch the Gemini radio from **Developer API**
   to **Vertex AI**
2. Fill in:
    - **Project** — your GCP project ID
    - **Location** — a Vertex region (defaults to `us-central1`)
    - **Credentials path** *(optional)* — path to a service-account JSON
      key file. Leave blank to use Application Default Credentials
      (`gcloud auth application-default login`)
3. **Save**. The model dropdown re-populates from Vertex once the project
   is set.

OAuth refresh is handled by `google-genai` automatically. The service-
account JSON path is stored in plaintext on purpose (the *path* isn't a
secret — the file's contents are, and they stay on disk where Google's
documented best practice keeps them).

## OpenAI / OpenAI-compatible

Anything that exposes an OpenAI-compatible REST API works — OpenAI itself,
Anthropic via [LiteLLM proxy](https://docs.litellm.ai), local Ollama, LM Studio,
vLLM, Together.ai, Groq, and so on.

In **Settings → LLM**:

1. Click **Add Custom Provider**
2. Fill in:
    - **Name** — a label like "OpenAI" / "Local Ollama" / "Anthropic"
    - **API endpoint** — the base URL (e.g. `https://api.openai.com/v1` or
      `http://localhost:11434/v1` for Ollama)
    - **API key** — leave blank for unauthenticated local endpoints
    - **Models** — comma-separated list (e.g. `gpt-4o-mini, gpt-4o, gpt-3.5-turbo`)
3. Click **Save**.

The custom providers are stored as a JSON blob in the OS keychain
(API keys included).

## Switching default model

The **Default Gemini model** dropdown in **Settings → LLM** sets a
fallback used by every feature page that doesn't have its own picker.

Pages with their own model picker:

- **Translate Text** — `Translate Text settings tab → Default model`
- **Translate Document** — picks per task; falls back to default
- **Subtitle / Voice / Dubbing / Live / Extract Text** —
  each has its own per-feature default in its Settings tab

This lets you mix-and-match: free Flash for live, Pro for big documents,
local Ollama for sensitive data.

## Where the keys are stored

| OS | Storage |
|---|---|
| **macOS** | Keychain (login keychain) |
| **Windows** | Credential Manager |
| **Linux (GNOME)** | Secret Service (gnome-keyring / KWallet) |
| **Linux (no daemon)** | Falls back to plaintext INI in `~/.config/ai-translate/settings.ini` |

The fallback INI value is migrated to the keychain on first read whenever
a keychain becomes available — no manual step.

## Headless / server install

Without a desktop session, you can still set keys via Python's `keyring`
CLI (after `uv sync`):

```bash
# Gemini
uv run keyring set ai-translate llm/gemini_api_key

# Custom providers (paste the JSON blob — see Settings UI for the schema)
uv run keyring set ai-translate llm/custom_providers
```

Or set the same INI keys directly in `settings.ini` — the app migrates
them to the keychain on first read.  The file lives at:

- **Linux** — `~/.config/ai-translate/settings.ini`
- **macOS** — `~/Library/Preferences/ai-translate/settings.ini`
- **Windows** — `%APPDATA%\ai-translate\settings.ini`

## Testing your setup

Quickest sanity check:

```bash
uv run ait --version
echo "Hello world." > /tmp/x.txt
uv run ait /tmp/x.txt --target French --quiet
cat /tmp/x_translated__fr.txt
```

If you see "Bonjour le monde." — you're done.

## Common errors

| Error | Likely cause |
|---|---|
| `AUTH_ERROR` | Wrong / expired API key. Re-paste in Settings. |
| `QUOTA_ERROR` | Free-tier requests-per-day exceeded. Wait, or pay. |
| `MODEL_NOT_FOUND` | Custom provider's `models` list doesn't include the requested model. |
| `VISION_NOT_SUPPORTED` | The model you picked can't do image input. Use a `flash` / `pro` / `vision` variant. |

See [Troubleshooting](../troubleshooting.md) for more.
