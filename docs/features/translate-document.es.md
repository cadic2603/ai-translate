---
description: Traduce PDFs, Word, Excel, PowerPoint, ODF, EPUB, HTML, JSON, YAML, SRT y 30+ otros formatos de archivo conservando el formato y la maquetación.
---

# Traducir documento

Traduce archivos completos — Office, PDF, EPUB, texto plano,
subtítulos, formatos de localización y más — con el formato preservado.

## Formatos soportados

| Categoría | Extensiones |
|---|---|
| Office | `.docx`, `.xlsx`, `.pptx`, `.odt`, `.ods`, `.odp`, `.doc`, `.xls`, `.ppt` |
| PDF | `.pdf` |
| Texto y web | `.txt`, `.md`, `.rst`, `.html`, `.htm`, `.xhtml`, `.xml`, `.rtf`, `.json`, `.csv` |
| eBooks | `.epub` |
| Subtítulos | `.srt`, `.vtt`, `.ass`, `.ssa` |
| Localización | `.po`, `.pot`, `.xliff`, `.xlf`, `.yaml`, `.yml`, `.properties`, `.strings` |

## Paso a paso

1. Haz clic en **Traducir documento** en la barra lateral.
2. Arrastra archivos (o haz clic en **Examinar**). Las carpetas también
   funcionan — los archivos soportados dentro se recogen recursivamente.
3. Elige **Origen** (o déjalo en `Detección automática`) y **Destino**.
4. Haz clic en **Traducir** — o pulsa `Ctrl+Enter`.
5. La tabla de historial debajo muestra el progreso por archivo
   (Pendiente → Traduciendo → Hecho / Fallido). La barra lateral
   muestra un spinner mientras alguna tarea está activa.
6. Haz clic en **Abrir** en una fila para abrir el archivo traducido.
   Clic derecho para opciones: retraducir, pausar, reintentar, eliminar.

## Dónde acaban los archivos

Por defecto, los archivos traducidos se guardan junto al original con
un sufijo `_translated_<src>_<tgt>`:

```
~/Documents/informe.docx
~/Documents/informe_translated_en_es.docx     ← aquí
```

Cambia esto en **Configuración → General → Ruta de almacenamiento de
traducciones** a un directorio personalizado.

## Límites y guardas

- **Tope de 100 archivos por arrastre** — arrastra más y recibirás una
  notificación. Traduce por lotes.
- **Detección de duplicados** — arrastra un archivo ya en la cola y
  verás una notificación (el duplicado se descarta, no se añade dos
  veces).
- **Auto-reanudación** — cierra la app mientras hay traducciones
  ejecutándose y se reanudarán en el siguiente lanzamiento (tareas
  Pendiente / Traduciendo).

## Opciones específicas de Office

La pestaña Traducción en **Configuración** expone estos interruptores
para archivos Office:

| Opción | Qué hace |
|---|---|
| **Traducir imágenes integradas** | Ejecuta OCR + visión LLM en imágenes dentro de `.docx` / `.xlsx` / `.pptx` y reinserta la imagen traducida. Requiere OCR configurado. |
| **Traducir comentarios** | Los comentarios / notas de revisión se traducen junto con el texto del cuerpo. |
| **Traducir formas y cuadros de texto** | Captura texto que vive en formas, llamadas y cuadros de texto flotantes. |
| **Traducir notas del orador** | Las notas del orador de PowerPoint se traducen. |
| **Traducir nombres de hojas** | Las etiquetas de pestañas de hojas Excel se traducen. |
| **Auto-convertir legado** | Los `.doc` / `.xls` / `.ppt` se convierten a OOXML moderno antes de traducir (mejor fidelidad). |
| **Auto-convertir ODF** | Los `.odt` / `.ods` / `.odp` se convierten a OOXML antes de traducir. |

Toda la traducción Office preserva el formato por run: negrita,
cursiva, subrayado, tachado, tamaño de fuente, color, hiperenlaces,
encabezados, pies de página, notas al pie, notas finales, todo.

### Traducción de imágenes incrustadas: omisión con advertencia + caché

Cuando **Traducir imágenes incrustadas** está activado, cada
imagen incrustada pasa por OCR → visión LLM → reinyección
renderizada. Dos comportamientos a tener en cuenta:

- **Omisión con advertencia**: si una imagen no se puede
  traducir (demasiado grande, corrupta, el modelo de visión
  rechaza el formato, etc.) el documento se completa de todos
  modos — la imagen rota permanece en el idioma original, se
  registra una advertencia en `app.log` y el bucle continúa
  con la siguiente imagen. Solo los errores fatales de LLM
  (`AUTH_ERROR`, `QUOTA_ERROR`, `VISION_NOT_SUPPORTED`)
  detienen la canalización inmediatamente porque bloquean
  también todas las imágenes restantes. El banner informativo
  encima de la casilla **Traducir imágenes incrustadas**
  documenta la política en línea.
- **Caché por imagen**: las traducciones de imagen
  satisfactorias se conservan en el directorio de
  almacenamiento interno de la tarea con clave SHA256 de los
  bytes de origen. Al reintentar, las imágenes ya traducidas
  acceden a la caché en lugar de volver a ejecutar OCR + LLM —
  el trabajo pagado no se repite. Las imágenes duplicadas (un
  logotipo de empresa en cada diapositiva) se traducen una
  vez y se reutilizan N − 1 veces.

El archivo de salida solo aparece en la carpeta de salida
elegida en caso de **éxito** — las traducciones parciales de
ejecuciones canceladas o fallidas permanecen confinadas en el
directorio de almacenamiento interno de la tarea, por lo que
su carpeta de salida nunca acumula documentos huérfanos a medio
traducir.

## Especificidades de PDF

Los PDFs usan un motor de extracción-superposición: el texto original
se redacta en su lugar y el texto traducido se superpone en las
mismas cajas, conservando la maquetación visual. El checkpoint por
página significa que una ejecución pausada / colapsada se reanuda
donde se quedó, no en la página 1.

Lo que se traduce:

- Texto del cuerpo (con detección de alineación — izquierda / centro /
  derecha / justificado)
- Marcadores / esquemas (entradas TOC)
- Campos de formulario (entradas de texto, desplegables, listas)
- Hiperenlaces (rectángulo del enlace actualizado para envolver el
  nuevo texto)
- Imágenes integradas (cuando **Traducir imágenes integradas** está
  activado)
- Comentarios / anotaciones PDF

Para PDFs escaneados (sin capa de texto integrada), el OCR se ejecuta
automáticamente por página. Configura tu motor OCR en
**Configuración → OCR**.

## Salida de derecha a izquierda

Las traducciones a **árabe**, **hebreo** o **persa** se renderizan
como RTL nativamente en cada formato de salida — `dir="rtl"` inyectado
en superposiciones PDF, HTML, y capítulos EPUB (con
`page-progression-direction="rtl"` en el OPF del EPUB para que Apple
Books y Kindle pasen las páginas en la dirección correcta); DOCX
`<w:bidi/>` + `<w:rtl/>`, PPTX `rtl="1"`, vista de hoja XLSX de
derecha a izquierda, ODT/ODS/ODP `style:writing-mode="rl-tb"`, RTF
`\rtldoc`, y reflejo de códigos de alineación ASS/SSA (`\an1` ↔
`\an3`, `\an4` ↔ `\an6`, etc.). Los alineamientos centrales no se
tocan.

## Atajos

| Atajo | Acción |
|---|---|
| `Ctrl+Enter` | Iniciar traducción |
| `Ctrl+O` | Examinar archivos |
| `Ctrl+F` | Enfocar búsqueda de historial |
| `Ctrl+P` | Pausar la cola activa |
| `Ctrl+G` | Continuar (reanudar) la cola activa |
| `Supr` | Eliminar entradas de historial seleccionadas |

`Ctrl+P` / `Ctrl+G` se suprimen cuando un campo de entrada de texto
tiene el foco, para que no choquen con la escritura.

## Cuando algo falla

Una tarea fallida muestra un estado rojo con un código de error y un
mensaje localizado — consulta la [guía de resolución de problemas](../troubleshooting.md)
para los comunes (`AUTH_ERROR`, `QUOTA_ERROR`, `FFMPEG_NOT_FOUND`,
etc.).
