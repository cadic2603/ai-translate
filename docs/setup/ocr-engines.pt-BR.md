---
description: Configure motores OCR para extração de texto de imagens e PDF — escolha entre Tesseract ou EasyOCR offline, ou Google Vision OCR baseado em cloud.
---

# Motores OCR

OCR é usado para ler texto de imagens — tanto na página
[Extrair texto](../features/extract-text.md) quanto como recuo dentro
da tradução de Documento quando uma página está digitalizada (sem
camada de texto) ou quando você liga **Traduzir imagens incorporadas**.

Você pode escolher entre três motores OCR.

## Tesseract (padrão recomendado)

Gratuito, rápido, offline. Precisa de uma instalação de sistema.

=== "macOS"
    ```bash
    brew install tesseract tesseract-lang
    ```

=== "Ubuntu / Debian"
    ```bash
    sudo apt install tesseract-ocr tesseract-ocr-all
    ```

    `tesseract-ocr-all` traz todos os idiomas suportados. Para
    economizar disco, instale apenas o que precisa (ex.
    `tesseract-ocr-fra` para francês).

=== "Fedora / RHEL"
    ```bash
    sudo dnf install tesseract tesseract-langpack-eng tesseract-langpack-fra
    ```

=== "Windows"
    Baixe o instalador em
    [releases do Tesseract da UB Mannheim](https://github.com/UB-Mannheim/tesseract/wiki).
    Execute, aceite os padrões — pacotes de idioma vêm embutidos.

Verificar:

```bash
tesseract --version
tesseract --list-langs
```

No app desktop: **Configurações → OCR → Método OCR = Tesseract**.
Pronto.

## EasyOCR

Gratuito, offline. Ótimo para scripts não-latinos (chinês, coreano,
japonês, tailandês). Modelos baixam no primeiro uso (~1 GB total).

```bash
uv sync --extra easyocr
```

No app desktop: **Configurações → OCR → Método OCR = EasyOCR**.

A primeira vez que você usa para um idioma, o modelo relevante
baixa para `~/.EasyOCR/`. Execuções subsequentes são instantâneas.

## Google Cloud Vision

Cloud, pago (1.000 solicitações grátis / mês). Maior precisão,
especialmente em conteúdo ruidoso / manuscrito / multi-script.

1. [Crie um projeto Google Cloud](https://console.cloud.google.com/projectcreate)
2. Habilite a [Vision API](https://console.cloud.google.com/apis/library/vision.googleapis.com)
3. [Crie uma chave de API](https://console.cloud.google.com/apis/credentials)
4. No app desktop: **Configurações → Serviço → Chave de API Google Cloud** → cole
5. **Configurações → OCR → Método OCR = Google Cloud OCR**

A mesma chave API Google Cloud alimenta Vision OCR, Speech-to-Text e
Text-to-Speech se você também habilitar essas APIs.

## Comparando precisão

A aba **Configurações → OCR** tem uma pequena tabela de comparação
embutida — cobertura de idiomas, online/offline, custo, precisão.
Releia sempre que estiver tentado a trocar.

## Quando o OCR é usado

| Lugar | Comportamento |
|---|---|
| **Página Extrair texto** (quando método = OCR) | OCR direto nas imagens soltadas |
| **Traduzir documento → PDF** | Recuo OCR em páginas apenas digitalizadas (sem camada de texto) |
| **Traduzir documento → Office** com **Traduzir imagens incorporadas** ligado | OCR + LLM vision em cada imagem incorporada |

## Dicas

!!! tip "Escolha o idioma de origem"
    A maioria dos motores OCR é muito mais precisa quando você diz a
    eles qual idioma esperar. As páginas Legenda / Documento /
    Extrair texto encaminham todas o seu seletor **Idioma de origem**
    para o motor OCR.

!!! tip "Tesseract é suficiente para texto impresso limpo"
    Não pule para OCR cloud até que Tesseract / EasyOCR tenha
    realmente falhado no seu conteúdo. Eles são grátis, rápidos e
    surpreendentemente bons.
