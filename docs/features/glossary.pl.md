---
description: Zarządzaj niestandardowymi zestawami glosariusza, aby egzekwować spójną terminologię w tłumaczeniach — import/eksport CSV, zakres na parę językową, priorytetyzacja per projekt.
---

# Glosariusz

Zablokuj konkretne terminy do konkretnych tłumaczeń w każdym zadaniu
tłumaczenia. Przydatne do nazw marek, terminologii produktów, żargonu
technicznego lub nazw postaci, które chcesz utrzymać spójne.

## Jak to działa

Glosariusz to lista par (termin źródłowy, termin docelowy)
pogrupowanych w **zestaw**. Gdy włączysz zestaw, każde wywołanie LLM
w aplikacji otrzymuje odpowiednie wpisy wstrzyknięte do promptu —
więc LLM widzi "użyj 'OpenAI' zamiast 'OpenAI', nie '开放AI'" przed
tłumaczeniem.

Wiele zestawów może być aktywnych jednocześnie. Tylko wpisy, których
źródło lub cel pojawia się w tekście partii, są dodawane do promptu
(kompresja per-call), więc glosariusz z 5000 wpisami pozostaje tani
w tokenach.

## Krok po kroku

1. Kliknij **Glosariusz** w pasku bocznym.
2. Kliknij **New Set** (`Ctrl+N`) i nadaj mu nazwę (np. "Project Acme").
3. Z zestawem wybranym po lewej, prawy panel pokazuje jego wpisy.
4. Kliknij **Add**, aby utworzyć nowy wpis. Wypełnij:
    - **Source** — oryginalny termin
    - **Target** — tłumaczenie do wymuszenia
    - Opcjonalnie komentarz / notatka
5. Powtórz dla każdego terminu.
6. Zaznacz pole **Active** na nazwie zestawu, aby włączyć go dla
   tłumaczeń.

## Aktywuj / dezaktywuj zestawy

Pole **Active** obok każdej nazwy zestawu kontroluje, czy jego wpisy
są wstrzykiwane do promptów LLM. Możesz pozostawić 50 nieaktywnych
zestawów w przechowywaniu i włączyć tylko 2, których potrzebujesz dla
bieżącego projektu.

## Import / Export (CSV)

- **Export** — wybierz zestaw, kliknij **Export** → zapisz jako
  `.csv`. Dwie kolumny: `source`, `target` (UTF-8, oddzielone
  przecinkami, RFC 4180-cytowane).
- **Import** — kliknij **Import** → wybierz `.csv` → wybierz zestaw
  docelowy (istniejący lub nowy). Przy zduplikowanym źródle
  otrzymasz prompt zastąp lub pomiń.

Format CSV round-tripuje, więc Export → edytuj w Excelu → Import
jest bezpieczne.

## Wyszukiwanie i filtrowanie

`Ctrl+F` skupia pole wyszukiwania. Wpisz dowolny podciąg, a wpisy
(i lista zestawów) filtrują się do pasujących; pasujący podciąg
jest wyróżniony. Wyczyszczenie wyszukiwania przywraca pełną listę.

Wyszukiwanie jest **nieczułe na akcenty i nieczułe na wielkość liter**
— `cafe` znajduje `café` i odwrotnie.

## Edycja w miejscu

Kliknij dowolną komórkę, aby edytować. Naciśnij `Tab`, aby przejść
do następnej komórki. Naciśnij `Esc`, aby cofnąć. Auto-zapis jest
wyzwalany, gdy klikniesz poza wierszem. Puste źródło lub cel cofa
wiersz zamiast zapisywać niepoprawny wpis.

## Usuwanie

- **Usuń pojedynczy wpis** — wybierz go, naciśnij `Delete`.
  Zobaczysz dialog potwierdzający.
- **Usuń cały zestaw** — wybierz zestaw, naciśnij `Delete`. Dialog
  pokazuje liczbę kaskadowych wpisów, więc wiesz, co usuwasz.

## Skróty

| Skrót | Akcja |
|---|---|
| `Ctrl+N` | Nowy zestaw |
| `Ctrl+F` | Skupienie wyszukiwania |
| `Delete` | Usuń wybrany wpis / zestaw |

## Wskazówki

!!! tip "Zakres per-zestaw"
    Zestaw to *logiczne* grupowanie. Grupuj według projektu, klienta,
    domeny (medyczna / prawna / gaming) — cokolwiek ma sens.
    Aktywuj tylko zestawy istotne dla bieżącego zadania.

!!! tip "Glosariusz nie nadpisuje tłumaczenia"
    LLM jest instruowany, aby używać wpisów glosariusza, ale pozostaje
    to wskazówka — niezwykle niezręczne wymuszone tłumaczenia mogą
    nadal wypłynąć. Używaj prostych par `termin → tłumaczenie`
    zamiast pełnych zdań.
