---
description: Installa FFmpeg in modo che AI Translate possa decodificare audio e video per la generazione di sottotitoli, la sintesi vocale e il doppiaggio video — richiesto per le funzionalità multimediali.
---

# FFmpeg

FFmpeg è richiesto per qualsiasi flusso audio / video:

- **Genera sottotitolo** — decodifica audio sorgente per STT
- **Genera voce** — combinazione di clip TTS temporizzati in un file
- **Doppiaggio** — STT → TTS → mux di nuovo nel video
- **Traduzione live** — quando la cattura audio di sistema passa
  attraverso `parec`

Non è incluso — installalo una volta sul tuo sistema.

## Installare

=== "macOS"
    ```bash
    brew install ffmpeg
    ```

=== "Ubuntu / Debian"
    ```bash
    sudo apt update && sudo apt install ffmpeg
    ```

=== "Fedora / RHEL"
    ```bash
    sudo dnf install ffmpeg
    ```

    O, per una build più completa, abilita prima
    [RPM Fusion](https://rpmfusion.org/Configuration).

=== "Arch / Manjaro"
    ```bash
    sudo pacman -S ffmpeg
    ```

=== "Windows"
    Scarica una build statica da <https://www.gyan.dev/ffmpeg/builds/>
    (la build "release essentials" va bene), decomprimi, poi aggiungi
    la cartella `bin/` al tuo PATH:

    1. Premi **Win + R**, digita `sysdm.cpl`, premi **Invio**
    2. **Avanzate → Variabili d'ambiente → Variabili di sistema → Path → Modifica**
    3. **Nuovo** → incolla il percorso assoluto della cartella `bin` di FFmpeg
    4. **OK** dappertutto, riavvia eventuali terminali aperti

## Verificare

```bash
ffmpeg -version
```

Dovresti vedere un banner di versione con `--enable-libx264 --enable-libvpx`
nella riga di configurazione. Se vedi "command not found",
l'installazione non è finita su PATH.

## Verifica pre-flight in-app

Le pagine Voce / Doppiaggio chiamano `shutil.which("ffmpeg")` prima di
iniziare il lavoro. Se FFmpeg non viene trovato, vedrai un finestra
di errore amichevole con un link di ritorno qui, non un'attività
mezza eseguita.

## Errore comune

| Errore | Significato |
|---|---|
| `FFMPEG_NOT_FOUND` | `ffmpeg` non è su PATH al momento in cui la pagina ha provato a eseguirlo. Installalo (sopra) e riavvia l'app. |

Nel server MCP (`ait-mcp`), lo stesso errore viene reincartato in un
messaggio leggibile:

> *"FFmpeg è richiesto per decodificare questo file audio/video ma
> non è installato o non è su PATH. Installa FFmpeg e riprova."*
