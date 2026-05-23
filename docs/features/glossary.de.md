---
description: Verwalten Sie benutzerdefinierte Glossarsätze, um konsistente Terminologie über Übersetzungen hinweg durchzusetzen — CSV-Import/Export, Bereich pro Sprachpaar, Priorisierung pro Projekt.
---

# Glossar

Sperren Sie bestimmte Begriffe an bestimmte Übersetzungen für jeden
Übersetzungs-Job. Nützlich für Markennamen, Produktterminologie,
technischen Jargon oder Charakternamen, die Sie konsistent halten möchten.

## Funktionsweise

Ein Glossar ist eine Liste von (Quellbegriff, Zielbegriff)-Paaren,
gruppiert in einem **Set**. Wenn Sie ein Set aktivieren, erhält jeder
LLM-Aufruf in der App die relevanten Einträge in den Prompt injiziert —
der LLM sieht also „verwende 'OpenAI' für 'OpenAI', nicht '开放AI'",
bevor er übersetzt.

Mehrere Sets können gleichzeitig aktiv sein. Nur Einträge, deren
Quelle oder Ziel im Batch-Text vorkommt, werden dem Prompt hinzugefügt
(Pro-Aufruf-Kompression), sodass ein 5.000-Einträge-Glossar bei den
Tokens günstig bleibt.

## Schritt-für-Schritt

1. Klicken Sie in der Seitenleiste auf **Glossar**.
2. Klicken Sie auf **Neues Set** (`Strg+N`) und geben Sie ihm einen
   Namen (z. B. „Projekt Acme").
3. Mit dem Set links ausgewählt zeigt das rechte Panel seine Einträge.
4. Klicken Sie auf **Hinzufügen**, um einen neuen Eintrag zu erstellen.
   Füllen Sie aus:
    - **Quelle** — der Originalbegriff
    - **Ziel** — die durchzusetzende Übersetzung
    - Optional einen Kommentar / Notiz
5. Wiederholen Sie für jeden Begriff.
6. Aktivieren Sie das **Aktiv**-Kontrollkästchen am Set-Namen, um es zu aktivieren.

## Sets aktivieren / deaktivieren

Das **Aktiv**-Kontrollkästchen neben jedem Set-Namen steuert, ob
seine Einträge in LLM-Prompts injiziert werden. Sie können 50
inaktive Sets im Speicher lassen und nur die 2 aktivieren, die Sie
für das aktuelle Projekt brauchen.

## Import / Export (CSV)

- **Export** — wählen Sie ein Set, klicken Sie auf **Exportieren** →
  speichern Sie als `.csv`. Zwei Spalten: `source`, `target` (UTF-8,
  kommagetrennt, RFC-4180-Quoting).
- **Import** — klicken Sie auf **Importieren** → wählen Sie eine
  `.csv` → wählen Sie ein Ziel-Set (existierend oder neu). Bei
  doppelter Quelle erhalten Sie einen Ersetzen-oder-Überspringen-Prompt.

Das CSV-Format ist Round-Trip-fähig, also ist ein Export →
in Excel bearbeiten → Import sicher.

## Suche und Filterung

`Strg+F` fokussiert das Suchfeld. Geben Sie einen beliebigen
Teilstring ein und die Einträge (und die Set-Liste) filtern auf
Treffer; der passende Teilstring wird hervorgehoben. Suche löschen
stellt die volle Liste wieder her.

Die Suche ist **akzent-unempfindlich und groß-/kleinschreibungs-unempfindlich** —
`cafe` findet `café` und umgekehrt.

## In-Place-Bearbeitung

Klicken Sie auf eine beliebige Zelle zum Bearbeiten. Drücken Sie
`Tab`, um zur nächsten Zelle zu wechseln. Drücken Sie `Esc` zum
Zurücksetzen. Auto-Speichern löst aus, wenn Sie aus der Zeile klicken.
Leere Quelle oder Ziel setzt die Zeile zurück, statt einen
ungültigen Eintrag zu speichern.

## Löschen

- **Einen einzelnen Eintrag löschen** — wählen, `Entf` drücken.
  Sie sehen einen Bestätigungsdialog.
- **Ein ganzes Set löschen** — wählen Sie das Set, drücken Sie `Entf`.
  Der Dialog zeigt den Cascade-Eintrag-Zähler, damit Sie wissen,
  was Sie zerstören.

## Tastenkürzel

| Kürzel | Aktion |
|---|---|
| `Strg+N` | Neues Set |
| `Strg+F` | Fokus auf Suche |
| `Entf` | Ausgewählten Eintrag / Set löschen |

## Tipps

!!! tip "Bereich pro Set"
    Ein Set ist eine *logische* Gruppierung. Gruppieren Sie nach
    Projekt, nach Kunde, nach Domäne (medizinisch / juristisch /
    Gaming) — was auch immer Sinn ergibt. Aktivieren Sie nur die
    Sets, die für die aktuelle Aufgabe relevant sind.

!!! tip "Glossar überschreibt nicht die Übersetzung"
    Der LLM wird angewiesen, die Glossareinträge zu verwenden, aber
    es bleibt ein Hinweis — extrem unbeholfene erzwungene
    Übersetzungen können trotzdem auftauchen. Verwenden Sie einfache
    `Begriff → Übersetzung`-Paare statt ganzer Sätze.
