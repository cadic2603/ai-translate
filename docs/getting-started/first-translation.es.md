---
description: Traduce tu primer documento con AI Translate en 5 minutos — arrastra y suelta un PDF, elige un idioma de destino y descarga la copia traducida.
---

# Tu primera traducción

Una ejecución rápida de extremo a extremo — menos de 5 minutos una vez
hecha la configuración.

!!! abstract "Antes de empezar"
    Necesitas la [instalación](installation.md) terminada y una clave
    de API de LLM configurada. La capa gratuita de Google Gemini es
    suficiente para un primer intento.

## Traducir un documento Word

1. Lanza la aplicación de escritorio:

    ```bash
    uv run python -m src.main
    ```

2. Haz clic en **Traducir documento** en la barra lateral izquierda.

3. Arrastra cualquier archivo `.docx` a la zona de soltado — o haz clic
   en **Examinar** para elegir uno.

4. El archivo aparece en la cola. Elige un idioma de destino arriba:

    - Origen: `Detección automática` (por defecto — normalmente correcto)
    - Destino: p. ej. `Francés`, `Vietnamita`, `Japonés`, `Chino (Simplificado)`

5. Haz clic en **Traducir** (o pulsa `Ctrl+Enter`).

6. Observa la barra de progreso en la tabla de historial al final de la
   página. Cuando llegue al 100%, haz clic en **Abrir** en la fila para
   abrir el archivo traducido — guardado junto al original con el
   sufijo `_translated_<src>_<tgt>`.

## Lo que acaba de pasar

- Tu `.docx` se clonó en una carpeta de almacenamiento por tarea para
  que el original no se toque.
- El texto se extrajo, se agrupó en chunks aptos para LLM, se tradujo
  y luego se reinyectó en el documento con todo el formato conservado
  (negrita, cursiva, fuentes, colores, encabezados, notas al pie,
  hiperenlaces…).
- Se escribió una entrada de historial en una base SQLite para que
  puedas reabrir, reejecutar o retraducir el archivo más tarde.

## Prueba ahora las victorias rápidas

=== "Traducir texto plano"

    Entra en **Traducir texto** en la barra lateral. Pega cualquier
    cosa, elige un destino, pulsa Enter. Salida en streaming, intercambio
    de idiomas (`Ctrl+L`), modo edición, reproducción TTS.

=== "Generar subtítulos"

    **Generar subtítulo** — suelta un `.mp4`. Recibirás un `.srt` en el
    idioma de origen. (Para traducir _y_ doblar el vídeo, usa la página
    Doblaje en su lugar.)

=== "Traducción de micrófono en vivo"

    **Traducción en vivo** — elige micrófono o audio del sistema, elige
    destino, Iniciar. Una ventana overlay flotante muestra los subtítulos
    en tiempo real.

## A dónde ir después

- Mira el [índice de funciones](../index.md#headline-features) para ver qué hace cada página.
- Conecta [más proveedores](../setup/llm-providers.md) (endpoints personalizados, ElevenLabs, Soniox, Google Cloud).
- Prueba el [CLI](../cli.md) para ejecuciones batch / por script.
