---
description: Instale AI Translate no Windows, macOS ou Linux a partir de binários pré-compilados ou do código-fonte — cobre Python, FFmpeg e definição opcional do LibreOffice.
---

# Instalação

## O que você precisa

- **Python 3.12 ou mais novo** ([download](https://www.python.org/downloads/))
- **[uv](https://docs.astral.sh/uv/)** — gerenciador de pacotes Python rápido. Instale com:

    === "macOS / Linux"
        ```bash
        curl -LsSf https://astral.sh/uv/install.sh | sh
        ```

    === "Windows"
        ```powershell
        powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
        ```

- **Uma chave de API LLM** — qualquer uma de:
    - [Google Gemini](https://aistudio.google.com/apikey) (camada gratuita disponível — recomendado para começar)
    - Qualquer endpoint compatível com OpenAI (OpenAI, Anthropic via proxy, Ollama / LM Studio local, etc.)

## Opcional, mas desbloqueia mais funcionalidades

| Ferramenta | Usado por | Quando você precisa |
|---|---|---|
| **FFmpeg** ([download](https://ffmpeg.org/download.html)) | Legenda, Voz, Dublagem, Live | Qualquer fluxo de áudio/vídeo |
| **LibreOffice** ([download](https://www.libreoffice.org/download/)) | Formatos Office no Linux/macOS | Traduzir legacy `.doc` / `.xls` / `.ppt`, ou qualquer ficheiro Office quando MS Office não estiver instalado |
| **Tesseract** ([guia de instalação](https://tesseract-ocr.github.io/tessdoc/Installation.html)) | Motor OCR (padrão) | Página Extrair texto, tradução de PDFs escaneados, tradução de imagens embutidas |
| **MS Office** + **pywin32** | Office no Windows | Tradução Office de máxima fidelidade no Windows |

Você pode instalar AI Translate sem nenhum desses — funcionalidades
que precisam deles avisam antes de falhar.

## Configurar

```bash
git clone https://github.com/cadic2603/ai-translate.git
cd ai-translate
uv sync
```

Isso instala tudo o necessário para executar o app desktop, o CLI e
o servidor MCP.

## Executar

=== "App desktop"
    ```bash
    uv run python -m src.main
    ```

=== "Linha de comando"
    ```bash
    uv run ait --version
    ```

=== "Servidor MCP"
    ```bash
    uv run ait-mcp           # transporte stdio (para Claude Desktop / Code)
    ```

## Adicione sua chave de API

Na primeira vez que você abrir o app desktop:

1. Clique em **Definições** na barra lateral
2. Abra a aba **LLM**
3. Cole sua **chave de API Google Gemini** (ou configure um provedor
   personalizado compatível com OpenAI). Utilizadors enterprise podem
   trocar Gemini para **modo Vertex AI** — aponte para um projeto
   e região GCP, opcionalmente forneça um caminho JSON de service
   account; veja [Provedores LLM](../setup/llm-providers.md) para detalhes.
4. Escolha um modelo padrão — qualquer variante Flash atual (ex.
   `gemini-2.5-flash`) é um sólido ponto de partida gratuito. Variantes
   Pro dão melhor qualidade a custo mais alto.
5. Feche Definições — pronto

As chaves são guardas no **chaveiro do seu OS** (Keychain macOS,
Credential Manager Windows, GNOME / KDE Secret Service no Linux), não
em texto plano em disco.

!!! tip "Instalação headless / servidor"
    Se você não pode executar o app desktop para configurar chaves,
    veja [Provedores LLM](../setup/llm-providers.md) para os comandos
    CLI keychain.

## Próximo: experimente

[Primeira tradução em 5 minutos →](first-translation.md){ .md-button .md-button--primary }
