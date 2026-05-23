---
description: Instala LibreOffice para que AI Translate pueda traducir formatos Office heredados (.doc, .xls, .ppt) y archivos ODF (.odt, .ods, .odp) en macOS y Linux.
---

# LibreOffice (formatos Office)

El pipeline de traducción Office elige el mejor backend disponible
en este orden:

1. **win32com** (Windows + MS Office instalado) — máxima fidelidad
2. **LibreOffice UNO** (multiplataforma) — repliegue cuando
   win32com no está
3. **python-docx / openpyxl / python-pptx** (solo formatos modernos)
   — repliegue pure-Python cuando ninguno de los anteriores está
   disponible

LibreOffice es **la única vía** para `.doc` / `.xls` / `.ppt`
heredados en Linux y macOS, y la vía recomendada en esas plataformas
para los formatos Office modernos también (mejor fidelidad que el
backend pure-Python, especialmente para tablas y objetos
integrados).

## Instalar

=== "macOS"
    ```bash
    brew install --cask libreoffice
    ```

    O descarga desde <https://www.libreoffice.org/download/download/>.

=== "Ubuntu / Debian"
    ```bash
    sudo apt install libreoffice
    ```

=== "Fedora / RHEL"
    ```bash
    sudo dnf install libreoffice
    ```

=== "Windows"
    La app de escritorio en Windows normalmente usa **win32com** con
    MS Office instalado — LibreOffice es el *repliegue* si MS Office
    falta. Instala desde <https://www.libreoffice.org/download/download/>.

## Verificar

```bash
soffice --version
```

Si obtienes "command not found" en macOS, el binario está en
`/Applications/LibreOffice.app/Contents/MacOS/soffice`. La app lo
auto-descubre a través de rutas de instalación comunes, pero puedes
sobrescribir en **Configuración → General → Ruta de LibreOffice**
si lo necesitas.

## Qué alimenta

Cuando LibreOffice es el backend activo:

| Característica | Nota |
|---|---|
| **Office moderno** (`.docx`, `.xlsx`, `.pptx`) | Usado como repliegue cuando win32com no está disponible |
| **Office heredado** (`.doc`, `.xls`, `.ppt`) | Requerido — Python puro no puede leerlos |
| **ODF** (`.odt`, `.ods`, `.odp`) | Usado para conversión ida-y-vuelta cuando **Auto-convertir ODF** está activado |
| **Auto-convertir legado / ODF → OOXML** | Requerido |

## Proceso en segundo plano

La primera vez que se necesita LibreOffice, la app lanza un proceso
`soffice` en modo headless y lo mantiene vivo a través de las
traducciones (`office_lifecycle.py`). Se cierra automáticamente al
salir de la app.

## Advertencias

!!! warning "Tiempo de inicio en la primera ejecución"
    La primera traducción que toca LibreOffice espera ~5-10 segundos
    a que `soffice` arranque. Las traducciones posteriores reusan
    el mismo proceso y son rápidas.

!!! info "Logs de crash JVM"
    El componente Java de LibreOffice ocasionalmente produce
    archivos `hs_err_pid*.log` cuando hace segfault. La app los
    enruta a un directorio temporal para que no contaminen tu
    carpeta de proyecto.

!!! tip "Auto-convertir legado / ODF"
    Habilita **Configuración → Traducción → Auto-convertir legado**
    si traduces rutinariamente `.doc` / `.xls` / `.ppt`. El pipeline
    los convierte a `.docx` / `.xlsx` / `.pptx` primero (vía
    `convert_to_modern_format`), traduce la copia moderna, luego
    convierte de vuelta. La fidelidad es mucho mayor que traducir
    el formato heredado directamente.
