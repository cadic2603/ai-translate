---
description: "Traduzione vocale in tempo reale: trascrivi e traduci microfono o audio di sistema dal vivo con backend Whisper o Soniox."
---

# Traduzione live

Sottotitoli e traduzioni in tempo reale dal microfono, dall'audio di
sistema o da entrambi — con una finestra overlay sempre in primo piano
opzionale, in modo che i sottotitoli stiano sopra qualsiasi cosa tu
stia guardando.

## Cosa puoi farci

- **Sottotitoli per riunioni dal vivo** — sottotitola una chiamata Zoom
  / Meet / Teams in un'altra lingua senza entrare come bot traduttore.
- **Apprendimento linguistico in tempo reale** — sottotitola contenuti
  in lingua straniera (film, podcast, lezioni) con la tua lingua nativa
  come traccia di traduzione.
- **Sottotitoli a livello di sistema** — cattura l'audio di sistema per
  sottotitolare YouTube / Netflix / qualsiasi cosa venga riprodotta
  sui tuoi altoparlanti.

## Cosa ti serve

- **FFmpeg** in `PATH` — vedi [Configurazione FFmpeg](../setup/ffmpeg.md).
- Un backend STT, uno tra:
    - **faster-whisper** — locale, offline, gratuito, predefinito
    - **Soniox** — cloud, a pagamento, diarizzazione speaker in tempo reale. Vedi [Configurazione Soniox](../setup/soniox.md).

- Per la **cattura audio di sistema**, il backend giusto per OS è
  selezionato automaticamente: Linux usa `parec` (PulseAudio /
  PipeWire), Windows usa il loopback WASAPI nativo (nella maggior parte
  dei casi senza software extra), macOS usa `ffmpeg -f avfoundation`
  contro un dispositivo loopback virtuale (BlackHole / Loopback /
  ecc.). Compare un banner di avviso inline con link di installazione
  cliccabili se manca qualcosa. Vedi
  [Configurazione → Audio di sistema](../setup/system-audio.md) per
  istruzioni complete di installazione per OS.

## Passo passo

1. Clicca su **Traduzione live** nella barra laterale.
2. Configura una volta in **Impostazioni → Live**:

    - **Lingua di origine** (lingua parlata)
    - **Lingua di destinazione** (o lascia vuoto per sola trascrizione)
    - **Sorgente audio**: Microfono / Audio di sistema / Entrambi
    - **Metodo STT**: Whisper / Soniox

3. Tornato sulla pagina Live, clicca su **Avvia** (`Ctrl+Enter`).
4. La trascrizione riempie il riquadro principale carta per carta. La
   finestra **Overlay** fluttuante mostra anche i sottotitoli
   (trascinala dove vuoi).
5. Clicca su **Stop** per terminare la sessione.

## La vista trascrizione

Scegli un layout nella barra degli strumenti:

- **Entrambi impilati** — originale + traduzione, uno sopra l'altro
- **Entrambi affiancati** — originale a sinistra, traduzione a destra
- **Solo originale** / **Solo traduzione**

I pulsanti della barra degli strumenti usano suffissi **`ON`** /
**`OFF`** per lo stato a colpo d'occhio — es. `TTS ON`, `TTS OFF`,
`Timestamp ON`, `Overlay OFF`.

Attiva/disattiva i **timestamp** con l'icona dell'orologio. Attiva/
disattiva la **riproduzione TTS** delle righe tradotte con l'icona
dell'altoparlante. Rispetta la tua scelta in **Impostazioni → Voce →
Metodo TTS** — Edge TTS (predefinito), ElevenLabs, Google Cloud TTS,
Gemini TTS o **Piper TTS** (completamente offline). Con Piper
selezionato, le voci mancanti per lingua **ricadono silenziosamente
su Edge TTS** durante lo stream — non c'è un modale di pre-flight
su questa pagina, poiché bloccare il flusso live con una finestra di
download sarebbe peggio del fallback.

## La finestra overlay

Una finestra strumenti trascinabile, ridimensionabile, sempre in primo
piano. Scorciatoie:

| Scorciatoia | Azione |
|---|---|
| `Ctrl+[` / `Ctrl+]` | Diminuisci / aumenta opacità |
| `Ctrl+Freccia` | Sposta l'overlay |
| `Ctrl+0` / `Ctrl+9` | Ingrandisci / rimpicciolisci |

Posizione, dimensione, opacità e dimensione del carattere persistono
tra le sessioni.

### Sincronizzazione live con le impostazioni

I controlli di dimensione del carattere e opacità funzionano in
entrambe le direzioni: trascinare il cursore **Dimensione
carattere** o **Opacità** in **Impostazioni → Traduzione live →
Configurazione overlay** aggiorna l'overlay aperto in tempo
reale e, viceversa, premere `+` / `-` / `Ctrl+[` / `Ctrl+]`
all'interno dell'overlay aggiorna i cursori in Impostazioni.
Non è necessario riavviare l'overlay.

### Segnaposto stato vuoto

Prima che venga catturato qualsiasi audio l'overlay mostra un
segnaposto ("Premi Avvia..." inattivo / "In ascolto..." dopo
aver fatto clic su Avvia) che rispecchia lo stato vuoto della
finestra principale — lo scambio rimane sincronizzato con il
pulsante di stato in esecuzione. Il segnaposto si adatta alla
larghezza × altezza corrente dell'overlay per rimanere leggibile
con qualsiasi dimensione della finestra.

### Modalità didascalie minime

La casella **Mostra didascalie minime** in Impostazioni →
Traduzione live → Configurazione overlay nasconde le etichette
di timestamp e oratore sull'overlay mantenendole visibili sulla
finestra principale. Utile quando l'overlay è condiviso con un
pubblico (modalità presentatore / condivisione schermo) ma si
desidera conservare i metadati completi nella propria vista di
lavoro. L'opzione è solo per l'overlay — non cambia la
preferenza "Etichette oratore" della finestra principale.

## Salvare la trascrizione

Clicca su **Salva trascrizione** per esportare la sessione in un file
`.txt` con timestamp, speaker, righe originali e righe tradotte.

## Scegliere un backend STT

| Backend | Migliore per | Costo | Latenza |
|---|---|---|---|
| **Whisper** (locale) | Offline, sensibile alla privacy | Gratuito | Media (~1 s dopo fine frase) |
| **Soniox** | Riunioni multi-speaker | A pagamento (~$0,005 / min) | Bassa (tempo reale) |

## Avvertenze

!!! warning "Selezione del microfono"
    L'ingresso microfono usa sempre il **dispositivo predefinito
    dell'OS** — non c'è un selettore in-app (sounddevice espone troppi
    plugin ALSA virtuali per essere utile, e l'OS già possiede la UI
    per il microfono predefinito). Imposta il tuo microfono preferito
    nelle impostazioni audio dell'OS prima di iniziare.

!!! warning "Backpressure TTS"
    La coda TTS è limitata alle 3 frasi più recenti — l'audio in coda
    più vecchio viene scartato se la sintesi rimane indietro. Questo
    mantiene la riproduzione vocale vicina ai sottotitoli sullo
    schermo.

!!! tip "ElevenLabs senza chiave"
    Se hai impostato il metodo TTS su ElevenLabs ma non è configurata
    nessuna chiave API, la pagina Live ricade automaticamente su Edge
    TTS e annuncia il fallback nell'etichetta di stato.

## Scorciatoie

| Scorciatoia | Azione |
|---|---|
| `Ctrl+Enter` | Avvia / Ferma |
| `Ctrl+K` | Pulisci log (con conferma) |
| `Ctrl+[` / `Ctrl+]` | Regola opacità overlay |
