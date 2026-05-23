---
description: Connetti ElevenLabs ad AI Translate per TTS neurale di alta qualità — genera voci fuori campo in oltre 30 lingue con un parlato realistico ed espressivo.
---

# ElevenLabs (TTS)

Sintesi vocale neurale premium. Usato dalle pagine
**[Genera voce](../features/generate-voice.md)**,
**[Doppiaggio](../features/dubbing.md)** e
**[Traduzione live](../features/live-translation.md)** quando scegli
ElevenLabs come metodo TTS.

## Ottenere una chiave API

1. Registrati su <https://elevenlabs.io>
2. Apri <https://elevenlabs.io/app/settings/api-keys>
3. Clicca su **+ Create New Key**, nominala (es. "ai-translate"),
   copia la chiave (sembra `sk_...`)

Il livello gratuito ti dà ~10.000 caratteri / mese, sufficienti per
testare. L'uso in produzione parte da circa 5 $/mese.

## Configurare nell'app

In **Impostazioni → Servizio**:

1. Incolla la chiave in **Chiave API ElevenLabs** → **Salva**
2. Inserisci il tuo **ID voce** preferito in **ID voce** (trova gli ID
   su <https://elevenlabs.io/app/voice-lab>; copia l'ID dall'URL di
   una voce). Lascia vuoto perché ElevenLabs scelga un default.

In **Impostazioni → Voce**:

1. Imposta **Metodo TTS** su **ElevenLabs**
2. Scegli il **Modello ElevenLabs**:

    | Modello | Migliore per |
    |---|---|
    | `eleven_multilingual_v2` (predefinito) | Uso generale, latenza/qualità bilanciate |
    | `eleven_v3` | Qualità massima (da usare per doppiaggi di produzione) |
    | `eleven_flash_v2_5` | Latenza più bassa (da usare per Traduzione live) |

## Cosa alimenta

| Pagina | Usa ElevenLabs quando |
|---|---|
| **Genera voce** | Vuoi voci fuori campo di qualità premium da file di sottotitoli |
| **Doppiaggio** | Vuoi una traccia di doppiaggio di alta qualità su un video tradotto |
| **Traduzione live** | Vuoi la riproduzione parlata dei sottotitoli tradotti in tempo reale |

## Clonazione vocale

ElevenLabs supporta la clonazione vocale personalizzata (piano a
pagamento). Una volta clonata una voce sul sito ElevenLabs, incolla
il suo ID voce in **Impostazioni → Servizio → ID voce** e la pipeline
di doppiaggio / generazione vocale lo userà.

## Avvertenze

!!! warning "Verifica pre-flight"
    Le pagine Voce / Doppiaggio verificano che la tua chiave API
    ElevenLabs sia impostata *prima* di iniziare il lavoro. Se manca,
    otterrai un dialogo amichevole che ti indirizza alle Impostazioni,
    non un'attività mezza eseguita.

!!! tip "La modalità Live ricade automaticamente"
    Sulla pagina **Traduzione live**, se hai selezionato ElevenLabs
    ma non hai configurato una chiave, l'app ricade su **Edge TTS**
    (gratuito) e annuncia il fallback nell'etichetta di stato in modo
    che tu possa risolverlo a tuo comodo.

!!! info "FFmpeg ancora richiesto"
    ElevenLabs restituisce byte audio; l'app usa ancora FFmpeg per
    convertire tra formati e combinare clip temporizzati in un file.
    Vedi [Configurazione FFmpeg](ffmpeg.md).

## Errori comuni

| Errore | Causa probabile |
|---|---|
| `AUTH_ERROR` | Chiave API errata / scaduta. Reincolla in Impostazioni → Servizio. |
| `QUOTA_ERROR` | Limite caratteri del livello gratuito raggiunto, o piano a pagamento esaurito. |
| `MODEL_NOT_FOUND` | Il modello ElevenLabs selezionato non è più disponibile; scegline un altro in Impostazioni → Voce. |
