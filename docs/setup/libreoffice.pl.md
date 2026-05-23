---
description: Zainstaluj LibreOffice, aby AI Translate mógł tłumaczyć stare formaty Office (.doc, .xls, .ppt) i pliki ODF (.odt, .ods, .odp) na macOS i Linux.
---

# LibreOffice (formaty Office)

Potok tłumaczenia Office wybiera najlepszy dostępny backend w tej
kolejności:

1. **win32com** (Windows + MS Office zainstalowany) — najwyższa
   wierność
2. **LibreOffice UNO** (wieloplatformowy) — fallback, gdy win32com
   nie ma
3. **python-docx / openpyxl / python-pptx** (tylko nowoczesne
   formaty) — fallback czysty Python, gdy żaden z powyższych nie
   jest dostępny

LibreOffice to **jedyna ścieżka** dla starych `.doc` / `.xls` /
`.ppt` na Linuxie i macOS, i zalecana ścieżka na tych platformach
także dla nowoczesnych formatów Office (lepsza wierność niż backend
czystego Pythona, zwłaszcza dla tabel i osadzonych obiektów).

## Zainstaluj

=== "macOS"
    ```bash
    brew install --cask libreoffice
    ```

    Lub pobierz z <https://www.libreoffice.org/download/download/>.

=== "Ubuntu / Debian"
    ```bash
    sudo apt install libreoffice
    ```

=== "Fedora / RHEL"
    ```bash
    sudo dnf install libreoffice
    ```

=== "Windows"
    Aplikacja desktopowa na Windows zwykle używa **win32com** z
    zainstalowanym MS Office — LibreOffice to *fallback*, jeśli
    brakuje MS Office. Zainstaluj z
    <https://www.libreoffice.org/download/download/>.

## Zweryfikuj

```bash
soffice --version
```

Jeśli otrzymasz "command not found" na macOS, binarka znajduje się
w `/Applications/LibreOffice.app/Contents/MacOS/soffice`. Aplikacja
auto-wykrywa to przez popularne ścieżki instalacji, ale możesz
nadpisać w **Settings → General → LibreOffice path**, jeśli to
konieczne.

## Co zasila

Gdy LibreOffice jest aktywnym backendem:

| Funkcja | Notatka |
|---|---|
| **Nowoczesny Office** (`.docx`, `.xlsx`, `.pptx`) | Używany jako fallback, gdy win32com nie jest dostępny |
| **Stary Office** (`.doc`, `.xls`, `.ppt`) | Wymagany — czysty Python nie potrafi ich odczytać |
| **ODF** (`.odt`, `.ods`, `.odp`) | Używany do konwersji round-trip, gdy **Auto-convert ODF** jest włączone |
| **Auto-convert legacy / ODF → OOXML** | Wymagany |

## Proces w tle

Przy pierwszej potrzebie LibreOffice aplikacja spawnuje proces
`soffice` w trybie headless i utrzymuje go przy życiu między
tłumaczeniami (`office_lifecycle.py`). Auto-zamyka się przy
wyjściu z aplikacji.

## Zastrzeżenia

!!! warning "Czas startu przy pierwszym uruchomieniu"
    Pierwsze tłumaczenie, które trafia w LibreOffice, czeka ~5-10
    sekund, aż `soffice` wystartuje. Kolejne tłumaczenia ponownie
    używają tego samego procesu i są szybkie.

!!! info "Logi crashy JVM"
    Komponent Java LibreOffice okazjonalnie produkuje pliki
    `hs_err_pid*.log`, gdy segfaultuje. Aplikacja kieruje je do
    katalogu temp, więc nie zanieczyszczają twojego folderu projektu.

!!! tip "Auto-convert legacy / ODF"
    Włącz **Settings → Translation → Auto-convert legacy**, jeśli
    rutynowo tłumaczysz `.doc` / `.xls` / `.ppt`. Potok najpierw
    konwertuje je do `.docx` / `.xlsx` / `.pptx` (przez
    `convert_to_modern_format`), tłumaczy nowoczesną kopię, potem
    konwertuje z powrotem. Wierność jest znacznie wyższa niż przy
    bezpośrednim tłumaczeniu starego formatu.
