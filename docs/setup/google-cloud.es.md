---
description: Conecta Google Cloud a AI Translate para Vision OCR, Speech-to-Text y Text-to-Speech — configura una clave API y habilita los servicios relevantes.
---

# Google Cloud (Vision OCR / Speech-to-Text / Text-to-Speech)

Una única clave API de Google Cloud alimenta tres backends opcionales:

- **Vision OCR** — motor OCR de pago (1.000 gratis / mes)
- **Speech-to-Text v1** — STT de pago (60 minutos / mes gratis)
- **Text-to-Speech v1** — TTS de pago (1 M de caracteres / mes
  gratis para WaveNet)

Solo necesitas habilitar las APIs que realmente uses.

## Obtener una clave API

1. [Crea un proyecto de Google Cloud](https://console.cloud.google.com/projectcreate)
2. Abre la biblioteca de API: <https://console.cloud.google.com/apis/library>
3. Habilita cualquiera de:
    - [Vision API](https://console.cloud.google.com/apis/library/vision.googleapis.com)
    - [Speech-to-Text API](https://console.cloud.google.com/apis/library/speech.googleapis.com)
    - [Text-to-Speech API](https://console.cloud.google.com/apis/library/texttospeech.googleapis.com)
4. [Crea una clave API](https://console.cloud.google.com/apis/credentials):
   haz clic en **+ Create Credentials → API key**
5. Copia la clave (parece `AIza...`).

!!! tip "Restringir la clave"
    En la página de detalle de la clave API, bajo **API restrictions**,
    restringe la clave solo a las APIs que has habilitado. De ese
    modo una clave filtrada no puede acumular facturas en servicios
    que no querías usar.

## Configurar en la app

En **Configuración → Servicio**:

1. Pega en **Clave API de Google Cloud** → **Guardar**

Esta única clave está ahora disponible para los tres servicios de
Google.

## Habilitar cada servicio

### Vision OCR

En **Configuración → OCR → Método OCR = Google Cloud OCR**.

Eso es todo — usará la misma clave de Servicio.

### Speech-to-Text

En **Configuración → Subtítulo → Método STT = Google Cloud** (para
las páginas Subtítulo / Voz) o **Configuración → Live → Método STT =
Google Cloud** (para la página Live).

En **Configuración → Subtítulo → Modelo STT de Google**, elige el
modelo de reconocimiento:

| Modelo | Mejor para |
|---|---|
| `latest_long` (predet.) | Audio de formato largo (entrevistas, conferencias) |
| `latest_short` | Comandos de voz, frases cortas |
| `phone_call` | Audio telefónico (8 kHz) |
| `medical_dictation` / `medical_conversation` | Audio del dominio médico |

### Text-to-Speech

En **Configuración → Voz → Método TTS = Google Cloud TTS**.

Por defecto el servidor elige una voz basada en idioma y género —
eso es lo que la mayoría de usuarios necesita. Fijar una voz Google
específica (p. ej. `en-US-Chirp3-HD-Charon`, `vi-VN-Wavenet-A`)
está soportado por el motor pero aún no expuesto como campo de
Configuración; se puede establecer editando
`voice/google_tts_voice_name` directamente en `settings.ini`. Los IDs
de voz se listan en
<https://cloud.google.com/text-to-speech/docs/voices>.

## Errores comunes

| Error | Causa probable |
|---|---|
| `AUTH_ERROR` | Clave errónea / caducada. Vuelve a pegar en Configuración → Servicio. |
| `API not enabled` | No has habilitado la API específica (Vision / Speech / TTS) en este proyecto Cloud. |
| `QUOTA_ERROR` | Límite de capa gratuita alcanzado para esta API. Espera, o actualiza facturación. |
| `INVALID_ARGUMENT_ERROR` | El nombre de voz no existe en el idioma que has elegido. |

## Guarda de coste

!!! warning
    Las tres APIs de Google son post-pago — una vez que excedes la
    capa gratuita, empiezas a ser facturado sin parar. Establece una
    [alerta de presupuesto](https://console.cloud.google.com/billing/budgets)
    en el proyecto Cloud antes de hacer trabajo de alto volumen.
