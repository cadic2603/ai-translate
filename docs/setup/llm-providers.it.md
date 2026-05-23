---
description: "Configura provider LLM per la traduzione: Google Gemini (consigliato), endpoint compatibili con OpenAI, o qualsiasi provider personalizzato con una chiave API."
---

# Provider LLM

Il pipeline di traduzione chiama un Large Language Model per la
traduzione effettiva. Puoi configurarne uno o molti; il selettore di
modello per funzionalità permette a ogni pagina di usarne uno
diverso.

## Google Gemini (consigliato per la prima configurazione) {: #google-gemini-recommended-for-first-time-setup }

Il livello gratuito è generoso e abbastanza buono per la maggior
parte degli usi personali.

1. Vai su <https://aistudio.google.com/apikey>
2. Clicca su **Create API key** (accedi col tuo account Google)
3. Copia la chiave (sembra `AIza...`)
4. Nell'app desktop: **Impostazioni → LLM → Chiave API Gemini** →
   incolla → **Salva**
5. Scegli un modello predefinito nel menu a tendina **Modello Gemini
   predefinito**. La gamma di Google tende a sembrare:

    - Varianti **Flash** (es. `gemini-2.5-flash`) — veloce, livello
      gratuito generoso, buona qualità. Punto di partenza
      consigliato.
    - Varianti **Pro** — più lente, qualità superiore, più costose.
    - **Flash-lite** — più veloce, più economica, qualità inferiore.

    I nomi esatti dei modelli disponibili dipendono da cosa Google
    ha rilasciato sul tuo account; scegline uno il cui nome contiene
    `flash` per un default bilanciato.

Fatto. La chiave è memorizzata nel keychain del tuo OS, non in
chiaro.

### Modalità Vertex AI (enterprise)

All'interno del blocco di configurazione Gemini, una coppia di radio
ti permette di passare da **Developer API** a **Vertex AI** — gli
stessi modelli Gemini, fatturati attraverso il tuo account GCP, con
controlli a livello organizzativo (VPC-SC, log di audit, residenza
regionale dei dati).

1. In **Impostazioni → LLM**, cambia il radio Gemini da **Developer
   API** a **Vertex AI**
2. Compila:
    - **Project** — il tuo ID progetto GCP
    - **Location** — una regione Vertex (predefinito `us-central1`)
    - **Credentials path** *(opzionale)* — percorso a un file JSON di
      chiave service account. Lascia vuoto per usare le Application
      Default Credentials (`gcloud auth application-default login`)
3. **Salva**. Il menu a tendina dei modelli si ripopola da Vertex
   una volta impostato il progetto.

L'aggiornamento OAuth è gestito automaticamente da `google-genai`.
Il percorso JSON del service account è memorizzato in chiaro a
proposito (il *percorso* non è un segreto — il contenuto del file lo
è, e rimane su disco dove la best practice documentata di Google lo
mantiene).

## OpenAI / Compatibili OpenAI

Tutto ciò che espone una API REST compatibile con OpenAI funziona —
OpenAI stessa, Anthropic via [proxy LiteLLM](https://docs.litellm.ai),
Ollama locale, LM Studio, vLLM, Together.ai, Groq, e così via.

In **Impostazioni → LLM**:

1. Clicca su **Add Custom Provider**
2. Compila:
    - **Name** — un'etichetta come "OpenAI" / "Local Ollama" /
      "Anthropic"
    - **API endpoint** — l'URL base (es. `https://api.openai.com/v1`
      o `http://localhost:11434/v1` per Ollama)
    - **API key** — lascia vuoto per endpoint locali non autenticati
    - **Models** — elenco separato da virgole (es. `gpt-4o-mini,
      gpt-4o, gpt-3.5-turbo`)
3. Clicca su **Save**.

I provider personalizzati sono memorizzati come blob JSON nel
keychain dell'OS (chiavi API incluse).

## Cambiare il modello predefinito

Il menu a tendina **Modello Gemini predefinito** in **Impostazioni →
LLM** imposta un fallback usato da ogni pagina di funzionalità che
non ha il proprio selettore.

Pagine con il proprio selettore di modello:

- **Traduci testo** — `scheda impostazioni Traduci testo → Modello predefinito`
- **Traduci documento** — sceglie per attività; ricade sul predefinito
- **Sottotitolo / Voce / Doppiaggio / Live / Estrai testo** —
  ognuna ha il proprio default per funzionalità nella sua scheda
  Impostazioni

Questo ti permette di mescolare e abbinare: Flash gratuito per live,
Pro per documenti grandi, Ollama locale per dati sensibili.

## Dove sono memorizzate le chiavi

| OS | Storage |
|---|---|
| **macOS** | Keychain (login keychain) |
| **Windows** | Gestione Credenziali |
| **Linux (GNOME)** | Secret Service (gnome-keyring / KWallet) |
| **Linux (no daemon)** | Ricade su INI in chiaro in `~/.config/ai-translate/settings.ini` |

Il valore INI di fallback viene migrato al keychain alla prima
lettura ogni volta che un keychain diventa disponibile — nessun
passo manuale.

## Installazione headless / server

Senza una sessione desktop, puoi ancora impostare le chiavi tramite
il CLI `keyring` di Python (dopo `uv sync`):

```bash
# Gemini
uv run keyring set ai-translate llm/gemini_api_key

# Provider personalizzati (incolla il blob JSON — vedi UI Impostazioni per lo schema)
uv run keyring set ai-translate llm/custom_providers
```

O imposta le stesse chiavi INI direttamente in `settings.ini` —
l'app le migra al keychain alla prima lettura. Il file si trova in:

- **Linux** — `~/.config/ai-translate/settings.ini`
- **macOS** — `~/Library/Preferences/ai-translate/settings.ini`
- **Windows** — `%APPDATA%\ai-translate\settings.ini`

## Testare la configurazione

Sanity check più veloce:

```bash
uv run ait --version
echo "Hello world." > /tmp/x.txt
uv run ait /tmp/x.txt --target Italian --quiet
cat /tmp/x_translated__it.txt
```

Se vedi "Ciao mondo." — hai finito.

## Errori comuni

| Errore | Causa probabile |
|---|---|
| `AUTH_ERROR` | Chiave API errata / scaduta. Reincolla in Impostazioni. |
| `QUOTA_ERROR` | Richieste-al-giorno del livello gratuito superate. Aspetta, o paga. |
| `MODEL_NOT_FOUND` | L'elenco `models` del provider personalizzato non include il modello richiesto. |
| `VISION_NOT_SUPPORTED` | Il modello che hai scelto non può fare input di immagini. Usa una variante `flash` / `pro` / `vision`. |

Vedi [Risoluzione dei problemi](../troubleshooting.md) per altro.
