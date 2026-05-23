---
description: Instale o LibreOffice para que o AI Translate possa traduzir formatos Office legados (.doc, .xls, .ppt) e arquivos ODF (.odt, .ods, .odp) no macOS e Linux.
---

# LibreOffice (formatos Office)

O pipeline de tradução Office escolhe o melhor backend disponível
nesta ordem:

1. **win32com** (Windows + MS Office instalado) — fidelidade máxima
2. **LibreOffice UNO** (multiplataforma) — recuo quando win32com não
   está aí
3. **python-docx / openpyxl / python-pptx** (apenas formatos modernos)
   — recuo pure-Python quando nenhum dos anteriores está disponível

LibreOffice é **o único caminho** para `.doc` / `.xls` / `.ppt`
legados no Linux e macOS, e o caminho recomendado nessas plataformas
também para formatos Office modernos (melhor fidelidade que o
backend pure-Python, especialmente para tabelas e objetos
embutidos).

## Instalar

=== "macOS"
    ```bash
    brew install --cask libreoffice
    ```

    Ou baixe de <https://www.libreoffice.org/download/download/>.

=== "Ubuntu / Debian"
    ```bash
    sudo apt install libreoffice
    ```

=== "Fedora / RHEL"
    ```bash
    sudo dnf install libreoffice
    ```

=== "Windows"
    O app desktop no Windows geralmente usa **win32com** com MS
    Office instalado — LibreOffice é o *recuo* se o MS Office estiver
    faltando. Instale de <https://www.libreoffice.org/download/download/>.

## Verificar

```bash
soffice --version
```

Se você obter "command not found" no macOS, o binário está em
`/Applications/LibreOffice.app/Contents/MacOS/soffice`. O app o
auto-descobre através de caminhos de instalação comuns, mas você
pode sobrescrever em **Configurações → Geral → Caminho do
LibreOffice** se necessário.

## O que ele alimenta

Quando o LibreOffice é o backend ativo:

| Recurso | Nota |
|---|---|
| **Office moderno** (`.docx`, `.xlsx`, `.pptx`) | Usado como recuo quando win32com não está disponível |
| **Office legado** (`.doc`, `.xls`, `.ppt`) | Necessário — Python puro não consegue lê-los |
| **ODF** (`.odt`, `.ods`, `.odp`) | Usado para conversão round-trip quando **Auto-converter ODF** está ligado |
| **Auto-converter legado / ODF → OOXML** | Necessário |

## Processo em segundo plano

A primeira vez que o LibreOffice é necessário, o app inicia um
processo `soffice` em modo headless e o mantém vivo através das
traduções (`office_lifecycle.py`). Ele se desliga automaticamente
ao sair do app.

## Ressalvas

!!! warning "Tempo de inicialização na primeira execução"
    A primeira tradução que atinge o LibreOffice espera ~5-10
    segundos para o `soffice` subir. Traduções subsequentes reusam
    o mesmo processo e são rápidas.

!!! info "Logs de crash JVM"
    O componente Java do LibreOffice ocasionalmente produz arquivos
    `hs_err_pid*.log` quando dá segfault. O app os direciona para um
    diretório temp para que não poluam sua pasta de projeto.

!!! tip "Auto-converter legado / ODF"
    Ative **Configurações → Tradução → Auto-converter legado** se
    você traduz `.doc` / `.xls` / `.ppt` rotineiramente. O pipeline
    os converte para `.docx` / `.xlsx` / `.pptx` primeiro (via
    `convert_to_modern_format`), traduz a cópia moderna, então
    converte de volta. A fidelidade é muito maior que traduzir o
    formato legado diretamente.
