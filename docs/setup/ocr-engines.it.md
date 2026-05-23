---
description: Configura motori OCR per l'estrazione di testo da immagini e PDF — scegli tra Tesseract o EasyOCR offline, o Google Vision OCR basato su cloud.
---

# Motori OCR

L'OCR è usato per leggere il testo dalle immagini — sia sulla pagina
[Estrai testo](../features/extract-text.md) sia come ripiego dentro
la traduzione di Documento quando una pagina è scansionata (senza
livello di testo) o quando attivi **Traduci immagini incorporate**.

Puoi scegliere tra tre motori OCR.

## Tesseract (predefinito raccomandato)

Gratuito, veloce, offline. Richiede un'installazione di sistema.

=== "macOS"
    ```bash
    brew install tesseract tesseract-lang
    ```

=== "Ubuntu / Debian"
    ```bash
    sudo apt install tesseract-ocr tesseract-ocr-all
    ```

    `tesseract-ocr-all` porta ogni lingua supportata. Per risparmiare
    disco, installa solo ciò di cui hai bisogno (es. `tesseract-ocr-fra`
    per il francese).

=== "Fedora / RHEL"
    ```bash
    sudo dnf install tesseract tesseract-langpack-eng tesseract-langpack-fra
    ```

=== "Windows"
    Scarica l'installer da
    [le release di Tesseract di UB Mannheim](https://github.com/UB-Mannheim/tesseract/wiki).
    Eseguilo, accetta i valori predefiniti — i pacchetti di lingua
    sono inclusi.

Verifica:

```bash
tesseract --version
tesseract --list-langs
```

Nell'app desktop: **Impostazioni → OCR → Metodo OCR = Tesseract**.
Fatto.

## EasyOCR

Gratuito, offline. Ottimo per script non-latini (cinese, coreano,
giapponese, thai). I modelli si scaricano al primo uso (~1 GB
totali).

```bash
uv sync --extra easyocr
```

Nell'app desktop: **Impostazioni → OCR → Metodo OCR = EasyOCR**.

La prima volta che lo usi per una lingua, il modello pertinente si
scarica in `~/.EasyOCR/`. Le esecuzioni successive sono istantanee.

## Google Cloud Vision

Cloud, a pagamento (1.000 richieste gratuite / mese). Massima
precisione, specialmente su contenuti rumorosi / scritti a mano /
multi-script.

1. [Crea un progetto Google Cloud](https://console.cloud.google.com/projectcreate)
2. Abilita la [Vision API](https://console.cloud.google.com/apis/library/vision.googleapis.com)
3. [Crea una chiave API](https://console.cloud.google.com/apis/credentials)
4. Nell'app desktop: **Impostazioni → Servizio → Chiave API Google Cloud** → incolla
5. **Impostazioni → OCR → Metodo OCR = Google Cloud OCR**

La stessa chiave API Google Cloud alimenta Vision OCR, Speech-to-Text
e Text-to-Speech se abiliti anche quelle API.

## Confrontando la precisione

La scheda **Impostazioni → OCR** ha una piccola tabella di confronto
integrata — copertura linguistica, online/offline, costo, precisione.
Rileggila ogni volta che sei tentato di cambiare.

## Quando viene usato l'OCR

| Posto | Comportamento |
|---|---|
| **Pagina Estrai testo** (quando metodo = OCR) | OCR diretto sulle immagini rilasciate |
| **Traduci documento → PDF** | Ripiego OCR su pagine solo-scansionate (senza livello di testo) |
| **Traduci documento → Office** con **Traduci immagini incorporate** attivo | OCR + LLM vision su ogni immagine incorporata |

## Suggerimenti

!!! tip "Scegli la lingua di origine"
    La maggior parte dei motori OCR è molto più precisa quando dici
    loro quale lingua aspettarsi. Le pagine Sottotitolo / Documento /
    Estrai testo inoltrano tutte il tuo selettore **Lingua di origine**
    al motore OCR.

!!! tip "Tesseract è sufficiente per testo stampato pulito"
    Non saltare all'OCR cloud finché Tesseract / EasyOCR non ha
    effettivamente fallito sul tuo contenuto. Sono gratuiti, veloci
    e sorprendentemente buoni.
