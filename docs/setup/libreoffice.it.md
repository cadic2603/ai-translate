---
description: Installa LibreOffice in modo che AI Translate possa tradurre formati Office legacy (.doc, .xls, .ppt) e file ODF (.odt, .ods, .odp) su macOS e Linux.
---

# LibreOffice (formati Office)

Il pipeline di traduzione Office sceglie il miglior backend
disponibile in questo ordine:

1. **win32com** (Windows + MS Office installato) — fedeltà massima
2. **LibreOffice UNO** (multipiattaforma) — ripiego quando win32com
   non c'è
3. **python-docx / openpyxl / python-pptx** (solo formati moderni)
   — ripiego pure-Python quando nessuno dei precedenti è disponibile

LibreOffice è **l'unica via** per `.doc` / `.xls` / `.ppt` legacy
su Linux e macOS, e la via consigliata su quelle piattaforme anche
per i formati Office moderni (migliore fedeltà del backend
pure-Python, specialmente per tabelle e oggetti incorporati).

## Installare

=== "macOS"
    ```bash
    brew install --cask libreoffice
    ```

    O scarica da <https://www.libreoffice.org/download/download/>.

=== "Ubuntu / Debian"
    ```bash
    sudo apt install libreoffice
    ```

=== "Fedora / RHEL"
    ```bash
    sudo dnf install libreoffice
    ```

=== "Windows"
    L'app desktop su Windows usa di solito **win32com** con MS Office
    installato — LibreOffice è il *ripiego* se MS Office manca.
    Installa da <https://www.libreoffice.org/download/download/>.

## Verificare

```bash
soffice --version
```

Se ottieni "command not found" su macOS, il binario si trova in
`/Applications/LibreOffice.app/Contents/MacOS/soffice`. L'app lo
auto-rileva attraverso percorsi di installazione comuni, ma puoi
sovrascrivere in **Impostazioni → Generale → Percorso LibreOffice**
se necessario.

## Cosa alimenta

Quando LibreOffice è il backend attivo:

| Caratteristica | Nota |
|---|---|
| **Office moderno** (`.docx`, `.xlsx`, `.pptx`) | Usato come ripiego quando win32com non è disponibile |
| **Office legacy** (`.doc`, `.xls`, `.ppt`) | Richiesto — Python puro non può leggerli |
| **ODF** (`.odt`, `.ods`, `.odp`) | Usato per la conversione round-trip quando **Conversione automatica ODF** è attiva |
| **Conversione automatica legacy / ODF → OOXML** | Richiesto |

## Processo in background

La prima volta che è necessario LibreOffice, l'app lancia un processo
`soffice` in modalità headless e lo mantiene vivo attraverso le
traduzioni (`office_lifecycle.py`). Si spegne automaticamente
all'uscita dell'app.

## Avvertenze

!!! warning "Tempo di avvio al primo lancio"
    La prima traduzione che tocca LibreOffice attende ~5-10 secondi
    per l'avvio di `soffice`. Le traduzioni successive riusano lo
    stesso processo e sono veloci.

!!! info "Log di crash JVM"
    Il componente Java di LibreOffice produce occasionalmente file
    `hs_err_pid*.log` quando va in segfault. L'app li indirizza in
    una directory temporanea in modo che non inquinino la tua
    cartella di progetto.

!!! tip "Conversione automatica legacy / ODF"
    Abilita **Impostazioni → Traduzione → Conversione automatica
    legacy** se traduci regolarmente `.doc` / `.xls` / `.ppt`. Il
    pipeline li converte prima in `.docx` / `.xlsx` / `.pptx`
    (tramite `convert_to_modern_format`), traduce la copia moderna,
    poi riconverte. La fedeltà è molto più alta che tradurre il
    formato legacy direttamente.
