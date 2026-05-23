---
description: Konvertiere Untertitel in gesprochenes Audio mit Edge TTS, ElevenLabs, Google Cloud TTS, Gemini TTS oder offline Piper TTS — bewahrt SRT-Timing für Synchronisations-Qualitäts-Sprachgenerierung.
---

# Stimme generieren (TTS)

Synthetisiere Untertiteldateien (mit Timing) oder beliebigen Text zu
MP3- / WAV-Audio. Fünf TTS-Backends: Edge TTS (kostenlos), ElevenLabs
(höchste Qualität), Google Cloud TTS, Gemini TTS (kostenlose Stufe)
und Piper TTS (offline).

## Was du brauchst

- **FFmpeg** im `PATH` — siehe [FFmpeg-Setup](../setup/ffmpeg.md).
- Ein TTS-Backend, eines von:
    - **Edge TTS** — kostenlos, kein Schlüssel, Standard. Verwendet
      die Cloud-Stimmen von Microsoft Edge.
    - **ElevenLabs** — kostenpflichtig, höchste Qualität. Siehe [ElevenLabs-Setup](../setup/elevenlabs.md).
    - **Google Cloud TTS** — kostenpflichtig, sehr gut. Siehe [Google Cloud-Setup](../setup/google-cloud.md).
    - **Gemini TTS** — kostenlose Stufe, natürliche vorgefertigte
      Stimmen. Verwendet deinen vorhandenen Gemini-API-Schlüssel aus
      dem LLM-Tab — kein zusätzliches Setup.
    - **Piper TTS** — vollständig offline neuronales TTS. Kein
      API-Schlüssel, keine Netzwerkaufrufe — Stimmen sind ~25–60 MB
      ONNX-Dateien, die einmal über **Einstellungen → Stimme → Piper
      TTS → Stimmen jetzt herunterladen** heruntergeladen werden. 32
      der 45 Sprachen der App haben heute eine Piper-Stimme; Sprachen
      ohne Piper-Abdeckung fallen zur Synthesezeit stillschweigend auf
      Edge TTS zurück.

## Schritt für Schritt

1. Klicke in der Seitenleiste auf **Stimme generieren**.
2. Lege eine oder mehrere `.srt` / `.vtt` / `.ass` / `.ssa`
   Untertiteldateien ab.
3. Wähle die **Sprache** (wenn möglich aus dem Untertiteldateinamen
   automatisch erkannt — z. B. `_translated_en_de.srt` wird als
   Deutsch erkannt).
4. Wähle das **Stimmgeschlecht** — `Weiblich` oder `Männlich`.
5. Wähle das **Ausgabeformat** — `.mp3` (Standard) oder `.wav`.
6. Klicke auf **Generieren** (oder `Ctrl+Enter`).
7. **Öffne** die Zeile, wenn fertig — sie spielt in deiner Standard-
   Audio-App ab.

## Ausgabe

Du erhältst eine einzelne Audiodatei mit den Sprachspuren, die am
Zeitstempel jedes Untertitels platziert sind. Stille Lücken füllen die
Zeit zwischen den Cues, sodass das Audio mit dem ursprünglichen Timing
synchron bleibt.

## Auswahl eines TTS-Backends

| Backend | Kosten | Stimmen | Notizen |
|---|---|---|---|
| **Edge TTS** | Kostenlos | Hunderte, alle wichtigen Sprachen | Standard. Kein Setup. |
| **ElevenLabs** | Kostenpflichtig (~5 $/Mo Einstiegsstufe) | Premium-Neuronale Stimmen, Sprach-Klonung | Höchste Qualität. Voice-ID wird in Einstellungen → Service festgelegt. |
| **Google Cloud TTS** | Kostenpflichtig (~4 $/M Zeichen; 1 M kostenlos / Monat) | WaveNet- / Studio-Stimmen in 50+ Sprachen | Starke WaveNet-Stimmen für europäische Sprachen. Standardmäßig wählt der Server eine Stimme nach Sprache + Geschlecht. |
| **Gemini TTS** | Kostenlose Stufe (Developer-API-Quoten gelten) | Natürliche vorgefertigte Stimmen in 24+ Sprachen — `Kore` (weiblich Standard) / `Puck` (männlich Standard) | Verwendet deinen Gemini-API-Schlüssel aus dem LLM-Tab. Ausgabe pro Aufruf auf ~30 s begrenzt; lange Texte werden automatisch an Satzgrenzen geteilt. |
| **Piper TTS** | Kostenlos, **offline** | Neuronale Stimmen in 32 der 45 Sprachen der App | Kein Schlüssel, kein Netz. Stimme pro Sprache wird auf Anfrage über **Einstellungen → Stimme → Piper TTS → Stimmen jetzt herunterladen** heruntergeladen (~25–60 MB jede). Pre-Flight fängt eine fehlende Stimme ab, bevor die Arbeit beginnt. |

Wechsle in **Einstellungen → Stimme → TTS-Methode**.

## Piper-TTS-Spezifika

Piper ist das einzige vollständig offline TTS-Backend in der App. Ein
paar Dinge, die du wissen solltest:

- **Stimmen-Bibliothek-Dialog** — öffne über **Einstellungen → Stimme
  → Piper TTS → Stimmen jetzt herunterladen**. Jede Sprachzeile zeigt
  einen `Weibliche Stimme`- und / oder `Männliche Stimme`-
  Download-Button (einige Sprachen sind nur ein Geschlecht). Stimmen
  kommen aus dem HuggingFace-Katalog
  [rhasspy/piper-voices](https://huggingface.co/rhasspy/piper-voices).
- **Abdeckung** — 32 der 45 Sprachen der App haben eine Piper-Stimme.
  Die 13 ohne Abdeckung (Belarussisch, Bengali, Chinesisch
  (Traditionell), Kroatisch, Estnisch, Hebräisch, Japanisch, Khmer,
  Koreanisch, Litauisch, Malaiisch, Mongolisch, Thailändisch) fallen
  zur Synthesezeit stillschweigend auf Edge TTS zurück, sodass die
  Synthese nie an einer fehlenden Stimme hart fehlschlägt.
- **Geschlechtsauflösung** — wenn du `Weiblich` wählst, versucht die
  Engine zuerst die weibliche Stimme für diese Sprache; wenn nur eine
  männliche Stimme existiert, verwendet sie diese stattdessen (und
  umgekehrt). Auf INFO-Ebene protokolliert.
- **Pre-Flight-Tor** — bevor ein Voice-Lauf beginnt, prüft die Seite,
  dass die Piper-Stimme pro Sprache auf der Festplatte ist. Wenn
  fehlend, bekommst du einen modalen Dialog mit einer **Einstellungen
  öffnen**-Schaltfläche, die dich direkt zur Stimmen-Bibliothek bringt,
  damit du sie herunterladen kannst, ohne deine Warteschlange zu
  verlieren.

## Gemini-TTS-Spezifika

Gemini TTS verwendet `gemini-2.5-flash-preview-tts` über die
Developer-API. Ein paar Dinge, die du wissen solltest:

- **Stimmenauswahl** erfolgt heute nach Geschlecht — Weiblich
  abbildet auf `Kore`, Männlich auf `Puck`. Beides sind klare,
  neutrale Stimmen, die über Sprachen hinweg funktionieren, ohne zu
  charakterhaft zu klingen.
- **Ausgabelängen-Limit** — jeder Gemini-API-Aufruf gibt höchstens
  ~30 s Sprache zurück. Die App teilt Eingabetext unter
  `_GEMINI_TTS_MAX_BYTES` (~2000 Byte ≈ 30 s) an Satzgrenzen, dann
  verkettet die Stücke via FFmpeg. Du wirst bei normalem
  Untertiteltext keine Kürzung treffen.
- **Audioformat** — Gemini gibt rohes PCM bei 24 kHz mono s16le aus;
  die App transkodiert pro Stück zu MP3 (oder WAV, wenn du es
  ausgewählt hast), damit die endgültige Datei deinem ausgewählten
  Ausgabeformat entspricht.
- **Vertex AI wird für TTS noch nicht unterstützt** — selbst wenn
  dein LLM-Tab für Vertex konfiguriert ist, benötigt Gemini TTS
  immer noch einen Developer-API-Schlüssel. Die App löst im Voraus
  `AUTH_ERROR` aus, wenn er fehlt.

## ElevenLabs-Modelle

Drei Modelle sind exponiert:

| Modell | Latenz | Qualität | Verwenden für |
|---|---|---|---|
| `eleven_multilingual_v2` (Standard) | Mittel | Hoch | Allgemeines TTS |
| `eleven_v3` | Mittel | Höchste | Studio / Produktion |
| `eleven_flash_v2_5` | Niedrig | Gut | Echtzeit / Live-Modus |

Konfiguriere in **Einstellungen → Stimme → ElevenLabs-Modell**.

## Tipps

!!! tip "Neu generieren"
    Rechtsklick auf eine Zeile → **Neu generieren**, um Stimmgeschlecht
    / TTS-Methode / Format zu wechseln, ohne die Übersetzung neu
    auszuführen.

!!! tip "Pre-Flight-Prüfungen"
    Die Seite validiert den ElevenLabs-API-Schlüssel (wenn ausgewählt)
    und die FFmpeg-Verfügbarkeit, bevor sie startet. Du siehst einen
    freundlichen Dialog, wenn etwas fehlt.

!!! warning "Stop ist atomar"
    Drücke **Stop** während der Synthese und du bekommst keine halb
    geschriebene MP3-Datei im Ausgabeverzeichnis — die Datei wird
    zuerst an einen temporären Ort geschrieben, dann nur bei Erfolg
    in Position verschoben.

## Tastenkürzel

| Tastenkürzel | Aktion |
|---|---|
| `Ctrl+Enter` | Generieren |
| `Ctrl+O` | Durchsuchen |
| `Ctrl+F` | Verlaufssuche fokussieren |
