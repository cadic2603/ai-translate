---
description: Skonfiguruj silniki OCR do ekstrakcji tekstu z obrazów i PDF — wybierz między offline Tesseract lub EasyOCR, lub chmurowym Google Vision OCR.
---

# Silniki OCR

OCR jest używany do odczytywania tekstu z obrazów — zarówno na
stronie [Extract Text](../features/extract-text.md), jak i jako
fallback wewnątrz tłumaczenia Document, gdy strona jest zeskanowana
(brak warstwy tekstowej) lub gdy włączasz **Translate embedded
images**.

Możesz wybierać spośród trzech silników OCR.

## Tesseract (zalecany domyślny)

Darmowy, szybki, offline. Wymaga instalacji systemowej.

=== "macOS"
    ```bash
    brew install tesseract tesseract-lang
    ```

=== "Ubuntu / Debian"
    ```bash
    sudo apt install tesseract-ocr tesseract-ocr-all
    ```

    `tesseract-ocr-all` wnosi każdy obsługiwany język. Aby
    oszczędzać dysk, zainstaluj tylko to, czego potrzebujesz (np.
    `tesseract-ocr-fra` dla francuskiego).

=== "Fedora / RHEL"
    ```bash
    sudo dnf install tesseract tesseract-langpack-eng tesseract-langpack-fra
    ```

=== "Windows"
    Pobierz instalator z
    [wydań Tesseract UB Mannheim](https://github.com/UB-Mannheim/tesseract/wiki).
    Uruchom go, zaakceptuj domyślne — pakiety językowe są
    dołączone.

Zweryfikuj:

```bash
tesseract --version
tesseract --list-langs
```

W aplikacji desktopowej: **Settings → OCR → OCR method = Tesseract**.
Gotowe.

## EasyOCR

Darmowy, offline. Świetny dla skryptów nielatynowych (chiński,
koreański, japoński, tajski). Modele pobierają się przy pierwszym
użyciu (~1 GB łącznie).

```bash
uv sync --extra easyocr
```

W aplikacji desktopowej: **Settings → OCR → OCR method = EasyOCR**.

Pierwszy raz, gdy używasz dla języka, odpowiedni model pobiera się
do `~/.EasyOCR/`. Kolejne uruchomienia są natychmiastowe.

## Google Cloud Vision

Chmurowy, płatny (1000 darmowych żądań / miesiąc). Najwyższa
dokładność, zwłaszcza na hałaśliwej / odręcznej / wielowieloskryptowej
zawartości.

1. [Utwórz projekt Google Cloud](https://console.cloud.google.com/projectcreate)
2. Włącz [Vision API](https://console.cloud.google.com/apis/library/vision.googleapis.com)
3. [Utwórz klucz API](https://console.cloud.google.com/apis/credentials)
4. W aplikacji desktopowej: **Settings → Service → Google Cloud
   API key** → wklej
5. **Settings → OCR → OCR method = Google Cloud OCR**

Ten sam klucz Google Cloud API zasila Vision OCR, Speech-to-Text i
Text-to-Speech, jeśli włączysz również te APIs.

## Porównywanie dokładności

Zakładka **Settings → OCR** ma wbudowaną małą tabelę porównawczą —
pokrycie językowe, online/offline, koszt, dokładność. Czytaj ją
ponownie, kiedy jesteś kuszony, by przełączyć.

## Kiedy używany jest OCR

| Miejsce | Zachowanie |
|---|---|
| **Strona Extract Text** (gdy method = OCR) | Bezpośredni OCR na upuszczonych obrazach |
| **Translate Document → PDF** | Fallback OCR na stronach tylko-skan (bez warstwy tekstowej) |
| **Translate Document → Office** z włączonym **Translate embedded images** | OCR + LLM vision na każdym osadzonym obrazie |

## Wskazówki

!!! tip "Wybierz język źródłowy"
    Większość silników OCR jest znacznie dokładniejsza, gdy mówisz
    im, jakiego języka oczekiwać. Strony Subtitle / Document /
    Extract Text wszystkie przekazują twój selektor **Source
    language** do silnika OCR.

!!! tip "Tesseract wystarcza dla czystego drukowanego tekstu"
    Nie sięgaj po chmurowy OCR, dopóki Tesseract / EasyOCR
    rzeczywiście nie zawiedzie na twojej zawartości. Są darmowe,
    szybkie i zaskakująco dobre.
