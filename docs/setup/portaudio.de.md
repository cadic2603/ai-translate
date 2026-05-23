---
description: Plattformübergreifende Mikrofon-Audioaufnahme für die Live-Übersetzung.
---

# PortAudio-Einrichtung (Mikrofon)

Die Funktion [Live-Übersetzung](../features/live-translation.md) verwendet das Python-Paket `sounddevice`, das auf der C-Bibliothek PortAudio basiert, um auf allen Betriebssystemen auf Mikrofongeräte zuzugreifen. Die meisten Benutzer müssen diese systemweite Abhängigkeit installieren.

## Windows
Die vorkompilierten Wheels für `sounddevice` und `PyAudio` bündeln unter Windows normalerweise die PortAudio-Binärdatei. Eine manuelle systemweite Installation ist normalerweise nicht erforderlich. Wenn Fehler auftreten, stellen Sie sicher, dass Ihre Audiotreiber auf dem neuesten Stand sind.

## macOS
Verwenden Sie Homebrew, um PortAudio zu installieren:

```bash
brew install portaudio
```

## Linux
Der Paketname hängt von Ihrer Distribution ab. Das Entwicklungspaket (das normalerweise auf `-dev` oder `-devel` endet) muss installiert werden, damit Python die C-Bindungen erstellen kann, wenn kein vorkompiliertes Wheel verfügbar ist.

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

## Fehlerbehebung

Wenn die Anwendung nach der Installation weiterhin meldet, dass sie nicht auf das Mikrofon zugreifen kann:

1. Stellen Sie sicher, dass Ihre Terminalanwendung (oder Desktopumgebung) die Berechtigung hat, auf das Mikrofon zuzugreifen (insbesondere unter macOS).
2. Starten Sie die Anwendung (oder das Terminal/den MCP-Server) neu, damit der neue Bibliothekspfad übernommen wird.
