---
description: Conecta ElevenLabs a AI Translate para TTS neuronal de alta calidad — genera voces en off en más de 30 idiomas con habla realista y expresiva.
---

# ElevenLabs (TTS)

Síntesis de voz neuronal premium. Usado por las páginas
**[Generar voz](../features/generate-voice.md)**,
**[Doblaje](../features/dubbing.md)** y
**[Traducción en vivo](../features/live-translation.md)** cuando eliges
ElevenLabs como método TTS.

## Obtener una clave API

1. Regístrate en <https://elevenlabs.io>
2. Abre <https://elevenlabs.io/app/settings/api-keys>
3. Haz clic en **+ Create New Key**, nómbrala (p. ej. "ai-translate"),
   copia la clave (parece `sk_...`)

La capa gratuita da ~10.000 caracteres / mes, suficiente para probar.
El uso en producción empieza alrededor de 5 $/mes.

## Configurar en la app

En **Configuración → Servicio**:

1. Pega la clave en **Clave API de ElevenLabs** → **Guardar**
2. Introduce tu **ID de voz** preferido en **ID de voz** (encuentra
   IDs en <https://elevenlabs.io/app/voice-lab>; copia el ID de la
   URL de una voz). Déjalo en blanco para que ElevenLabs elija uno
   por defecto.

En **Configuración → Voz**:

1. Establece **Método TTS** en **ElevenLabs**
2. Elige el **Modelo ElevenLabs**:

    | Modelo | Mejor para |
    |---|---|
    | `eleven_multilingual_v2` (predeterminado) | Uso general, latencia/calidad equilibradas |
    | `eleven_v3` | Calidad máxima (usar para doblajes de producción) |
    | `eleven_flash_v2_5` | Latencia más baja (usar para Traducción en vivo) |

## Qué alimenta

| Página | Usa ElevenLabs cuando |
|---|---|
| **Generar voz** | Quieres voces en off de calidad premium desde archivos de subtítulos |
| **Doblaje** | Quieres una pista de doblaje de alta calidad en un vídeo traducido |
| **Traducción en vivo** | Quieres reproducción hablada de subtítulos traducidos en tiempo real |

## Clonación de voz

ElevenLabs soporta clonación de voz personalizada (plan de pago). Una
vez que hayas clonado una voz en el sitio de ElevenLabs, pega su ID
de voz en **Configuración → Servicio → ID de voz** y el pipeline de
doblaje / generación de voz lo usará.

## Advertencias

!!! warning "Comprobación pre-flight"
    Las páginas Voz / Doblaje comprueban que tu clave API ElevenLabs
    esté establecida *antes* de empezar el trabajo. Si falta,
    obtendrás un diálogo amigable que te apunta a Configuración, no
    una tarea a medio ejecutar.

!!! tip "El modo Live cae automáticamente"
    En la página **Traducción en vivo**, si has seleccionado
    ElevenLabs pero no has configurado una clave, la app cae a
    **Edge TTS** (gratis) y anuncia el fallback en la etiqueta de
    estado para que puedas arreglarlo cuando convenga.

!!! info "FFmpeg sigue siendo requerido"
    ElevenLabs devuelve bytes de audio; la app sigue usando FFmpeg
    para convertir entre formatos y combinar clips con timing en un
    archivo. Ver [Configuración FFmpeg](ffmpeg.md).

## Errores comunes

| Error | Causa probable |
|---|---|
| `AUTH_ERROR` | Clave API errónea / caducada. Vuelve a pegar en Configuración → Servicio. |
| `QUOTA_ERROR` | Límite de caracteres de la capa gratuita alcanzado, o plan de pago agotado. |
| `MODEL_NOT_FOUND` | El modelo ElevenLabs seleccionado ya no está disponible; elige otro en Configuración → Voz. |
