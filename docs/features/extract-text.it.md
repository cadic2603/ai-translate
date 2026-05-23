---
description: Estrai testo da immagini e screenshot usando motori OCR (Tesseract, EasyOCR, Google Vision) o LLM vision — output in TXT o DOCX.
---

# Estrai testo

Tira fuori il testo dalle immagini — ricevute, screenshot, documenti
fotografati, pagine scansionate, qualsiasi cosa. Output in `.txt`
(semplice) o `.docx` (paragrafi formattati).

Questa pagina **non traduce** — solo estrae. Manda l'output a
Traduci documento se vuoi anche tradurre.

## Due metodi di estrazione

| Metodo | Migliore per |
|---|---|
| **OCR** | Alto volume / batch / sensibile ai costi (gratis o quasi gratis per immagine) |
| **LLM vision** | Preservazione del layout, script misti, immagini di bassa qualità, scrittura a mano |

Scegli il default in **Impostazioni → Estrai testo → Metodo di estrazione**.

## Motori OCR (metodo OCR)

| Motore | Costo | Offline | Lingue | Note |
|---|---|---|---|---|
| **Tesseract** | Gratis | Sì | 100+ | Default. Necessita installazione di sistema. |
| **EasyOCR** | Gratis | Sì (dopo download modello) | 80+ | Migliore per script non latini. ~1 GB di modelli. |
| **Google Cloud Vision** | A pagamento (1.000 gratis / mese) | No | 60+ | Massima accuratezza. |

Configura in **Impostazioni → OCR**.

## Procedura

1. Clicca **Estrai testo** nella barra laterale.
2. Rilascia uno o più file immagine (`.png`, `.jpg`, `.jpeg`, `.bmp`,
   `.webp`, `.tiff`, `.tif`).
3. Scegli la **Lingua sorgente** (aiuta l'OCR a scegliere il modello giusto).
4. Scegli il **Formato di output** — `.txt` o `.docx`.
5. Clicca **Estrai** (o `Ctrl+Invio`).
6. **Apri** la riga quando fatto.

## Quando usare cosa

- **Ricevuta / fattura ricca di testo** → Tesseract è veloce e accurato.
- **Note manoscritte fotografate** → LLM vision vince di parecchio.
- **Pannelli manga / fumetto** → EasyOCR (gestisce bene il testo CJK verticale).
- **Modulo con molti campi piccoli** → Google Cloud Vision tende a
  preservare i confini dei campi meglio degli altri.

## Suggerimenti

!!! tip "OCR o LLM, non entrambi"
    La pagina sceglie un metodo e lo esegue. Per confrontare gli
    output, esegui la stessa immagine due volte con metodi diversi.

!!! tip "Dialog Configurazione richiesta"
    Se scegli OCR ma nessun motore OCR è configurato (o LLM ma nessuna
    chiave LLM configurata), la pagina mostra un singolo dialog
    "Configurazione richiesta" che porta direttamente al tab
    Impostazioni rilevante.

## Scorciatoie

| Scorciatoia | Azione |
|---|---|
| `Ctrl+Invio` | Estrai |
| `Ctrl+O` | Sfoglia |
| `Ctrl+F` | Focus ricerca cronologia |
