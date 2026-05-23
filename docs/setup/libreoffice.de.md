---
description: Installiere LibreOffice, damit AI Translate Legacy-Office-Formate (.doc, .xls, .ppt) und ODF-Dateien (.odt, .ods, .odp) auf macOS und Linux übersetzen kann.
---

# LibreOffice (Office-Formate)

Die Office-Übersetzungspipeline wählt das beste verfügbare Backend in
dieser Reihenfolge:

1. **win32com** (Windows + MS Office installiert) — höchste Treue
2. **LibreOffice UNO** (plattformübergreifend) — Fallback, wenn
   win32com nicht da ist
3. **python-docx / openpyxl / python-pptx** (nur moderne Formate) —
   Pure-Python-Fallback, wenn keiner der oben genannten verfügbar ist

LibreOffice ist **der einzige Weg** für Legacy-`.doc` / `.xls` /
`.ppt` auf Linux und macOS, und der empfohlene Weg auf diesen
Plattformen auch für moderne Office-Formate (bessere Treue als das
Pure-Python-Backend, besonders für Tabellen und eingebettete Objekte).

## Installieren

=== "macOS"
    ```bash
    brew install --cask libreoffice
    ```

    Oder lade von <https://www.libreoffice.org/download/download/>
    herunter.

=== "Ubuntu / Debian"
    ```bash
    sudo apt install libreoffice
    ```

=== "Fedora / RHEL"
    ```bash
    sudo dnf install libreoffice
    ```

=== "Windows"
    Die Desktop-App auf Windows verwendet normalerweise **win32com**
    mit installiertem MS Office — LibreOffice ist der *Fallback*,
    wenn MS Office fehlt. Installiere von
    <https://www.libreoffice.org/download/download/>.

## Überprüfen

```bash
soffice --version
```

Wenn du "command not found" auf macOS erhältst, befindet sich die
Binärdatei unter
`/Applications/LibreOffice.app/Contents/MacOS/soffice`. Die App
entdeckt sie automatisch über gängige Installationspfade, aber du
kannst in **Einstellungen → Allgemein → LibreOffice-Pfad** überschreiben,
wenn nötig.

## Was es antreibt

Wenn LibreOffice das aktive Backend ist:

| Funktion | Hinweis |
|---|---|
| **Modernes Office** (`.docx`, `.xlsx`, `.pptx`) | Als Fallback verwendet, wenn win32com nicht verfügbar ist |
| **Legacy-Office** (`.doc`, `.xls`, `.ppt`) | Erforderlich — Pure Python kann sie nicht lesen |
| **ODF** (`.odt`, `.ods`, `.odp`) | Wird für Roundtrip-Konvertierung verwendet, wenn **ODF auto-konvertieren** aktiviert ist |
| **Auto-Konvertierung Legacy / ODF → OOXML** | Erforderlich |

## Hintergrundprozess

Beim ersten Mal, wenn LibreOffice benötigt wird, startet die App einen
`soffice`-Prozess im Headless-Modus und hält ihn über Übersetzungen
hinweg am Leben (`office_lifecycle.py`). Er beendet sich automatisch
beim App-Beenden.

## Hinweise

!!! warning "Startzeit beim ersten Lauf"
    Die erste Übersetzung, die LibreOffice trifft, wartet ~5-10
    Sekunden, bis `soffice` hochfährt. Nachfolgende Übersetzungen
    verwenden denselben Prozess und sind schnell.

!!! info "JVM-Crash-Logs"
    Die Java-Komponente von LibreOffice produziert gelegentlich
    `hs_err_pid*.log`-Dateien, wenn sie segfaulted. Die App leitet
    diese in ein temporäres Verzeichnis, damit sie deinen
    Projektordner nicht verschmutzen.

!!! tip "Auto-Konvertierung Legacy / ODF"
    Aktiviere **Einstellungen → Übersetzung → Auto-Konvertierung
    Legacy**, wenn du regelmäßig `.doc` / `.xls` / `.ppt` übersetzt.
    Die Pipeline konvertiert sie zuerst in `.docx` / `.xlsx` / `.pptx`
    (über `convert_to_modern_format`), übersetzt die moderne Kopie
    und konvertiert dann zurück. Die Treue ist viel höher als beim
    direkten Übersetzen des Legacy-Formats.
