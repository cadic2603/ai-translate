---
description: Diagnostica problemi di AI Translate — font mancanti, errori FFmpeg, problemi del converter LibreOffice, fallimenti setup OCR, e autenticazione API LLM.
---

# Risoluzione problemi

Errori comuni, cosa significano, e come risolverli.

## Errori di setup

### "LLM is not configured"

Non hai ancora aggiunto una chiave API. Apri l'app desktop →
**Impostazioni → LLM** → incolla una chiave. Vedi
[Provider LLM](setup/llm-providers.md) per la guida completa.

### `AUTH_ERROR`

La chiave API LLM è sbagliata o scaduta.

- **Gemini** — genera una nuova chiave a
  <https://aistudio.google.com/apikey>, reincolla in
  **Impostazioni → LLM**.
- **Provider personalizzato** — verifica che la chiave sia valida
  (curl all'endpoint manualmente con lo stesso header
  `Authorization: Bearer …`). Se l'endpoint è cambiato, aggiorna
  anche il campo **Endpoint API**.

### `QUOTA_ERROR`

Hai raggiunto un limite del livello gratuito o del piano a pagamento.

- **Gemini livello gratuito** — la quota di richieste giornaliera
  varia per modello (vedi
  <https://ai.google.dev/gemini-api/docs/rate-limits>). Aspetta un
  giorno, o passa a pagamento.
- **OpenAI / altri** — controlla la dashboard di fatturazione. Molti
  provider hanno "spend cap" che mettono in pausa le richieste quando
  li raggiungi.

### `MODEL_NOT_FOUND`

Il nome del modello che hai scelto non è disponibile.

- Provider personalizzati — assicurati che il modello sia nella lista
  **Models** separata da virgole in **Impostazioni → LLM**.
- Lista Gemini integrata — passa a un modello documentato in
  **Impostazioni → LLM → Modello Gemini default**.

### `VISION_NOT_SUPPORTED`

Hai scelto un modello non-vision e hai provato a tradurre un'immagine
/ PDF scansionato. Passa a un modello il cui nome contenga `flash`,
`pro` o `vision` (es. `gpt-4o` per OpenAI, qualsiasi variante Gemini
Flash o Pro corrente per Gemini).

## Errori audio / video

### `FFMPEG_NOT_FOUND`

FFmpeg non è nel PATH. Vedi [Setup FFmpeg](setup/ffmpeg.md) per il
comando di installazione del tuo OS.

Il server MCP riavvolge questo come: *"FFmpeg is required to decode
this audio/video file but is not installed or not on PATH."*

### La pagina Live non mostra sottotitoli

- **Sorgente audio sbagliata** — apri **Impostazioni → Live → Sorgente
  audio** e assicurati che corrisponda a ciò che vuoi davvero
  (Microfono / Sistema / Entrambi).
- **Mic mutato** — controlla le impostazioni audio dell'OS; l'app usa
  il dispositivo di input di default.
- **Audio di sistema non configurato** — vedi
  [Cattura audio di sistema](setup/system-audio.md) per gli step
  loopback macOS / Windows.

### Output vocale silenzioso / vuoto

- **ElevenLabs senza chiave** — la pagina Voice mostra un dialog
  amichevole pre-flight; se è passato, il file potrebbe essere byte
  vuoti. Controlla **Impostazioni → Service → ElevenLabs API key**.
- **Errore di rete Edge TTS** — Edge TTS richiede internet; se il tuo
  firewall blocca `speech.platform.bing.com`, passa a ElevenLabs,
  Google Cloud TTS, o **Piper TTS** (completamente offline).

### Dialog "Piper voice not installed"

Le pagine Voice / Dubbing / Translate Text controllano pre-flight che
la voce Piper per la tua lingua target sia su disco prima che parta
qualsiasi worker. Se non c'è, vedrai un modal con un bottone
**Apri Impostazioni**.

Per scaricare la voce:

1. Clicca su **Apri Impostazioni** nel dialog (o apri
   **Impostazioni → Voce** manualmente).
2. Assicurati che **Metodo TTS** sia impostato su **Piper TTS**.
3. Clicca su **Scarica voci ora** per aprire il dialog libreria voci.
4. Trova la riga della tua lingua target, poi clicca su **Female
   voice** o **Male voice** accanto. Le voci sono file ONNX di
   ~25–60 MB scaricati da HuggingFace; una volta per lingua.
5. Chiudi il dialog e riesegui il tuo job di traduzione / voice / dub.

Se la tua lingua target non è nella lista, non ha copertura Piper —
il motore ricade silenziosamente su Edge TTS al momento della sintesi,
quindi non hai bisogno di scaricare nulla davvero. Le 13 lingue senza
voci Piper oggi: bielorusso, bengalese, cinese (tradizionale), croato,
estone, ebraico, giapponese, khmer, coreano, lituano, malese, mongolo,
tailandese.

La pagina **Traduzione live** è l'unico posto che *non* mostrerà
questo dialog — interrompere uno stream live con un modal sarebbe
peggio del fallback, quindi i casi di voce mancante lì vanno
silenziosamente a Edge TTS.

## Errori di traduzione documento

### La traduzione PDF fallisce su una pagina specifica

I PDF usano checkpointing per pagina — le pagine riuscite non vengono
rifatte. La pagina fallita logga uno stack in `app.log`; colpevoli
comuni:

- La pagina è una **scansione senza layer di testo** e OCR non è
  configurato. Configura **Impostazioni → OCR** (vedi
  [Motori OCR](setup/ocr-engines.md)).
- La pagina contiene **layout matematico complesso** che l'LLM ha
  rovinato. Prova un modello più forte (una variante Pro invece di Flash).

### La traduzione Office rompe la formattazione

- **Formati moderni** (`.docx`, `.xlsx`, `.pptx`) — la formattazione
  è preservata per run via round-trip HTML. Se vedi tag `<b>` vaganti
  nell'output, l'LLM non li ha chiusi — riesegui con un modello più
  forte.
- **Formati legacy** (`.doc`, `.xls`, `.ppt`) — attiva
  **Impostazioni → Traduzione → Auto-convert legacy** per fedeltà
  molto migliore. La pipeline converte in `.docx` prima, traduce,
  riconverte.

### La coda di traduzione si ferma a metà batch

Esci dall'app e controlla il database:

```bash
sqlite3 ~/.local/share/ai-translate/translator.db \
  "SELECT id, status, error_code, file_name FROM history WHERE status NOT IN ('Done', 'Failed') ORDER BY created_at DESC LIMIT 10;"
```

Righe `Translating` non toccate da minuti significano che un worker
è crashato silenziosamente. Rilancia l'app desktop — riprende
automaticamente i task Pending / Translating all'avvio.

## Problemi trasversali

### File multipli alla volta tradotti silenziosamente come uno

Rilascia un file alla volta, OPPURE controlla la colonna **Files**
nell'header della coda — dovrebbe mostrare il conteggio che hai
rilasciato. Il cap di 100 file mostra una notifica quando superato.

### La sidebar mostra uno spinner per sempre

Indica che un worker è ancora segnalato come in esecuzione. Esci
dall'app in modo pulito (no SIGKILL) — gli hook autouse cleanup
resettano i flag. Se un SIGKILL ha lasciato lo stato bloccato, pulisci
i worker DB manualmente:

```bash
sqlite3 ~/.local/share/ai-translate/translator.db \
  "UPDATE history SET status='Failed', error_code=99 WHERE status IN ('Pending', 'Translating');"
```

### Dove sono i log? {: #where-are-the-logs }

| OS | Percorso |
|---|---|
| **Linux** | `~/.local/state/log/ai-translate/app.log` |
| **macOS** | `~/Library/Logs/ai-translate/app.log` |
| **Windows** | `%LOCALAPPDATA%\ai-translate\logs\app.log` |

I log catturano sempre DEBUG+ indipendentemente dalla verbosità della
console. L'output console è INFO+ di default; passa `--verbose` al
CLI per mirrorare il log file completo su stdout.

## Ancora bloccato?

- Vedi la [FAQ](faq.md) per domande a livello design.
- Apri un issue a <https://github.com/cadic2603/ai-translate/issues>
  con: OS, versione Python, il comando che fallisce, lo slice
  rilevante di `app.log`, e una descrizione di cosa ti aspettavi.
