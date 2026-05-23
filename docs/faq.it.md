---
description: "Domande comuni su AI Translate: formati di file supportati, funzionalità gratuite vs a pagamento, uso offline, scelte di provider LLM e selezione del motore OCR."
---

# Domande frequenti

## Generale

### Funziona offline?

Per lo più sì. Specificamente:

- **La traduzione** richiede un LLM. L'API Gemini gratuita è online;
  **Ollama / LM Studio locale** tramite le impostazioni Custom Provider
  è completamente offline.
- **OCR** con **Tesseract** o **EasyOCR** è offline.
- **STT** con **Whisper** (default) è offline.
- **TTS** con **Edge TTS** (default) è online; **ElevenLabs** /
  **Google Cloud TTS** / **Gemini TTS** sono online (gratuiti o a
  pagamento); **Piper TTS** è TTS neurale completamente offline —
  nessuna chiave, nessuna chiamata di rete una volta scaricata la voce
  per lingua (file ONNX di ~25–60 MB) tramite **Impostazioni → Voce
  → Piper TTS → Scarica voci ora**.

Per un setup completamente air-gapped: Custom Provider → LLM locale,
Tesseract o EasyOCR per OCR, Whisper per STT, e Piper TTS per output vocale.

### Dove sono salvati i miei file tradotti?

Accanto all'originale per default, con suffisso `_translated_<src>_<tgt>`
(es. `report_translated_en_fr.docx`). Sovrascrivi per funzionalità in
**Impostazioni → Generale → Percorso archiviazione traduzioni**.

### Dove sono memorizzate le mie impostazioni?

File INI in:

| OS | Percorso |
|---|---|
| **Linux** | `~/.config/ai-translate/settings.ini` |
| **macOS** | `~/Library/Preferences/ai-translate/settings.ini` |
| **Windows** | `%APPDATA%\ai-translate\settings.ini` |

Le chiavi API vivono nel keychain dell'OS (non nell'INI). La cronologia
di traduzione vive in un DB SQLite nella directory dei dati.

### Come vengono gestiti i miei dati?

- **Local-first** — il testo non lascia mai la tua macchina a meno
  che tu non stia chiamando un servizio LLM / OCR / STT / TTS cloud.
- **Nessuna telemetria** — l'app non chiama casa. L'unica richiesta
  in uscita che l'app fa da sola è il controllo opzionale di
  aggiornamento GitHub Releases (toggle in
  **Impostazioni → Generale**); i backend cloud chiamano solo i
  rispettivi vendor.
- **Chiavi API** — memorizzate nel keychain dell'OS. Il fallback
  keychain dell'app desktop è un INI in chiaro quando non è disponibile
  alcun daemon keychain.

### Posso tradurre un Google Doc / pagina Notion?

Non direttamente. Esporta in `.docx` prima, traduci, poi importa il
file tradotto indietro. Stessa cosa per Notion (esporta come Markdown
/ HTML), Confluence (esporta come `.docx`), ecc.

## Scegliere modelli / motori

### Quale modello LLM dovrei usare?

Per la maggior parte degli utenti:

- **Qualsiasi variante Gemini Flash** — livello gratuito, veloce,
  sorprendentemente buono. Usa per traduzioni quotidiane. I nomi
  appaiono come `gemini-2.5-flash`, `gemini-3-flash-preview`, ecc.,
  a seconda di cosa è attualmente disponibile.
- **Qualsiasi variante Gemini Pro** — pagamento per token, qualità
  superiore. Usa per documenti importanti (legali, tecnici,
  customer-facing).
- **Ollama locale** con un modello 7B-13B — quando hai bisogno di
  offline / privacy.

Il selettore di modello per funzionalità significa che puoi usare un
modello veloce per traduzioni in stile chat e riservare quello costoso
per documenti.

### Quale motore OCR dovrei usare?

- **Tesseract** per testo stampato pulito nei principali script.
  Gratuito, offline, veloce.
- **EasyOCR** per script non latini (specialmente CJK) e immagini più
  rumorose.
- **Google Cloud Vision** per scrittura a mano, script misti, e la
  massima accuratezza quando puoi pagare.

### Quale metodo STT dovrei usare?

- **Whisper local** per offline / privacy.
- **Soniox** per registrazioni multi-speaker — le label degli speaker
  fanno il round-trip nel tuo SRT.
- **Google Cloud STT** per audio telefonico / medico (i loro modelli
  di dominio sono buoni).
- **Gemini Live** per traduzione speech-to-speech in tempo reale.

### Quale backend TTS?

- **Edge TTS** per voci gratuite di alta qualità.
- **ElevenLabs** per voci premium / brandizzate / clonate.
- **Google Cloud TTS** per voci WaveNet in lingue long-tail dove Edge
  ha copertura sottile.
- **Gemini TTS** per voci prebuilt naturali gratuite riutilizzando la
  tua chiave API Gemini esistente.
- **Piper TTS** quando hai bisogno di output vocale **offline /
  air-gapped**. Trade-off: ogni lingua richiede un download voce
  one-time di ~25–60 MB tramite **Impostazioni → Voce → Piper TTS
  → Scarica voci ora**, e 13 delle 45 lingue dell'app non hanno voce
  Piper (quelle ricadono silenziosamente su Edge TTS).

## Workflow

### Come traduco un'intera cartella?

Rilascia la cartella nella drop zone di **Traduci documento**. I file
supportati all'interno (ricorsivamente) vengono accodati; tutto il
resto viene saltato silenziosamente. C'è un cap di 100 file per drop;
batch più grandi → dividi in più drop.

### Posso mettere in pausa e riprendere traduzioni?

Sì. Esci dall'app in qualsiasi momento — i task Pending / Translating
riprendono al prossimo lancio. Il checkpointing per task significa che
la pagina 47 di 100 di un PDF non viene rifatta quando riprendi.

### Posso modificare una traduzione a mano?

Per **Traduci testo** — sì, clicca sul pannello destro e digita. La
modifica si salva automaticamente nel record cronologia della voce.

Per **Traduci documento** — apri il file tradotto nel tuo editor
abituale (Word, LibreOffice, ecc.) e modifica lì. L'app non fa il
round-trip delle modifiche indietro nella cronologia.

### Posso tradurre in massa una lista di stringhe?

Usa il CLI:

```bash
ait *.txt --target French
```

O per stringhe in-process (es. stringhe UI estratte dal codice),
chiama lo strumento MCP `translate_text` con una lista, o usa l'API
Python direttamente:

```python
from src.core.llm_engine import translate_text
out = translate_text(texts=["Hello", "World"], target_lang="French")
```

## Glossario

### Perché l'LLM non sta usando il mio glossario?

Tre cose da controllare:

1. Il set è **attivo** (checkbox spuntata).
2. Il termine sorgente nel tuo glossario appare effettivamente nel
   testo sorgente (la compressione per chiamata invia all'LLM solo le
   voci che corrispondono al testo del batch — risparmia token, ma
   significa che un termine sorgente con typo è invisibile).
3. Il modello è abbastanza forte — `flash-lite` a volte ignora
   suggerimenti che `flash` e `pro` onorano.

### I termini glossario vengono abbinati indipendentemente dagli accenti?

Sì. Sia la ricerca glossario sia la barra di ricerca nella pagina
Glossario usano una funzione di normalizzazione che rimuove accenti e
case. Quindi `cafe`, `Café` e `CAFE` corrispondono tutti a una voce la
cui sorgente è `Café`.

## Privacy

### Raccogliete dati di utilizzo?

No. L'app non ha SDK di analytics. Il controllo opzionale di
aggiornamento interroga un singolo endpoint GitHub Releases all'avvio;
è togglable in **Impostazioni → Generale**.

### Le mie chiavi API sono al sicuro?

Sono memorizzate nel keychain del tuo OS (Keychain su macOS, Credential
Manager su Windows, Secret Service su Linux). Altri processi non
possono leggerle senza il tuo permesso esplicito. Il fallback (quando
non è disponibile alcun daemon keychain — tipicamente server Linux
headless) è un INI in chiaro sotto la directory di configurazione del
tuo utente; in quella modalità le chiavi sono protette da permessi
file ma non crittografate.
