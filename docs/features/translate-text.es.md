---
description: Traduce instantáneamente fragmentos de texto a más de 45 idiomas con AI Translate — pega, escribe o habla; soporta modo edición, reproducción TTS y intercambio de idiomas.
---

# Traducir texto

Traducción LLM instantánea con auto-detección, intercambio de idiomas,
salida en streaming y reproducción TTS. Mejor para fragmentos cortos,
uso tipo chat y prueba de tu configuración LLM.

## Paso a paso

1. Haz clic en **Traducir texto** en la barra lateral.
2. Escribe o pega tu texto fuente en el panel izquierdo.
3. El idioma **Origen** se auto-detecta mientras escribes (con `langdetect`).
4. Elige un idioma **Destino** del menú desplegable derecho.
5. Haz clic en **Traducir** (o pulsa `Ctrl+Enter`).
6. La traducción aparece en streaming token por token en el panel derecho.

## Lo que obtienes

- **Salida en streaming** — la traducción aparece a medida que el LLM
  la genera, sin esperar la respuesta completa.
- **Auto-detección de fuente** — el selector de fuente se actualiza en
  tiempo real. Haz clic para anular.
- **Modo edición** — haz clic en el panel derecho para editar la
  traducción manualmente. Pulsa `Esc` para cancelar una traducción
  en vuelo; púlsalo de nuevo para salir del modo edición.
- **Reutilización del historial** — cada traducción se guarda. Haz clic
  en una entrada en el panel Historial de traducción de texto debajo
  para recargar ambos paneles; las ediciones actualizan la entrada
  original en lugar de crear un duplicado.
- **Reproducción TTS** — haz clic en **Escuchar** junto a cualquiera
  de los paneles para oírlo en voz alta. Honra tu selección en
  **Configuración → Voz → Método TTS** — Edge TTS (predeterminado),
  ElevenLabs, Google Cloud TTS, Gemini TTS o **Piper TTS**
  (totalmente offline). Con Piper seleccionado, el botón Escuchar
  ejecuta el mismo pre-flight que la página Voz: una voz por idioma
  faltante muestra un diálogo modal con un botón **Abrir Configuración**
  para descargarla. Los hits de caché omiten el pre-flight por completo.
- **Selector de modelo por funcionalidad** — cuando hay más de un LLM
  configurado, un menú desplegable te permite elegir un modelo Flash
  rápido por velocidad o un modelo Pro más pesado por calidad,
  sólo para esta página.

## Atajos

| Atajo | Acción |
|---|---|
| `Ctrl+Enter` | Traducir |
| `Ctrl+L` | Intercambiar origen ↔ destino |
| `Esc` | Cancelar traducción en vuelo, o salir del modo edición |
| `Ctrl+F` | Foco en búsqueda de historial |

## Trucos

!!! tip "Idiomas RTL"
    Las traducciones a **árabe**, **hebreo** o **persa** se renderizan
    automáticamente de derecha a izquierda en el panel de salida. El
    mismo manejo RTL se traslada a la salida de archivo en todos los
    formatos de la página [Traducir documento](translate-document.md)
    (PDF, DOCX, PPTX, XLSX, ODF, RTF, HTML, EPUB, ASS/SSA), y el persa
    recibe una voz `fa-IR` nativa para reproducción Edge TTS.

!!! tip "Caché del botón Escuchar"
    La primera vez que pulsas Escuchar para un par (texto, idioma)
    dado, el audio se sintetiza y cachea en disco. Las reproducciones
    siguientes son instantáneas. La caché se borra al inicio de la
    aplicación, así cada sesión empieza limpia.

!!! tip "Dónde van las claves"
    La página Traducir texto lee las mismas entradas de keychain que
    el resto de la aplicación — ver
    [Proveedores LLM](../setup/llm-providers.md).
