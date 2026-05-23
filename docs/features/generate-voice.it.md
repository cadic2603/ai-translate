---
description: Converti i sottotitoli in audio parlato con Edge TTS, ElevenLabs, Google Cloud TTS, Gemini TTS o Piper TTS offline — preserva il timing SRT per generazione vocale di qualità da doppiaggio.
---

# Genera voce (TTS)

Sintetizza file di sottotitoli (con timing) o testo arbitrario in
audio MP3 / WAV. Cinque backend TTS: Edge TTS (gratuito), ElevenLabs
(alta qualità), Google Cloud TTS, Gemini TTS (livello gratuito) e
Piper TTS (offline).

## Cosa ti serve

- **FFmpeg** in `PATH` — vedi [Configurazione FFmpeg](../setup/ffmpeg.md).
- Un backend TTS, uno tra:
    - **Edge TTS** — gratuito, senza chiave, predefinito. Usa le voci
      cloud di Microsoft Edge.
    - **ElevenLabs** — a pagamento, qualità massima. Vedi [Configurazione ElevenLabs](../setup/elevenlabs.md).
    - **Google Cloud TTS** — a pagamento, molto buono. Vedi [Configurazione Google Cloud](../setup/google-cloud.md).
    - **Gemini TTS** — livello gratuito, voci predefinite naturali.
      Riutilizza la tua chiave API Gemini esistente dalla scheda LLM
      — nessuna configurazione extra.
    - **Piper TTS** — TTS neurale completamente offline. Senza chiave
      API, senza chiamate di rete — le voci sono file ONNX da
      ~25–60 MB scaricati una volta tramite **Impostazioni → Voce →
      Piper TTS → Scarica voci ora**. 32 delle 45 lingue dell'app
      hanno una voce Piper oggi; le lingue senza copertura Piper
      ricadono silenziosamente su Edge TTS al momento della sintesi.

## Passo passo

1. Clicca su **Genera voce** nella barra laterale.
2. Rilascia uno o più file di sottotitoli `.srt` / `.vtt` /
   `.ass` / `.ssa`.
3. Scegli la **Lingua** (rilevata automaticamente dal nome del file
   del sottotitolo quando possibile — es. `_translated_en_it.srt` è
   rilevato come italiano).
4. Scegli il **Genere della voce** — `Femminile` o `Maschile`.
5. Scegli il **Formato di output** — `.mp3` (predefinito) o `.wav`.
6. Clicca su **Genera** (o `Ctrl+Invio`).
7. **Apri** la riga quando finito — viene riprodotto nella tua app
   audio predefinita.

## Output

Ottieni un singolo file audio con le tracce vocali posizionate al
timestamp di ogni sottotitolo. Spazi vuoti silenziosi riempiono il
tempo tra i cue in modo che l'audio rimanga sincronizzato con il
timing originale.

## Scegliere un backend TTS

| Backend | Costo | Voci | Note |
|---|---|---|---|
| **Edge TTS** | Gratuito | Centinaia, tutte le lingue principali | Predefinito. Nessuna configurazione. |
| **ElevenLabs** | A pagamento (~$5/mese livello entry) | Voci neurali premium, clonazione vocale | Qualità massima. L'ID voce è impostato in Impostazioni → Servizio. |
| **Google Cloud TTS** | A pagamento (~$4/M caratteri; 1 M gratis / mese) | Voci WaveNet / Studio in 50+ lingue | Voci WaveNet forti per lingue europee. Per impostazione predefinita il server sceglie una voce in base a lingua + genere. |
| **Gemini TTS** | Livello gratuito (si applicano le quote Developer API) | Voci predefinite naturali in 24+ lingue — `Kore` (femminile predef.) / `Puck` (maschile predef.) | Riutilizza la tua chiave API Gemini dalla scheda LLM. Output per chiamata limitato a ~30 s; testi lunghi divisi automaticamente ai confini di frase. |
| **Piper TTS** | Gratuito, **offline** | Voci neurali in 32 delle 45 lingue dell'app | Nessuna chiave, nessuna rete. Voce per lingua scaricata su richiesta da **Impostazioni → Voce → Piper TTS → Scarica voci ora** (~25–60 MB ciascuna). Il pre-flight cattura una voce mancante prima che il lavoro inizi. |

Cambia in **Impostazioni → Voce → Metodo TTS**.

## Specificità Piper TTS

Piper è l'unico backend TTS completamente offline nell'app. Alcune
cose da sapere:

- **Finestra di dialogo della libreria voci** — apri tramite
  **Impostazioni → Voce → Piper TTS → Scarica voci ora**. Ogni riga di
  lingua mostra un pulsante di download `Voce femminile` e / o
  `Voce maschile` (alcune lingue sono mono-genere). Le voci vengono
  dal catalogo HuggingFace
  [rhasspy/piper-voices](https://huggingface.co/rhasspy/piper-voices).
- **Copertura** — 32 delle 45 lingue dell'app hanno una voce Piper.
  Le 13 senza copertura (bielorusso, bengalese, cinese (tradizionale),
  croato, estone, ebraico, giapponese, khmer, coreano, lituano,
  malese, mongolo, thailandese) ricadono silenziosamente su Edge TTS
  al momento della sintesi, quindi la sintesi non fallisce mai
  duramente per una voce mancante.
- **Risoluzione del genere** — quando scegli `Femminile`, il motore
  prova prima la voce femminile per quella lingua; se esiste solo una
  voce maschile, usa quella invece (e viceversa). Registrato a livello
  INFO.
- **Cancello pre-flight** — prima che inizi un'esecuzione Voce, la
  pagina verifica che la voce Piper per la lingua sia su disco. Se
  manca, ottieni una finestra modale con un pulsante **Apri
  impostazioni** che ti porta direttamente alla libreria voci per
  scaricarla senza perdere la coda.

## Specificità Gemini TTS

Gemini TTS usa `gemini-2.5-flash-preview-tts` tramite la Developer API.
Alcune cose da sapere:

- **La selezione della voce** è oggi per genere — Femminile mappa a
  `Kore`, Maschile a `Puck`. Entrambe sono voci chiare, neutre che
  funzionano in tutte le lingue senza suonare troppo caratterizzate.
- **Limite di lunghezza dell'output** — ogni chiamata API Gemini
  restituisce al massimo ~30 s di parlato. L'app suddivide il testo
  in input sotto `_GEMINI_TTS_MAX_BYTES` (~2000 byte ≈ 30 s) ai
  confini di frase, poi concatena i pezzi tramite FFmpeg. Non
  incontrerai troncamento su testo di sottotitolo normale.
- **Formato audio** — Gemini emette PCM grezzo a 24 kHz mono s16le;
  l'app transcodifica per pezzo a MP3 (o WAV se l'hai scelto) in modo
  che il file finale corrisponda al tuo formato di output selezionato.
- **Vertex AI non è ancora supportato per TTS** — anche se la tua
  scheda LLM è configurata per Vertex, Gemini TTS ha ancora bisogno
  di una chiave API Developer. L'app solleva `AUTH_ERROR` in
  anticipo se manca.

## Modelli ElevenLabs

Tre modelli sono esposti:

| Modello | Latenza | Qualità | Da usare per |
|---|---|---|---|
| `eleven_multilingual_v2` (predef.) | Media | Alta | TTS generale |
| `eleven_v3` | Media | Massima | Studio / produzione |
| `eleven_flash_v2_5` | Bassa | Buona | Tempo reale / modalità Live |

Configura in **Impostazioni → Voce → Modello ElevenLabs**.

## Suggerimenti

!!! tip "Rigenera"
    Tasto destro su una riga → **Rigenera** per scambiare genere
    della voce / metodo TTS / formato senza rieseguire la traduzione.

!!! tip "Verifiche pre-flight"
    La pagina convalida la chiave API ElevenLabs (quando selezionata)
    e la disponibilità di FFmpeg prima di iniziare. Vedrai una
    finestra di dialogo amichevole se manca qualcosa.

!!! warning "Stop è atomico"
    Premi **Stop** durante la sintesi e non otterrai un MP3 scritto a
    metà nella directory di output — il file viene scritto prima in
    una posizione temporanea, poi spostato in posizione solo in caso
    di successo.

## Scorciatoie

| Scorciatoia | Azione |
|---|---|
| `Ctrl+Invio` | Genera |
| `Ctrl+O` | Sfoglia |
| `Ctrl+F` | Focalizza ricerca cronologia |
