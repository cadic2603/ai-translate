---
description: Erfasse Systemaudio auf Linux, macOS und Windows für die Live-Seite von AI Translate — übersetze in Echtzeit jeden Sound, der auf deinem Computer abgespielt wird.
---

# Systemaudio-Erfassung (Live)

Die Seite **[Live-Übersetzung](../features/live-translation.md)** kann
**Systemaudio** erfassen (alles, was über deine Lautsprecher gespielt
wird), damit du jede Medien untertiteln / übersetzen kannst — Zoom-
Anrufe, YouTube, Netflix, Spiele, Systemklänge.

In **Einstellungen → Live → Audioquelle** (oder die Combo oben auf
der Live-Seite) wähle:

- **Mikrofon** — nur dein Mikro
- **Systemaudio** — nur was über deine Lautsprecher abgespielt wird
- **Beide** — beide gemischt (gut zum Erzählen über Medien oder zum
  Erfassen hybrider Meetings)

Wenn du **Systemaudio** oder **Beide** wählst, dispatched die App
zum richtigen Erfassungsbackend für dein OS. Ein Inline-Warnbanner
mit anklickbaren Installationslinks erscheint, wenn die OS-
Voraussetzungen nicht erfüllt sind, damit du keine Sitzung starten
musst, um herauszufinden, dass etwas fehlt.

## Linux (PulseAudio / PipeWire)

Funktioniert sofort auf jeder modernen Distro.

Die App verwendet `parec` (PulseAudio Recorder), um die **Monitor-
Quelle** deines Standardsinks abzugreifen. Der PulseAudio-
Kompatibilitäts-Shim von PipeWire macht dies transparent — du
brauchst kein rohes PulseAudio.

```bash
parec --version    # sollte etwas ausdrucken
```

Wenn `parec` fehlt, erkennt das Warnbanner den Paketmanager deiner
Distro und fügt den genauen Installationsbefehl ein — zum Beispiel:

> Systemaudio-Erfassung benötigt PulseAudio oder PipeWire — führe `sudo apt-get install pulseaudio` aus.

Erkannt auf apt-get / dnf / pacman / zypper / apk; du kannst den
Befehl direkt in ein Terminal kopieren-einfügen.

## macOS

CoreAudio exponiert Systemaudio nicht nativ, also brauchst du ein
**virtuelles Loopback-Gerät** — installiere eines von:

- **[BlackHole](https://existential.audio/blackhole/)** — kostenlos, Open Source
- **[Loopback](https://rogueamoeba.com/loopback/)** — kostenpflichtig, polierte GUI
- **[Soundflower](https://github.com/mattingalls/Soundflower)** — Legacy-Free-Option
- **[iShowU Audio Capture](https://shinywhitebox.com/audio-capture)** — kostenpflichtig

Die App erkennt sie automatisch über
`ffmpeg -f avfoundation -list_devices` und verwendet das erste
Match. Du musst das Loopback nicht als deinen Standardausgang /
-eingang setzen — die Erfassung passiert direkt über das
avfoundation-Backend von `ffmpeg`.

Nach der Installation wähle einfach **Systemaudio** im Combo der
Live-Seite und das Warnbanner verschwindet.

## Windows

Nativ — **keine zusätzliche Software nötig** in den meisten Fällen.

Die App spricht direkt mit **WASAPI loopback** über das Python-Paket
[`soundcard`](https://github.com/bastibe/SoundCard) (automatisch mit
der App auf Windows installiert). Dies ist dieselbe native
Loopback-API, die Tauri- / Rust-Desktop-Apps verwenden; sie erfasst
den Standard-Lautsprecherausgang ohne ein virtuelles Kabel.

Wenn aus irgendeinem Grund WASAPI loopback nicht verfügbar ist
(ältere Windows-Versionen, ungewöhnliches Audiotreiber), fällt die
App auf `ffmpeg -f dshow` gegen ein virtuelles DirectShow-Loopback-
Gerät zurück. Wähle eines von:

- **[Screen Capture Recorder](https://github.com/rdp/screen-capture-recorder-to-video-windows-free)** — kostenlos, bietet `virtual-audio-capturer`
- **[VB-Audio Virtual Cable](https://vb-audio.com/Cable/)** — kostenlos, kommt als `CABLE Output (VB-Audio Virtual Cable)`
- **Stereo Mix (Realtek Audio)** — Legacy-Onboard-Option, oft standardmäßig deaktiviert

Die App sondiert diese in Reihenfolge und verwendet das erste
vorhandene.

## Warum „Beide" deine Stimme UND Systemaudio aufnimmt

Im **Beide**-Modus öffnet die App ZWEI Erfassungsströme parallel —
dein Mikrofon über `sounddevice`, Systemaudio über das OS-spezifische
Backend oben — und mischt sie auf Sample-Block-Granularität. Dies
ist der richtige Modus zum Erzählen über ein Video oder zum Erfassen
beider Seiten eines hybriden Meetings (deine Stimme plus Teilnehmer
auf Lautsprechern).

> **Tipp:** Wenn du ein Echo hörst oder doppelte Untertitel
> bekommst, hast du Systemaudio, das durch dein Mikrofon kommt
> (laute Lautsprecher → Mikro nimmt es auf). Wechsle zu nur
> **Systemaudio** oder verwende Kopfhörer.

## Fehlerbehebung

| Symptom | Wahrscheinliche Ursache |
|---|---|
| Live-Seite startet, aber keine Untertitel | Falsche Audioquelle ausgewählt oder dein Standard-Mikro ist stummgeschaltet |
| Untertitel für deine Stimme, aber nicht das YouTube-Video | Systemaudio-Voraussetzung ist nicht installiert (Banner sollte Installationsanweisungen anzeigen) |
| Untertitel doppelt (Echo) | „Beide"-Modus nimmt Systemaudio zweimal auf — einmal von Lautsprechern über Mikrofon, einmal über Loopback. Wechsle nur zu Systemaudio oder verwende Kopfhörer |
| Banner bleibt sichtbar nach Installation der fehlenden Software | Wechsle die Tabs und komm zurück — das Banner prüft beim Anzeigen der Seite erneut |
| macOS: BlackHole installiert, aber Banner immer noch oben | Bestätige, dass BlackHole in der Audiogerätliste von `ffmpeg -f avfoundation -list_devices true -i ""` steht; die App muss es dort sehen |
| Windows: WASAPI loopback schlägt trotz keinem Fehler fehl | Versuche VB-Audio Virtual Cable als Fallback zu installieren; ältere Windows-Versionen oder einige Audiotreiber exponieren Loopback nicht über `soundcard` |
