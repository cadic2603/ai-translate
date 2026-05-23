---
description: Traduci istantaneamente frammenti di testo in 45+ lingue con AI Translate — incolla, digita o parla; supporta modalità modifica, riproduzione TTS e scambio lingue.
---

# Traduci testo

Traduzione LLM istantanea con auto-rilevamento, scambio lingue, output
in streaming e riproduzione TTS. Migliore per frammenti brevi, uso
stile chat e test della configurazione LLM.

## Procedura

1. Clicca **Traduci testo** nella barra laterale.
2. Digita o incolla il testo sorgente nel pannello sinistro.
3. La lingua **Sorgente** si auto-rileva mentre digiti (alimentato da `langdetect`).
4. Scegli una lingua **Destinazione** dal dropdown destro.
5. Clicca **Traduci** (o premi `Ctrl+Invio`).
6. La traduzione fluisce in streaming token per token nel pannello destro.

## Cosa ottieni

- **Output in streaming** — la traduzione appare mentre l'LLM la
  genera, nessuna attesa per la risposta intera.
- **Auto-rilevamento sorgente** — il selettore sorgente si aggiorna
  in tempo reale. Clicca per sovrascrivere.
- **Modalità modifica** — clicca sul pannello destro per modificare
  la traduzione manualmente. Premi `Esc` per annullare una traduzione
  in volo; premilo di nuovo per uscire dalla modalità modifica.
- **Riuso cronologia** — ogni traduzione viene salvata. Clicca una
  voce nel pannello Cronologia traduzione testo sotto per ricaricare
  entrambi i pannelli; le modifiche aggiornano la voce originale
  invece di creare un duplicato.
- **Riproduzione TTS** — clicca **Ascolta** accanto a un pannello per
  sentirlo letto ad alta voce. Onora la tua selezione in
  **Impostazioni → Voce → Metodo TTS** — Edge TTS (default),
  ElevenLabs, Google Cloud TTS, Gemini TTS o **Piper TTS**
  (completamente offline). Con Piper selezionato, il pulsante Ascolta
  esegue lo stesso pre-flight della pagina Voce: una voce per lingua
  mancante mostra un dialog modal con pulsante **Apri Impostazioni**
  per scaricarla. I cache hit saltano il pre-flight completamente.
- **Selettore modello per funzionalità** — quando sono configurati
  più LLM, un dropdown ti lascia scegliere un modello Flash veloce
  per velocità o un modello Pro più pesante per qualità, solo per
  questa pagina.

## Scorciatoie

| Scorciatoia | Azione |
|---|---|
| `Ctrl+Invio` | Traduci |
| `Ctrl+L` | Scambia sorgente ↔ destinazione |
| `Esc` | Annulla traduzione in volo, o esci dalla modalità modifica |
| `Ctrl+F` | Focus ricerca cronologia |

## Suggerimenti

!!! tip "Lingue RTL"
    Le traduzioni in **Arabo**, **Ebraico** o **Persiano** si
    renderizzano automaticamente da destra a sinistra nel pannello
    output. La stessa gestione RTL viene portata all'output file in
    ogni formato sulla pagina [Traduci documento](translate-document.md)
    (PDF, DOCX, PPTX, XLSX, ODF, RTF, HTML, EPUB, ASS/SSA), e il
    Persiano ottiene una voce `fa-IR` nativa per la riproduzione Edge TTS.

!!! tip "Cache pulsante Ascolta"
    La prima volta che premi Ascolta per una coppia (testo, lingua)
    data, l'audio viene sintetizzato e cacheato su disco. Le
    riproduzioni successive sono istantanee. Il cache viene cancellato
    all'avvio dell'app, quindi ogni sessione inizia fresca.

!!! tip "Dove vanno le chiavi"
    La pagina Traduci testo legge le stesse voci keychain del resto
    dell'app — vedi [Provider LLM](../setup/llm-providers.md).
