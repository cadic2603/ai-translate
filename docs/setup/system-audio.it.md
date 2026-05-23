---
description: Cattura l'audio di sistema su Linux, macOS e Windows per la pagina Live di AI Translate — traduci qualsiasi suono riprodotto sul tuo computer in tempo reale.
---

# Cattura audio di sistema (Live)

La pagina **[Traduzione live](../features/live-translation.md)** può
catturare l'**audio di sistema** (tutto ciò che viene riprodotto sui
tuoi altoparlanti) in modo che tu possa sottotitolare / tradurre
qualsiasi media — chiamate Zoom, YouTube, Netflix, giochi, suoni di
sistema.

In **Impostazioni → Live → Sorgente audio** (o il combo in cima alla
pagina Live), scegli:

- **Microfono** — solo il tuo microfono
- **Audio di sistema** — solo ciò che viene riprodotto sui tuoi
  altoparlanti
- **Entrambi** — entrambi mixati (utile per narrare sopra un media
  o catturare riunioni ibride)

Quando scegli **Audio di sistema** o **Entrambi**, l'app dispatch al
backend di cattura giusto per il tuo OS. Compare un banner di
avviso inline con link di installazione cliccabili se i prerequisiti
OS non sono soddisfatti, in modo che tu non debba avviare una
sessione per scoprire che manca qualcosa.

## Linux (PulseAudio / PipeWire)

Funziona out-of-the-box su ogni distro moderna.

L'app usa `parec` (PulseAudio Recorder) per intercettare la **fonte
monitor** del tuo sink predefinito. Lo shim di compatibilità
PulseAudio di PipeWire rende questo trasparente — non ti serve
PulseAudio puro.

```bash
parec --version    # dovrebbe stampare qualcosa
```

Se `parec` manca, il banner di avviso rileva il gestore di
pacchetti della tua distro e include il comando di installazione
esatto — per esempio:

> La cattura audio di sistema richiede PulseAudio o PipeWire — esegui `sudo apt-get install pulseaudio`.

Rilevato su apt-get / dnf / pacman / zypper / apk; puoi
copia-incollare il comando direttamente in un terminale.

## macOS

CoreAudio non espone l'audio di sistema nativamente, quindi ti serve
un **dispositivo loopback virtuale** — installa uno di:

- **[BlackHole](https://existential.audio/blackhole/)** — gratuito, open source
- **[Loopback](https://rogueamoeba.com/loopback/)** — a pagamento, GUI raffinata
- **[Soundflower](https://github.com/mattingalls/Soundflower)** — opzione gratuita legacy
- **[iShowU Audio Capture](https://shinywhitebox.com/audio-capture)** — a pagamento

L'app li auto-rileva tramite
`ffmpeg -f avfoundation -list_devices` e usa il primo match. Non
serve impostare il loopback come tua uscita / ingresso predefinito
— la cattura avviene direttamente attraverso il backend
avfoundation di `ffmpeg`.

Dopo l'installazione, scegli semplicemente **Audio di sistema** nel
combo della pagina Live e il banner di avviso scompare.

## Windows

Nativo — **nessun software extra necessario** nella maggior parte
dei casi.

L'app parla direttamente con **WASAPI loopback** tramite il pacchetto
Python [`soundcard`](https://github.com/bastibe/SoundCard) (installato
automaticamente con l'app su Windows). Questa è la stessa API
loopback nativa che usano le app desktop Tauri / Rust; cattura
l'output dell'altoparlante predefinito senza un cavo virtuale.

Se per qualche ragione WASAPI loopback non è disponibile (versioni
di Windows più vecchie, driver audio insolito), l'app ricade su
`ffmpeg -f dshow` contro un dispositivo DirectShow loopback
virtuale. Scegli uno di:

- **[Screen Capture Recorder](https://github.com/rdp/screen-capture-recorder-to-video-windows-free)** — gratuito, fornisce `virtual-audio-capturer`
- **[VB-Audio Virtual Cable](https://vb-audio.com/Cable/)** — gratuito, viene come `CABLE Output (VB-Audio Virtual Cable)`
- **Stereo Mix (Realtek Audio)** — opzione integrata legacy, spesso disabilitata di default

L'app sonda questi in ordine e usa il primo presente.

## Perché "Entrambi" cattura la tua voce E l'audio di sistema

In modalità **Entrambi**, l'app apre DUE flussi di cattura in
parallelo — il tuo microfono via `sounddevice`, l'audio di sistema
via il backend specifico per OS sopra — e li mixa a granularità di
blocco di campioni. Questa è la modalità giusta per narrare sopra
un video, o per catturare entrambi i lati di una riunione ibrida
(la tua voce più i partecipanti sugli altoparlanti).

> **Suggerimento:** se senti un eco o ottieni sottotitoli duplicati,
> hai audio di sistema che entra dal tuo microfono (altoparlanti
> forti → microfono li capta). Passa solo a **Audio di sistema**, o
> usa cuffie.

## Risoluzione dei problemi

| Sintomo | Causa probabile |
|---|---|
| La pagina Live si avvia ma niente sottotitoli | Sorgente audio sbagliata selezionata, o il tuo microfono predefinito è in muto |
| Sottotitoli per la tua voce ma non per il video YouTube | Il prerequisito audio di sistema non è installato (il banner dovrebbe mostrare le istruzioni di installazione) |
| Sottotitoli doppi (eco) | La modalità "Entrambi" capta l'audio di sistema due volte — una volta dagli altoparlanti via microfono, una volta via loopback. Passa solo ad Audio di sistema o usa cuffie |
| Il banner rimane visibile dopo aver installato il software mancante | Cambia scheda e torna — il banner ricontrolla allo show della pagina |
| macOS: BlackHole installato ma banner ancora attivo | Conferma che BlackHole sia nell'elenco dei dispositivi audio di `ffmpeg -f avfoundation -list_devices true -i ""`; l'app deve vederlo lì |
| Windows: WASAPI loopback fallisce nonostante nessun errore | Prova a installare VB-Audio Virtual Cable come ripiego; le versioni di Windows più vecchie o alcuni driver audio non espongono loopback tramite `soundcard` |
