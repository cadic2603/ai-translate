---
description: "Preguntas comunes sobre AI Translate: formatos de archivo soportados, funciones gratuitas vs de pago, uso offline, opciones de proveedor LLM y selección de motor OCR."
---

# Preguntas frecuentes

## General

### ¿Funciona offline?

Mayormente sí. Específicamente:

- **La traducción** necesita un LLM. La API gratuita de Gemini es online;
  **Ollama / LM Studio local** a través de la configuración de Proveedor
  Personalizado es completamente offline.
- **OCR** con **Tesseract** o **EasyOCR** es offline.
- **STT** con **Whisper** (por defecto) es offline.
- **TTS** con **Edge TTS** (por defecto) es online; **ElevenLabs** /
  **Google Cloud TTS** / **Gemini TTS** son online (gratuitos o de pago);
  **Piper TTS** es TTS neural completamente offline — sin clave, sin
  llamadas de red una vez que has descargado la voz por idioma (archivo
  ONNX de ~25–60 MB) vía **Configuración → Voz → Piper TTS → Descargar
  voces ahora**.

Para una configuración totalmente air-gapped: Proveedor Personalizado →
LLM local, Tesseract o EasyOCR para OCR, Whisper para STT, y Piper TTS
para salida de voz.

### ¿Dónde se guardan mis archivos traducidos?

Junto al original por defecto, con un sufijo `_translated_<src>_<tgt>`
(p. ej. `report_translated_en_fr.docx`). Sobrescribe por función en
**Configuración → General → Ruta de almacenamiento de traducciones**.

### ¿Dónde se almacenan mis configuraciones?

Archivo INI en:

| OS | Ruta |
|---|---|
| **Linux** | `~/.config/ai-translate/settings.ini` |
| **macOS** | `~/Library/Preferences/ai-translate/settings.ini` |
| **Windows** | `%APPDATA%\ai-translate\settings.ini` |

Las claves de API viven en el keychain del OS (no en el INI). El
historial de traducción vive en una BD SQLite en el directorio de datos.

### ¿Cómo se manejan mis datos?

- **Local-first** — el texto nunca abandona tu máquina a menos que
  estés llamando a un servicio LLM / OCR / STT / TTS en la nube.
- **Sin telemetría** — la app no llama a casa. La única solicitud
  saliente que la app hace por sí misma es la verificación opcional
  de actualización de GitHub Releases (toggle en
  **Configuración → General**); los backends de la nube solo llaman
  a sus respectivos vendedores.
- **Claves de API** — almacenadas en el keychain de tu OS. El fallback
  de keychain de la app de escritorio es un INI en texto plano cuando
  no hay daemon de keychain disponible.

### ¿Puedo traducir un Google Doc / página de Notion?

No directamente. Exporta a `.docx` primero, traduce, luego importa el
archivo traducido de vuelta. Igual para Notion (exportar como Markdown
/ HTML), Confluence (exportar como `.docx`), etc.

## Eligiendo modelos / motores

### ¿Qué modelo LLM debería usar?

Para la mayoría de usuarios:

- **Cualquier variante Gemini Flash** — capa gratuita, rápido,
  sorprendentemente bueno. Úsalo para traducciones diarias. Los nombres
  parecen `gemini-2.5-flash`, `gemini-3-flash-preview`, etc.,
  dependiendo de qué esté disponible.
- **Cualquier variante Gemini Pro** — pago por token, mayor calidad.
  Úsalo para documentos importantes (legales, técnicos, de cara al cliente).
- **Ollama local** con un modelo 7B-13B — cuando necesites offline / privacidad.

El selector de modelo por función significa que puedes usar un modelo
rápido para traducción tipo chat y reservar el caro para documentos.

### ¿Qué motor OCR debería usar?

- **Tesseract** para texto impreso limpio en scripts principales.
  Gratis, offline, rápido.
- **EasyOCR** para scripts no latinos (especialmente CJK) e imágenes
  más ruidosas.
- **Google Cloud Vision** para escritura a mano, scripts mixtos, y la
  mayor precisión cuando puedas pagar.

### ¿Qué método STT debería usar?

- **Whisper local** para offline / privacidad.
- **Soniox** para grabaciones multi-orador — las etiquetas de orador
  hacen round-trip a tu SRT.
- **Google Cloud STT** para audio telefónico / médico (sus modelos de
  dominio son buenos).
- **Gemini Live** para traducción speech-to-speech en tiempo real.

### ¿Qué backend TTS?

- **Edge TTS** para voces gratuitas de alta calidad.
- **ElevenLabs** para voces premium / de marca / clonadas.
- **Google Cloud TTS** para voces WaveNet en idiomas long-tail donde
  Edge tiene cobertura escasa.
- **Gemini TTS** para voces prebuilt naturales gratuitas reutilizando
  tu clave de API Gemini existente.
- **Piper TTS** cuando necesites salida de voz **offline / air-gapped**.
  Compromiso: cada idioma necesita una descarga única de voz de
  ~25–60 MB vía **Configuración → Voz → Piper TTS → Descargar voces
  ahora**, y 13 de los 45 idiomas de la app no tienen voz Piper (esos
  caen silenciosamente a Edge TTS).

## Flujo de trabajo

### ¿Cómo traduzco una carpeta entera?

Suelta la carpeta en la zona de soltado de **Traducir documento**. Los
archivos soportados dentro (recursivamente) se ponen en cola; todo lo
demás se omite silenciosamente. Hay un tope de 100 archivos por
soltada; batches más grandes → divídelos en múltiples soltadas.

### ¿Puedo pausar y reanudar traducciones?

Sí. Cierra la app en cualquier momento — las tareas Pending /
Translating se reanudan en el próximo lanzamiento. El checkpointing
por tarea significa que la página 47 de 100 de un PDF no se rehace
cuando reanudas.

### ¿Puedo editar una traducción a mano?

Para **Traducir texto** — sí, haz clic en el panel derecho y escribe.
La edición se guarda automáticamente en el registro de historial de la
entrada.

Para **Traducir documento** — abre el archivo traducido en tu editor
habitual (Word, LibreOffice, etc.) y edita ahí. La app no hace
round-trip de las ediciones de vuelta al historial.

### ¿Puedo traducir en bloque una lista de cadenas?

Usa el CLI:

```bash
ait *.txt --target French
```

O para cadenas in-process (p. ej. cadenas UI extraídas del código),
llama a la herramienta MCP `translate_text` con una lista, o usa la
API Python directamente:

```python
from src.core.llm_engine import translate_text
out = translate_text(texts=["Hello", "World"], target_lang="French")
```

## Glosario

### ¿Por qué el LLM no usa mi glosario?

Tres cosas que verificar:

1. El conjunto está **activo** (checkbox marcado).
2. El término fuente en tu glosario realmente aparece en el texto
   fuente (la compresión por llamada solo envía al LLM las entradas
   que coinciden con el texto del batch — ahorra tokens, pero significa
   que un término fuente mal escrito es invisible).
3. El modelo es lo suficientemente fuerte — `flash-lite` a veces
   ignora pistas que `flash` y `pro` honran.

### ¿Los términos del glosario coinciden indistintamente a los acentos?

Sí. Tanto la búsqueda del glosario como la barra de búsqueda en la
página Glosario usan una función de normalización que quita acentos y
mayúsculas. Así que `cafe`, `Café` y `CAFE` todos coinciden con una
entrada cuyo origen es `Café`.

## Privacidad

### ¿Recopiláis algún dato de uso?

No. La app no tiene SDK de analítica. La verificación opcional de
actualización consulta un único endpoint de GitHub Releases al inicio;
es togglable en **Configuración → General**.

### ¿Mis claves de API están seguras?

Se almacenan en el keychain de tu OS (Keychain en macOS, Credential
Manager en Windows, Secret Service en Linux). Otros procesos no pueden
leerlas sin tu permiso explícito. El fallback (cuando no hay daemon de
keychain disponible — típicamente servidores Linux headless) es un INI
en texto plano bajo el directorio de configuración de tu usuario; en
ese modo las claves están protegidas por permisos de archivo pero no
encriptadas criptográficamente.
