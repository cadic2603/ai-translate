---
description: Extrahieren Sie Text aus Bildern und Screenshots mit OCR-Engines (Tesseract, EasyOCR, Google Vision) oder LLM-Vision — Ausgabe als TXT oder DOCX.
---

# Text extrahieren

Holen Sie den Text aus Bildern — Quittungen, Screenshots, fotografierte
Dokumente, gescannte Seiten, alles. Ausgabe als `.txt` (einfacher
Text) oder `.docx` (formatierte Absätze).

Diese Seite **übersetzt nicht** — sie extrahiert nur. Leiten Sie die
Ausgabe in „Dokument übersetzen", wenn Sie auch übersetzen möchten.

## Zwei Extraktionsmethoden

| Methode | Geeignet für |
|---|---|
| **OCR** | Hohes Volumen / Batch / kostensensibel (kostenlos oder fast kostenlos pro Bild) |
| **LLM-Vision** | Layout-Erhaltung, gemischte Skripte, Bilder schlechter Qualität, Handschrift |

Wählen Sie den Standard in **Einstellungen → Text extrahieren → Extraktionsmethode**.

## OCR-Engines (OCR-Methode)

| Engine | Kosten | Offline | Sprachen | Hinweise |
|---|---|---|---|---|
| **Tesseract** | Kostenlos | Ja | 100+ | Standard. Benötigt Systeminstallation. |
| **EasyOCR** | Kostenlos | Ja (nach Modell-Download) | 80+ | Am besten für nicht-lateinische Skripte. ~1 GB Modelle. |
| **Google Cloud Vision** | Kostenpflichtig (1.000 kostenlos / Monat) | Nein | 60+ | Höchste Genauigkeit. |

Konfigurieren Sie in **Einstellungen → OCR**.

## Schritt-für-Schritt

1. Klicken Sie in der Seitenleiste auf **Text extrahieren**.
2. Lassen Sie eine oder mehrere Bilddateien fallen (`.png`, `.jpg`,
   `.jpeg`, `.bmp`, `.webp`, `.tiff`, `.tif`).
3. Wählen Sie die **Quellsprache** (hilft OCR, das richtige Modell zu wählen).
4. Wählen Sie das **Ausgabeformat** — `.txt` oder `.docx`.
5. Klicken Sie auf **Extrahieren** (oder `Strg+Eingabe`).
6. **Öffnen** Sie die Zeile, wenn fertig.

## Wann was verwenden

- **Textreiche Quittung / Rechnung** → Tesseract ist schnell und genau.
- **Fotografierte handschriftliche Notizen** → LLM-Vision gewinnt deutlich.
- **Manga / Comic-Panels** → EasyOCR (handhabt vertikalen CJK-Text gut).
- **Formular mit vielen kleinen Feldern** → Google Cloud Vision
  bewahrt Feldgrenzen tendenziell besser als die anderen.

## Tipps

!!! tip "OCR oder LLM, nicht beides"
    Die Seite wählt eine Methode und führt sie aus. Zum Vergleichen
    der Ausgaben starten Sie dasselbe Bild zweimal mit unterschiedlichen
    Methoden.

!!! tip "Setup-erforderlich-Dialog"
    Wenn Sie OCR wählen, aber keine OCR-Engine konfiguriert ist (oder
    LLM, aber kein LLM-Schlüssel konfiguriert ist), zeigt die Seite
    einen einzigen „Setup erforderlich"-Dialog, der direkt zum
    relevanten Einstellungs-Tab führt.

## Tastenkürzel

| Kürzel | Aktion |
|---|---|
| `Strg+Eingabe` | Extrahieren |
| `Strg+O` | Durchsuchen |
| `Strg+F` | Fokus auf Verlaufssuche |
