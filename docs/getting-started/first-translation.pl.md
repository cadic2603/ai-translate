---
description: Przetłumacz swój pierwszy dokument za pomocą AI Translate w 5 minut — przeciągnij i upuść PDF, wybierz język docelowy i pobierz przetłumaczoną kopię.
---

# Twoje pierwsze tłumaczenie

Szybkie uruchomienie end-to-end — poniżej 5 minut po zakończeniu
konfiguracji.

!!! abstract "Zanim zaczniesz"
    Musisz mieć zakończoną [instalację](installation.md) i
    skonfigurowany klucz LLM API. Darmowy poziom Google Gemini jest
    wystarczający do pierwszej próby.

## Tłumaczenie dokumentu Word

1. Uruchom aplikację desktopową:

    ```bash
    uv run python -m src.main
    ```

2. Kliknij **Tłumacz dokument** w lewym pasku bocznym.

3. Przeciągnij dowolny plik `.docx` do strefy upuszczania — lub
   kliknij **Przeglądaj**, aby wybrać.

4. Plik pojawia się w kolejce. Wybierz język docelowy u góry:

    - Źródło: `Auto-detect` (domyślnie — zwykle poprawnie)
    - Cel: np. `French`, `Vietnamese`, `Japanese`,
      `Chinese (Simplified)`

5. Kliknij **Tłumacz** (lub naciśnij `Ctrl+Enter`).

6. Obserwuj pasek postępu w tabeli historii na dole strony. Gdy
   osiągnie 100%, kliknij **Otwórz** w wierszu, aby otworzyć
   przetłumaczony plik — zapisany obok oryginału z sufiksem
   `_translated_<src>_<tgt>`.

## Co się właśnie stało

- Twój `.docx` został sklonowany do folderu pamięci dla każdego
  zadania, aby oryginał pozostał nietknięty.
- Tekst został wyekstrahowany, podzielony na fragmenty przyjazne
  dla LLM, przetłumaczony i ponownie wstrzyknięty do dokumentu z
  zachowaniem całego formatowania (pogrubienia, kursywy, czcionek,
  kolorów, nagłówków, przypisów, hiperłączy…).
- Wpis historii został zapisany do bazy danych SQLite, więc możesz
  ponownie otworzyć, ponownie uruchomić lub ponownie przetłumaczyć
  plik później.

## Wypróbuj szybkie wygrane

=== "Tłumaczenie zwykłego tekstu"

    Przejdź do **Tłumacz tekst** w pasku bocznym. Wklej cokolwiek,
    wybierz cel, naciśnij Enter. Wyjście strumieniowe, zamiana
    języków (`Ctrl+L`), tryb edycji, odtwarzanie TTS.

=== "Generowanie napisów"

    **Generuj napisy** — upuść `.mp4`. Otrzymasz `.srt` w języku
    źródłowym. (Aby przetłumaczyć _i_ zdubbingować wideo, użyj
    zamiast tego strony Dubbing.)

=== "Tłumaczenie mikrofonu na żywo"

    **Tłumaczenie na żywo** — wybierz mikrofon lub dźwięk systemowy,
    wybierz cel, Start. Pływające okno overlay pokazuje napisy w
    czasie rzeczywistym.

## Dokąd dalej

- Zobacz [indeks funkcji](../index.md#headline-features), aby
  dowiedzieć się, co robi każda strona.
- Podłącz [więcej dostawców](../setup/llm-providers.md)
  (niestandardowe endpointy, ElevenLabs, Soniox, Google Cloud).
- Wypróbuj [CLI](../cli.md) dla uruchomień wsadowych / skryptowych.

