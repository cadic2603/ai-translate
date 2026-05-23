---
description: Usa la interfaz de línea de comandos ait para traducir archivos sin interfaz gráfica — soporta PDFs, documentos Office, subtítulos y 45+ idiomas desde un script o job de CI.
---

# Línea de comandos (`ait`)

Traducción headless — el mismo pipeline que la aplicación de escritorio,
sin pantalla requerida. Útil para CI, jobs batch, servidores y flujos
de trabajo scriptados.

## Inicio rápido

```bash
ait report.docx --target French
```

La salida aterriza junto a la fuente como
`report_translated_<src>_<tgt>.docx`.

## Recetas comunes

### Múltiples archivos

```bash
ait *.pdf --target Japanese
```

La expansión glob es trabajo del shell (Unix). En Windows / `cmd.exe`,
lista los archivos explícitamente o usa PowerShell:

```powershell
ait (Get-ChildItem *.pdf) --target Japanese
```

### Directorio de salida personalizado

```bash
ait report.docx --target French --output ./translated/
```

El directorio se crea si no existe. Si no se puede crear (permiso
denegado, etc.) obtienes un error claro y código de salida 2 — sin
ejecución parcial.

### Especificar idioma fuente

```bash
ait letter.txt --target German --source "English (US)"
```

La coincidencia de fuente no distingue mayúsculas/minúsculas. "Chinese"
solo imprime una pista:

```bash
ait letter.txt --target Chinese
# Error: unknown target language 'Chinese'.
# Did you mean one of: Chinese (Simplified), Chinese (Traditional)?
```

### Elegir un modelo específico

```bash
ait big-doc.pdf --target French --model "Gemini:gemini-2.5-pro"
# O cualquier otro Provider:model_name registrado en la pestaña LLM de la app de escritorio.
```

El formato es estrictamente `Provider:model_name`. Faltan dos puntos
→ salida 2 con un mensaje claro en lugar de caer silenciosamente al
modelo Gemini por defecto.

### Opciones Office

```bash
ait deck.pptx --target Vietnamese \
    --translate-images \
    --translate-comments \
    --translate-shapes \
    --translate-notes
```

`--translate-images` requiere OCR configurado (ver
[Motores OCR](setup/ocr-engines.md)).

### Auto-conversión de formatos antiguos

```bash
ait old-doc.doc --target French --convert-legacy
```

El pipeline convierte `.doc` → `.docx` primero (mejor fidelidad),
traduce la copia moderna, reconvierte. Igual para `--convert-odf` y
`.odt` / `.ods` / `.odp`.

### Silencioso / verboso

```bash
ait report.docx --target French --quiet      # solo errores
ait report.docx --target French --verbose    # firehose DEBUG completo
```

El modo por defecto imprime un banner y progreso por tarea a stderr;
el detalle completo (volcados de body HTTP, logs de retry) aterriza
en el directorio de logs de la app de la plataforma sin importar el
verbosidad de consola (ver
[Resolución de problemas → ¿Dónde están los logs?](troubleshooting.md#where-are-the-logs)
para la ruta en tu OS).

### Listar idiomas soportados

```bash
ait --list-languages
```

Imprime los 45 idiomas soportados. Útil para encadenar en bucles shell.

### Versión

```bash
ait --version
# ait 0.1.0
```

## Códigos de salida

| Código | Significado |
|---|---|
| `0` | Todas las tareas exitosas |
| `2` | Error de argumento (idioma desconocido, destino faltante, modelo malformado, salida no escribible, extensión de archivo no soportada) |
| `3` | LLM no configurado |
| `4` | Fallo parcial (algunas exitosas, algunas no) |
| `5` | Todas fallidas |
| `130` | Interrumpido (`Ctrl+C`) |

## Cancelación

`Ctrl+C` una vez — cancelación cooperativa. El checkpoint de la tarea
actual se guarda, el pipeline sale limpiamente en el siguiente límite
de polling.

`Ctrl+C` de nuevo — interrupción dura. Úsalo con moderación; archivos
parciales pueden quedar en estado a medio escribir.

## Referencia completa de flags

```bash
ait --help
```

Muestra cada flag con su valor por defecto. El mismo contenido
resumido aquí:

| Flag | Por defecto | Notas |
|---|---|---|
| `--target / -t LANG` | _requerido_ | No distingue mayúsculas/minúsculas |
| `--source / -s LANG` | autodetección | No distingue mayúsculas/minúsculas |
| `--output / -o DIR` | padre de la fuente | Creado si falta |
| `--model / -m PROVIDER:MODEL` | por defecto del desktop | Formato estricto |
| `--ocr-method METHOD` | `TesseractOCR` | `Tesseract`, `EasyOCR`, `Google Cloud OCR` |
| `--translate-images` | off | Requiere OCR configurado |
| `--translate-comments` | off | Comentarios Office |
| `--translate-shapes` | off | Formas / cuadros de texto |
| `--translate-notes` | off | Notas del orador en PowerPoint |
| `--translate-sheet-names` | off | Pestañas de hoja Excel |
| `--convert-legacy` | off | `.doc`/`.xls`/`.ppt` → formato moderno |
| `--convert-odf` | off | `.odt`/`.ods`/`.odp` → OOXML |
| `--keep-history` | off | Conservar entradas de historial tras completar |
| `--quiet / -q` | off | Solo errores en consola |
| `--verbose / -v` | off | Firehose DEBUG |
| `--list-languages` | — | Imprime 45 idiomas y sale |
| `--version` | — | Imprime versión y sale |

## Trucos

!!! tip "Configura una vez, usa en todas partes"
    El CLI comparte sus claves de API y configuraciones con la app de
    escritorio — configura todo una vez en la GUI, luego automatiza
    con `ait` desde ahí.

!!! tip "Caché de endpoint cold-start"
    Para cada par `(endpoint, modelo)`, la elección chat-vs-responses-API
    y la variante de payload que funciona se persisten a
    `llm_endpoint_cache.json` en el directorio de caché del OS
    (`~/.cache/ai-translate/` en Linux,
    `~/Library/Caches/ai-translate/` en macOS,
    `%LOCALAPPDATA%\ai-translate\cache\` en Windows). Las invocaciones
    CLI cold-start saltan completamente el probe de auto-detección
    tras la primera llamada exitosa — útil cuando script contra
    despliegues Azure / vLLM / OpenRouter / Anthropic / DeepSeek que
    necesitan tuning de payload específico al proveedor. La caché es
    segura multi-proceso y multi-thread (read-merge-write bajo RLock
    con rename atómico).

!!! tip "Streams de salida"
    El modo por defecto imprime el banner, lista de tareas en cola, y
    progreso por tarea a **stdout** (line-buffered para que se entrelace
    correctamente con errores); mensajes de error y registros de log
    van a **stderr**. Combina con `--quiet` para suprimir stdout
    completamente para piping limpio:

    ```bash
    ait --list-languages | grep -i japanese    # datos en stdout
    ait file.txt --target French --quiet 2> errors.log
    ```
