---
description: Configura motores OCR para extracción de texto de imágenes y PDF — elige entre Tesseract o EasyOCR offline, o Google Vision OCR basado en cloud.
---

# Motores OCR

El OCR se usa para leer texto de imágenes — tanto en la página
[Extraer texto](../features/extract-text.md) como como repliegue
dentro de la traducción de Documento cuando una página está
escaneada (sin capa de texto) o cuando activas **Traducir imágenes
integradas**.

Puedes elegir entre tres motores OCR.

## Tesseract (predeterminado recomendado)

Gratis, rápido, offline. Necesita una instalación de sistema.

=== "macOS"
    ```bash
    brew install tesseract tesseract-lang
    ```

=== "Ubuntu / Debian"
    ```bash
    sudo apt install tesseract-ocr tesseract-ocr-all
    ```

    `tesseract-ocr-all` trae todos los idiomas soportados. Para
    ahorrar disco, instala solo lo que necesites (p. ej.
    `tesseract-ocr-fra` para francés).

=== "Fedora / RHEL"
    ```bash
    sudo dnf install tesseract tesseract-langpack-eng tesseract-langpack-fra
    ```

=== "Windows"
    Descarga el instalador desde
    [los releases de Tesseract de UB Mannheim](https://github.com/UB-Mannheim/tesseract/wiki).
    Ejecútalo, acepta los valores por defecto — los paquetes de
    idioma vienen incluidos.

Verificar:

```bash
tesseract --version
tesseract --list-langs
```

En la app desktop: **Configuración → OCR → Método OCR = Tesseract**.
Listo.

## EasyOCR

Gratis, offline. Ideal para escrituras no-latinas (chino, coreano,
japonés, tailandés). Los modelos se descargan al primer uso (~1 GB
en total).

```bash
uv sync --extra easyocr
```

En la app desktop: **Configuración → OCR → Método OCR = EasyOCR**.

La primera vez que lo uses para un idioma, el modelo relevante se
descarga a `~/.EasyOCR/`. Las ejecuciones siguientes son
instantáneas.

## Google Cloud Vision

Cloud, de pago (1.000 solicitudes gratis / mes). Precisión máxima,
especialmente en contenido ruidoso / manuscrito / multi-escritura.

1. [Crea un proyecto Google Cloud](https://console.cloud.google.com/projectcreate)
2. Habilita la [Vision API](https://console.cloud.google.com/apis/library/vision.googleapis.com)
3. [Crea una clave API](https://console.cloud.google.com/apis/credentials)
4. En la app desktop: **Configuración → Servicio → Clave API Google Cloud** → pega
5. **Configuración → OCR → Método OCR = Google Cloud OCR**

La misma clave API Google Cloud alimenta Vision OCR, Speech-to-Text
y Text-to-Speech si también habilitas esas APIs.

## Comparando precisión

La pestaña **Configuración → OCR** tiene una pequeña tabla de
comparación integrada — cobertura de idiomas, online/offline, coste,
precisión. Reléela cada vez que estés tentado a cambiar.

## Cuándo se usa OCR

| Lugar | Comportamiento |
|---|---|
| **Página Extraer texto** (cuando método = OCR) | OCR directo sobre las imágenes soltadas |
| **Traducir documento → PDF** | Repliegue OCR en páginas solo escaneadas (sin capa de texto) |
| **Traducir documento → Office** con **Traducir imágenes integradas** activado | OCR + LLM vision en cada imagen integrada |

## Consejos

!!! tip "Elige el idioma origen"
    La mayoría de motores OCR son mucho más precisos cuando les dices
    qué idioma esperar. Las páginas Subtítulo / Documento / Extraer
    texto reenvían todas tu selector **Idioma origen** al motor OCR.

!!! tip "Tesseract es suficiente para texto impreso limpio"
    No corras al OCR cloud hasta que Tesseract / EasyOCR haya
    realmente fallado en tu contenido. Son gratis, rápidos y
    sorprendentemente buenos.
