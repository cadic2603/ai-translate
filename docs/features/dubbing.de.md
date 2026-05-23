---
description: "Synchronisieren Sie Videos End-to-End: Audio transkribieren, Untertitel übersetzen, Sprache in der Zielsprache synthetisieren und zurück in das Originalvideo mischen."
---

# Video-Synchronisation

Vollständige **STT → Übersetzen → TTS → Mix**-Pipeline, die eine
Videodatei in einer anderen Sprache mit ersetzter Sprachspur
produziert. Das Original-Audio wird verworfen; die neue Synchronisations-Spur
ist auf die Untertitel getimt.

## Was Sie brauchen

- **FFmpeg** im `PATH` — siehe [FFmpeg-Setup](../setup/ffmpeg.md).
- Ein STT-Backend (Standard: lokales Whisper, keine Einrichtung nötig)
- Ein TTS-Backend — Edge TTS (Standard), ElevenLabs, Google Cloud TTS,
  Gemini TTS oder **Piper TTS** (vollständig offline; Per-Sprach-Stimmen
  einmal heruntergeladen über **Einstellungen → Stimme → Piper TTS →
  Stimmen jetzt herunterladen**)
- Ein konfigurierter **LLM** für den Übersetzungsschritt

## Schritt-für-Schritt

1. Klicken Sie in der Seitenleiste auf **Synchronisation**.
2. Lassen Sie eine oder mehrere Videodateien fallen (`.mp4`, `.webm`,
   `.mkv`, `.avi`, `.mov`, `.wmv`).
3. Wählen Sie die **Quellsprache** (die im Video *gesprochene* Sprache)
   und die **Zielsprache**, in die synchronisiert werden soll.
4. Klicken Sie auf **Synchronisation starten** (`Strg+Eingabe`).
5. Beobachten Sie den Pro-Aufgabe-Fortschritt in der Verlaufstabelle.
   Er durchläuft vier Phasen:

| Phase | Bereich | Was passiert |
|---|---|---|
| **STT** | 5–25% | Transkribiert das Quell-Audio |
| **Übersetzen** | 25–50% | LLM übersetzt jede Untertitelzeile |
| **TTS** | 50–90% | Synthetisiert Zielsprach-Stimme für jede Zeile |
| **Mix** | 90–100% | FFmpeg ersetzt die Audiospur |

6. Wenn fertig, **Öffnen** Sie die Zeile, um das synchronisierte Video abzuspielen.

## Ausgaben

Für jedes Eingabevideo erhalten Sie vier Dateien im Ausgabeverzeichnis:

```
movie.mp4
movie_dubbed_en_fr.mp4              ← synchronisiertes Video
movie_subtitle_en.srt               ← Originalsprachen-Untertitel
movie_subtitle_fr.srt               ← übersetzter Untertitel
movie_voice_fr.mp3                  ← synthetisierte Sprachspur
```

## Eine pausierte / abgestürzte Ausführung fortsetzen

Die Pipeline checkpointet nach jeder Phase. Wenn Sie **Stopp**
drücken, die App beenden oder abstürzen, setzt das Drücken von
**Fortsetzen** auf der Zeile von der letzten abgeschlossenen Phase
fort — Sie zahlen nicht erneut für STT oder Übersetzung, wenn sie
bereits gemacht waren.

Rechtsklick auf einen Done-/Failed-Eintrag für diese Optionen:

- **Fortsetzen** — setzt vom letzten Checkpoint fort, ohne erneut zu fragen.
- **Neu synchronisieren** — öffnet den Sprachpicker erneut; wenn Sie
  ein neues Ziel wählen, werden die Übersetzungs- und TTS-Checkpoints
  verworfen (Sie zahlen nicht erneut für STT). Dasselbe Ziel zu wählen
  führt effektiv vom letzten Checkpoint aus erneut aus, wie „Fortsetzen".
- **Öffnen** — spielt das synchronisierte Video ab.

## Hinweise

!!! warning "Lippensynchronität"
    Synchronisation passt zu den *Timestamps* des Quell-Audios, nicht
    zu Lippenbewegungen. Übersetzte Zeilen, die viel länger als das
    Original sind, klingen gehetzt; viel kürzere Zeilen lassen
    Schweigen. Für professionelle Synchronisation würde man
    normalerweise nach diesem Durchlauf manuell neu timen — eine
    Zukunftsfunktion.

!!! tip "Pre-Flight-Checks"
    Die Seite validiert FFmpeg + Ihre TTS-Backend-Schlüssel vor dem
    Start. Fehlender Schlüssel → freundlicher Dialog, keine
    halb-ausgeführte Synchronisation. Mit **Piper TTS** ausgewählt
    prüft sie auch, ob die Per-Sprach-Piper-Stimme auf der Festplatte
    ist; fehlende Stimme → Modal-Dialog mit **Einstellungen öffnen**-Button,
    der Sie in die Stimmenbibliothek bringt, sodass Sie keine STT- +
    Übersetzungs-Zeit verbrennen, nur um beim TTS-Schritt zu scheitern.

!!! tip "Zielsprache ändern"
    Bei einem Re-Target verwirft die Pipeline die Übersetzungs- + TTS-Checkpoints
    (ihr Inhalt ist nicht mehr gültig für die neue Sprache), behält aber
    den STT-Checkpoint — Sie sparen die Transkriptionskosten.

## Tastenkürzel

| Kürzel | Aktion |
|---|---|
| `Strg+Eingabe` | Synchronisation starten |
| `Strg+O` | Durchsuchen |
| `Strg+F` | Fokus auf Verlaufssuche |
| `Strg+P` | Aktive Warteschlange pausieren |
| `Strg+G` | Aktive Warteschlange fortsetzen |

`Strg+P` / `Strg+G` werden unterdrückt, wenn ein Texteingabefeld
Fokus hat, sodass sie nicht mit der Eingabe kollidieren.
