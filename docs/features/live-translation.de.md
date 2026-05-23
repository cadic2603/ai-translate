---
description: "Echtzeit-Sprachübersetzung: transkribiere und übersetze Mikrofon- oder Systemaudio live mit Whisper- oder Soniox-Backends."
---

# Live-Übersetzung

Echtzeit-Untertitel und -Übersetzungen vom Mikrofon, Systemaudio oder
beidem — mit einem optionalen Overlay-Fenster, das immer im Vordergrund
bleibt, damit die Untertitel über dem liegen, was du gerade ansiehst.

## Wofür du es nutzen kannst

- **Live-Meeting-Untertitel** — untertitele einen Zoom- / Meet- / Teams-Anruf
  in einer anderen Sprache, ohne als Übersetzer-Bot beizutreten.
- **Echtzeit-Sprachenlernen** — untertitele fremdsprachige Inhalte
  (Filme, Podcasts, Vorlesungen) mit deiner Muttersprache als
  Übersetzungsspur.
- **Systemweite Untertitel** — erfasse Systemaudio, um YouTube /
  Netflix / alles, was über deine Lautsprecher läuft, zu untertiteln.

## Was du brauchst

- **FFmpeg** im `PATH` — siehe [FFmpeg-Setup](../setup/ffmpeg.md).
- Ein STT-Backend, eines von:
    - **faster-whisper** — lokal, offline, kostenlos, Standard
    - **Soniox** — Cloud, kostenpflichtig, Echtzeit-Sprecher-Diarisierung. Siehe [Soniox-Setup](../setup/soniox.md).

- Für die **Systemaudio-Erfassung** wird das richtige Backend pro OS
  automatisch ausgewählt: Linux nutzt `parec` (PulseAudio / PipeWire),
  Windows nutzt natives WASAPI-Loopback (in den meisten Fällen keine
  zusätzliche Software), macOS nutzt `ffmpeg -f avfoundation` mit einem
  virtuellen Loopback-Gerät (BlackHole / Loopback / etc.). Ein Inline-
  Warnbanner mit anklickbaren Installationslinks erscheint, falls etwas
  fehlt. Siehe [Setup → Systemaudio](../setup/system-audio.md) für
  vollständige Installationsanweisungen pro OS.

## Schritt für Schritt

1. Klicke in der Seitenleiste auf **Live-Übersetzung**.
2. Konfiguriere einmalig unter **Einstellungen → Live**:

    - **Quellsprache** (gesprochene Sprache)
    - **Zielsprache** (oder leer lassen für reine Transkription)
    - **Audioquelle**: Mikrofon / Systemaudio / Beide
    - **STT-Methode**: Whisper / Soniox

3. Zurück auf der Live-Seite klicke auf **Start** (`Ctrl+Enter`).
4. Die Transkription füllt den Hauptbereich Karte für Karte. Das
   schwebende **Overlay**-Fenster zeigt ebenfalls Untertitel
   (zieh es dahin, wo du es haben willst).
5. Klicke auf **Stop**, um die Sitzung zu beenden.

## Die Transkriptionsansicht

Wähle ein Layout in der Symbolleiste:

- **Beide gestapelt** — Original + Übersetzung, eines über dem anderen
- **Beide nebeneinander** — Original links, Übersetzung rechts
- **Nur Original** / **Nur Übersetzung**

Die Symbolleisten-Schaltflächen verwenden **`AN`** / **`AUS`**-Suffixe
für den Status auf einen Blick — z. B. `TTS AN`, `TTS AUS`,
`Zeitstempel AN`, `Overlay AUS`.

Schalte **Zeitstempel** mit dem Uhr-Icon ein/aus. Schalte die
**TTS-Wiedergabe** der übersetzten Zeilen mit dem Lautsprecher-Icon
ein/aus. Folgt deiner Auswahl unter **Einstellungen → Stimme →
TTS-Methode** — Edge TTS (Standard), ElevenLabs, Google Cloud TTS,
Gemini TTS oder **Piper TTS** (vollständig offline). Mit ausgewähltem
Piper fallen fehlende Stimmen pro Sprache **stillschweigend auf Edge
TTS zurück** — auf dieser Seite gibt es keinen modalen Pre-Flight, da
das Blockieren des Live-Flusses durch einen Download-Dialog schlimmer
wäre als das Fallback.

## Das Overlay-Fenster

Ein ziehbares, größenveränderbares, immer-im-Vordergrund Werkzeugfenster.
Tastenkürzel:

| Tastenkürzel | Aktion |
|---|---|
| `Ctrl+[` / `Ctrl+]` | Deckkraft verringern / erhöhen |
| `Ctrl+Pfeil` | Overlay verschieben |
| `Ctrl+0` / `Ctrl+9` | Vergrößern / verkleinern |

Position, Größe, Deckkraft und Schriftgröße bleiben zwischen Sitzungen
erhalten.

### Echtzeit-Synchronisierung mit Einstellungen

Schriftgröße und Deckkraft funktionieren in beide Richtungen:
Ziehen Sie den Regler **Schriftgröße** oder **Deckkraft** unter
**Einstellungen → Live → Overlay-Konfiguration** und das geöffnete
Overlay aktualisiert sich in Echtzeit. Umgekehrt aktualisieren die
Tasten `+` / `-` / `Ctrl+[` / `Ctrl+]` innerhalb des Overlays die
Regler in den Einstellungen. Kein Neuöffnen des Overlays nötig.

### Platzhalter für leeren Zustand

Vor der Audioaufnahme zeigt das Overlay einen Platzhalter
("Drücken Sie Start..." im Leerlauf / "Höre zu..." nach Start) der
den Leerzustand des Hauptfensters spiegelt — der Wechsel erfolgt
synchron zur laufenden Statusanzeige. Der Platzhalter skaliert mit
der aktuellen Breite × Höhe des Overlays und bleibt in jeder
Fenstergröße lesbar.

### Minimale-Untertitel-Modus

Das Kontrollkästchen **Minimale Untertitel anzeigen** unter
Einstellungen → Live → Overlay-Konfiguration verbirgt die
Zeitstempel- und Sprecher-Chips auf dem Overlay, während sie im
Hauptfenster sichtbar bleiben. Nützlich, wenn das Overlay mit
einem Publikum geteilt wird (Präsentationsmodus / Bildschirm­
freigabe), Sie aber in Ihrer Arbeitsansicht volle Metadaten
behalten möchten. Die Umschaltung gilt nur für das Overlay — sie
ändert nicht Ihre "Sprecherbeschriftungen"-Einstellung für das
Hauptfenster.

## Transkription speichern

Klicke auf **Transkription speichern**, um die Sitzung in eine
`.txt`-Datei mit Zeitstempeln, Sprechern, Originalzeilen und
übersetzten Zeilen zu exportieren.

## Auswahl eines STT-Backends

| Backend | Am besten für | Kosten | Latenz |
|---|---|---|---|
| **Whisper** (lokal) | Offline, datenschutzsensitiv | Kostenlos | Mittel (~1 s nach Satzende) |
| **Soniox** | Meetings mit mehreren Sprechern | Kostenpflichtig (~0,005 $ / Min.) | Niedrig (Echtzeit) |

## Hinweise

!!! warning "Mikrofonauswahl"
    Der Mikrofoneingang nutzt immer das **Standardgerät des OS** — es
    gibt keine In-App-Auswahl (sounddevice zeigt zu viele virtuelle
    ALSA-Plugins, um nützlich zu sein, und das OS besitzt bereits die
    UI für das Standardmikrofon). Stelle dein bevorzugtes Mikrofon in
    den Soundeinstellungen deines OS ein, bevor du startest.

!!! warning "TTS-Backpressure"
    Die TTS-Warteschlange ist auf die letzten 3 Sätze begrenzt — älteres
    Audio in der Warteschlange wird verworfen, wenn die Synthese
    hinterherhinkt. So bleibt die gesprochene Wiedergabe nahe an den
    Untertiteln auf dem Bildschirm.

!!! tip "ElevenLabs ohne Schlüssel"
    Wenn du die TTS-Methode auf ElevenLabs gesetzt hast, aber kein
    API-Schlüssel konfiguriert ist, fällt die Live-Seite automatisch
    auf Edge TTS zurück und kündigt das Fallback im Statuslabel an.

## Tastenkürzel

| Tastenkürzel | Aktion |
|---|---|
| `Ctrl+Enter` | Start / Stop |
| `Ctrl+K` | Log löschen (mit Bestätigung) |
| `Ctrl+[` / `Ctrl+]` | Overlay-Deckkraft anpassen |
