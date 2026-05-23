---
description: Convierte subtítulos en audio hablado con Edge TTS, ElevenLabs, Google Cloud TTS, Gemini TTS o Piper TTS offline — preserva el timing SRT para generación de voz con calidad de doblaje.
---

# Generar voz (TTS)

Sintetiza archivos de subtítulos (con timing) o texto arbitrario a
audio MP3 / WAV. Cinco backends TTS: Edge TTS (gratis), ElevenLabs
(alta calidad), Google Cloud TTS, Gemini TTS (capa gratuita) y
Piper TTS (offline).

## Lo que necesitas

- **FFmpeg** en `PATH` — ver [Configuración FFmpeg](../setup/ffmpeg.md).
- Un backend TTS, uno de:
    - **Edge TTS** — gratis, sin clave, predeterminado. Usa las voces
      cloud de Microsoft Edge.
    - **ElevenLabs** — de pago, máxima calidad. Ver [Configuración ElevenLabs](../setup/elevenlabs.md).
    - **Google Cloud TTS** — de pago, muy bueno. Ver [Configuración Google Cloud](../setup/google-cloud.md).
    - **Gemini TTS** — capa gratuita, voces predefinidas naturales.
      Reutiliza tu clave API de Gemini existente de la pestaña LLM
      — sin configuración extra.
    - **Piper TTS** — TTS neuronal totalmente offline. Sin clave de
      API, sin llamadas de red — las voces son archivos ONNX de
      ~25–60 MB descargados una vez vía **Configuración → Voz → Piper
      TTS → Descargar voces ahora**. 32 de los 45 idiomas de la app
      tienen una voz Piper hoy; los idiomas sin cobertura Piper caen
      silenciosamente a Edge TTS al momento de la síntesis.

## Paso a paso

1. Haz clic en **Generar voz** en la barra lateral.
2. Suelta uno o más archivos de subtítulos `.srt` / `.vtt` /
   `.ass` / `.ssa`.
3. Elige el **Idioma** (auto-detectado del nombre de archivo del
   subtítulo cuando es posible — p. ej. `_translated_en_es.srt` se
   detecta como español).
4. Elige el **Género de voz** — `Femenino` o `Masculino`.
5. Elige el **Formato de salida** — `.mp3` (predeterminado) o `.wav`.
6. Haz clic en **Generar** (o `Ctrl+Enter`).
7. **Abre** la fila cuando termine — se reproduce en tu app de audio
   predeterminada.

## Salida

Obtienes un único archivo de audio con las pistas de voz colocadas en
el timestamp de cada subtítulo. Los huecos silenciosos rellenan el
tiempo entre cues para que el audio se mantenga sincronizado con el
timing original.

## Eligiendo un backend TTS

| Backend | Coste | Voces | Notas |
|---|---|---|---|
| **Edge TTS** | Gratis | Cientos, todos los idiomas mayores | Predeterminado. Sin configuración. |
| **ElevenLabs** | De pago (~$5/mes capa de entrada) | Voces neuronales premium, clonación de voz | Máxima calidad. ID de voz se establece en Configuración → Servicio. |
| **Google Cloud TTS** | De pago (~$4/M chars; 1 M gratis / mes) | Voces WaveNet / Studio en 50+ idiomas | Voces WaveNet fuertes para idiomas europeos. Por defecto el servidor elige una voz según idioma + género. |
| **Gemini TTS** | Capa gratuita (cuotas de Developer API aplican) | Voces predefinidas naturales en 24+ idiomas — `Kore` (femenino predet.) / `Puck` (masculino predet.) | Reutiliza tu clave API de Gemini de la pestaña LLM. Salida por llamada limitada a ~30 s; los textos largos se cortan automáticamente en límites de oración. |
| **Piper TTS** | Gratis, **offline** | Voces neuronales en 32 de los 45 idiomas de la app | Sin clave, sin red. Voz por idioma descargada bajo demanda desde **Configuración → Voz → Piper TTS → Descargar voces ahora** (~25–60 MB cada una). El pre-flight atrapa una voz faltante antes de que empiece el trabajo. |

Cambia en **Configuración → Voz → Método TTS**.

## Especificidades de Piper TTS

Piper es el único backend TTS totalmente offline en la app. Algunas
cosas a saber:

- **Diálogo de biblioteca de voces** — abre vía **Configuración → Voz
  → Piper TTS → Descargar voces ahora**. Cada fila de idioma muestra
  un botón de descarga `Voz femenina` y / o `Voz masculina` (algunos
  idiomas son de un solo género). Las voces vienen del catálogo
  HuggingFace [rhasspy/piper-voices](https://huggingface.co/rhasspy/piper-voices).
- **Cobertura** — 32 de los 45 idiomas de la app tienen una voz
  Piper. Los 13 sin cobertura (bielorruso, bengalí, chino
  (tradicional), croata, estonio, hebreo, japonés, jemer, coreano,
  lituano, malayo, mongol, tailandés) caen silenciosamente a Edge
  TTS al momento de la síntesis, así que la síntesis nunca falla
  duro en una voz faltante.
- **Resolución de género** — cuando eliges `Femenino`, el motor
  primero intenta la voz femenina para ese idioma; si solo existe
  una voz masculina, la usa en su lugar (y viceversa). Registrado
  a nivel INFO.
- **Puerta pre-flight** — antes de que comience una ejecución de Voz,
  la página verifica que la voz Piper por idioma esté en disco. Si
  falta, obtienes un diálogo modal con un botón **Abrir
  Configuración** que te lleva directamente a la biblioteca de voces
  para descargarla sin perder tu cola.

## Especificidades de Gemini TTS

Gemini TTS usa `gemini-2.5-flash-preview-tts` vía la Developer API.
Algunas cosas a saber:

- **Selección de voz** es por género hoy — Femenino mapea a `Kore`,
  Masculino a `Puck`. Ambas son voces claras y neutras que funcionan
  a través de idiomas sin sonar demasiado caracterizadas.
- **Tope de longitud de salida** — cada llamada API Gemini devuelve
  como máximo ~30 s de habla. La app trocea texto de entrada bajo
  `_GEMINI_TTS_MAX_BYTES` (~2000 bytes ≈ 30 s) en límites de oración,
  luego concatena los trozos vía FFmpeg. No te encontrarás con
  truncado en texto de subtítulo normal.
- **Formato de audio** — Gemini emite PCM crudo a 24 kHz mono s16le;
  la app transcodifica por trozo a MP3 (o WAV si lo elegiste) para
  que el archivo final coincida con tu formato de salida seleccionado.
- **Vertex AI todavía no es compatible para TTS** — incluso si tu
  pestaña LLM está configurada para Vertex, Gemini TTS aún necesita
  una clave API de Developer. La app lanza `AUTH_ERROR` por adelantado
  si falta.

## Modelos ElevenLabs

Tres modelos están expuestos:

| Modelo | Latencia | Calidad | Usar para |
|---|---|---|---|
| `eleven_multilingual_v2` (predet.) | Media | Alta | TTS general |
| `eleven_v3` | Media | Máxima | Studio / producción |
| `eleven_flash_v2_5` | Baja | Buena | Tiempo real / modo Live |

Configura en **Configuración → Voz → Modelo ElevenLabs**.

## Consejos

!!! tip "Regenerar"
    Clic derecho en una fila → **Regenerar** para cambiar género de
    voz / método TTS / formato sin reejecutar la traducción.

!!! tip "Comprobaciones pre-flight"
    La página valida la clave API de ElevenLabs (cuando se selecciona)
    y la disponibilidad de FFmpeg antes de empezar. Verás un diálogo
    amigable si algo falta.

!!! warning "Stop es atómico"
    Pulsa **Stop** durante la síntesis y no obtendrás un MP3 medio
    escrito en el directorio de salida — el archivo se escribe en una
    ubicación temporal primero, luego se mueve en su lugar solo en
    caso de éxito.

## Atajos

| Atajo | Acción |
|---|---|
| `Ctrl+Enter` | Generar |
| `Ctrl+O` | Examinar |
| `Ctrl+F` | Enfocar búsqueda de historial |
