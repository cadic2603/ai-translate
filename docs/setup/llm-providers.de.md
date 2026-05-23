---
description: "Konfiguriere LLM-Anbieter für die Übersetzung: Google Gemini (empfohlen), OpenAI-kompatible Endpoints oder beliebigen benutzerdefinierten Anbieter mit API-Schlüssel."
---

# LLM-Anbieter

Die Übersetzungspipeline ruft ein Large Language Model für die
tatsächliche Übersetzung auf. Du kannst einen oder mehrere
konfigurieren; der Modellauswähler pro Feature lässt jede Seite einen
anderen verwenden.

## Google Gemini (empfohlen für die Erstkonfiguration) {: #google-gemini-recommended-for-first-time-setup }

Die kostenlose Stufe ist großzügig und gut genug für die meisten
persönlichen Nutzungen.

1. Gehe zu <https://aistudio.google.com/apikey>
2. Klicke auf **Create API key** (melde dich mit deinem Google-Konto
   an)
3. Kopiere den Schlüssel (sieht aus wie `AIza...`)
4. In der Desktop-App: **Einstellungen → LLM → Gemini-API-Schlüssel**
   → einfügen → **Speichern**
5. Wähle ein Standardmodell im Dropdown **Standard-Gemini-Modell**.
   Googles Reihe sieht tendenziell aus wie:

    - **Flash**-Varianten (z. B. `gemini-2.5-flash`) — schnell,
      großzügige kostenlose Stufe, gute Qualität. Empfohlener
      Ausgangspunkt.
    - **Pro**-Varianten — langsamer, höhere Qualität, teurer.
    - **Flash-lite** — am schnellsten, am billigsten, niedrigere
      Qualität.

    Die genauen verfügbaren Modellnamen hängen davon ab, was Google
    auf deinem Konto bereitgestellt hat; wähle eines, dessen Name
    `flash` enthält, für einen ausgewogenen Standard.

Fertig. Der Schlüssel wird im OS-Schlüsselbund gespeichert, nicht im
Klartext.

### Vertex-AI-Modus (Enterprise)

Innerhalb des Gemini-Konfigurationsblocks lässt dich ein Radio-Paar
zwischen **Developer API** und **Vertex AI** wechseln — dieselben
Gemini-Modelle, abgerechnet über dein GCP-Konto, mit Steuerelementen
auf Org-Ebene (VPC-SC, Audit-Logs, regionale Datenresidenz).

1. In **Einstellungen → LLM** wechsle den Gemini-Radio von
   **Developer API** auf **Vertex AI**
2. Fülle aus:
    - **Project** — deine GCP-Projekt-ID
    - **Location** — eine Vertex-Region (Standard `us-central1`)
    - **Credentials path** *(optional)* — Pfad zu einer Service-
      Account-JSON-Schlüsseldatei. Lasse leer, um Application Default
      Credentials zu verwenden
      (`gcloud auth application-default login`)
3. **Speichern**. Das Modell-Dropdown füllt sich aus Vertex neu, sobald
   das Projekt gesetzt ist.

OAuth-Aktualisierung wird von `google-genai` automatisch behandelt.
Der Service-Account-JSON-Pfad wird absichtlich im Klartext
gespeichert (der *Pfad* ist kein Geheimnis — der Inhalt der Datei ist
es, und er bleibt auf der Festplatte, wo Googles dokumentierte beste
Praxis ihn aufbewahrt).

## OpenAI / OpenAI-kompatibel

Alles, was eine OpenAI-kompatible REST-API freigibt, funktioniert —
OpenAI selbst, Anthropic via [LiteLLM-Proxy](https://docs.litellm.ai),
lokales Ollama, LM Studio, vLLM, Together.ai, Groq usw.

In **Einstellungen → LLM**:

1. Klicke auf **Add Custom Provider**
2. Fülle aus:
    - **Name** — ein Label wie „OpenAI" / „Local Ollama" /
      „Anthropic"
    - **API endpoint** — die Basis-URL (z. B.
      `https://api.openai.com/v1` oder `http://localhost:11434/v1`
      für Ollama)
    - **API key** — leer lassen für nicht-authentifizierte lokale
      Endpoints
    - **Models** — kommagetrennte Liste (z. B. `gpt-4o-mini,
      gpt-4o, gpt-3.5-turbo`)
3. Klicke auf **Save**.

Die benutzerdefinierten Anbieter werden als JSON-Blob im OS-
Schlüsselbund gespeichert (API-Schlüssel inklusive).

## Standardmodell wechseln

Das Dropdown **Standard-Gemini-Modell** in **Einstellungen → LLM**
legt einen Fallback fest, der von jeder Feature-Seite verwendet wird,
die keinen eigenen Auswähler hat.

Seiten mit eigenem Modellauswähler:

- **Text übersetzen** — `Tab Texteinstellungen → Standardmodell`
- **Dokument übersetzen** — wählt pro Aufgabe; fällt auf den
  Standard zurück
- **Untertitel / Stimme / Synchronisation / Live / Text extrahieren**
  — jeder hat seinen eigenen Pro-Feature-Standard in seinem
  Einstellungs-Tab

Das lässt dich mischen und kombinieren: kostenloses Flash für Live,
Pro für große Dokumente, lokales Ollama für sensible Daten.

## Wo die Schlüssel gespeichert werden

| OS | Speicher |
|---|---|
| **macOS** | Schlüsselbund (Login-Schlüsselbund) |
| **Windows** | Anmeldeinformationsverwaltung |
| **Linux (GNOME)** | Secret Service (gnome-keyring / KWallet) |
| **Linux (kein Daemon)** | Fällt auf Klartext-INI in `~/.config/ai-translate/settings.ini` zurück |

Der Fallback-INI-Wert wird beim ersten Lesen in den Schlüsselbund
migriert, sobald ein Schlüsselbund verfügbar wird — kein manueller
Schritt.

## Headless- / Serverinstallation

Ohne Desktop-Sitzung kannst du Schlüssel immer noch über Pythons
`keyring`-CLI setzen (nach `uv sync`):

```bash
# Gemini
uv run keyring set ai-translate llm/gemini_api_key

# Benutzerdefinierte Anbieter (füge das JSON-Blob ein — siehe Einstellungs-UI für das Schema)
uv run keyring set ai-translate llm/custom_providers
```

Oder setze die gleichen INI-Schlüssel direkt in `settings.ini` — die
App migriert sie beim ersten Lesen in den Schlüsselbund. Die Datei
befindet sich unter:

- **Linux** — `~/.config/ai-translate/settings.ini`
- **macOS** — `~/Library/Preferences/ai-translate/settings.ini`
- **Windows** — `%APPDATA%\ai-translate\settings.ini`

## Setup testen

Schnellstmöglicher Sanity-Check:

```bash
uv run ait --version
echo "Hello world." > /tmp/x.txt
uv run ait /tmp/x.txt --target German --quiet
cat /tmp/x_translated__de.txt
```

Wenn du „Hallo Welt." siehst — bist du fertig.

## Häufige Fehler

| Fehler | Wahrscheinliche Ursache |
|---|---|
| `AUTH_ERROR` | Falscher / abgelaufener API-Schlüssel. Erneut in Einstellungen einfügen. |
| `QUOTA_ERROR` | Anfragen-pro-Tag der kostenlosen Stufe überschritten. Warte oder zahle. |
| `MODEL_NOT_FOUND` | Die `models`-Liste des benutzerdefinierten Anbieters enthält das angeforderte Modell nicht. |
| `VISION_NOT_SUPPORTED` | Das ausgewählte Modell kann keine Bild-Eingabe. Verwende eine `flash`- / `pro`- / `vision`-Variante. |

Siehe [Troubleshooting](../troubleshooting.md) für mehr.
