---
description: Instala AI Translate en Windows, macOS o Linux desde binarios precompilados o desde el código fuente — cubre Python, FFmpeg y configuración opcional de LibreOffice.
---

# Instalación

## Lo que necesitas

- **Python 3.12 o más reciente** ([descarga](https://www.python.org/downloads/))
- **[uv](https://docs.astral.sh/uv/)** — gestor de paquetes Python rápido. Instala con:

    === "macOS / Linux"
        ```bash
        curl -LsSf https://astral.sh/uv/install.sh | sh
        ```

    === "Windows"
        ```powershell
        powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
        ```

- **Una clave de API LLM** — cualquiera de:
    - [Google Gemini](https://aistudio.google.com/apikey) (capa gratuita disponible — recomendado para empezar)
    - Cualquier endpoint compatible con OpenAI (OpenAI, Anthropic vía proxy, Ollama / LM Studio local, etc.)

## Opcional, pero desbloquea más funciones

| Herramienta | Usado por | Cuándo lo necesitas |
|---|---|---|
| **FFmpeg** ([descarga](https://ffmpeg.org/download.html)) | Subtítulos, Voz, Doblaje, Live | Cualquier flujo de audio/vídeo |
| **LibreOffice** ([descarga](https://www.libreoffice.org/download/)) | Formatos Office en Linux/macOS | Traducir legacy `.doc` / `.xls` / `.ppt`, o cualquier archivo Office cuando MS Office no está instalado |
| **Tesseract** ([guía de instalación](https://tesseract-ocr.github.io/tessdoc/Installation.html)) | Motor OCR (por defecto) | Página Extraer texto, traducción de PDFs escaneados, traducción de imágenes embebidas |
| **MS Office** + **pywin32** | Office en Windows | Traducción Office de máxima fidelidad en Windows |

Puedes instalar AI Translate sin ninguno de estos — las funciones que los
necesitan te lo dirán antes de fallar.

## Configúralo

```bash
git clone https://github.com/cadic2603/ai-translate.git
cd ai-translate
uv sync
```

Eso instala todo lo necesario para ejecutar la aplicación de escritorio,
el CLI y el servidor MCP.

## Ejecútalo

=== "Aplicación de escritorio"
    ```bash
    uv run python -m src.main
    ```

=== "Línea de comandos"
    ```bash
    uv run ait --version
    ```

=== "Servidor MCP"
    ```bash
    uv run ait-mcp           # transporte stdio (para Claude Desktop / Code)
    ```

## Añade tu clave de API

La primera vez que abras la aplicación de escritorio:

1. Haz clic en **Configuración** en la barra lateral
2. Abre la pestaña **LLM**
3. Pega tu **clave de API de Google Gemini** (o configura un proveedor
   personalizado compatible con OpenAI). Los usuarios empresariales pueden
   cambiar Gemini a **modo Vertex AI** — apúntalo a un proyecto y región
   GCP, opcionalmente proporciona una ruta JSON de cuenta de servicio;
   ver [Proveedores LLM](../setup/llm-providers.md) para los detalles.
4. Elige un modelo por defecto — cualquier variante Flash actual (por
   ej. `gemini-2.5-flash`) es un punto de partida gratuito sólido. Las
   variantes Pro dan mejor calidad a un coste más alto.
5. Cierra Configuración — has terminado

Las claves se guardan en el **trousseau de tu OS** (Keychain de macOS,
Credential Manager de Windows, Secret Service de GNOME / KDE en Linux),
no en texto plano en disco.

!!! tip "Instalación headless / servidor"
    Si no puedes ejecutar la aplicación de escritorio para configurar
    las claves, ver [Proveedores LLM](../setup/llm-providers.md) para los
    comandos CLI keyring.

## Siguiente: pruébalo

[Primera traducción en 5 minutos →](first-translation.md){ .md-button .md-button--primary }
