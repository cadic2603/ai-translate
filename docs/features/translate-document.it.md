---
description: Traduci PDF, Word, Excel, PowerPoint, ODF, EPUB, HTML, JSON, YAML, SRT e oltre 30 altri formati di file preservando formattazione e impaginazione.
---

# Traduci documento

Traduci file completi — Office, PDF, EPUB, testo semplice, sottotitoli,
formati di localizzazione e altro — con la formattazione preservata.

## Formati supportati

| Categoria | Estensioni |
|---|---|
| Office | `.docx`, `.xlsx`, `.pptx`, `.odt`, `.ods`, `.odp`, `.doc`, `.xls`, `.ppt` |
| PDF | `.pdf` |
| Testo & web | `.txt`, `.md`, `.rst`, `.html`, `.htm`, `.xhtml`, `.xml`, `.rtf`, `.json`, `.csv` |
| eBook | `.epub` |
| Sottotitoli | `.srt`, `.vtt`, `.ass`, `.ssa` |
| Localizzazione | `.po`, `.pot`, `.xliff`, `.xlf`, `.yaml`, `.yml`, `.properties`, `.strings` |

## Passo passo

1. Clicca su **Traduci documento** nella barra laterale.
2. Trascina i file dentro (o clicca su **Sfoglia**). Anche le cartelle
   funzionano — i file supportati al loro interno vengono raccolti
   ricorsivamente.
3. Scegli **Origine** (o lascia su `Rilevamento automatico`) e
   **Destinazione**.
4. Clicca su **Traduci** — o premi `Ctrl+Invio`.
5. La tabella della cronologia sotto mostra l'avanzamento per file
   (In attesa → Traduzione → Fatto / Fallito). La barra laterale
   mostra uno spinner mentre un'attività è attiva.
6. Clicca su **Apri** su una riga per aprire il file tradotto.
   Tasto destro per le opzioni: ritraduci, metti in pausa, riprova,
   elimina.

## Dove finiscono i file

Per impostazione predefinita, i file tradotti vengono salvati accanto
all'originale con un suffisso `_translated_<src>_<tgt>`:

```
~/Documents/relazione.docx
~/Documents/relazione_translated_en_it.docx     ← qui
```

Modificalo in **Impostazioni → Generale → Percorso di archiviazione
delle traduzioni** in una directory personalizzata.

## Limiti e protezioni

- **Limite di 100 file per drop** — trascinandone di più riceverai una
  notifica. Traduci a lotti.
- **Rilevamento duplicati** — trascina un file già in coda e vedrai
  una notifica (il duplicato viene scartato, non aggiunto due volte).
- **Ripresa automatica** — chiudi l'app mentre le traduzioni sono in
  esecuzione e riprenderanno al successivo avvio (attività In attesa /
  Traduzione).

## Opzioni specifiche per Office

La scheda Traduzione in **Impostazioni** espone questi interruttori
per i file Office:

| Opzione | Cosa fa |
|---|---|
| **Traduci immagini incorporate** | Esegue OCR + LLM vision sulle immagini all'interno di `.docx` / `.xlsx` / `.pptx` e reinserisce l'immagine tradotta. Richiede OCR configurato. |
| **Traduci commenti** | I commenti / note di revisione vengono tradotti insieme al testo del corpo. |
| **Traduci forme & caselle di testo** | Cattura il testo che vive in forme, callout e caselle di testo fluttuanti. |
| **Traduci note del relatore** | Le note del relatore di PowerPoint vengono tradotte. |
| **Traduci nomi dei fogli** | Le etichette delle schede dei fogli Excel vengono tradotte. |
| **Conversione automatica legacy** | `.doc` / `.xls` / `.ppt` vengono convertiti in OOXML moderno prima della traduzione (migliore fedeltà). |
| **Conversione automatica ODF** | `.odt` / `.ods` / `.odp` vengono convertiti in OOXML prima della traduzione. |

Tutta la traduzione Office preserva la formattazione per run:
grassetto, corsivo, sottolineato, barrato, dimensione del font,
colore, hyperlink, intestazioni, piè di pagina, note a piè di pagina,
note di chiusura, tutto.

### Traduzione di immagini incorporate: salta-con-avviso + cache

Quando **Traduci immagini incorporate** è attivo, ogni immagine
incorporata passa attraverso OCR → visione LLM →
reiniezione renderizzata. Due comportamenti da conoscere:

- **Salta-con-avviso**: se un'immagine non può essere tradotta
  (troppo grande, danneggiata, il modello di visione rifiuta
  il formato, ecc.) il documento si completa comunque —
  l'immagine rotta rimane nella lingua originale, un avviso
  viene registrato in `app.log` e il ciclo continua con
  l'immagine successiva. Solo gli errori LLM fatali
  (`AUTH_ERROR`, `QUOTA_ERROR`, `VISION_NOT_SUPPORTED`)
  arrestano la pipeline immediatamente perché bloccano anche
  tutte le immagini rimanenti. Il banner informativo sopra
  la casella **Traduci immagini incorporate** documenta la
  politica inline.
- **Cache per-immagine**: le traduzioni di immagini riuscite
  vengono mantenute nella directory di archiviazione interna
  dell'attività con chiave SHA256 dei byte di origine. Al
  riprovo, le immagini già tradotte raggiungono la cache
  invece di rieseguire OCR + LLM — il lavoro pagato non
  viene ripetuto. Le immagini duplicate (un logo aziendale
  in ogni slide) vengono tradotte una volta e riutilizzate
  N − 1 volte.

Il file di output appare nella cartella di output scelta
solo in caso di **successo** — le traduzioni parziali da
esecuzioni annullate o fallite rimangono confinate nella
directory di archiviazione interna dell'attività, quindi la
tua cartella di output non raccoglie mai documenti orfani
tradotti a metà.

## Specificità PDF

I PDF utilizzano un motore extract-overlay: il testo originale viene
redatto sul posto e il testo tradotto viene sovrapposto nelle stesse
caselle, mantenendo l'impaginazione visiva. Il checkpoint per pagina
significa che un'esecuzione in pausa / crashata riprende da dove si
era fermata, non da pagina 1.

Cosa viene tradotto:

- Testo del corpo (con rilevamento dell'allineamento — sinistra /
  centro / destra / giustificato)
- Segnalibri / strutture (voci TOC)
- Campi modulo (input di testo, menu a discesa, caselle elenco)
- Hyperlink (rettangolo del link aggiornato per avvolgere il nuovo
  testo)
- Immagini incorporate (quando **Traduci immagini incorporate** è
  attivo)
- Commenti / annotazioni PDF

Per i PDF scansionati (senza livello di testo incorporato), l'OCR
viene eseguito automaticamente per pagina. Configura il tuo motore
OCR in **Impostazioni → OCR**.

## Output da destra a sinistra

Le traduzioni in **arabo**, **ebraico** o **persiano** vengono
renderizzate come RTL nativamente in ogni formato di output —
`dir="rtl"` iniettato in overlay PDF, HTML e capitoli EPUB (con
`page-progression-direction="rtl"` nell'OPF dell'EPUB in modo che
Apple Books e Kindle sfoglino le pagine nella direzione corretta);
DOCX `<w:bidi/>` + `<w:rtl/>`, PPTX `rtl="1"`, vista del foglio XLSX
da destra a sinistra, ODT/ODS/ODP `style:writing-mode="rl-tb"`, RTF
`\rtldoc` e mirroring dei codici di allineamento ASS/SSA (`\an1` ↔
`\an3`, `\an4` ↔ `\an6`, ecc.). Gli allineamenti centrali non
vengono toccati.

## Scorciatoie

| Scorciatoia | Azione |
|---|---|
| `Ctrl+Invio` | Avvia traduzione |
| `Ctrl+O` | Sfoglia file |
| `Ctrl+F` | Focalizza ricerca cronologia |
| `Ctrl+P` | Metti in pausa la coda attiva |
| `Ctrl+G` | Continua (riprendi) la coda attiva |
| `Canc` | Elimina voci di cronologia selezionate |

`Ctrl+P` / `Ctrl+G` sono soppressi quando un input di testo ha il
focus, in modo che non si scontrino con la digitazione.

## Quando le cose falliscono

Un'attività fallita mostra uno stato rosso con un codice di errore e
un messaggio localizzato — vedi la [guida alla risoluzione dei
problemi](../troubleshooting.md) per quelli comuni (`AUTH_ERROR`,
`QUOTA_ERROR`, `FFMPEG_NOT_FOUND`, ecc.).
