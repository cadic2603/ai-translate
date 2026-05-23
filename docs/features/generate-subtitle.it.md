---
description: Genera sottotitoli SRT, VTT, ASS o SSA da qualsiasi audio o video — usa Whisper o Google Cloud Speech-to-Text per trascrizione di alta qualità.
---

# Genera sottotitolo (STT)

Trascrive audio o video in sottotitoli con timing. Cattura il parlato
ed emette SRT / VTT / ASS / SSA — con traduzione opzionale nello stesso passaggio.

## Cosa ti serve

- **FFmpeg** in `PATH` per la decodifica audio/video — vedi [Setup FFmpeg](../setup/ffmpeg.md).
- Un backend di trascrizione, uno di:
    - **faster-whisper** — locale, offline, gratis (default; nessun setup necessario)
    - **Google Cloud Speech-to-Text** — cloud, a pagamento, più accurato su audio rumoroso. Vedi [Setup Google Cloud](../setup/google-cloud.md).
    - **Soniox** — cloud, a pagamento, tempo reale e diarizzazione speaker. Vedi [Setup Soniox](../setup/soniox.md).

## Procedura

1. Clicca **Genera sottotitolo** nella barra laterale.
2. Rilascia uno o più file audio / video (`.mp3`, `.wav`, `.m4a`,
   `.flac`, `.ogg`, `.aac`, `.wma`, `.mp4`, `.webm`, `.mkv`, `.avi`,
   `.mov`, `.wmv`).
3. Scegli la **Lingua sorgente** (la lingua *parlata* nell'audio) —
   lascia su `Rilevamento automatico` per farla scoprire a Whisper.
4. Scegli una **Lingua destinazione** — scegli `Nessuna traduzione`
   per una trascrizione semplice, o una qualsiasi delle 45 lingue
   supportate per tradurre la trascrizione nello stesso passaggio.
5. Scegli il **Formato di output** (SRT / VTT / ASS / SSA).
6. Clicca **Genera** (o `Ctrl+Invio`).
7. Guarda la coda. **Apri** la riga quando fatto.

## Scelta formato

| Formato | Migliore per |
|---|---|
| **SRT** | Universale — quasi ogni player lo supporta |
| **VTT** | Elementi `<track>` di HTML5 `<video>` |
| **ASS / SSA** | Karaoke, sottotitoli stilizzati, flussi fansub |

I quattro formati fanno round-trip attraverso lo stesso parser, quindi
puoi cambiare formato output su una ri-traduzione senza perdere il timing.

## Dimensione modello Whisper

Cambia in **Impostazioni → Sottotitolo**:

| Modello | Dimensione | Velocità | Accuratezza |
|---|---|---|---|
| `tiny` | ~75 MB | molto veloce | bassa |
| `base` (default) | ~150 MB | veloce | discreta |
| `small` | ~500 MB | media | buona |
| `medium` | ~1.5 GB | lento | alta |
| `large` | ~3 GB | molto lento | migliore |

I modelli si scaricano al primo uso e vengono cacheati localmente.
Su connessione lenta la prima esecuzione sembra lunga; le successive
sono veloci.

## Confronto metodi STT

| Backend | Costo | Online? | Diarizzazione speaker | Lingue |
|---|---|---|---|---|
| **Whisper** (locale) | Gratis | No | No | 99 |
| **Google Cloud STT** | A pagamento | Sì | Sì (modello `latest_long`) | 125+ |
| **Soniox** | A pagamento | Sì | Sì (label per token) | 60+ |

Cambia in **Impostazioni → Sottotitolo → Metodo STT**.

## Suggerimenti

- **Pulsante Stop** — interrompe un batch in corso. I file in coda
  dietro l'attivo restano in coda; puoi riprendere più tardi.
- **Ri-genera** — clic destro su una voce Done per rieseguire con
  formato / lingua / metodo STT diverso.
- **Audio lungo** — Whisper gestisce ore di audio bene; budget di
  ~1 minuto di elaborazione per minuto di audio su CPU con modello `base`.

## Scorciatoie

| Scorciatoia | Azione |
|---|---|
| `Ctrl+Invio` | Genera |
| `Ctrl+O` | Sfoglia |
| `Ctrl+F` | Focus ricerca cronologia |
