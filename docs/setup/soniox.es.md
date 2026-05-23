---
description: Configura Soniox para transcripción de voz en tiempo real en la página Live de AI Translate — soporta diarización de hablantes, términos de glosario y traducción en vivo.
---

# Soniox (STT)

Transcripción de voz en tiempo real vía la API WebSocket de Soniox.
Usado por las páginas **[Subtítulo](../features/generate-subtitle.md)** y
**[Traducción en vivo](../features/live-translation.md)** cuando eliges
Soniox como método STT.

## Por qué Soniox

- **Tiempo real** — los tokens llegan mientras el hablante todavía
  habla.
- **Diarización de hablantes** — etiquetas de hablante por token
  (p. ej. _Hablante 1: Hola…_).
- **Traducción en flujo** — Soniox puede traducir mientras
  transcribe, ahorrando un viaje LLM extra.
- **Multi-idioma** — auto-detecta el idioma origen incluso en mitad
  del flujo.

## Obtener una clave API

1. Regístrate en <https://console.soniox.com>
2. Abre **API keys** → **Create new API key**
3. Cópiala (parece `Bearer ...`; copia solo el token sin el prefijo
   `Bearer `).

El precio se cobra por minuto de audio (~$0.005 / minuto al momento
de escribir) — ver <https://soniox.com/pricing>.

## Configurar en la app

En **Configuración → Servicio**:

1. Pega la clave en **Clave API Soniox** → **Guardar**

En **Configuración → Live** *(para traducción en vivo)* o
**Configuración → Subtítulo** *(para generación de subtítulos)*:

1. Establece **Método STT** en **Soniox**

## Qué alimenta

| Página | Usa Soniox cuando |
|---|---|
| **Subtítulo** | Grabaciones multi-hablante (entrevistas, paneles, reuniones) donde quieres etiquetas de hablantes en el SRT |
| **Traducción en vivo** | Subtitulado de reuniones en tiempo real, especialmente con múltiples hablantes |

## Términos de glosario

El WebSocket de Soniox acepta un glosario de términos para sesgar el
reconocimiento. La app reenvía automáticamente tus entradas de
glosario activas — nombres de marcas / nombres propios / jerga se
reconocen más fiablemente.

## Advertencias

!!! warning "Solo en línea"
    Soniox es solo cloud; si tu audio es sensible (médico, legal),
    usa Whisper (local) en su lugar.

!!! info "Reconexión"
    El WebSocket se reconecta automáticamente en fallos transitorios
    con backoff exponencial. Las sesiones largas se mantienen
    conectadas a través de breves cortes de red.

## Errores comunes

| Error | Causa probable |
|---|---|
| `AUTH_ERROR` | Clave API errónea / caducada. Vuelve a pegar en Configuración → Servicio. |
| `QUOTA_ERROR` | Límite del plan superado. |
| `CONNECTION_ERROR` | Red bloqueada / firewall. Inténtalo desde otra red. |
