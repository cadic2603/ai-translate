---
description: Captura de audio de micrófono multiplataforma para traducción en vivo.
---

# Configuración de PortAudio (Micrófono)

La función de [Traducción en vivo](../features/live-translation.md) utiliza el paquete de Python `sounddevice`, que se basa en la biblioteca C PortAudio para acceder a los dispositivos de micrófono en todos los sistemas operativos. La mayoría de los usuarios necesitan instalar esta dependencia a nivel del sistema.

## Windows
Las ruedas precompiladas (wheels) para `sounddevice` y `PyAudio` generalmente empaquetan el binario de PortAudio en Windows. La instalación manual a nivel de sistema normalmente no es necesaria. Si encuentra errores, asegúrese de que sus controladores de audio estén actualizados.

## macOS
Use Homebrew para instalar PortAudio:

```bash
brew install portaudio
```

## Linux
El nombre del paquete depende de su distribución. El paquete de desarrollo (que normalmente termina en `-dev` o `-devel`) debe instalarse para que Python pueda compilar las vinculaciones de C si no hay una rueda precompilada disponible.

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

## Solución de problemas

Si la aplicación sigue informando que no puede acceder al micrófono después de la instalación:

1. Asegúrese de que su aplicación de terminal (o entorno de escritorio) tenga permiso para acceder al micrófono (especialmente en macOS).
2. Reinicie la aplicación (o el terminal/servidor MCP) para que adquiera la nueva ruta de la biblioteca.
