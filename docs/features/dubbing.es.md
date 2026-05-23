---
description: "Dobla videos de extremo a extremo: transcribe el audio, traduce los subtítulos, sintetiza el habla en el idioma destino y mézclalo de nuevo en el video original."
---

# Doblaje de video

Pipeline completo **STT → Traducir → TTS → Mix** que produce un
archivo de video en otro idioma con la pista de voz reemplazada. El
audio original se descarta; la nueva pista de doblaje está sincronizada
con los subtítulos.

## Lo que necesitas

- **FFmpeg** en `PATH` — ver [Configuración FFmpeg](../setup/ffmpeg.md).
- Un backend STT (por defecto Whisper local, sin configuración)
- Un backend TTS — Edge TTS (predeterminado), ElevenLabs, Google
  Cloud TTS, Gemini TTS, o **Piper TTS** (totalmente offline; voces
  por idioma descargadas una vez vía **Configuración → Voz → Piper
  TTS → Descargar voces ahora**)
- Un **LLM** configurado para el paso de traducción

## Paso a paso

1. Haz clic en **Doblaje** en la barra lateral.
2. Suelta uno o varios archivos de video (`.mp4`, `.webm`, `.mkv`,
   `.avi`, `.mov`, `.wmv`).
3. Elige el **Idioma origen** (el idioma *hablado* en el video) y
   el **Idioma destino** al que doblar.
4. Haz clic en **Iniciar doblaje** (`Ctrl+Enter`).
5. Observa el progreso por tarea en la tabla de historial. Pasa por
   cuatro fases:

| Fase | Rango | Qué pasa |
|---|---|---|
| **STT** | 5–25% | Transcribiendo el audio origen |
| **Traducir** | 25–50% | LLM traduciendo cada línea de subtítulo |
| **TTS** | 50–90% | Sintetizando voz idioma-destino para cada línea |
| **Mix** | 90–100% | FFmpeg reemplaza la pista de audio |

6. Cuando termine, **Abre** la fila para reproducir el video doblado.

## Salidas

Por cada video de entrada obtienes cuatro archivos en el directorio
de salida:

```
movie.mp4
movie_dubbed_en_fr.mp4              ← video doblado
movie_subtitle_en.srt               ← subtítulo idioma original
movie_subtitle_fr.srt               ← subtítulo traducido
movie_voice_fr.mp3                  ← pista de voz sintetizada
```

## Reanudar una ejecución pausada / colapsada

El pipeline hace checkpoint después de cada fase. Si pulsas **Detener**,
cierras la app o crash, pulsar **Continuar** en la fila reanuda desde
la última fase completada — no vuelves a pagar por STT o traducción
si ya estaban hechos.

Clic derecho en una entrada Done / Failed para estas opciones:

- **Continuar** — reanuda desde el último checkpoint sin re-prompt.
- **Re-doblar** — reabre el selector de idioma; si eliges un nuevo
  destino, los checkpoints traducir y TTS se descartan (no vuelves a
  pagar por STT). Elegir el mismo destino efectivamente reejecuta
  desde el último checkpoint, igual que Continuar.
- **Abrir** — reproduce el video doblado.

## Advertencias

!!! warning "Sincronización labial"
    El doblaje coincide con los *timestamps* del audio origen, no con
    los movimientos labiales. Las líneas traducidas mucho más largas
    que el original sonarán apresuradas; las mucho más cortas dejarán
    silencio. Para doblaje profesional usualmente se re-temporiza
    manualmente después de esta pasada — es una característica futura.

!!! tip "Verificaciones pre-flight"
    La página valida FFmpeg + las claves de tu backend TTS antes de
    empezar. Clave faltante → diálogo amigable, no doblaje a medias.
    Con **Piper TTS** seleccionado, también verifica que la voz Piper
    por idioma esté en disco; voz faltante → diálogo modal con botón
    **Abrir Configuración** que te lleva a la biblioteca de voces,
    así no quemas tiempo de STT + traducción para fallar en el paso TTS.

!!! tip "Cambiar idioma destino"
    En un re-target el pipeline descarta los checkpoints traducir +
    TTS (su contenido ya no es válido para el nuevo idioma) pero
    mantiene el checkpoint STT — ahorras el coste de transcripción.

## Atajos

| Atajo | Acción |
|---|---|
| `Ctrl+Enter` | Iniciar doblaje |
| `Ctrl+O` | Navegar |
| `Ctrl+F` | Foco en búsqueda de historial |
| `Ctrl+P` | Pausar la cola activa |
| `Ctrl+G` | Continuar (reanudar) la cola activa |

`Ctrl+P` / `Ctrl+G` se suprimen cuando un campo texto tiene el foco,
así no chocan con la escritura.
