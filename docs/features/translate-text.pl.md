---
description: Tłumacz natychmiast fragmenty tekstu w 45+ językach z AI Translate — wklej, pisz lub mów; obsługuje tryb edycji, odtwarzanie TTS i zamianę języków.
---

# Tłumacz tekst

Natychmiastowe tłumaczenie LLM z auto-wykrywaniem, zamianą języków,
strumieniowym wyjściem i odtwarzaniem TTS. Najlepsze do krótkich
fragmentów, użycia w stylu czatu i testowania konfiguracji LLM.

## Krok po kroku

1. Kliknij **Tłumacz tekst** w pasku bocznym.
2. Wpisz lub wklej swój tekst źródłowy w lewym panelu.
3. Język **źródłowy** auto-wykrywa się podczas pisania (zasilane
   przez `langdetect`).
4. Wybierz język **docelowy** z rozwijanego menu po prawej.
5. Kliknij **Tłumacz** (lub naciśnij `Ctrl+Enter`).
6. Tłumaczenie strumieniuje do prawego panelu token po tokenie.

## Co dostajesz

- **Wyjście strumieniowe** — tłumaczenie pojawia się gdy LLM je
  generuje, bez czekania na całą odpowiedź.
- **Auto-wykrywanie źródła** — selektor źródła aktualizuje się w
  czasie rzeczywistym. Kliknij, aby nadpisać.
- **Tryb edycji** — kliknij prawy panel, aby edytować tłumaczenie
  ręcznie. Naciśnij `Escape`, aby anulować tłumaczenie w toku;
  naciśnij ponownie, aby wyjść z trybu edycji.
- **Ponowne użycie historii** — każde tłumaczenie jest zapisywane.
  Kliknij wpis w panelu Text Translation History poniżej, aby
  ponownie załadować oba panele; edycje aktualizują oryginalny
  wpis zamiast tworzyć duplikat.
- **Odtwarzanie TTS** — kliknij przycisk **Słuchaj** obok dowolnego
  panelu, aby usłyszeć go odczytany na głos. Honoruje wybór
  **Settings → Voice → TTS method** — Edge TTS (domyślnie),
  ElevenLabs, Google Cloud TTS, Gemini TTS lub **Piper TTS**
  (całkowicie offline). Z wybranym Piperem przycisk Słuchaj
  uruchamia ten sam pre-flight co strona Voice: brakujący głos
  per-język wyświetla modal z przyciskiem **Open Settings**, abyś
  mógł go pobrać. Trafienia w cache całkowicie pomijają pre-flight.
- **Wybór modelu per-funkcję** — gdy skonfigurowanych jest więcej
  niż jeden LLM, rozwijane menu pozwala wybrać szybki model Flash
  dla prędkości lub cięższy Pro dla jakości, tylko dla tej strony.

## Skróty

| Skrót | Akcja |
|---|---|
| `Ctrl+Enter` | Tłumacz |
| `Ctrl+L` | Zamień źródłowy ↔ docelowy |
| `Escape` | Anuluj tłumaczenie w toku lub wyjdź z trybu edycji |
| `Ctrl+F` | Skupienie na wyszukiwaniu historii |

## Wskazówki

!!! tip "Języki RTL"
    Tłumaczenia na **arabski**, **hebrajski** lub **perski**
    automatycznie renderują się od prawej do lewej w panelu wyjścia.
    Ta sama obsługa RTL przenosi się do wyjścia plików we wszystkich
    formatach na stronie [Tłumacz dokument](translate-document.md)
    (PDF, DOCX, PPTX, XLSX, ODF, RTF, HTML, EPUB, ASS/SSA), a perski
    otrzymuje natywny głos `fa-IR` do odtwarzania Edge TTS.

!!! tip "Cache przycisku Słuchaj"
    Przy pierwszym kliknięciu Słuchaj dla danej pary (tekst, język)
    audio jest syntetyzowane i buforowane na dysku. Kolejne
    odtwarzania są natychmiastowe. Cache jest czyszczona przy starcie
    aplikacji, więc każda sesja zaczyna od nowa.

!!! tip "Gdzie idą klucze"
    Strona Tłumacz tekst czyta te same wpisy keychain co reszta
    aplikacji — zobacz [Dostawcy LLM](../setup/llm-providers.md).
