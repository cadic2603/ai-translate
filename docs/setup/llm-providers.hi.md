---
description: "Translation के लिए LLM providers configure करें: Google Gemini (recommended), OpenAI-compatible endpoints, या API key के साथ कोई भी custom provider।"
---

# LLM Providers

Translation pipeline actual translation के लिए एक Large Language
Model call करती है। आप एक या कई configure कर सकते हैं;
per-feature model picker हर पेज को एक different उपयोग करने देता
है।

## Google Gemini (first-time setup के लिए recommended) {: #google-gemini-recommended-for-first-time-setup }

Free tier generous है और अधिकांश personal use के लिए काफी अच्छा
है।

1. <https://aistudio.google.com/apikey> पर जाएँ
2. **Create API key** क्लिक करें (अपने Google account के साथ
   sign in करें)
3. Key copy करें (ऐसा दिखता है `AIza...`)
4. Desktop ऐप में: **Settings → LLM → Gemini API key** → paste →
   **Save**
5. **Default Gemini model** dropdown में एक default model चुनें।
   Google की lineup ऐसी दिखती है:

    - **Flash** variants (जैसे `gemini-2.5-flash`) — fast, generous
      free tier, good quality। Recommended starting point।
    - **Pro** variants — slower, उच्च quality, अधिक expensive।
    - **Flash-lite** — fastest, cheapest, lower quality।

    Available exact model names उस पर depend करते हैं जो Google ने
    आपके account पर rolled out किया है; एक balanced default के
    लिए वह चुनें जिसके name में `flash` हो।

Done। Key plain text में नहीं, आपके OS keychain में store होती है।

### Vertex AI mode (enterprise)

Gemini configuration block के अंदर, एक radio pair आपको **Developer
API** से **Vertex AI** पर flip करने देता है — same Gemini models,
आपके GCP account के माध्यम से billed, org-level controls के साथ
(VPC-SC, audit logs, regional data residency)।

1. **Settings → LLM** में, Gemini radio को **Developer API** से
   **Vertex AI** पर switch करें
2. भरें:
    - **Project** — आपका GCP project ID
    - **Location** — एक Vertex region (`us-central1` पर default)
    - **Credentials path** *(optional)* — एक service-account JSON
      key file का path। Application Default Credentials उपयोग करने
      के लिए blank छोड़ दें
      (`gcloud auth application-default login`)
3. **Save**। Project set होने पर model dropdown Vertex से re-populate
   होता है।

OAuth refresh `google-genai` द्वारा automatically handled है।
Service-account JSON path उद्देश्य से plaintext में store होता है
(*path* secret नहीं है — file की contents हैं, और वे disk पर
रहती हैं जहाँ Google की documented best practice उन्हें रखती है)।

## OpenAI / OpenAI-compatible

कुछ भी जो एक OpenAI-compatible REST API expose करता है काम करता
है — OpenAI itself, [LiteLLM proxy](https://docs.litellm.ai) के
माध्यम से Anthropic, local Ollama, LM Studio, vLLM, Together.ai,
Groq, और इत्यादि।

**Settings → LLM** में:

1. **Add Custom Provider** क्लिक करें
2. भरें:
    - **Name** — एक label जैसे "OpenAI" / "Local Ollama" /
      "Anthropic"
    - **API endpoint** — base URL (जैसे `https://api.openai.com/v1`
      या Ollama के लिए `http://localhost:11434/v1`)
    - **API key** — unauthenticated local endpoints के लिए blank
      छोड़ें
    - **Models** — comma-separated list (जैसे `gpt-4o-mini,
      gpt-4o, gpt-3.5-turbo`)
3. **Save** क्लिक करें।

Custom providers OS keychain में एक JSON blob के रूप में store
होते हैं (API keys included)।

## Default model switching

**Settings → LLM** में **Default Gemini model** dropdown हर
feature page द्वारा उपयोग किया जाने वाला एक fallback set करता
है जिसके पास अपना picker नहीं है।

अपने स्वयं के model picker वाले पेज:

- **Translate Text** — `Translate Text settings tab → Default model`
- **Translate Document** — task per pick; default पर fall back
- **Subtitle / Voice / Dubbing / Live / Extract Text** — हर एक
  के पास अपने Settings tab में अपना per-feature default है

यह आपको mix-and-match करने देता है: live के लिए free Flash, बड़े
documents के लिए Pro, sensitive data के लिए local Ollama।

## Keys कहाँ store होती हैं

| OS | Storage |
|---|---|
| **macOS** | Keychain (login keychain) |
| **Windows** | Credential Manager |
| **Linux (GNOME)** | Secret Service (gnome-keyring / KWallet) |
| **Linux (no daemon)** | `~/.config/ai-translate/settings.ini` में plaintext INI पर fall back |

जब भी एक keychain available होता है, fallback INI value को पहले
read पर keychain में migrate किया जाता है — कोई manual step नहीं।

## Headless / server install

Desktop session के बिना, आप अभी भी Python के `keyring` CLI के
माध्यम से keys set कर सकते हैं (`uv sync` के बाद):

```bash
# Gemini
uv run keyring set ai-translate llm/gemini_api_key

# Custom providers (JSON blob paste करें — schema के लिए Settings UI देखें)
uv run keyring set ai-translate llm/custom_providers
```

या same INI keys को सीधे `settings.ini` में set करें — ऐप पहले
read पर इन्हें keychain में migrate कर देती है। File यहाँ है:

- **Linux** — `~/.config/ai-translate/settings.ini`
- **macOS** — `~/Library/Preferences/ai-translate/settings.ini`
- **Windows** — `%APPDATA%\ai-translate\settings.ini`

## अपना setup test करना

सबसे तेज़ sanity check:

```bash
uv run ait --version
echo "Hello world." > /tmp/x.txt
uv run ait /tmp/x.txt --target Hindi --quiet
cat /tmp/x_translated__hi.txt
```

यदि आप "हैलो वर्ल्ड।" देखते हैं — आप तैयार हैं।

## Common errors

| Error | Likely cause |
|---|---|
| `AUTH_ERROR` | गलत / expired API key। Settings में फिर से paste करें। |
| `QUOTA_ERROR` | Free-tier requests-per-day exceeded। Wait, या pay। |
| `MODEL_NOT_FOUND` | Custom provider की `models` list requested model को include नहीं करती। |
| `VISION_NOT_SUPPORTED` | आपने जो model चुना है वह image input नहीं कर सकता। एक `flash` / `pro` / `vision` variant उपयोग करें। |

अधिक के लिए [Troubleshooting](../troubleshooting.md) देखें।
