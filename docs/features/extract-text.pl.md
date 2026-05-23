---
description: Wyodrębniaj tekst z obrazów i zrzutów ekranu używając silników OCR (Tesseract, EasyOCR, Google Vision) lub LLMów wizyjnych — wyjście do TXT lub DOCX.
---

# Wyodrębnij tekst

Uzyskaj tekst z obrazów — paragony, zrzuty ekranu, sfotografowane
dokumenty, zeskanowane strony, cokolwiek. Wyjście `.txt` (zwykły) lub
`.docx` (sformatowane akapity).

Ta strona **nie tłumaczy** — tylko wyodrębnia. Przekaż wyjście do
Translate Document, jeśli chcesz też tłumaczenia.

## Dwie metody ekstrakcji

| Metoda | Najlepsza do |
|---|---|
| **OCR** | Duża objętość / wsad / wrażliwa na koszty (darmowa lub prawie darmowa na obraz) |
| **LLM vision** | Zachowanie układu, mieszane skrypty, obrazy niskiej jakości, pismo odręczne |

Wybierz domyślną w **Settings → Extract Text → Extraction method**.

## Silniki OCR (metoda OCR)

| Silnik | Koszt | Offline | Języki | Notatki |
|---|---|---|---|---|
| **Tesseract** | Darmowy | Tak | 100+ | Domyślny. Wymaga instalacji systemowej. |
| **EasyOCR** | Darmowy | Tak (po pobraniu modeli) | 80+ | Najlepszy dla skryptów nielatynowych. ~1 GB modeli. |
| **Google Cloud Vision** | Płatny (1000 darmowych / miesiąc) | Nie | 60+ | Najwyższa dokładność. |

Skonfiguruj w **Settings → OCR**.

## Krok po kroku

1. Kliknij **Wyodrębnij tekst** w pasku bocznym.
2. Upuść jeden lub więcej plików obrazów (`.png`, `.jpg`, `.jpeg`,
   `.bmp`, `.webp`, `.tiff`, `.tif`).
3. Wybierz **język źródłowy** (pomaga OCR wybrać właściwy model).
4. Wybierz **format wyjściowy** — `.txt` lub `.docx`.
5. Kliknij **Wyodrębnij** (lub `Ctrl+Enter`).
6. Kliknij **Otwórz** w wierszu po zakończeniu.

## Kiedy czego użyć

- **Paragon / faktura z dużą ilością tekstu** → Tesseract jest
  szybki i dokładny.
- **Sfotografowane notatki odręczne** → Modele LLM Vision dają znacznie lepsze rezultaty.
- **Panele mangi / komiksu** → EasyOCR (dobrze obsługuje pionowy
  tekst CJK).
- **Formularz z wieloma małymi polami** → Google Cloud Vision lepiej
  zachowuje granice pól niż inne.

## Wskazówki

!!! tip "OCR lub LLM, nie oba"
    Strona wybiera jedną metodę i ją uruchamia. Aby porównać wyjścia,
    uruchom ten sam obraz dwa razy z różnymi metodami.

!!! tip "Dialog Setup Required"
    Jeśli wybierzesz OCR, ale żaden silnik OCR nie jest skonfigurowany
    (lub LLM, ale żaden klucz LLM nie jest skonfigurowany), strona
    wyświetla pojedynczy dialog "Setup Required", który linkuje
    bezpośrednio do odpowiedniej zakładki Settings.

## Skróty

| Skrót | Akcja |
|---|---|
| `Ctrl+Enter` | Wyodrębnij |
| `Ctrl+O` | Przeglądaj |
| `Ctrl+F` | Aktywuj wyszukiwanie w historii |
