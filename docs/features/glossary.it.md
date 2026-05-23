---
description: Gestisci set di glossari personalizzati per imporre terminologia coerente nelle traduzioni — import/export CSV, ambito per coppia di lingue, priorità per progetto.
---

# Glossario

Blocca termini specifici a traduzioni specifiche in ogni job di
traduzione. Utile per nomi di marca, terminologia di prodotto, gergo
tecnico o nomi di personaggi che vuoi mantenere coerenti.

## Come funziona

Un glossario è una lista di coppie (termine sorgente, termine destinazione)
raggruppate in un **set**. Quando attivi un set, ogni chiamata LLM
nell'app riceve le voci pertinenti iniettate nel prompt — quindi il
LLM vede "usa 'OpenAI' per 'OpenAI', non '开放AI'" prima di tradurre.

Più set possono essere attivi contemporaneamente. Solo le voci la cui
sorgente o destinazione appare nel testo del batch vengono aggiunte
al prompt (compressione per chiamata), quindi un glossario di 5.000
voci rimane economico in termini di token.

## Procedura

1. Clicca **Glossario** nella barra laterale.
2. Clicca **Nuovo set** (`Ctrl+N`) e dagli un nome (es. "Progetto Acme").
3. Con il set selezionato a sinistra, il pannello destro mostra le sue voci.
4. Clicca **Aggiungi** per creare una nuova voce. Compila:
    - **Sorgente** — il termine originale
    - **Destinazione** — la traduzione da imporre
    - Opzionalmente un commento / nota
5. Ripeti per ogni termine.
6. Spunta la casella **Attivo** sul nome del set per abilitarlo.

## Attivare / disattivare set

La casella **Attivo** accanto a ogni nome di set controlla se le sue
voci vengono iniettate nei prompt LLM. Puoi lasciare 50 set inattivi
in archiviazione e attivare solo i 2 di cui hai bisogno per il
progetto corrente.

## Import / Export (CSV)

- **Esporta** — seleziona un set, clicca **Esporta** → salva come
  `.csv`. Due colonne: `source`, `target` (UTF-8, separato da virgole,
  quoting RFC 4180).
- **Importa** — clicca **Importa** → scegli un `.csv` → scegli un set
  destinazione (esistente o nuovo). Su sorgente duplicata otterrai
  un prompt sostituisci-o-salta.

Il formato CSV fa round-trip, quindi un Esporta → modifica in
Excel → Importa è sicuro.

## Ricerca e filtro

`Ctrl+F` mette il focus sulla barra di ricerca. Digita qualsiasi
sottostringa e le voci (e l'elenco dei set) si filtrano sui match;
la sottostringa corrispondente è evidenziata. Cancellare la ricerca
ripristina l'elenco completo.

La ricerca è **insensibile agli accenti e insensibile al case** —
`cafe` trova `café` e viceversa.

## Modifica in loco

Clicca su qualsiasi cella per modificare. Premi `Tab` per spostarti
alla cella successiva. Premi `Esc` per ripristinare. Auto-salvataggio
si attiva quando clicchi fuori dalla riga. Sorgente o destinazione
vuote ripristinano la riga invece di salvare una voce non valida.

## Eliminazione

- **Eliminare una voce** — selezionala, premi `Canc`. Vedrai un
  dialog di conferma.
- **Eliminare un intero set** — seleziona il set, premi `Canc`. Il
  dialog mostra il conteggio voci a cascata così sai cosa stai eliminando.

## Scorciatoie

| Scorciatoia | Azione |
|---|---|
| `Ctrl+N` | Nuovo set |
| `Ctrl+F` | Focus ricerca |
| `Canc` | Elimina voce / set selezionato |

## Suggerimenti

!!! tip "Ambito per set"
    Un set è un raggruppamento *logico*. Raggruppa per progetto, per
    cliente, per dominio (medico / legale / gaming) — qualsiasi cosa
    abbia senso. Attiva solo i set rilevanti al lavoro corrente.

!!! tip "Il glossario non sovrascrive la traduzione"
    Al LLM viene istruito di usare le voci del glossario, ma rimane
    un suggerimento — traduzioni forzate estremamente goffe possono
    ancora apparire. Usa coppie semplici `termine → traduzione`
    invece di intere frasi.
