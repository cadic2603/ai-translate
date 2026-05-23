---
description: Expón AI Translate como herramientas Model Context Protocol para que Claude Desktop, Claude Code y otros clientes MCP puedan traducir texto, archivos y audio.
---

# Servidor MCP (`ait-mcp`)

Expone el pipeline de traducción como herramientas **Model Context
Protocol** para que agentes de IA como Claude Desktop y Claude Code
puedan manejarlo directamente — "Traduce este PDF al francés" se
convierte en una llamada de herramienta, no en copy-paste.

## Lo que se expone

Nueve herramientas:

| Herramienta | Propósito |
|---|---|
| `translate_text` | Traducir una lista de cadenas |
| `translate_document` | Encolar tareas de traducción de archivos (devuelve IDs de tareas) |
| `get_task_status` | Consultar el estado de la tarea |
| `cancel_task` | Cancelación cooperativa de tareas en vuelo |
| `extract_image_text` | OCR o visión LLM |
| `transcribe_audio` | Audio → SRT |
| `synthesize_speech` | Texto → MP3 / WAV |
| `query_glossary` | Listar conjuntos / entradas de glosario |
| `list_languages` | Las 45 idiomas soportados |

## Ejecutar el servidor

```bash
ait-mcp                       # transporte stdio (por defecto para agentes desktop)
ait-mcp --transport sse       # Server-Sent Events para clientes web
ait-mcp --transport sse --port 9000
```

`stdio` es lo que cualquier cliente MCP espera a menos que hayas
configurado SSE explícitamente.

## Añadir a Claude Desktop

1. Abre Claude Desktop → **Settings → Developer → Edit Config**
2. Añade esta entrada bajo `mcpServers`:

    ```json
    {
      "mcpServers": {
        "ai-translate": {
          "command": "uv",
          "args": ["run", "--project", "/absolute/path/to/ai-translate", "ait-mcp"]
        }
      }
    }
    ```

    Reemplaza `/absolute/path/to/ai-translate` con la ruta del repo clonado.

3. Cierra y vuelve a abrir Claude Desktop. El icono del martillo debería
   ahora mostrar "ai-translate" con las 9 herramientas. Prueba:

    > "Traduce este PDF (`/home/me/report.pdf`) al francés — guarda
    > la salida junto a la fuente."

## Añadir a Claude Code

`~/.config/claude-code/mcp_servers.json` (o `claude mcp add` desde
dentro de Claude Code):

```json
{
  "ai-translate": {
    "command": "uv",
    "args": ["run", "--project", "/absolute/path/to/ai-translate", "ait-mcp"]
  }
}
```

Reinicia Claude Code. Las mismas 9 herramientas se vuelven invocables.

## Añadir a otros clientes MCP

Cualquier cliente compatible con MCP toma una forma similar:

- **Command** — `uv run --project /path/to/ai-translate ait-mcp`
- **Transport** — stdio (por defecto)

Para clientes basados en HTTP / SSE, ejecuta
`ait-mcp --transport sse --port 9000` y apunta el cliente a
`http://localhost:9000`.

## Garantías de validación

Cada herramienta devuelve la misma forma en errores para que los agentes
puedan manejar fallos de manera consistente:

| Entrada incorrecta | Respuesta de la herramienta |
|---|---|
| Idioma desconocido | `ValueError: Unknown … language '<input>'. Call list_languages to see supported values.` |
| LLM no configurado | `RuntimeError: LLM is not configured. Run the desktop app and set up your API key…` |
| Tipo de archivo no soportado | `ValueError` listando extensiones permitidas |
| `model="…"` malformado (sin `:`) | `ValueError` en lugar de usar silenciosamente el por defecto |
| IDs de tarea desconocidos en `cancel_task` | Devueltos en el array `unknown` — sin error |
| FFmpeg faltante en `transcribe_audio` | `RuntimeError: FFmpeg is required…` (re-envuelto del tag `FFMPEG_NOT_FOUND` del motor) |

Los agentes que llaman a estas herramientas pueden confiar en estos contratos.

## Concurrencia

`translate_document` ejecuta el pipeline en un hilo daemon. Cada batch
obtiene su propio evento de cancelación, así que cancelar un batch no
perturba otro. El servidor MCP rastrea pipelines activos en un mapa
local del proceso (limpiado automáticamente cuando el pipeline termina).

## Casos de uso

- **"Traduce los docs de esta codebase al vietnamita"** — apunta al
  agente a la carpeta docs, batchea llamadas `translate_document` y
  consulta `get_task_status` hasta que cada uno termine.
- **"¿Qué idiomas soportas?"** — el agente llama a `list_languages`,
  lee la respuesta.
- **"Traduce este recibo japonés"** — el agente llama a
  `extract_image_text` en la foto, luego `translate_text` sobre el resultado.
- **"Genera subtítulos vietnamitas para esta grabación de Zoom"** —
  el agente llama a `transcribe_audio` para obtener un SRT en el
  idioma fuente, luego `translate_text` sobre cada cue para localizar,
  y reensambla el SRT.

!!! note "El doblaje de vídeo no es una herramienta MCP"
    El pipeline completo STT → traducir → TTS → mux (la página
    **Doblaje** de la app de escritorio) sólo está disponible a través
    de la GUI ahora mismo. Desde MCP puedes componer el equivalente
    tú mismo con `transcribe_audio` + `translate_text` +
    `synthesize_speech`, pero necesitarás manejar el paso de mux con
    timing (FFmpeg) por fuera.

## Trucos

!!! tip "Configura una vez, los agentes funcionan en todas partes"
    El servidor MCP comparte claves API y configuraciones con la app
    de escritorio y el CLI. Configura tu LLM / OCR / TTS una vez en
    la GUI, luego cualquier agente que hable con `ait-mcp` hereda la
    misma configuración.

!!! tip "Caché de endpoint cold-start"
    Para cada par `(endpoint, modelo)`, la elección
    chat-vs-responses-API y la variante de payload funcionante se
    persisten a `llm_endpoint_cache.json` en el directorio de caché
    del OS (`~/.cache/ai-translate/` en Linux,
    `~/Library/Caches/ai-translate/` en macOS,
    `%LOCALAPPDATA%\ai-translate\cache\` en Windows). Procesos
    `ait-mcp` frescos saltan completamente el probe de auto-detección
    tras la primera llamada exitosa — agentes que spawnan el servidor
    bajo demanda no pagan los round-trips de detección de variantes
    en cada invocación. La caché es segura multi-proceso y multi-thread
    (read-merge-write bajo RLock con rename atómico).

!!! tip "Selector de modelo por herramienta"
    Las herramientas `translate_text` y `translate_document` aceptan
    un parámetro `model` opcional — los agentes pueden elegir un
    modelo rápido para turnos rápidos y uno más pesado para salida
    de producción sin necesitar que el usuario reconfigure la app
    de escritorio.

!!! warning "Pipelines de larga duración"
    `translate_document` devuelve inmediatamente con IDs de tarea.
    Se espera que el agente consulte `get_task_status` hasta que cada
    tarea alcance `Done` o `Failed`. No esperes síncronamente dentro
    de la llamada de herramienta; eso arriesga que el timeout del
    cliente MCP se dispare.
