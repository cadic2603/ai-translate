---
description: "Doppia video end-to-end: trascrivi l'audio, traduci i sottotitoli, sintetizza il parlato nella lingua di destinazione e mixalo nel video originale."
---

# Doppiaggio video

Pipeline completo **STT → Tradurre → TTS → Mix** che produce un file
video in un'altra lingua con la traccia vocale sostituita. L'audio
originale viene scartato; la nuova traccia di doppiaggio è temporizzata
sui sottotitoli.

## Cosa ti serve

- **FFmpeg** in `PATH` — vedi [Setup FFmpeg](../setup/ffmpeg.md).
- Un backend STT (default: Whisper locale, nessun setup necessario)
- Un backend TTS — Edge TTS (default), ElevenLabs, Google Cloud TTS,
  Gemini TTS, o **Piper TTS** (completamente offline; voci per lingua
  scaricate una volta via **Impostazioni → Voce → Piper TTS → Scarica
  voci ora**)
- Un **LLM** configurato per il passo di traduzione

## Procedura

1. Clicca **Doppiaggio** nella barra laterale.
2. Rilascia uno o più file video (`.mp4`, `.webm`, `.mkv`, `.avi`,
   `.mov`, `.wmv`).
3. Scegli la **Lingua sorgente** (la lingua *parlata* nel video) e
   la **Lingua destinazione** in cui doppiare.
4. Clicca **Avvia doppiaggio** (`Ctrl+Invio`).
5. Guarda il progresso per task nella tabella della cronologia.
   Passa attraverso quattro fasi:

| Fase | Range | Cosa succede |
|---|---|---|
| **STT** | 5–25% | Trascrizione dell'audio sorgente |
| **Tradurre** | 25–50% | LLM traduce ogni riga di sottotitolo |
| **TTS** | 50–90% | Sintesi voce lingua-destinazione per ogni riga |
| **Mix** | 90–100% | FFmpeg sostituisce la traccia audio |

6. Quando completo, **Apri** la riga per riprodurre il video doppiato.

## Output

Per ogni video di input ottieni quattro file nella directory di output:

```
movie.mp4
movie_dubbed_en_fr.mp4              ← video doppiato
movie_subtitle_en.srt               ← sottotitolo lingua originale
movie_subtitle_fr.srt               ← sottotitolo tradotto
movie_voice_fr.mp3                  ← traccia vocale sintetizzata
```

## Riprendere un'esecuzione in pausa / crashata

Il pipeline fa checkpoint dopo ogni fase. Se premi **Stop**, esci
dall'app o crashi, premere **Continua** sulla riga riprende dall'ultima
fase completata — non ripaghi per STT o traduzione se erano già fatti.

Clic destro su una voce Done / Failed per queste opzioni:

- **Continua** — riprende dall'ultimo checkpoint senza ri-prompt.
- **Ri-doppiare** — riapre il selettore lingua; se scegli un nuovo
  destinazione, i checkpoint tradurre e TTS vengono scartati (non
  ripaghi per STT). Scegliere la stessa destinazione di fatto
  riesegue dall'ultimo checkpoint, come Continua.
- **Apri** — riproduce il video doppiato.

## Avvertenze

!!! warning "Sincronizzazione labiale"
    Il doppiaggio corrisponde ai *timestamp* dell'audio sorgente,
    non ai movimenti delle labbra. Le righe tradotte molto più lunghe
    dell'originale suoneranno frettolose; le molto più corte
    lasceranno silenzio. Per il doppiaggio professionale di solito
    si re-temporizza manualmente dopo questo passaggio — è una
    funzionalità futura.

!!! tip "Verifiche pre-flight"
    La pagina valida FFmpeg + le chiavi del tuo backend TTS prima di
    iniziare. Chiave mancante → dialog amichevole, nessun doppiaggio
    a metà. Con **Piper TTS** selezionato, verifica anche che la voce
    Piper per lingua sia su disco; voce mancante → dialog modal con
    pulsante **Apri Impostazioni** che ti porta nella libreria voci,
    così non bruci tempo STT + traduzione per fallire al passo TTS.

!!! tip "Cambiare lingua destinazione"
    Su un re-target il pipeline scarta i checkpoint tradurre + TTS
    (il loro contenuto non è più valido per la nuova lingua) ma
    conserva il checkpoint STT — risparmi il costo di trascrizione.

## Scorciatoie

| Scorciatoia | Azione |
|---|---|
| `Ctrl+Invio` | Avvia doppiaggio |
| `Ctrl+O` | Sfoglia |
| `Ctrl+F` | Focus ricerca cronologia |
| `Ctrl+P` | Pausa coda attiva |
| `Ctrl+G` | Continua (riprendi) coda attiva |

`Ctrl+P` / `Ctrl+G` sono soppressi quando un text-input ha il focus,
così non collidono con la digitazione.
