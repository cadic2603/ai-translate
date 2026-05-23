---
description: Captura audio del sistema en Linux, macOS y Windows para la página Live de AI Translate — traduce cualquier sonido reproducido en tu computadora en tiempo real.
---

# Captura de audio del sistema (Live)

La página **[Traducción en vivo](../features/live-translation.md)**
puede capturar el **audio del sistema** (todo lo que reproduce en tus
altavoces) para que puedas subtitular / traducir cualquier media —
llamadas Zoom, YouTube, Netflix, juegos, sonidos del sistema.

En **Configuración → Live → Fuente de audio** (o el combo en la
parte superior de la página Live), elige:

- **Micrófono** — solo tu micro
- **Audio del sistema** — solo lo que se reproduce en tus altavoces
- **Ambos** — ambos mezclados (bueno para narrar sobre media o
  capturar reuniones híbridas)

Cuando eliges **Audio del sistema** o **Ambos**, la app despacha al
backend de captura correcto para tu OS. Aparece una banner de
advertencia en línea con enlaces de instalación clicables si los
prerequisitos del OS no están cumplidos, así no tienes que iniciar
una sesión para descubrir que algo falta.

## Linux (PulseAudio / PipeWire)

Funciona desde el primer momento en cualquier distro moderna.

La app usa `parec` (PulseAudio Recorder) para tocar la **fuente
monitor** de tu sink por defecto. El shim de compatibilidad
PulseAudio de PipeWire hace esto transparente — no necesitas
PulseAudio puro.

```bash
parec --version    # debería imprimir algo
```

Si `parec` falta, el banner de advertencia detecta el gestor de
paquetes de tu distro y añade el comando de instalación exacto —
por ejemplo:

> La captura de audio del sistema necesita PulseAudio o PipeWire — ejecuta `sudo apt-get install pulseaudio`.

Detectado en apt-get / dnf / pacman / zypper / apk; puedes
copiar-pegar el comando directamente en una terminal.

## macOS

CoreAudio no expone audio del sistema nativamente, así que necesitas
un **dispositivo loopback virtual** — instala uno de:

- **[BlackHole](https://existential.audio/blackhole/)** — gratis, código abierto
- **[Loopback](https://rogueamoeba.com/loopback/)** — de pago, GUI pulida
- **[Soundflower](https://github.com/mattingalls/Soundflower)** — opción gratis legacy
- **[iShowU Audio Capture](https://shinywhitebox.com/audio-capture)** — de pago

La app los auto-detecta vía `ffmpeg -f avfoundation -list_devices`
y usa la primera coincidencia. No necesitas establecer el loopback
como tu salida / entrada por defecto — la captura ocurre
directamente a través del backend avfoundation de `ffmpeg`.

Después de instalar, simplemente elige **Audio del sistema** en el
combo de la página Live y la banner de advertencia desaparece.

## Windows

Nativo — **no se necesita software extra** en la mayoría de los casos.

La app habla directamente con **WASAPI loopback** vía el paquete
Python [`soundcard`](https://github.com/bastibe/SoundCard)
(instalado automáticamente con la app en Windows). Esta es la misma
API de loopback nativa que usan las apps desktop Tauri / Rust;
captura la salida del altavoz por defecto sin un cable virtual.

Si por alguna razón WASAPI loopback no está disponible (versiones
de Windows más antiguas, controlador de audio inusual), la app cae
a `ffmpeg -f dshow` contra un dispositivo DirectShow loopback
virtual. Elige uno de:

- **[Screen Capture Recorder](https://github.com/rdp/screen-capture-recorder-to-video-windows-free)** — gratis, provee `virtual-audio-capturer`
- **[VB-Audio Virtual Cable](https://vb-audio.com/Cable/)** — gratis, viene como `CABLE Output (VB-Audio Virtual Cable)`
- **Stereo Mix (Realtek Audio)** — opción integrada legacy, a menudo deshabilitada por defecto

La app sondea por estos en orden y usa el primero presente.

## Por qué "Ambos" capta tu voz Y el audio del sistema

En modo **Ambos**, la app abre DOS flujos de captura en paralelo —
tu micro vía `sounddevice`, audio del sistema vía el backend
específico del OS arriba — y los mezcla a granularidad de bloque de
muestreo. Este es el modo correcto para narrar sobre un vídeo, o
para capturar ambos lados de una reunión híbrida (tu voz más los
participantes en altavoces).

> **Consejo:** si oyes un eco o obtienes subtítulos duplicados,
> tienes audio del sistema entrando por tu micrófono (altavoces
> fuertes → mic los capta). Cambia a **Audio del sistema** solo, o
> usa auriculares.

## Resolución de problemas

| Síntoma | Causa probable |
|---|---|
| La página Live arranca pero no hay subtítulos | Mal fuente de audio seleccionada, o tu micro por defecto está silenciado |
| Subtítulos para tu voz pero no para el vídeo de YouTube | El prerrequisito de audio del sistema no está instalado (el banner debería mostrar instrucciones de instalación) |
| Subtítulos dos veces (eco) | Modo "Ambos" capta audio del sistema dos veces — una vez de altavoces por mic, una vez por loopback. Cambia a Audio del sistema solo o usa auriculares |
| El banner permanece visible tras instalar el software faltante | Cambia de pestaña y vuelve — el banner re-verifica al mostrar la página |
| macOS: BlackHole instalado pero banner sigue arriba | Confirma que BlackHole está en la lista de dispositivos audio de `ffmpeg -f avfoundation -list_devices true -i ""`; la app necesita verlo allí |
| Windows: WASAPI loopback falla a pesar de no haber error | Prueba instalar VB-Audio Virtual Cable como repliegue; versiones de Windows más antiguas o algunos controladores de audio no exponen loopback via `soundcard` |
