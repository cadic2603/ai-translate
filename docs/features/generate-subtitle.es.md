---
description: Genera subtítulos SRT, VTT, ASS o SSA desde cualquier audio o video — usa Whisper o Google Cloud Speech-to-Text para transcripción de alta calidad.
---

# Generar subtítulo (STT)

Transcribe audio o video en subtítulos con tiempos. Capta el habla y
emite SRT / VTT / ASS / SSA — con traducción opcional en la misma pasada.

## Lo que necesitas

- **FFmpeg** en `PATH` para decodificación audio/video — ver [Configuración FFmpeg](../setup/ffmpeg.md).
- Un backend de transcripción, uno de:
    - **faster-whisper** — local, offline, gratis (predeterminado; sin configuración necesaria)
    - **Google Cloud Speech-to-Text** — cloud, de pago, más preciso en audio ruidoso. Ver [Configuración Google Cloud](../setup/google-cloud.md).
    - **Soniox** — cloud, de pago, en tiempo real y diarización de oradores. Ver [Configuración Soniox](../setup/soniox.md).

## Paso a paso

1. Haz clic en **Generar subtítulo** en la barra lateral.
2. Suelta uno o varios archivos audio / video (`.mp3`, `.wav`, `.m4a`,
   `.flac`, `.ogg`, `.aac`, `.wma`, `.mp4`, `.webm`, `.mkv`, `.avi`,
   `.mov`, `.wmv`).
3. Elige el **Idioma origen** (el idioma *hablado* en el audio) —
   deja en `Detección automática` para que Whisper lo descubra.
4. Elige un **Idioma destino** — elige `Sin traducción` para una
   transcripción simple, o cualquiera de los 45 idiomas soportados
   para que se traduzca en la misma pasada.
5. Elige el **Formato de salida** (SRT / VTT / ASS / SSA).
6. Haz clic en **Generar** (o `Ctrl+Enter`).
7. Observa la cola. **Abre** la fila cuando termine.

## Elección de formato

| Formato | Mejor para |
|---|---|
| **SRT** | Universal — casi todos los reproductores lo soportan |
| **VTT** | Elementos `<track>` de HTML5 `<video>` |
| **ASS / SSA** | Karaoke, subtítulos con estilo, flujos fansub |

Los cuatro formatos round-trip por el mismo parser, así que puedes
cambiar el formato de salida en una re-traducción sin perder el timing.

## Tamaño del modelo Whisper

Cambia en **Configuración → Subtítulo**:

| Modelo | Tamaño | Velocidad | Precisión |
|---|---|---|---|
| `tiny` | ~75 MB | muy rápido | baja |
| `base` (predeterminado) | ~150 MB | rápido | decente |
| `small` | ~500 MB | medio | buena |
| `medium` | ~1.5 GB | lento | alta |
| `large` | ~3 GB | muy lento | mejor |

Los modelos se descargan en el primer uso y se cachean localmente.
En una conexión lenta la primera ejecución parece larga; las siguientes
son rápidas.

## Comparación de métodos STT

| Backend | Coste | ¿Online? | Diarización de oradores | Idiomas |
|---|---|---|---|---|
| **Whisper** (local) | Gratis | No | No | 99 |
| **Google Cloud STT** | De pago | Sí | Sí (modelo `latest_long`) | 125+ |
| **Soniox** | De pago | Sí | Sí (etiquetas por token) | 60+ |

Cambia en **Configuración → Subtítulo → Método STT**.

## Trucos

- **Botón Detener** — interrumpe un batch en vuelo. Los archivos en
  cola detrás del activo permanecen en cola; puedes reanudar más tarde.
- **Re-generar** — clic derecho en una entrada Done para reejecutar
  con formato / idioma / método STT diferente.
- **Audio largo** — Whisper maneja horas de audio bien; presupuesta
  ~1 minuto de procesamiento por minuto de audio en CPU con modelo `base`.

## Atajos

| Atajo | Acción |
|---|---|
| `Ctrl+Enter` | Generar |
| `Ctrl+O` | Navegar |
| `Ctrl+F` | Foco en búsqueda de historial |
