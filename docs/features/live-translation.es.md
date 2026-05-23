---
description: "Traducción de habla en tiempo real: transcribe y traduce micrófono o audio del sistema en vivo con backends Whisper o Soniox."
---

# Traducción en vivo

Subtítulos y traducciones en tiempo real desde micrófono, audio del
sistema, o ambos — con una ventana overlay siempre arriba opcional
para que los subtítulos queden sobre lo que sea que estés viendo.

## Qué puedes hacer con esto

- **Subtítulos de reuniones en vivo** — subtitula una llamada Zoom /
  Meet / Teams en otro idioma sin entrar como bot traductor.
- **Aprendizaje de idioma en tiempo real** — subtitula contenido en
  idioma extranjero (películas, podcasts, conferencias) con tu idioma
  nativo como pista de traducción.
- **Subtítulos a nivel sistema** — captura audio del sistema para
  subtitular YouTube / Netflix / cualquier cosa que se reproduzca
  en tus altavoces.

## Lo que necesitas

- **FFmpeg** en `PATH` — ver [Configuración FFmpeg](../setup/ffmpeg.md).
- Un backend STT, uno de:
    - **faster-whisper** — local, offline, gratis, predeterminado
    - **Soniox** — cloud, de pago, diarización de oradores en tiempo real. Ver [Configuración Soniox](../setup/soniox.md).

- Para la **captura de audio del sistema**, el backend correcto por
  OS se auto-selecciona: Linux usa `parec` (PulseAudio / PipeWire),
  Windows usa WASAPI loopback nativo (sin software extra en la
  mayoría de casos), macOS usa `ffmpeg -f avfoundation` contra un
  dispositivo loopback virtual (BlackHole / Loopback / etc.). Aparece
  una bandera de advertencia en línea con enlaces de instalación
  clicables si falta algo. Ver
  [Configuración → Audio del sistema](../setup/system-audio.md) para
  instrucciones completas de instalación por OS.

## Paso a paso

1. Haz clic en **Traducción en vivo** en la barra lateral.
2. Configura una vez en **Configuración → Live**:

    - **Idioma origen** (idioma hablado)
    - **Idioma destino** (o déjalo vacío para sólo transcripción)
    - **Fuente de audio**: Micrófono / Audio del sistema / Ambos
    - **Método STT**: Whisper / Soniox

3. De vuelta en la página Live, haz clic en **Empezar a escuchar**
   (`Ctrl+Enter`).
4. La transcripción llena el panel principal tarjeta a tarjeta. La
   ventana **Overlay** flotante también muestra subtítulos (arrástrala
   donde quieras).
5. Haz clic en **Detener** para terminar la sesión.

## La vista de transcripción

Elige un layout en la barra de herramientas:

- **Apilado** — original + traducción, uno encima del otro
- **Lado a lado** — original a la izquierda, traducción a la derecha
- **Sólo original** / **Sólo traducción**

Los botones de la barra de herramientas usan sufijos **`ON`** / **`OFF`**
para estado a primera vista — por ejemplo `TTS ON`, `TTS OFF`,
`Timestamps ON`, `Overlay OFF`.

Activa/desactiva **timestamps** con el icono del reloj.
Activa/desactiva la **reproducción TTS** de las líneas traducidas
con el icono del altavoz. Honra tu selección en
**Configuración → Voz → Método TTS** — Edge TTS (predeterminado),
ElevenLabs, Google Cloud TTS, Gemini TTS, o **Piper TTS** (totalmente
offline). Con Piper seleccionado, las voces por idioma faltantes
**caen silenciosamente a Edge TTS** en mitad del flujo — no hay
pre-flight modal en esta página, ya que bloquear el flujo en vivo
con un diálogo de descarga sería peor que el fallback.

## La ventana overlay

Una ventana herramienta arrastrable, redimensionable y siempre arriba.
Atajos:

| Atajo | Acción |
|---|---|
| `Ctrl+[` / `Ctrl+]` | Disminuir / aumentar opacidad |
| `Ctrl+Flecha` | Mover el overlay |
| `Ctrl+0` / `Ctrl+9` | Agrandar / encoger |

Posición, tamaño, opacidad y tamaño de fuente persisten entre sesiones.

### Sincronización en vivo con la configuración

Los controles de tamaño de fuente y opacidad funcionan en ambos
sentidos: arrastrar el control **Tamaño de fuente** u **Opacidad**
en **Configuración → Traducción en vivo → Configuración del
overlay** actualiza el overlay abierto en tiempo real, y a la
inversa, pulsar `+` / `-` / `Ctrl+[` / `Ctrl+]` dentro del overlay
actualiza los controles en Configuración. No requiere reiniciar
el overlay.

### Marcador de posición de estado vacío

Antes de capturar audio el overlay muestra un marcador
("Pulse Iniciar..." inactivo / "Escuchando..." una vez pulsado
Iniciar) que refleja el estado vacío de la ventana principal — el
cambio se mantiene sincronizado con la insignia de estado en
ejecución. El marcador se adapta al ancho × alto actual del
overlay y permanece legible en cualquier tamaño de ventana.

### Modo de subtítulos mínimos

La casilla **Mostrar subtítulos mínimos** en Configuración →
Traducción en vivo → Configuración del overlay oculta las
etiquetas de marca de tiempo y orador en el overlay mientras se
mantienen visibles en la ventana principal. Útil cuando se
comparte el overlay con una audiencia (modo presentador /
pantalla compartida) pero desea mantener los metadatos completos
en su vista de trabajo. La opción es solo del overlay — no cambia
su preferencia de "Etiquetas de orador" para la ventana principal.

## Guardar la transcripción

Haz clic en **Guardar transcripción** para exportar la sesión a un
archivo `.txt` con timestamps, oradores, líneas originales y
líneas traducidas.

## Eligiendo backend STT

| Backend | Mejor para | Coste | Latencia |
|---|---|---|---|
| **Whisper** (local) | Offline, sensible a privacidad | Gratis | Media (~1 s tras fin de oración) |
| **Soniox** | Reuniones multi-orador | De pago (~$0.005 / min) | Baja (tiempo real) |

## Advertencias

!!! warning "Selección de micrófono"
    La entrada de micrófono siempre usa el **dispositivo predeterminado
    del OS** — no hay selector en la app (sounddevice expone demasiados
    plugins ALSA virtuales para ser útil, y el OS ya posee la UI del
    micrófono predeterminado). Configura tu micrófono preferido en la
    configuración de sonido del OS antes de empezar.

!!! warning "Backpressure TTS"
    La cola TTS está limitada a las 3 oraciones más recientes — el
    audio en cola más antiguo se descarta si la síntesis se queda
    atrás. Esto mantiene la reproducción hablada cerca de los
    subtítulos en pantalla.

!!! tip "ElevenLabs sin clave"
    Si has puesto el método TTS en ElevenLabs pero no se ha configurado
    una clave de API, la página Live cae automáticamente a Edge TTS
    y anuncia el fallback en la etiqueta de estado.

## Atajos

| Atajo | Acción |
|---|---|
| `Ctrl+Enter` | Iniciar / Detener |
| `Ctrl+K` | Limpiar log (con confirmación) |
| `Ctrl+[` / `Ctrl+]` | Ajustar opacidad del overlay |
