---
description: Traduci il tuo primo documento con AI Translate in 5 minuti — trascina e rilascia un PDF, scegli una lingua di destinazione e scarica la copia tradotta.
---

# La tua prima traduzione

Un'esecuzione end-to-end veloce — meno di 5 minuti una volta fatto il setup.

!!! abstract "Prima di iniziare"
    Devi avere completato l'[installazione](installation.md) e
    configurato una chiave API LLM. Il livello gratuito di Google
    Gemini è sufficiente per un primo tentativo.

## Tradurre un documento Word

1. Avvia l'app desktop:

    ```bash
    uv run python -m src.main
    ```

2. Clicca su **Traduci documento** nella barra laterale sinistra.

3. Trascina qualsiasi file `.docx` nell'area di rilascio — o clicca
   **Sfoglia** per sceglierne uno.

4. Il file appare nella coda. Scegli una lingua di destinazione in alto:

    - Sorgente: `Rilevamento automatico` (predefinito — di solito corretto)
    - Destinazione: es. `Francese`, `Vietnamita`, `Giapponese`, `Cinese (Semplificato)`

5. Clicca **Traduci** (o premi `Ctrl+Invio`).

6. Guarda la barra di progresso nella tabella della cronologia in
   fondo alla pagina. Quando raggiunge il 100%, clicca **Apri** sulla
   riga per aprire il file tradotto — salvato accanto all'originale
   con un suffisso `_translated_<src>_<tgt>`.

## Cosa è appena successo

- Il tuo `.docx` è stato clonato in una cartella di archiviazione
  per task così l'originale non viene toccato.
- Il testo è stato estratto, raggruppato in chunk adatti all'LLM,
  tradotto, poi reiniettato nel documento con tutta la formattazione
  preservata (grassetto, corsivo, font, colori, intestazioni, note
  a piè di pagina, hyperlink…).
- Una voce di cronologia è stata scritta in un database SQLite così
  puoi riaprire, ri-eseguire o ritradurre il file più tardi.

## Prova ora le vincite veloci

=== "Tradurre testo semplice"

    Salta in **Traduci testo** nella barra laterale. Incolla qualsiasi
    cosa, scegli una destinazione, premi Invio. Output in streaming,
    scambio lingue (`Ctrl+L`), modalità modifica, riproduzione TTS.

=== "Generare sottotitoli"

    **Genera sottotitolo** — rilascia un `.mp4`. Riceverai un `.srt`
    nella lingua sorgente. (Per tradurre _e_ doppiare il video, usa
    la pagina Doppiaggio invece.)

=== "Traduzione microfono dal vivo"

    **Traduzione live** — scegli microfono o audio di sistema, scegli
    una destinazione, Avvia. Una finestra overlay flottante mostra i
    sottotitoli in tempo reale.

## Dove andare dopo

- Vedi l'[indice delle funzionalità](../index.md#headline-features) per cosa fa ogni pagina.
- Collega [altri provider](../setup/llm-providers.md) (endpoint personalizzati, ElevenLabs, Soniox, Google Cloud).
- Prova il [CLI](../cli.md) per esecuzioni batch / scriptate.
