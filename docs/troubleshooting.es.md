---
description: Diagnostica problemas de AI Translate — fuentes faltantes, errores de FFmpeg, problemas del conversor LibreOffice, fallos de configuración OCR y autenticación de la API LLM.
---

# Resolución de problemas

Errores comunes, qué significan y cómo arreglarlos.

## Errores de configuración

### "LLM is not configured"

No has añadido una clave de API todavía. Abre la app de escritorio →
**Configuración → LLM** → pega una clave. Ver
[Proveedores LLM](setup/llm-providers.md) para la guía completa.

### `AUTH_ERROR`

La clave de API LLM es incorrecta o ha expirado.

- **Gemini** — genera una nueva clave en
  <https://aistudio.google.com/apikey>, vuelve a pegarla en
  **Configuración → LLM**.
- **Proveedor personalizado** — verifica que la clave es válida (curl
  el endpoint manualmente con el mismo header
  `Authorization: Bearer …`). Si el endpoint se movió, actualiza
  también el campo **Endpoint API**.

### `QUOTA_ERROR`

Has alcanzado un límite de capa gratuita o de plan de pago.

- **Capa gratuita Gemini** — la cuota de solicitudes diarias varía por
  modelo (ver <https://ai.google.dev/gemini-api/docs/rate-limits>).
  Espera un día, o pasa a pago.
- **OpenAI / otros** — verifica tu dashboard de facturación. Muchos
  proveedores tienen "spend caps" que pausan solicitudes cuando los
  alcanzas.

### `MODEL_NOT_FOUND`

El nombre de modelo que elegiste no está disponible.

- Proveedores personalizados — asegúrate de que el modelo está en la
  lista **Models** separada por comas en **Configuración → LLM**.
- Lista Gemini integrada — cambia a un modelo documentado en
  **Configuración → LLM → Modelo Gemini por defecto**.

### `VISION_NOT_SUPPORTED`

Elegiste un modelo no-vision e intentaste traducir una imagen / PDF
escaneado. Cambia a un modelo cuyo nombre contenga `flash`, `pro` o
`vision` (p. ej. `gpt-4o` para OpenAI, cualquier variante actual de
Gemini Flash o Pro para Gemini).

## Errores de audio / vídeo

### `FFMPEG_NOT_FOUND`

FFmpeg no está en PATH. Ver [Configuración FFmpeg](setup/ffmpeg.md)
para el comando de instalación de tu OS.

El servidor MCP reescribe esto como: *"FFmpeg is required to decode
this audio/video file but is not installed or not on PATH."*

### La página Live no muestra subtítulos

- **Fuente de audio incorrecta** — abre **Configuración → Live →
  Fuente de audio** y asegúrate de que coincide con lo que realmente
  quieres (Micrófono / Sistema / Ambos).
- **Mic muteado** — verifica la configuración de sonido del OS; la
  app usa tu dispositivo de entrada por defecto.
- **Audio del sistema no configurado** — ver
  [Captura de audio del sistema](setup/system-audio.md) para los pasos
  de loopback macOS / Windows.

### Salida de voz silenciosa / vacía

- **ElevenLabs sin clave** — la página Voice muestra un diálogo
  amigable pre-vuelo; si pasó, el archivo puede ser bytes vacíos.
  Verifica **Configuración → Servicio → ElevenLabs API key**.
- **Error de red Edge TTS** — Edge TTS requiere internet; si tu
  firewall bloquea `speech.platform.bing.com`, cambia a ElevenLabs,
  Google Cloud TTS, o **Piper TTS** (completamente offline).

### Diálogo "Piper voice not installed"

Las páginas Voice / Dubbing / Translate Text verifican pre-vuelo que
la voz Piper para tu idioma destino está en disco antes de que un
worker comience. Si no, verás un modal con un botón **Abrir
configuración**.

Para descargar la voz:

1. Haz clic en **Abrir configuración** en el diálogo (o abre
   **Configuración → Voz** manualmente).
2. Asegúrate de que **Método TTS** está en **Piper TTS**.
3. Haz clic en **Descargar voces ahora** para abrir el diálogo de la
   biblioteca de voces.
4. Encuentra la fila de tu idioma destino, luego haz clic en
   **Female voice** o **Male voice** al lado. Las voces son archivos
   ONNX de ~25–60 MB descargados desde HuggingFace; una vez por idioma.
5. Cierra el diálogo y vuelve a ejecutar tu tarea de
   traducción / voz / dub.

Si tu idioma destino no está en la lista, no tiene cobertura Piper —
el motor cae silenciosamente a Edge TTS al sintetizar, así que en
realidad no necesitas descargar nada. Los 13 idiomas sin voces Piper
hoy: bielorruso, bengalí, chino (tradicional), croata, estonio, hebreo,
japonés, jemer, coreano, lituano, malayo, mongol, tailandés.

La página **Traducción en vivo** es el único lugar que *no* mostrará
este diálogo — interrumpir un stream en vivo con un modal sería peor
que el fallback, así que los casos de voz faltante allí van
silenciosamente a Edge TTS.

## Errores de traducción de documentos

### La traducción PDF falla en una página específica

Los PDFs usan checkpointing por página — las páginas exitosas no se
rehacen. La página fallida loguea un stack en `app.log`; culpables comunes:

- La página es un **escaneo sin capa de texto** y OCR no está
  configurado. Configura **Configuración → OCR** (ver
  [Motores OCR](setup/ocr-engines.md)).
- La página contiene **layout matemático complejo** que el LLM
  destrozó. Prueba un modelo más fuerte (una variante Pro en lugar de Flash).

### La traducción Office rompe el formato

- **Formatos modernos** (`.docx`, `.xlsx`, `.pptx`) — el formato se
  preserva por run vía round-trip HTML. Si ves etiquetas `<b>` sueltas
  en la salida, el LLM no las cerró — vuelve a ejecutar con un modelo
  más fuerte.
- **Formatos antiguos** (`.doc`, `.xls`, `.ppt`) — activa
  **Configuración → Traducción → Auto-convert legacy** para fidelidad
  mucho mejor. El pipeline convierte a `.docx` primero, traduce,
  reconvierte.

### La cola de traducción se detiene a mitad de batch

Cierra la app y verifica la base de datos:

```bash
sqlite3 ~/.local/share/ai-translate/translator.db \
  "SELECT id, status, error_code, file_name FROM history WHERE status NOT IN ('Done', 'Failed') ORDER BY created_at DESC LIMIT 10;"
```

Filas `Translating` que no han sido tocadas en minutos significan
que un worker crasheó silenciosamente. Vuelve a lanzar la app de
escritorio — auto-reanuda tareas Pending / Translating al inicio.

## Problemas transversales

### Múltiples archivos a la vez se traducen silenciosamente como uno

Suelta un archivo a la vez, O verifica la columna **Files** en el
encabezado de la cola — debería mostrar el número que soltaste. El
tope de 100 archivos muestra una notificación cuando se excede.

### La barra lateral muestra un spinner para siempre

Indica que un worker todavía está marcado como en ejecución. Cierra
la app limpiamente (sin SIGKILL) — los hooks de limpieza autouse
resetean los flags. Si un SIGKILL dejó estado pegado, limpia los
workers DB manualmente:

```bash
sqlite3 ~/.local/share/ai-translate/translator.db \
  "UPDATE history SET status='Failed', error_code=99 WHERE status IN ('Pending', 'Translating');"
```

### ¿Dónde están los logs? {: #where-are-the-logs }

| OS | Ruta |
|---|---|
| **Linux** | `~/.local/state/log/ai-translate/app.log` |
| **macOS** | `~/Library/Logs/ai-translate/app.log` |
| **Windows** | `%LOCALAPPDATA%\ai-translate\logs\app.log` |

Los logs siempre capturan DEBUG+ sin importar la verbosidad de
consola. La salida de consola es INFO+ por defecto; pasa `--verbose`
al CLI para mirrorar el log de archivo completo en stdout.

## ¿Sigues atascado?

- Ver la [FAQ](faq.md) para preguntas a nivel de diseño.
- Reporta un issue en
  <https://github.com/cadic2603/ai-translate/issues> con: OS, versión
  Python, el comando que falla, la sección relevante de `app.log`, y
  una descripción de lo que esperabas.
