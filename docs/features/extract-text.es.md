---
description: Extrae texto de imágenes y capturas de pantalla usando motores OCR (Tesseract, EasyOCR, Google Vision) o visión LLM — salida a TXT o DOCX.
---

# Extraer texto

Saca el texto de las imágenes — recibos, capturas de pantalla,
documentos fotografiados, páginas escaneadas, cualquier cosa. Salida
a `.txt` (plano) o `.docx` (párrafos formateados).

Esta página **no traduce** — sólo extrae. Pasa la salida a Traducir
documento si también quieres traducir.

## Dos métodos de extracción

| Método | Mejor para |
|---|---|
| **OCR** | Alto volumen / lote / sensible al coste (gratis o casi gratis por imagen) |
| **LLM vision** | Preservación de layout, scripts mixtos, imágenes de baja calidad, escritura a mano |

Elige el predeterminado en **Configuración → Extraer texto → Método de extracción**.

## Motores OCR (método OCR)

| Motor | Coste | Offline | Idiomas | Notas |
|---|---|---|---|---|
| **Tesseract** | Gratis | Sí | 100+ | Predeterminado. Necesita instalación del sistema. |
| **EasyOCR** | Gratis | Sí (tras descarga del modelo) | 80+ | Mejor para scripts no latinos. ~1 GB de modelos. |
| **Google Cloud Vision** | De pago (1.000 gratis / mes) | No | 60+ | Mayor precisión. |

Configura en **Configuración → OCR**.

## Paso a paso

1. Haz clic en **Extraer texto** en la barra lateral.
2. Suelta uno o varios archivos de imagen (`.png`, `.jpg`, `.jpeg`,
   `.bmp`, `.webp`, `.tiff`, `.tif`).
3. Elige el **Idioma de origen** (ayuda al OCR a elegir el modelo correcto).
4. Elige el **Formato de salida** — `.txt` o `.docx`.
5. Haz clic en **Extraer** (o `Ctrl+Enter`).
6. **Abre** la fila cuando termine.

## Cuándo usar qué

- **Recibo / factura denso en texto** → Tesseract es rápido y preciso.
- **Notas manuscritas fotografiadas** → la visión LLM gana de lejos.
- **Paneles de manga / cómic** → EasyOCR (maneja bien texto CJK vertical).
- **Formulario con muchos campos pequeños** → Google Cloud Vision
  tiende a preservar los límites de campos mejor que los demás.

## Trucos

!!! tip "OCR o LLM, no ambos"
    La página elige un método y lo ejecuta. Para comparar salidas,
    ejecuta la misma imagen dos veces con métodos diferentes.

!!! tip "Diálogo de configuración requerida"
    Si eliges OCR pero no hay motor OCR configurado (o LLM pero no
    hay clave LLM configurada), la página muestra un único diálogo
    "Configuración requerida" que enlaza directamente con la pestaña
    de Configuración relevante.

## Atajos

| Atajo | Acción |
|---|---|
| `Ctrl+Enter` | Extraer |
| `Ctrl+O` | Navegar |
| `Ctrl+F` | Foco en búsqueda de historial |
