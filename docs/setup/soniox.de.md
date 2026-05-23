---
description: Konfiguriere Soniox für Echtzeit-Sprache-zu-Text auf der Live-Seite von AI Translate — unterstützt Sprecher-Diarisierung, Glossarbegriffe und Live-Übersetzung.
---

# Soniox (STT)

Echtzeit-Sprache-zu-Text über die Soniox-WebSocket-API. Verwendet von
den Seiten **[Untertitel](../features/generate-subtitle.md)** und
**[Live-Übersetzung](../features/live-translation.md)**, wenn du
Soniox als STT-Methode wählst.

## Warum Soniox

- **Echtzeit** — Tokens kommen an, während der Sprecher noch spricht.
- **Sprecher-Diarisierung** — Sprecherlabels pro Token (z. B.
  _Sprecher 1: Hallo…_).
- **In-Stream-Übersetzung** — Soniox kann während der Transkription
  übersetzen und spart so einen zusätzlichen LLM-Roundtrip.
- **Mehrsprachig** — erkennt die Quellsprache automatisch, auch
  mitten im Stream.

## API-Schlüssel besorgen

1. Registriere dich auf <https://console.soniox.com>
2. Öffne **API keys** → **Create new API key**
3. Kopiere ihn (sieht aus wie `Bearer ...`; kopiere nur das Token
   ohne das `Bearer `-Präfix).

Die Preisgestaltung ist pro Minute Audio gemessen (~0,005 $ / Minute
zum Zeitpunkt des Schreibens) — siehe <https://soniox.com/pricing>.

## In der App konfigurieren

In **Einstellungen → Service**:

1. Füge den Schlüssel in **Soniox-API-Schlüssel** → **Speichern**

In **Einstellungen → Live** *(für Live-Übersetzung)* oder
**Einstellungen → Untertitel** *(für Untertitel-Generierung)*:

1. Setze **STT-Methode** auf **Soniox**

## Was es antreibt

| Seite | Verwende Soniox, wenn |
|---|---|
| **Untertitel** | Aufnahmen mit mehreren Sprechern (Interviews, Panels, Meetings), wo du Sprecherlabels im SRT willst |
| **Live-Übersetzung** | Echtzeit-Meeting-Untertitelung, besonders mit mehreren Sprechern |

## Glossarbegriffe

Der Soniox-WebSocket akzeptiert ein Glossar von Begriffen, um die
Erkennung zu beeinflussen. Die App leitet deine aktiven Glossareinträge
automatisch weiter — Markennamen / Eigennamen / Fachjargon werden
zuverlässiger erkannt.

## Hinweise

!!! warning "Nur online"
    Soniox ist nur Cloud; wenn dein Audio sensibel ist (medizinisch,
    juristisch), verwende stattdessen Whisper (lokal).

!!! info "Wiederverbindung"
    Der WebSocket verbindet sich bei vorübergehenden Fehlern
    automatisch mit exponentiellem Backoff wieder. Lange Sitzungen
    bleiben durch kurze Netzwerkausfälle verbunden.

## Häufige Fehler

| Fehler | Wahrscheinliche Ursache |
|---|---|
| `AUTH_ERROR` | Falscher / abgelaufener API-Schlüssel. Erneut in Einstellungen → Service einfügen. |
| `QUOTA_ERROR` | Plan-Limit überschritten. |
| `CONNECTION_ERROR` | Netzwerk blockiert / Firewall. Versuche es von einem anderen Netzwerk. |
