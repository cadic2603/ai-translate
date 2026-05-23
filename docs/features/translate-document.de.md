---
description: Übersetze PDFs, Word, Excel, PowerPoint, ODF, EPUB, HTML, JSON, YAML, SRT und 30+ weitere Dateiformate unter Beibehaltung von Formatierung und Layout.
---

# Dokument übersetzen

Übersetze ganze Dateien — Office, PDF, EPUB, Klartext, Untertitel,
Lokalisierungsformate und mehr — mit erhaltener Formatierung.

## Unterstützte Formate

| Kategorie | Endungen |
|---|---|
| Office | `.docx`, `.xlsx`, `.pptx`, `.odt`, `.ods`, `.odp`, `.doc`, `.xls`, `.ppt` |
| PDF | `.pdf` |
| Text & Web | `.txt`, `.md`, `.rst`, `.html`, `.htm`, `.xhtml`, `.xml`, `.rtf`, `.json`, `.csv` |
| eBooks | `.epub` |
| Untertitel | `.srt`, `.vtt`, `.ass`, `.ssa` |
| Lokalisierung | `.po`, `.pot`, `.xliff`, `.xlf`, `.yaml`, `.yml`, `.properties`, `.strings` |

## Schritt für Schritt

1. Klicke in der Seitenleiste auf **Dokument übersetzen**.
2. Ziehe Dateien hinein (oder klicke auf **Durchsuchen**). Ordner
   funktionieren auch — unterstützte Dateien darin werden rekursiv
   erkannt.
3. Wähle **Quelle** (oder lasse auf `Automatisch erkennen`) und
   **Ziel**.
4. Klicke auf **Übersetzen** — oder drücke `Ctrl+Enter`.
5. Die Verlaufstabelle darunter zeigt den Fortschritt pro Datei
   (Ausstehend → Übersetzen → Fertig / Fehlgeschlagen). Die
   Seitenleiste zeigt einen Spinner, solange eine Aufgabe aktiv ist.
6. Klicke auf **Öffnen** in einer Zeile, um die übersetzte Datei zu
   öffnen. Rechtsklick für Optionen: erneut übersetzen, pausieren,
   wiederholen, löschen.

## Wo Dateien landen

Standardmäßig werden übersetzte Dateien neben dem Original mit dem
Suffix `_translated_<src>_<tgt>` gespeichert:

```
~/Documents/bericht.docx
~/Documents/bericht_translated_en_de.docx     ← hier
```

Ändere dies unter **Einstellungen → Allgemein → Speicherpfad für
Übersetzungen** in ein benutzerdefiniertes Verzeichnis.

## Limits und Schutzmaßnahmen

- **100-Datei-Drop-Limit** — wenn du mehr ablegst, bekommst du eine
  Benachrichtigung. Übersetze in Stapeln.
- **Duplikaterkennung** — lege eine Datei ab, die bereits in der
  Warteschlange ist, und du siehst eine Benachrichtigung (das
  Duplikat wird verworfen, nicht doppelt hinzugefügt).
- **Automatische Wiederaufnahme** — beende die App, während
  Übersetzungen laufen, und sie werden beim nächsten Start
  fortgesetzt (Aufgaben mit Status Ausstehend / Übersetzen).

## Office-spezifische Optionen

Der Übersetzungs-Tab in **Einstellungen** zeigt diese Schalter für
Office-Dateien:

| Option | Was sie macht |
|---|---|
| **Eingebettete Bilder übersetzen** | Führt OCR + LLM-Vision auf Bildern in `.docx` / `.xlsx` / `.pptx` aus und fügt das übersetzte Bild wieder ein. Benötigt konfiguriertes OCR. |
| **Kommentare übersetzen** | Kommentare / Überprüfungsnotizen werden zusammen mit dem Haupttext übersetzt. |
| **Formen & Textfelder übersetzen** | Erfasst Text, der in Formen, Sprechblasen und schwebenden Textfeldern liegt. |
| **Sprechernotizen übersetzen** | PowerPoint-Sprechernotizen werden übersetzt. |
| **Blattnamen übersetzen** | Excel-Blattregisterbeschriftungen werden übersetzt. |
| **Legacy automatisch konvertieren** | `.doc` / `.xls` / `.ppt` werden vor der Übersetzung in modernes OOXML konvertiert (bessere Wiedergabetreue). |
| **ODF automatisch konvertieren** | `.odt` / `.ods` / `.odp` werden vor der Übersetzung in OOXML konvertiert. |

Jede Office-Übersetzung erhält die Formatierung pro Run: fett, kursiv,
unterstrichen, durchgestrichen, Schriftgröße, Farbe, Hyperlinks,
Kopfzeilen, Fußzeilen, Fußnoten, Endnoten, alles davon.

### Eingebettete Bildübersetzung: Skip-with-warning + Cache

Wenn **Eingebettete Bilder übersetzen** aktiviert ist, durchläuft
jedes Bild OCR → LLM-Vision → gerendertes Wiedereinfügen. Zwei
Verhaltensweisen sind wissenswert:

- **Skip-with-warning**: Wenn ein Bild nicht übersetzt werden
  kann (zu groß, beschädigt, vom Modell abgelehnt), wird das
  Dokument trotzdem fertiggestellt — das defekte Bild bleibt
  in der Originalsprache, eine Warnung wird in `app.log`
  protokolliert und die Schleife setzt mit dem nächsten Bild
  fort. Nur fatale LLM-Fehler (`AUTH_ERROR`, `QUOTA_ERROR`,
  `VISION_NOT_SUPPORTED`) stoppen die Pipeline sofort, weil
  sie auch alle übrigen Bilder blockieren. Der Info-Banner
  über dem Kontrollkästchen **Eingebettete Bilder übersetzen**
  dokumentiert die Richtlinie inline.
- **Per-Image-Cache**: Erfolgreiche Bildübersetzungen werden
  unter dem internen Speicherverzeichnis der Aufgabe abgelegt,
  gekeyed über SHA256 der Quellbytes. Beim erneuten Versuch
  treffen bereits übersetzte Bilder den Cache, anstatt OCR +
  LLM erneut auszuführen — bezahlte Arbeit wird nicht
  wiederholt. Doppelte Bilder (ein Firmenlogo auf jeder Folie)
  werden einmal übersetzt und N − 1 Mal wiederverwendet.

Die Ausgabedatei erscheint nur bei **Erfolg** im gewählten
Ausgabeordner — Teilübersetzungen aus abgebrochenen oder
fehlgeschlagenen Läufen bleiben auf das interne
Speicherverzeichnis der Aufgabe beschränkt, sodass Ihr
Ausgabeordner nie verwaiste halb übersetzte Dokumente
sammelt.

## PDF-Spezifika

PDFs verwenden eine Extract-Overlay-Engine: der Originaltext wird an
Ort und Stelle redigiert und der übersetzte Text in dieselben
Boxen überlagert, wobei das visuelle Layout erhalten bleibt. Pro-Seite-
Checkpointing bedeutet, dass ein pausierter / abgestürzter Lauf von
dort fortgesetzt wird, wo er aufgehört hat, nicht von Seite 1.

Was übersetzt wird:

- Haupttext (mit Ausrichtungserkennung — links / Mitte / rechts /
  Blocksatz)
- Lesezeichen / Gliederungen (Inhaltsverzeichniseinträge)
- Formularfelder (Texteingaben, Dropdowns, Listenfelder)
- Hyperlinks (Link-Rechteck wird aktualisiert, um den neuen Text zu
  umschließen)
- Eingebettete Bilder (wenn **Eingebettete Bilder übersetzen**
  aktiviert ist)
- PDF-Kommentare / Anmerkungen

Für gescannte PDFs (ohne eingebettete Textebene) wird OCR pro Seite
automatisch ausgeführt. Konfiguriere deine OCR-Engine unter
**Einstellungen → OCR**.

## Rechts-nach-links-Ausgabe

Übersetzungen ins **Arabische**, **Hebräische** oder **Persische**
werden in jedem Ausgabeformat nativ als RTL gerendert — `dir="rtl"`
in PDF-Overlays, HTML und EPUB-Kapitel injiziert (mit
`page-progression-direction="rtl"` im EPUB-OPF, damit Apple Books und
Kindle in die richtige Richtung blättern); DOCX `<w:bidi/>` +
`<w:rtl/>`, PPTX `rtl="1"`, XLSX-Rechts-nach-links-Blattansicht,
ODT/ODS/ODP `style:writing-mode="rl-tb"`, RTF `\rtldoc` und
ASS/SSA-Ausrichtungscode-Spiegelung (`\an1` ↔ `\an3`, `\an4` ↔
`\an6` etc.). Mittenausrichtungen werden nicht angetastet.

## Tastenkürzel

| Tastenkürzel | Aktion |
|---|---|
| `Ctrl+Enter` | Übersetzung starten |
| `Ctrl+O` | Nach Dateien durchsuchen |
| `Ctrl+F` | Verlaufssuche fokussieren |
| `Ctrl+P` | Aktive Warteschlange pausieren |
| `Ctrl+G` | Aktive Warteschlange fortsetzen |
| `Entf` | Ausgewählte Verlaufseinträge löschen |

`Ctrl+P` / `Ctrl+G` werden unterdrückt, wenn ein Texteingabefeld den
Fokus hat, damit sie nicht mit dem Tippen kollidieren.

## Wenn etwas fehlschlägt

Eine fehlgeschlagene Aufgabe zeigt einen roten Status mit einem
Fehlercode und einer lokalisierten Meldung — siehe den
[Troubleshooting-Leitfaden](../troubleshooting.md) für gängige
(`AUTH_ERROR`, `QUOTA_ERROR`, `FFMPEG_NOT_FOUND` usw.).
