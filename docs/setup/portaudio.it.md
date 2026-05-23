---
description: Acquisizione audio dal microfono multipiattaforma per la traduzione dal vivo.
---

# Configurazione PortAudio (Microfono)

La funzione [Traduzione dal vivo](../features/live-translation.md) utilizza il pacchetto Python `sounddevice`, che si basa sulla libreria C PortAudio per accedere ai dispositivi microfonici su tutti i sistemi operativi. La maggior parte degli utenti deve installare questa dipendenza a livello di sistema.

## Windows
I wheel precompilati per `sounddevice` e `PyAudio` in genere raggruppano il binario PortAudio su Windows. L'installazione manuale a livello di sistema normalmente non è necessaria. In caso di errori, assicurarsi che i driver audio siano aggiornati.

## macOS
Usa Homebrew per installare PortAudio:

```bash
brew install portaudio
```

## Linux
Il nome del pacchetto dipende dalla distribuzione. Il pacchetto di sviluppo (che in genere termina con `-dev` o `-devel`) deve essere installato in modo che Python possa creare i binding C se non è disponibile un wheel precompilato.

=== "Ubuntu / Debian / Mint"

    ```bash
    sudo apt-get install portaudio19-dev
    ```

=== "Fedora / RHEL"

    ```bash
    sudo dnf install portaudio-devel
    ```

=== "Arch Linux"

    ```bash
    sudo pacman -S portaudio
    ```

## Risoluzione dei problemi

Se l'applicazione continua a segnalare di non poter accedere al microfono dopo l'installazione:

1. Assicurati che l'applicazione terminale (o l'ambiente desktop) sia autorizzata ad accedere al microfono (in particolare su macOS).
2. Riavvia l'applicazione (o il terminale/server MCP) in modo che acquisisca il nuovo percorso della libreria.
