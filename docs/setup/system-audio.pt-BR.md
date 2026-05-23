---
description: Capture áudio do sistema no Linux, macOS e Windows para a página Live do AI Translate — traduza qualquer som tocando no seu computador em tempo real.
---

# Captura de áudio do sistema (Live)

A página **[Tradução ao vivo](../features/live-translation.md)**
pode capturar **áudio do sistema** (tudo o que está tocando nos seus
alto-falantes) para que você possa legendar / traduzir qualquer
mídia — chamadas Zoom, YouTube, Netflix, jogos, sons do sistema.

Em **Configurações → Live → Fonte de áudio** (ou o combo no topo
da página Live), escolha:

- **Microfone** — apenas seu microfone
- **Áudio do sistema** — apenas o que está tocando nos seus
  alto-falantes
- **Ambos** — ambos misturados (bom para narrar sobre mídia ou
  capturar reuniões híbridas)

Quando você escolhe **Áudio do sistema** ou **Ambos**, o app
despacha para o backend de captura correto para seu SO. Um banner
de aviso inline com links de instalação clicáveis aparece se os
pré-requisitos do SO não forem atendidos, então você não precisa
iniciar uma sessão para descobrir que algo está faltando.

## Linux (PulseAudio / PipeWire)

Funciona out-of-the-box em toda distro moderna.

O app usa `parec` (PulseAudio Recorder) para tocar a **fonte
monitor** do seu sink padrão. O shim de compatibilidade PulseAudio
do PipeWire torna isso transparente — você não precisa de
PulseAudio puro.

```bash
parec --version    # deve imprimir algo
```

Se `parec` está faltando, o banner de aviso detecta o gerenciador
de pacotes da sua distro e insere o comando de instalação exato —
por exemplo:

> A captura de áudio do sistema precisa de PulseAudio ou PipeWire — execute `sudo apt-get install pulseaudio`.

Detectado em apt-get / dnf / pacman / zypper / apk; você pode
copiar-colar o comando diretamente em um terminal.

## macOS

O CoreAudio não expõe áudio do sistema nativamente, então você
precisa de um **dispositivo loopback virtual** — instale um de:

- **[BlackHole](https://existential.audio/blackhole/)** — gratuito, código aberto
- **[Loopback](https://rogueamoeba.com/loopback/)** — pago, GUI polida
- **[Soundflower](https://github.com/mattingalls/Soundflower)** — opção gratuita legada
- **[iShowU Audio Capture](https://shinywhitebox.com/audio-capture)** — pago

O app os auto-detecta via
`ffmpeg -f avfoundation -list_devices` e usa o primeiro match. Não
precisa definir o loopback como sua saída / entrada padrão — a
captura acontece diretamente através do backend avfoundation do
`ffmpeg`.

Após instalar, basta escolher **Áudio do sistema** no combo da
página Live e o banner de aviso desaparece.

## Windows

Nativo — **nenhum software extra necessário** na maioria dos casos.

O app fala diretamente com **WASAPI loopback** via o pacote Python
[`soundcard`](https://github.com/bastibe/SoundCard) (instalado
automaticamente com o app no Windows). Esta é a mesma API de
loopback nativa que apps desktop Tauri / Rust usam; ela captura a
saída do alto-falante padrão sem um cabo virtual.

Se por alguma razão o WASAPI loopback não estiver disponível
(versões mais antigas do Windows, driver de áudio incomum), o app
cai para `ffmpeg -f dshow` contra um dispositivo DirectShow loopback
virtual. Escolha um de:

- **[Screen Capture Recorder](https://github.com/rdp/screen-capture-recorder-to-video-windows-free)** — gratuito, fornece `virtual-audio-capturer`
- **[VB-Audio Virtual Cable](https://vb-audio.com/Cable/)** — gratuito, vem como `CABLE Output (VB-Audio Virtual Cable)`
- **Stereo Mix (Realtek Audio)** — opção on-board legada, frequentemente desabilitada por padrão

O app sonda por estes em ordem e usa o primeiro presente.

## Por que "Ambos" capta sua voz E o áudio do sistema

No modo **Ambos**, o app abre DOIS fluxos de captura em paralelo —
seu microfone via `sounddevice`, áudio do sistema via o backend
específico do SO acima — e os mistura na granularidade de bloco de
amostra. Este é o modo certo para narrar sobre um vídeo, ou para
capturar ambos os lados de uma reunião híbrida (sua voz mais os
participantes nos alto-falantes).

> **Dica:** se você ouvir um eco ou obtiver legendas duplicadas,
> você tem áudio do sistema entrando pelo seu microfone
> (alto-falantes altos → microfone os pega). Mude para **Áudio do
> sistema** apenas, ou use fones de ouvido.

## Solução de problemas

| Sintoma | Causa provável |
|---|---|
| Página Live inicia mas sem legendas | Fonte de áudio errada selecionada, ou seu microfone padrão está mudo |
| Legendas para sua voz mas não para o vídeo do YouTube | Pré-requisito de áudio do sistema não está instalado (o banner deve mostrar instruções de instalação) |
| Legendas duas vezes (eco) | Modo "Ambos" capta áudio do sistema duas vezes — uma vez de alto-falantes via microfone, uma vez via loopback. Mude para Áudio do sistema apenas ou use fones |
| Banner permanece visível após instalar o software faltante | Mude de aba e volte — o banner re-verifica ao mostrar a página |
| macOS: BlackHole instalado mas banner ainda em cima | Confirme que BlackHole está na lista de dispositivos de áudio de `ffmpeg -f avfoundation -list_devices true -i ""`; o app precisa vê-lo lá |
| Windows: WASAPI loopback falha apesar de não haver erro | Tente instalar VB-Audio Virtual Cable como recuo; versões mais antigas do Windows ou alguns drivers de áudio não expõem loopback via `soundcard` |
