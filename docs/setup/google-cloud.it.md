---
description: Connetti Google Cloud ad AI Translate per Vision OCR, Speech-to-Text e Text-to-Speech — configura una chiave API e abilita i servizi pertinenti.
---

# Google Cloud (Vision OCR / Speech-to-Text / Text-to-Speech)

Una singola chiave API Google Cloud alimenta tre backend opzionali:

- **Vision OCR** — motore OCR a pagamento (1.000 gratis / mese)
- **Speech-to-Text v1** — STT a pagamento (60 minuti / mese gratis)
- **Text-to-Speech v1** — TTS a pagamento (1 M caratteri / mese
  gratis per WaveNet)

Devi abilitare solo le API che effettivamente usi.

## Ottenere una chiave API

1. [Crea un progetto Google Cloud](https://console.cloud.google.com/projectcreate)
2. Apri la libreria API: <https://console.cloud.google.com/apis/library>
3. Abilita una di:
    - [Vision API](https://console.cloud.google.com/apis/library/vision.googleapis.com)
    - [Speech-to-Text API](https://console.cloud.google.com/apis/library/speech.googleapis.com)
    - [Text-to-Speech API](https://console.cloud.google.com/apis/library/texttospeech.googleapis.com)
4. [Crea una chiave API](https://console.cloud.google.com/apis/credentials):
   clicca **+ Create Credentials → API key**
5. Copia la chiave (sembra `AIza...`).

!!! tip "Limita la chiave"
    Nella pagina di dettaglio della chiave API, sotto **API
    restrictions**, limita la chiave solo alle API che hai abilitato.
    In quel modo una chiave trapelata non può accumulare fatture su
    servizi che non intendevi usare.

## Configurare nell'app

In **Impostazioni → Servizio**:

1. Incolla in **Chiave API Google Cloud** → **Salva**

Questa chiave singola è ora disponibile per tutti e tre i servizi
Google.

## Abilitare ogni servizio

### Vision OCR

In **Impostazioni → OCR → Metodo OCR = Google Cloud OCR**.

Tutto qui — userà la stessa chiave dal Servizio.

### Speech-to-Text

In **Impostazioni → Sottotitolo → Metodo STT = Google Cloud** (per
le pagine Sottotitolo / Voce) o **Impostazioni → Live → Metodo STT =
Google Cloud** (per la pagina Live).

In **Impostazioni → Sottotitolo → Modello STT Google**, scegli il
modello di riconoscimento:

| Modello | Migliore per |
|---|---|
| `latest_long` (predef.) | Audio in formato lungo (interviste, conferenze) |
| `latest_short` | Comandi vocali, frasi brevi |
| `phone_call` | Audio telefonico (8 kHz) |
| `medical_dictation` / `medical_conversation` | Audio del dominio medico |

### Text-to-Speech

In **Impostazioni → Voce → Metodo TTS = Google Cloud TTS**.

Per impostazione predefinita il server sceglie una voce in base a
lingua e genere — è tutto ciò di cui la maggior parte degli utenti ha
bisogno. Bloccare una voce Google specifica (es.
`en-US-Chirp3-HD-Charon`, `vi-VN-Wavenet-A`) è supportato dal motore
ma non ancora esposto come campo Impostazioni; può essere impostato
modificando `voice/google_tts_voice_name` direttamente in
`settings.ini`. Gli ID delle voci sono elencati su
<https://cloud.google.com/text-to-speech/docs/voices>.

## Errori comuni

| Errore | Causa probabile |
|---|---|
| `AUTH_ERROR` | Chiave errata / scaduta. Reincolla in Impostazioni → Servizio. |
| `API not enabled` | Non hai abilitato la specifica API (Vision / Speech / TTS) su questo progetto Cloud. |
| `QUOTA_ERROR` | Limite del livello gratuito raggiunto per questa API. Aspetta, o aggiorna la fatturazione. |
| `INVALID_ARGUMENT_ERROR` | Il nome della voce non esiste nella lingua scelta. |

## Protezione costi

!!! warning
    Tutte e tre le API Google sono pagate posticipatamente — una
    volta superato il livello gratuito inizi ad essere fatturato senza
    stop. Imposta un [avviso di budget](https://console.cloud.google.com/billing/budgets)
    sul progetto Cloud prima di fare lavoro ad alto volume.
