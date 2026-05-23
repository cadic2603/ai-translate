---
description: Zainstaluj FFmpeg, aby AI Translate mógł dekodować audio i wideo dla generowania napisów, syntezy głosu i dubbingu wideo — wymagane dla funkcji medialnych.
---

# FFmpeg

FFmpeg jest wymagany dla każdego przepływu audio / wideo:

- **Generuj napisy** — dekodowanie audio źródłowego dla STT
- **Generuj głos** — łączenie taktowanych klipów TTS w jeden plik
- **Dubbing** — STT → TTS → mux z powrotem do wideo
- **Tłumaczenie na żywo** — gdy przechwytywanie audio systemowego
  idzie przez `parec`

Nie jest dołączony — zainstaluj go raz na swoim systemie.

## Zainstaluj

=== "macOS"
    ```bash
    brew install ffmpeg
    ```

=== "Ubuntu / Debian"
    ```bash
    sudo apt update && sudo apt install ffmpeg
    ```

=== "Fedora / RHEL"
    ```bash
    sudo dnf install ffmpeg
    ```

    Lub, dla bardziej kompletnego buildu, najpierw włącz
    [RPM Fusion](https://rpmfusion.org/Configuration).

=== "Arch / Manjaro"
    ```bash
    sudo pacman -S ffmpeg
    ```

=== "Windows"
    Pobierz statyczny build z
    <https://www.gyan.dev/ffmpeg/builds/> (build "release
    essentials" jest w porządku), rozpakuj, potem dodaj folder
    `bin/` do swojego PATH:

    1. Naciśnij **Win + R**, wpisz `sysdm.cpl`, naciśnij **Enter**
    2. **Advanced → Environment Variables → System variables → Path → Edit**
    3. **New** → wklej absolutną ścieżkę folderu `bin` FFmpeg
    4. **OK** wszędzie, zrestartuj otwarte terminale

## Zweryfikuj

```bash
ffmpeg -version
```

Powinieneś zobaczyć banner wersji z `--enable-libx264 --enable-libvpx`
w linii konfiguracji. Jeśli widzisz "command not found", instalacja
nie trafiła do PATH.

## Sprawdzenie pre-flight w aplikacji

Strony Voice / Dubbing wywołują `shutil.which("ffmpeg")` przed
rozpoczęciem pracy. Jeśli FFmpeg nie zostanie znaleziony, zobaczysz
przyjazny dialog błędu z linkiem z powrotem tutaj, a nie pół-uruchomione
zadanie.

## Częsty błąd

| Error | Znaczenie |
|---|---|
| `FFMPEG_NOT_FOUND` | `ffmpeg` nie jest w PATH w momencie, gdy strona próbowała go uruchomić. Zainstaluj go (powyżej) i zrestartuj aplikację. |

W serwerze MCP (`ait-mcp`) ten sam błąd jest przepakowywany na
czytelną wiadomość:

> *"FFmpeg is required to decode this audio/video file but is not
> installed or not on PATH. Install FFmpeg and try again."*
