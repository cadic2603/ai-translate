---
description: Esponi AI Translate come strumenti Model Context Protocol affinché Claude Desktop, Claude Code e altri client MCP possano tradurre testo, file e audio.
---

# Server MCP (`ait-mcp`)

Espone la pipeline di traduzione come strumenti **Model Context
Protocol** affinché agenti AI come Claude Desktop e Claude Code possano
guidarla direttamente — "Traduci questo PDF in francese" diventa una
chiamata di strumento, non un copia-incolla.

## Cosa viene esposto

Nove strumenti:

| Strumento | Scopo |
|---|---|
| `translate_text` | Tradurre una lista di stringhe |
| `translate_document` | Mettere in coda task di traduzione di file (restituisce ID dei task) |
| `get_task_status` | Polling stato del task |
| `cancel_task` | Cancellazione cooperativa di task in corso |
| `extract_image_text` | OCR o LLM vision |
| `transcribe_audio` | Audio → SRT |
| `synthesize_speech` | Testo → MP3 / WAV |
| `query_glossary` | Elencare set / voci di glossario |
| `list_languages` | Tutte le 45 lingue supportate |

## Eseguire il server

```bash
ait-mcp                       # trasporto stdio (default per agenti desktop)
ait-mcp --transport sse       # Server-Sent Events per client web
ait-mcp --transport sse --port 9000
```

`stdio` è ciò che ogni client MCP si aspetta a meno che tu non abbia
configurato esplicitamente SSE.

## Aggiungere a Claude Desktop

1. Apri Claude Desktop → **Settings → Developer → Edit Config**
2. Aggiungi questa voce sotto `mcpServers`:

    ```json
    {
      "mcpServers": {
        "ai-translate": {
          "command": "uv",
          "args": ["run", "--project", "/absolute/path/to/ai-translate", "ait-mcp"]
        }
      }
    }
    ```

    Sostituisci `/absolute/path/to/ai-translate` con il percorso del repo clonato.

3. Esci e riapri Claude Desktop. L'icona del martello dovrebbe ora
   mostrare "ai-translate" con tutti i 9 strumenti. Prova:

    > "Traduci questo PDF (`/home/me/report.pdf`) in francese — salva
    > l'output accanto alla sorgente."

## Aggiungere a Claude Code

`~/.config/claude-code/mcp_servers.json` (o `claude mcp add` da
dentro Claude Code):

```json
{
  "ai-translate": {
    "command": "uv",
    "args": ["run", "--project", "/absolute/path/to/ai-translate", "ait-mcp"]
  }
}
```

Riavvia Claude Code. Gli stessi 9 strumenti diventano richiamabili.

## Aggiungere ad altri client MCP

Qualsiasi client compatibile MCP assume una forma simile:

- **Command** — `uv run --project /path/to/ai-translate ait-mcp`
- **Transport** — stdio (default)

Per client basati su HTTP / SSE, esegui
`ait-mcp --transport sse --port 9000` e punta il client a
`http://localhost:9000`.

## Garanzie di validazione

Ogni strumento restituisce la stessa forma sugli errori in modo che
gli agenti possano gestire i fallimenti in modo coerente:

| Input errato | Risposta dello strumento |
|---|---|
| Lingua sconosciuta | `ValueError: Unknown … language '<input>'. Call list_languages to see supported values.` |
| LLM non configurato | `RuntimeError: LLM is not configured. Run the desktop app and set up your API key…` |
| Tipo file non supportato | `ValueError` che elenca le estensioni consentite |
| `model="…"` malformato (senza `:`) | `ValueError` invece di usare silenziosamente il default |
| ID task sconosciuti in `cancel_task` | Restituiti nell'array `unknown` — nessun errore |
| FFmpeg mancante in `transcribe_audio` | `RuntimeError: FFmpeg is required…` (riavvolto dal tag `FFMPEG_NOT_FOUND` grezzo del motore) |

Gli agenti che chiamano questi strumenti possono fare affidamento su
questi contratti.

## Concorrenza

`translate_document` esegue la pipeline in un thread daemon. Ogni
batch riceve il proprio evento di cancellazione, così cancellare un
batch non disturba un altro. Il server MCP traccia le pipeline attive
in una mappa locale al processo (pulita automaticamente quando la
pipeline finisce).

## Casi d'uso

- **"Traduci la doc di questa codebase in vietnamita"** — punta
  l'agente alla cartella docs, esegue batch di chiamate
  `translate_document` e fa polling di `get_task_status` finché
  ognuno finisce.
- **"Quali lingue supportate?"** — l'agente chiama `list_languages`,
  legge la risposta.
- **"Traduci questa ricevuta giapponese"** — l'agente chiama
  `extract_image_text` sulla foto, poi `translate_text` sul risultato.
- **"Genera sottotitoli vietnamiti per questa registrazione Zoom"** —
  l'agente chiama `transcribe_audio` per ottenere un SRT nella lingua
  sorgente, poi `translate_text` su ogni cue per localizzare, e
  riassembla l'SRT.

!!! note "Il doppiaggio video non è uno strumento MCP"
    La pipeline completa STT → tradurre → TTS → mux (la pagina
    **Doppiaggio** dell'app desktop) è disponibile solo tramite la
    GUI al momento. Da MCP puoi comporre l'equivalente da solo con
    `transcribe_audio` + `translate_text` + `synthesize_speech`, ma
    devi gestire il passaggio di mux consapevole del timing (FFmpeg)
    all'esterno.

## Suggerimenti

!!! tip "Configura una volta, gli agenti funzionano ovunque"
    Il server MCP condivide chiavi API e impostazioni con l'app
    desktop e il CLI. Configura il tuo LLM / OCR / TTS una volta nella
    GUI, poi ogni agente che parla con `ait-mcp` eredita lo stesso setup.

!!! tip "Cache endpoint cold-start"
    Per ogni coppia `(endpoint, modello)`, la scelta
    chat-vs-responses-API e la variante di payload funzionante sono
    persistite in `llm_endpoint_cache.json` nella directory cache OS
    (`~/.cache/ai-translate/` su Linux,
    `~/Library/Caches/ai-translate/` su macOS,
    `%LOCALAPPDATA%\ai-translate\cache\` su Windows). Processi
    `ait-mcp` freschi saltano completamente il probe di
    auto-rilevamento dopo la prima chiamata riuscita — agenti che
    spawnano il server su richiesta non pagano i round-trip di
    rilevamento varianti su ogni invocazione. La cache è sicura
    multi-processo e multi-thread (read-merge-write sotto RLock con
    rename atomico).

!!! tip "Selettore modello per strumento"
    Gli strumenti `translate_text` e `translate_document` accettano
    un parametro `model` opzionale — gli agenti possono scegliere un
    modello veloce per turni rapidi e uno più pesante per output di
    produzione senza richiedere all'utente di riconfigurare l'app desktop.

!!! warning "Pipeline a lunga esecuzione"
    `translate_document` ritorna immediatamente con ID dei task. Ci
    si aspetta che l'agente faccia polling di `get_task_status` finché
    ogni task raggiunge `Done` o `Failed`. Non aspettare in modo
    sincrono dentro la chiamata dello strumento; rischia di far
    scattare il timeout del client MCP.
