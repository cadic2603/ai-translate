---
description: Tłumacz pliki PDF, Word, Excel, PowerPoint, ODF, EPUB, HTML, JSON, YAML, SRT i ponad 30 innych formatów plików, zachowując formatowanie i układ.
---

# Tłumacz dokument

Tłumacz całe pliki — Office, PDF, EPUB, zwykły tekst, napisy,
formaty lokalizacji i inne — z zachowanym formatowaniem.

## Obsługiwane formaty

| Kategoria | Rozszerzenia |
|---|---|
| Office | `.docx`, `.xlsx`, `.pptx`, `.odt`, `.ods`, `.odp`, `.doc`, `.xls`, `.ppt` |
| PDF | `.pdf` |
| Tekst i web | `.txt`, `.md`, `.rst`, `.html`, `.htm`, `.xhtml`, `.xml`, `.rtf`, `.json`, `.csv` |
| eBooki | `.epub` |
| Napisy | `.srt`, `.vtt`, `.ass`, `.ssa` |
| Lokalizacja | `.po`, `.pot`, `.xliff`, `.xlf`, `.yaml`, `.yml`, `.properties`, `.strings` |

## Krok po kroku

1. Kliknij **Tłumacz dokument** w pasku bocznym.
2. Przeciągnij pliki (lub kliknij **Przeglądaj**). Foldery też
   działają — obsługiwane pliki w środku są zbierane rekursywnie.
3. Wybierz **Source** (lub pozostaw `Auto-detect`) i **Target**.
4. Kliknij **Tłumacz** — lub naciśnij `Ctrl+Enter`.
5. Tabela historii poniżej pokazuje postęp per-plik (Pending →
   Translating → Done / Failed). Pasek boczny pokazuje spinner,
   gdy jakieś zadanie jest aktywne.
6. Kliknij **Open** w wierszu, aby otworzyć przetłumaczony plik.
   Kliknij prawym dla opcji: re-translate, pause, retry, delete.

## Gdzie kończą pliki

Domyślnie przetłumaczone pliki są zapisywane obok oryginału z
sufiksem `_translated_<src>_<tgt>`:

```
~/Documents/report.docx
~/Documents/report_translated_en_fr.docx     ← tutaj
```

Zmień to w **Settings → General → Translation storage path** na
katalog niestandardowy.

## Limity i strażnicy

- **Limit upuszczania 100 plików** — upuść więcej, a otrzymasz
  powiadomienie. Tłumacz w partiach.
- **Wykrywanie duplikatów** — upuść plik już w kolejce, a zobaczysz
  powiadomienie (duplikat jest porzucany, nie dodawany dwukrotnie).
- **Auto-resume** — wyjdź z aplikacji podczas działających
  tłumaczeń, a wznowią się przy następnym uruchomieniu (zadania
  Pending / Translating).

## Opcje specyficzne dla Office

Zakładka Translation w **Settings** eksponuje te przełączniki dla
plików Office:

| Opcja | Co robi |
|---|---|
| **Translate embedded images** | Uruchamia OCR + LLM vision na obrazach wewnątrz `.docx` / `.xlsx` / `.pptx` i ponownie wstawia przetłumaczony obraz. Wymaga skonfigurowanego OCR. |
| **Translate comments** | Komentarze / notatki recenzji są tłumaczone wraz z tekstem treści. |
| **Translate shapes & text boxes** | Przechwytuje tekst znajdujący się w kształtach, callout-ach i pływających polach tekstowych. |
| **Translate speaker notes** | Notatki prezentera PowerPoint są tłumaczone. |
| **Translate sheet names** | Etykiety kart arkuszy Excel są tłumaczone. |
| **Auto-convert legacy** | `.doc` / `.xls` / `.ppt` są konwertowane do nowoczesnego OOXML przed tłumaczeniem (lepsza wierność). |
| **Auto-convert ODF** | `.odt` / `.ods` / `.odp` są konwertowane do OOXML przed tłumaczeniem. |

Całe tłumaczenie Office zachowuje formatowanie per-run: pogrubienie,
kursywę, podkreślenie, przekreślenie, rozmiar czcionki, kolor,
hiperłącza, nagłówki, stopki, przypisy, przypisy końcowe, wszystko.

### Tłumaczenie obrazów osadzonych: pomiń z ostrzeżeniem i pamięć podręczna

Gdy **Tłumacz obrazy osadzone** jest włączone, każdy osadzony
obraz przechodzi przez OCR → wizję LLM → renderowane
ponowne wstrzyknięcie. Dwa zachowania warte wiedzy:

- **Pomiń z ostrzeżeniem**: jeśli jeden obraz nie powiedzie
  się w tłumaczeniu (zbyt duży, uszkodzony, model wizji
  odrzuca format itp.), dokument i tak zostanie ukończony —
  uszkodzony obraz pozostaje w oryginalnym języku, ostrzeżenie
  jest rejestrowane w `app.log`, a pętla kontynuuje z
  następnym obrazem. Tylko fatalne błędy LLM (`AUTH_ERROR`,
  `QUOTA_ERROR`, `VISION_NOT_SUPPORTED`) natychmiast
  zatrzymują potok, ponieważ blokują również każdy
  pozostały obraz. Baner informacyjny nad polem wyboru
  **Tłumacz obrazy osadzone** dokumentuje zasady w sposób
  wbudowany.
- **Pamięć podręczna na obraz**: pomyślne tłumaczenia obrazów
  są utrzymywane w wewnętrznym katalogu przechowywania
  zadania z kluczem SHA256 bajtów źródłowych. Przy ponownej
  próbie już przetłumaczone obrazy trafiają do pamięci
  podręcznej zamiast ponownie uruchamiać OCR + LLM — opłacona
  praca nie jest powtarzana. Powielone obrazy (logo firmy
  na każdym slajdzie) są tłumaczone raz i ponownie używane
  N − 1 razy.

Plik wyjściowy pojawia się w wybranym folderze wyjściowym
tylko po **sukcesie** — częściowe tłumaczenia z anulowanych
lub nieudanych uruchomień pozostają zamknięte w wewnętrznym
katalogu przechowywania zadania, dzięki czemu folder
wyjściowy nigdy nie gromadzi osieroconych dokumentów
przetłumaczonych w połowie.

## Specyfika PDF

PDF-y używają silnika extract-overlay: oryginalny tekst jest
redaktowany w miejscu, a przetłumaczony tekst nakładany na te same
ramki, zachowując układ wizualny. Per-page checkpointing oznacza,
że wstrzymane / zawieszone uruchomienie wznawia się od miejsca
zatrzymania, a nie od strony 1.

Co jest tłumaczone:

- Tekst treści (z wykrywaniem wyrównania — lewe / środkowe / prawe
  / justowane)
- Zakładki / outline'y (wpisy TOC)
- Pola formularza (wejścia tekstowe, dropdowny, list boxy)
- Hiperłącza (link rect aktualizowany, aby otoczyć nowy tekst)
- Obrazy osadzone (gdy **Translate embedded images** włączone)
- Komentarze / adnotacje PDF

Dla skanowanych PDF-ów (brak osadzonej warstwy tekstowej) OCR
uruchamia się automatycznie per-strona. Skonfiguruj swój silnik OCR
w **Settings → OCR**.

## Wyjście od prawej do lewej

Tłumaczenia na **arabski**, **hebrajski** lub **perski** renderują
się natywnie jako RTL w każdym formacie wyjściowym — `dir="rtl"`
wstrzykiwane do nakładek PDF, HTML i rozdziałów EPUB (z
`page-progression-direction="rtl"` w OPF EPUB, aby Apple Books i
Kindle zmieniały strony w prawidłowym kierunku); DOCX `<w:bidi/>` +
`<w:rtl/>`, PPTX `rtl="1"`, widok arkusza XLSX od prawej do lewej,
ODT/ODS/ODP `style:writing-mode="rl-tb"`, RTF `\rtldoc` i
mirroring kodów wyrównania ASS/SSA (`\an1` ↔ `\an3`, `\an4` ↔
`\an6` itd.). Wyrównania środkowe pozostają nietknięte.

## Skróty

| Skrót | Akcja |
|---|---|
| `Ctrl+Enter` | Rozpocznij tłumaczenie |
| `Ctrl+O` | Przeglądaj pliki |
| `Ctrl+F` | Skupienie wyszukiwania historii |
| `Ctrl+P` | Wstrzymaj aktywną kolejkę |
| `Ctrl+G` | Kontynuuj aktywną kolejkę |
| `Delete` | Usuń wybrane wpisy historii |

`Ctrl+P` / `Ctrl+G` są tłumione, gdy pole tekstowe ma fokus, więc
nie kolidują z pisaniem.

## Gdy coś nie działa

Nieudane zadanie pokazuje czerwony status z kodem błędu i
zlokalizowanym komunikatem — zobacz [przewodnik troubleshooting](../troubleshooting.md)
dla typowych (`AUTH_ERROR`, `QUOTA_ERROR`, `FFMPEG_NOT_FOUND` itd.).
