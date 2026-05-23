---
description: Wieloplatformowe przechwytywanie dźwięku z mikrofonu na potrzeby tłumaczenia na żywo.
---

# Konfiguracja PortAudio (Mikrofon)

Funkcja [Tłumaczenie na żywo](../features/live-translation.md) korzysta z pakietu Python `sounddevice`, który opiera się na bibliotece C PortAudio, aby uzyskać dostęp do urządzeń mikrofonowych we wszystkich systemach operacyjnych. Większość użytkowników musi zainstalować tę zależność na poziomie systemu.

## Windows
Wstępnie skompilowane pakiety wheel dla `sounddevice` i `PyAudio` zazwyczaj zawierają plik binarny PortAudio w systemie Windows. Ręczna instalacja na poziomie systemu zwykle nie jest konieczna. W przypadku wystąpienia błędów upewnij się, że sterowniki dźwięku są aktualne.

## macOS
Użyj Homebrew, aby zainstalować PortAudio:

```bash
brew install portaudio
```

## Linux
Nazwa pakietu zależy od Twojej dystrybucji. Pakiet programistyczny (zwykle kończący się na `-dev` lub `-devel`) musi zostać zainstalowany, aby środowisko Python mogło zbudować wiązania języka C, jeśli wstępnie skompilowany pakiet wheel nie jest dostępny.

=== "Ubuntu / Debian / Mint"

    ```bash
    sudo apt-get install portaudio19-dev
    ```

=== "Fedora / RHEL"

    ```bash
    sudo dnf install portaudio-devel
    ```

=== "Arch Linux"

    ```bash
    sudo pacman -S portaudio
    ```

## Rozwiązywanie problemów

Jeśli aplikacja nadal zgłasza, że nie może uzyskać dostępu do mikrofonu po instalacji:

1. Upewnij się, że aplikacja terminala (lub środowisko pulpitu) ma uprawnienia do uzyskiwania dostępu do mikrofonu (zwłaszcza w systemie macOS).
2. Uruchom ponownie aplikację (lub terminal/serwer MCP), aby pobrała nową ścieżkę biblioteki.
