---
description: "Configura proveedores de LLM para la traducción: Google Gemini (recomendado), endpoints compatibles con OpenAI, o cualquier proveedor personalizado con una clave API."
---

# Proveedores LLM

El pipeline de traducción llama a un Large Language Model para la
traducción real. Puedes configurar uno o varios; el selector de
modelo por característica permite que cada página use uno diferente.

## Google Gemini (recomendado para configuración inicial) {: #google-gemini-recommended-for-first-time-setup }

La capa gratuita es generosa y suficiente para la mayoría de uso
personal.

1. Ve a <https://aistudio.google.com/apikey>
2. Haz clic en **Create API key** (inicia sesión con tu cuenta de
   Google)
3. Copia la clave (parece `AIza...`)
4. En la app desktop: **Configuración → LLM → Clave API Gemini** →
   pega → **Guardar**
5. Elige un modelo predeterminado en el desplegable **Modelo Gemini
   predeterminado**. La línea de Google tiende a parecerse a:

    - Variantes **Flash** (p. ej. `gemini-2.5-flash`) — rápida, capa
      gratuita generosa, buena calidad. Punto de partida recomendado.
    - Variantes **Pro** — más lenta, mayor calidad, más cara.
    - **Flash-lite** — la más rápida, la más barata, menor calidad.

    Los nombres de modelo exactos disponibles dependen de qué ha
    desplegado Google a tu cuenta; elige uno cuyo nombre contenga
    `flash` para un predeterminado equilibrado.

Listo. La clave se almacena en el llavero de tu OS, no en texto
plano.

### Modo Vertex AI (empresarial)

Dentro del bloque de configuración de Gemini, un par de radios te
permite alternar entre **Developer API** y **Vertex AI** — los mismos
modelos Gemini, facturados a través de tu cuenta GCP, con controles
a nivel de organización (VPC-SC, registros de auditoría, residencia
regional de datos).

1. En **Configuración → LLM**, cambia el radio Gemini de
   **Developer API** a **Vertex AI**
2. Rellena:
    - **Project** — tu ID de proyecto GCP
    - **Location** — una región Vertex (por defecto `us-central1`)
    - **Credentials path** *(opcional)* — ruta a un archivo JSON de
      clave de cuenta de servicio. Déjalo en blanco para usar las
      Application Default Credentials
      (`gcloud auth application-default login`)
3. **Guardar**. El desplegable de modelos se rellena de nuevo desde
   Vertex una vez establecido el proyecto.

El refresco OAuth lo maneja `google-genai` automáticamente. La ruta
JSON de la cuenta de servicio se almacena en texto plano a propósito
(la *ruta* no es un secreto — el contenido del archivo lo es, y
permanece en disco donde la mejor práctica documentada de Google lo
mantiene).

## OpenAI / Compatible con OpenAI

Cualquier cosa que exponga una API REST compatible con OpenAI
funciona — el propio OpenAI, Anthropic vía
[proxy LiteLLM](https://docs.litellm.ai), Ollama local, LM Studio,
vLLM, Together.ai, Groq, etc.

En **Configuración → LLM**:

1. Haz clic en **Add Custom Provider**
2. Rellena:
    - **Name** — una etiqueta como "OpenAI" / "Local Ollama" /
      "Anthropic"
    - **API endpoint** — la URL base (p. ej.
      `https://api.openai.com/v1` o `http://localhost:11434/v1` para
      Ollama)
    - **API key** — déjala en blanco para endpoints locales no
      autenticados
    - **Models** — lista separada por comas (p. ej. `gpt-4o-mini,
      gpt-4o, gpt-3.5-turbo`)
3. Haz clic en **Save**.

Los proveedores personalizados se almacenan como un blob JSON en el
llavero del OS (claves API incluidas).

## Cambiar el modelo predeterminado

El desplegable **Modelo Gemini predeterminado** en **Configuración →
LLM** establece un repliegue usado por cada página de característica
que no tiene su propio selector.

Páginas con su propio selector de modelo:

- **Traducir texto** — `pestaña de configuración Traducir texto → Modelo predeterminado`
- **Traducir documento** — elige por tarea; cae al predeterminado
- **Subtítulo / Voz / Doblaje / Live / Extraer texto** — cada una
  tiene su propio predeterminado por característica en su pestaña de
  Configuración

Esto te permite mezclar-y-combinar: Flash gratis para live, Pro para
documentos grandes, Ollama local para datos sensibles.

## Dónde se almacenan las claves

| OS | Almacenamiento |
|---|---|
| **macOS** | Llavero (login keychain) |
| **Windows** | Administrador de credenciales |
| **Linux (GNOME)** | Secret Service (gnome-keyring / KWallet) |
| **Linux (sin daemon)** | Cae a INI en texto plano en `~/.config/ai-translate/settings.ini` |

El valor INI de repliegue se migra al llavero en la primera lectura
cada vez que un llavero se vuelve disponible — sin paso manual.

## Instalación headless / servidor

Sin sesión de escritorio, todavía puedes establecer claves vía el
CLI `keyring` de Python (tras `uv sync`):

```bash
# Gemini
uv run keyring set ai-translate llm/gemini_api_key

# Proveedores personalizados (pega el blob JSON — ver UI de Configuración para el esquema)
uv run keyring set ai-translate llm/custom_providers
```

O establece las mismas claves INI directamente en `settings.ini` —
la app las migra al llavero en la primera lectura. El archivo está
en:

- **Linux** — `~/.config/ai-translate/settings.ini`
- **macOS** — `~/Library/Preferences/ai-translate/settings.ini`
- **Windows** — `%APPDATA%\ai-translate\settings.ini`

## Probar tu configuración

Comprobación rápida:

```bash
uv run ait --version
echo "Hello world." > /tmp/x.txt
uv run ait /tmp/x.txt --target Spanish --quiet
cat /tmp/x_translated__es.txt
```

Si ves "Hola mundo." — has terminado.

## Errores comunes

| Error | Causa probable |
|---|---|
| `AUTH_ERROR` | Clave API errónea / caducada. Vuelve a pegar en Configuración. |
| `QUOTA_ERROR` | Solicitudes-por-día de la capa gratuita superadas. Espera, o paga. |
| `MODEL_NOT_FOUND` | La lista `models` del proveedor personalizado no incluye el modelo solicitado. |
| `VISION_NOT_SUPPORTED` | El modelo que elegiste no puede hacer entrada de imagen. Usa una variante `flash` / `pro` / `vision`. |

Ver [Resolución de problemas](../troubleshooting.md) para más.
