---
description: Configura Soniox per la trascrizione vocale in tempo reale nella pagina Live di AI Translate — supporta diarizzazione dei parlanti, termini di glossario e traduzione live.
---

# Soniox (STT)

Trascrizione vocale in tempo reale tramite l'API WebSocket di Soniox.
Usato dalle pagine **[Sottotitolo](../features/generate-subtitle.md)** e
**[Traduzione live](../features/live-translation.md)** quando scegli
Soniox come metodo STT.

## Perché Soniox

- **Tempo reale** — i token arrivano mentre il parlante sta ancora
  parlando.
- **Diarizzazione dei parlanti** — etichette di parlante per token
  (es. _Parlante 1: Ciao…_).
- **Traduzione in stream** — Soniox può tradurre durante la
  trascrizione, risparmiando un round trip LLM extra.
- **Multi-lingua** — rileva automaticamente la lingua di origine
  anche a metà stream.

## Ottenere una chiave API

1. Registrati su <https://console.soniox.com>
2. Apri **API keys** → **Create new API key**
3. Copiala (sembra `Bearer ...`; copia solo il token senza il
   prefisso `Bearer `).

Il prezzo è misurato per minuto di audio (~$0,005 / minuto al momento
della scrittura) — vedi <https://soniox.com/pricing>.

## Configurare nell'app

In **Impostazioni → Servizio**:

1. Incolla la chiave in **Chiave API Soniox** → **Salva**

In **Impostazioni → Live** *(per la traduzione live)* o
**Impostazioni → Sottotitolo** *(per la generazione di sottotitoli)*:

1. Imposta **Metodo STT** su **Soniox**

## Cosa alimenta

| Pagina | Usa Soniox quando |
|---|---|
| **Sottotitolo** | Registrazioni multi-parlante (interviste, panel, riunioni) dove vuoi etichette di parlante nell'SRT |
| **Traduzione live** | Sottotitolazione di riunioni in tempo reale, specialmente con più parlanti |

## Termini di glossario

Il WebSocket di Soniox accetta un glossario di termini per influenzare
il riconoscimento. L'app inoltra automaticamente le tue voci di
glossario attive — nomi di marchi / nomi propri / gergo vengono
riconosciuti più affidabilmente.

## Avvertenze

!!! warning "Solo online"
    Soniox è solo cloud; se il tuo audio è sensibile (medico, legale),
    usa Whisper (locale) invece.

!!! info "Riconnessione"
    Il WebSocket si riconnette automaticamente su errori transitori
    con backoff esponenziale. Le sessioni lunghe rimangono connesse
    attraverso brevi interruzioni di rete.

## Errori comuni

| Errore | Causa probabile |
|---|---|
| `AUTH_ERROR` | Chiave API errata / scaduta. Reincolla in Impostazioni → Servizio. |
| `QUOTA_ERROR` | Limite del piano superato. |
| `CONNECTION_ERROR` | Rete bloccata / firewall. Riprova da una rete diversa. |
