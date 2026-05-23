---
description: Installiere FFmpeg, damit AI Translate Audio und Video für Untertitelerstellung, Sprachsynthese und Videosynchronisation dekodieren kann — erforderlich für Medienfunktionen.
---

# FFmpeg

FFmpeg ist für jeden Audio- / Video-Workflow erforderlich:

- **Untertitel generieren** — Dekodieren von Quellaudio für STT
- **Stimme generieren** — Kombinieren von zeitlich abgestimmten
  TTS-Clips zu einer Datei
- **Synchronisation** — STT → TTS → wieder in das Video gemuxt
- **Live-Übersetzung** — wenn die Systemaudio-Erfassung über `parec`
  läuft

Es ist nicht gebündelt — installiere es einmal auf deinem System.

## Installieren

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

    Oder für eine vollständigere Build aktiviere zuerst
    [RPM Fusion](https://rpmfusion.org/Configuration).

=== "Arch / Manjaro"
    ```bash
    sudo pacman -S ffmpeg
    ```

=== "Windows"
    Lade einen statischen Build von <https://www.gyan.dev/ffmpeg/builds/>
    herunter (der "release essentials"-Build ist in Ordnung), entpacke
    ihn, dann füge den `bin/`-Ordner zu deinem PATH hinzu:

    1. Drücke **Win + R**, tippe `sysdm.cpl`, drücke **Enter**
    2. **Erweitert → Umgebungsvariablen → Systemvariablen → Path → Bearbeiten**
    3. **Neu** → füge den absoluten Pfad zum `bin`-Ordner von FFmpeg ein
    4. **OK** überall, starte alle offenen Terminals neu

## Überprüfen

```bash
ffmpeg -version
```

Du solltest ein Versionsbanner mit `--enable-libx264 --enable-libvpx`
in der Konfigurationszeile sehen. Wenn du "command not found" siehst,
ist die Installation nicht im PATH gelandet.

## In-App-Pre-Flight-Prüfung

Die Stimme- / Synchronisations-Seiten rufen `shutil.which("ffmpeg")`
auf, bevor die Arbeit beginnt. Wenn FFmpeg nicht gefunden wird, siehst
du einen freundlichen Fehlerdialog mit einem Link hierher, keine
halb-ausgeführte Aufgabe.

## Häufiger Fehler

| Fehler | Bedeutung |
|---|---|
| `FFMPEG_NOT_FOUND` | `ffmpeg` ist nicht im PATH zu dem Zeitpunkt, als die Seite versuchte, es auszuführen. Installiere es (oben) und starte die App neu. |

Im MCP-Server (`ait-mcp`) wird derselbe Fehler in eine
menschenlesbare Nachricht umgepackt:

> *„FFmpeg ist erforderlich, um diese Audio-/Videodatei zu
> dekodieren, ist aber nicht installiert oder nicht im PATH.
> Installiere FFmpeg und versuche es erneut."*
