---
description: AI Translate es un traductor de escritorio gratuito y multiplataforma para documentos, PDFs, subtítulos, audio y voz en vivo en más de 45 idiomas.
---

# AI Translate

Un traductor de escritorio gratuito y multiplataforma que maneja **45 idiomas**
y va mucho más allá del texto plano — traduce documentos, audio, vídeo, voz
en vivo, capturas de pantalla y más, todo a través de un único pipeline
impulsado por LLM.

<div class="grid cards" markdown>

-   :material-cursor-default-click-outline:{ .lg .middle } **Aplicación de escritorio**

    ---

    Arrastra un archivo, elige un idioma de destino, recibe una copia
    traducida. Arrastrar y soltar, historial, glosarios, todo.

    [:octicons-arrow-right-24: Tutorial de 5 minutos](getting-started/first-translation.md)

-   :material-console:{ .lg .middle } **Línea de comandos**

    ---

    `ait report.docx --target French` — el mismo pipeline, scriptable y
    sin interfaz. Útil para CI, jobs batch, servidores.

    [:octicons-arrow-right-24: Guía CLI](cli.md)

-   :material-robot-outline:{ .lg .middle } **Agentes de IA (MCP)**

    ---

    Expone la traducción como herramientas de Model Context Protocol
    para que Claude Desktop, Claude Code y otros clientes MCP puedan
    llamarlas directamente.

    [:octicons-arrow-right-24: Configuración MCP](mcp.md)

</div>

## Lo que puedes traducir

| Tipo | Formatos |
|---|---|
| **Documentos Office** | `.docx`, `.xlsx`, `.pptx`, `.odt`, `.ods`, `.odp`, más legacy `.doc` / `.xls` / `.ppt` |
| **PDFs** | traducción extract-overlay con preservación de layout, traducción de marcadores / formularios / enlaces, fallback OCR para escaneos |
| **Texto y web** | `.txt`, `.md`, `.rst`, `.html` / `.htm` / `.xhtml`, `.xml`, `.rtf`, `.json`, `.csv`, `.epub` |
| **Subtítulos** | `.srt`, `.vtt`, `.ass`, `.ssa` |
| **Localización** | `.po`, `.pot`, `.xliff` / `.xlf`, `.yaml` / `.yml`, `.properties`, `.strings` |
| **Imágenes** | `.png`, `.jpg`, `.jpeg`, `.bmp`, `.webp`, `.tiff`, `.tif` (OCR o visión LLM) |
| **Audio** | `.mp3`, `.wav`, `.m4a`, `.flac`, `.ogg`, `.aac`, `.wma` |
| **Vídeo** | `.mp4`, `.webm`, `.mkv`, `.avi`, `.mov`, `.wmv` (pipeline de doblaje completo) |

## Funcionalidades destacadas {: #headline-features }

- **[Traducir texto](features/translate-text.md)** — traducción LLM instantánea con detección automática, edición en sitio, reproducción TTS. Los idiomas de derecha a izquierda (árabe, hebreo, persa) se renderizan nativamente.
- **[Traducir documento](features/translate-document.md)** — suelta archivos, observa un spinner de progreso por tarea, recibe copias traducidas lado a lado. Los destinos RTL reciben markup bidi apropiado; `Ctrl+P` / `Ctrl+G` pausan y continúan la cola.
- **[Generar subtítulo (STT)](features/generate-subtitle.md)** — transcribe audio / vídeo a SRT / VTT / ASS / SSA.
- **[Generar voz (TTS)](features/generate-voice.md)** — sintetiza subtítulos a MP3 / WAV con timing.
- **[Doblaje de vídeo](features/dubbing.md)** — STT → traducir → TTS → mezcla completa de vuelta al vídeo fuente.
- **[Traducción en vivo](features/live-translation.md)** — overlay de subtítulos en tiempo real desde micrófono o audio del sistema.
- **[Extraer texto](features/extract-text.md)** — OCR o visión LLM → `.txt` / `.docx`.
- **[Glosario](features/glossary.md)** — aplica terminología consistente en todas las traducciones.

!!! tip "Modo Vertex AI para Gemini"
    Los usuarios empresariales pueden cambiar las llamadas Gemini de la
    API Developer a **Vertex AI** en **Configuración → LLM** —
    apúntalo a tu proyecto y región GCP, opcionalmente proporciona una
    ruta JSON de cuenta de servicio. Ver
    [Proveedores LLM](setup/llm-providers.md#google-gemini-recommended-for-first-time-setup).

!!! tip "¿Primera vez aquí?"
    Empieza con [Instalación](getting-started/installation.md), luego el
    [tutorial de primera traducción de 5 minutos](getting-started/first-translation.md).
    Tendrás un documento traducido en menos de 10 minutos desde un clon fresco.
