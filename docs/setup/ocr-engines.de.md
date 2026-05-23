---
description: Richte OCR-Engines für Bild- und PDF-Textextraktion ein — wähle zwischen offline Tesseract oder EasyOCR oder cloudbasiertem Google Vision OCR.
---

# OCR-Engines

OCR wird verwendet, um Text aus Bildern zu lesen — sowohl auf der
Seite [Text extrahieren](../features/extract-text.md) als auch als
Fallback innerhalb der Dokument-Übersetzung, wenn eine Seite gescannt
ist (keine Textebene) oder wenn du **Eingebettete Bilder übersetzen**
einschaltest.

Du kannst aus drei OCR-Engines wählen.

## Tesseract (empfohlener Standard)

Kostenlos, schnell, offline. Benötigt eine Systeminstallation.

=== "macOS"
    ```bash
    brew install tesseract tesseract-lang
    ```

=== "Ubuntu / Debian"
    ```bash
    sudo apt install tesseract-ocr tesseract-ocr-all
    ```

    `tesseract-ocr-all` bringt jede unterstützte Sprache. Um Platz
    zu sparen, installiere nur, was du brauchst (z. B.
    `tesseract-ocr-fra` für Französisch).

=== "Fedora / RHEL"
    ```bash
    sudo dnf install tesseract tesseract-langpack-eng tesseract-langpack-fra
    ```

=== "Windows"
    Lade den Installer von [UB Mannheims Tesseract-Releases](https://github.com/UB-Mannheim/tesseract/wiki)
    herunter. Führe ihn aus, akzeptiere die Standardwerte —
    Sprachpakete sind gebündelt.

Überprüfen:

```bash
tesseract --version
tesseract --list-langs
```

In der Desktop-App: **Einstellungen → OCR → OCR-Methode = Tesseract**.
Fertig.

## EasyOCR

Kostenlos, offline. Großartig für nicht-lateinische Schriften
(Chinesisch, Koreanisch, Japanisch, Thailändisch). Modelle laden
beim ersten Gebrauch herunter (~1 GB insgesamt).

```bash
uv sync --extra easyocr
```

In der Desktop-App: **Einstellungen → OCR → OCR-Methode = EasyOCR**.

Beim ersten Mal, wenn du es für eine Sprache verwendest, lädt das
relevante Modell nach `~/.EasyOCR/`. Nachfolgende Läufe sind sofort.

## Google Cloud Vision

Cloud, kostenpflichtig (1.000 kostenlose Anfragen / Monat). Höchste
Genauigkeit, besonders bei verrauschtem / handschriftlichem /
multi-skriptem Inhalt.

1. [Erstelle ein Google-Cloud-Projekt](https://console.cloud.google.com/projectcreate)
2. Aktiviere die [Vision API](https://console.cloud.google.com/apis/library/vision.googleapis.com)
3. [Erstelle einen API-Schlüssel](https://console.cloud.google.com/apis/credentials)
4. In der Desktop-App: **Einstellungen → Service → Google-Cloud-API-Schlüssel** → einfügen
5. **Einstellungen → OCR → OCR-Methode = Google Cloud OCR**

Derselbe Google-Cloud-API-Schlüssel treibt Vision OCR, Speech-to-Text
und Text-to-Speech, wenn du auch diese APIs aktivierst.

## Genauigkeit vergleichen

Der Tab **Einstellungen → OCR** hat eine kleine Vergleichstabelle
eingebaut — Sprachabdeckung, online/offline, Kosten, Genauigkeit.
Lies sie erneut, wann immer du versucht bist, zu wechseln.

## Wann OCR verwendet wird

| Ort | Verhalten |
|---|---|
| **Text-extrahieren-Seite** (wenn Methode = OCR) | Direktes OCR auf den abgelegten Bildern |
| **Dokument übersetzen → PDF** | OCR-Fallback nur auf Scan-Seiten (keine Textebene) |
| **Dokument übersetzen → Office** mit **Eingebettete Bilder übersetzen** an | OCR + LLM-Vision auf jedem eingebetteten Bild |

## Tipps

!!! tip "Wähle die Quellsprache"
    Die meisten OCR-Engines sind viel genauer, wenn du ihnen sagst,
    welche Sprache zu erwarten ist. Die Untertitel- / Dokument- /
    Text-extrahieren-Seiten leiten alle deinen **Quellsprache**-Picker
    an die OCR-Engine weiter.

!!! tip "Tesseract reicht für sauberen gedruckten Text"
    Greife nicht nach Cloud-OCR, bevor Tesseract / EasyOCR tatsächlich
    an deinem Inhalt gescheitert ist. Sie sind kostenlos, schnell und
    überraschend gut.
