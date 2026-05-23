---
description: Erzeugen Sie SRT-, VTT-, ASS- oder SSA-Untertitel aus jedem Audio oder Video — verwendet Whisper oder Google Cloud Speech-to-Text für hochwertige Transkription.
---

# Untertitel erzeugen (STT)

Transkribieren Sie Audio oder Video in zeitgesteuerte Untertitel.
Erfasst Sprache und gibt SRT / VTT / ASS / SSA aus — mit optionaler
Übersetzung im selben Durchlauf.

## Was Sie brauchen

- **FFmpeg** im `PATH` für Audio-/Video-Dekodierung — siehe [FFmpeg-Setup](../setup/ffmpeg.md).
- Ein Transkriptions-Backend, eines von:
    - **faster-whisper** — lokal, offline, kostenlos (Standard; keine Einrichtung nötig)
    - **Google Cloud Speech-to-Text** — Cloud, kostenpflichtig, genauer bei verrauschtem Audio. Siehe [Google-Cloud-Setup](../setup/google-cloud.md).
    - **Soniox** — Cloud, kostenpflichtig, Echtzeit und Sprecher-Diarisation. Siehe [Soniox-Setup](../setup/soniox.md).

## Schritt-für-Schritt

1. Klicken Sie in der Seitenleiste auf **Untertitel erzeugen**.
2. Lassen Sie eine oder mehrere Audio-/Videodateien fallen
   (`.mp3`, `.wav`, `.m4a`, `.flac`, `.ogg`, `.aac`, `.wma`,
   `.mp4`, `.webm`, `.mkv`, `.avi`, `.mov`, `.wmv`).
3. Wählen Sie die **Quellsprache** (die im Audio *gesprochene* Sprache) —
   lassen Sie auf `Auto-Erkennung`, damit Whisper sie herausfindet.
4. Wählen Sie eine **Zielsprache** — wählen Sie `Keine Übersetzung`
   für ein einfaches Transkript oder eine der 45 unterstützten Sprachen,
   um das Transkript im selben Durchlauf zu übersetzen.
5. Wählen Sie das **Ausgabeformat** (SRT / VTT / ASS / SSA).
6. Klicken Sie auf **Erzeugen** (oder `Strg+Eingabe`).
7. Beobachten Sie die Warteschlange. **Öffnen** Sie die Zeile, wenn fertig.

## Formatauswahl

| Format | Geeignet für |
|---|---|
| **SRT** | Universell — fast jeder Player unterstützt es |
| **VTT** | HTML5-`<video>`-`<track>`-Elemente |
| **ASS / SSA** | Karaoke, gestylte Untertitel, Fansub-Workflows |

Die vier Formate gehen durch denselben Parser hin und zurück, sodass
Sie das Ausgabeformat bei einer Re-Übersetzung ändern können, ohne
das Timing zu verlieren.

## Whisper-Modellgröße

Wechseln in **Einstellungen → Untertitel**:

| Modell | Größe | Geschwindigkeit | Genauigkeit |
|---|---|---|---|
| `tiny` | ~75 MB | sehr schnell | niedrig |
| `base` (Standard) | ~150 MB | schnell | passabel |
| `small` | ~500 MB | mittel | gut |
| `medium` | ~1,5 GB | langsam | hoch |
| `large` | ~3 GB | sehr langsam | beste |

Modelle werden bei der ersten Verwendung heruntergeladen und lokal
gecacht. Bei langsamer Verbindung fühlt sich der erste Lauf lang an;
nachfolgende Läufe sind schnell.

## STT-Methoden-Vergleich

| Backend | Kosten | Online? | Sprecher-Diarisation | Sprachen |
|---|---|---|---|---|
| **Whisper** (lokal) | Kostenlos | Nein | Nein | 99 |
| **Google Cloud STT** | Kostenpflichtig | Ja | Ja (`latest_long`-Modell) | 125+ |
| **Soniox** | Kostenpflichtig | Ja | Ja (Pro-Token-Sprecher-Labels) | 60+ |

Wechseln in **Einstellungen → Untertitel → STT-Methode**.

## Tipps

- **Stop-Taste** — unterbricht einen laufenden Batch. Dateien hinter
  dem aktiven bleiben in der Warteschlange; Sie können später fortsetzen.
- **Neu erzeugen** — Rechtsklick auf einen erledigten Eintrag, um mit
  einem anderen Format / Sprache / STT-Methode neu zu laufen.
- **Lange Audios** — Whisper bewältigt stundenlanges Audio gut; ca.
  1 Minute Verarbeitung pro Minute Audio auf CPU mit `base`-Modell budgetieren.

## Tastenkürzel

| Kürzel | Aktion |
|---|---|
| `Strg+Eingabe` | Erzeugen |
| `Strg+O` | Durchsuchen |
| `Strg+F` | Fokus auf Verlaufssuche |
