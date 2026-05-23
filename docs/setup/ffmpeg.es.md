---
description: Instala FFmpeg para que AI Translate pueda decodificar audio y vídeo para la generación de subtítulos, síntesis de voz y doblaje de vídeo — requerido para las funciones multimedia.
---

# FFmpeg

FFmpeg es requerido para cualquier flujo de audio / vídeo:

- **Generar subtítulo** — decodificación de audio de origen para STT
- **Generar voz** — combinación de clips TTS con timing en un archivo
- **Doblaje** — STT → TTS → mux de vuelta al vídeo
- **Traducción en vivo** — cuando la captura de audio del sistema pasa
  por `parec`

No está incluido — instálalo una vez en tu sistema.

## Instalar

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

    O, para una compilación más completa, habilita
    [RPM Fusion](https://rpmfusion.org/Configuration) primero.

=== "Arch / Manjaro"
    ```bash
    sudo pacman -S ffmpeg
    ```

=== "Windows"
    Descarga una compilación estática desde <https://www.gyan.dev/ffmpeg/builds/>
    (la build "release essentials" está bien), descomprime, luego
    añade la carpeta `bin/` a tu PATH:

    1. Pulsa **Win + R**, teclea `sysdm.cpl`, pulsa **Enter**
    2. **Avanzado → Variables de entorno → Variables del sistema → Path → Editar**
    3. **Nuevo** → pega la ruta absoluta de la carpeta `bin` de FFmpeg
    4. **Aceptar** en todo, reinicia cualquier terminal abierta

## Verificar

```bash
ffmpeg -version
```

Deberías ver un banner de versión con `--enable-libx264 --enable-libvpx`
en la línea de configuración. Si ves "command not found", la
instalación no acabó en PATH.

## Comprobación pre-flight en la app

Las páginas Voz / Doblaje llaman a `shutil.which("ffmpeg")` antes de
empezar el trabajo. Si FFmpeg no se encuentra, verás un diálogo de
error amigable con un enlace de vuelta aquí, no una tarea a medio
ejecutar.

## Error común

| Error | Significado |
|---|---|
| `FFMPEG_NOT_FOUND` | `ffmpeg` no está en PATH en el momento en que la página intentó ejecutarlo. Instálalo (arriba) y reinicia la app. |

En el servidor MCP (`ait-mcp`), el mismo error se re-envuelve en un
mensaje legible por humanos:

> *"FFmpeg es requerido para decodificar este archivo de audio/vídeo
> pero no está instalado o no está en PATH. Instala FFmpeg y vuelve
> a intentar."*
