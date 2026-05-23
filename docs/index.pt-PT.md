---
description: AI Translate é um tradutor desktop gratuito e multiplataforma para documentos, PDFs, legendas, áudio e fala ao vivo em mais de 45 idiomas.
---

# AI Translate

Um tradutor desktop gratuito e multiplataforma que lida com **45 idiomas**
e vai muito além de texto puro — traduz documentos, áudio, vídeo, fala ao
vivo, capturas de ecrã e mais, tudo através de um único pipeline movido
por LLM.

<div class="grid cards" markdown>

-   :material-cursor-default-click-outline:{ .lg .middle } **Aplicação desktop**

    ---

    Arraste um ficheiro, escolha um idioma de destino, receba uma cópia
    traduzida. Arrastar e soltar, histórico, glossários, tudo.

    [:octicons-arrow-right-24: Tutorial de 5 minutos](getting-started/first-translation.md)

-   :material-console:{ .lg .middle } **Linha de comando**

    ---

    `ait report.docx --target French` — o mesmo pipeline, scriptável e
    sem interface. Útil para CI, jobs em lote, servidores.

    [:octicons-arrow-right-24: Guia CLI](cli.md)

-   :material-robot-outline:{ .lg .middle } **Agentes de IA (MCP)**

    ---

    Expõe a tradução como ferramentas Model Context Protocol para que
    Claude Desktop, Claude Code e outros clientes MCP possam chamá-las
    diretamente.

    [:octicons-arrow-right-24: Definição MCP](mcp.md)

</div>

## O que você pode traduzir

| Tipo | Formatos |
|---|---|
| **Documentos Office** | `.docx`, `.xlsx`, `.pptx`, `.odt`, `.ods`, `.odp`, mais legacy `.doc` / `.xls` / `.ppt` |
| **PDFs** | tradução extract-overlay com preservação de layout, tradução de marcadores / formulários / links, fallback OCR para escaneados |
| **Texto e web** | `.txt`, `.md`, `.rst`, `.html` / `.htm` / `.xhtml`, `.xml`, `.rtf`, `.json`, `.csv`, `.epub` |
| **Legendas** | `.srt`, `.vtt`, `.ass`, `.ssa` |
| **Localização** | `.po`, `.pot`, `.xliff` / `.xlf`, `.yaml` / `.yml`, `.properties`, `.strings` |
| **Imagens** | `.png`, `.jpg`, `.jpeg`, `.bmp`, `.webp`, `.tiff`, `.tif` (OCR ou visão LLM) |
| **Áudio** | `.mp3`, `.wav`, `.m4a`, `.flac`, `.ogg`, `.aac`, `.wma` |
| **Vídeo** | `.mp4`, `.webm`, `.mkv`, `.avi`, `.mov`, `.wmv` (pipeline de dublagem completo) |

## Funcionalidades principais {: #headline-features }

- **[Traduzir texto](features/translate-text.md)** — tradução LLM instantânea com auto-detecção, edição no local, reprodução TTS. Idiomas da direita para esquerda (árabe, hebraico, persa) renderizam nativamente.
- **[Traduzir documento](features/translate-document.md)** — solte ficheiros, observe um spinner de progresso por tarefa, receba cópias traduzidas lado a lado. Alvos RTL recebem markup bidi apropriado; `Ctrl+P` / `Ctrl+G` pausam e continuam a fila.
- **[Gerar legenda (STT)](features/generate-subtitle.md)** — transcreve áudio / vídeo em SRT / VTT / ASS / SSA.
- **[Gerar voz (TTS)](features/generate-voice.md)** — sintetiza legendas em MP3 / WAV com timing.
- **[Dublagem de vídeo](features/dubbing.md)** — STT → traduzir → TTS → mix completo de volta no vídeo fonte.
- **[Tradução ao vivo](features/live-translation.md)** — overlay de legendas em tempo real do microfone ou áudio do sistema.
- **[Extrair texto](features/extract-text.md)** — OCR ou visão LLM → `.txt` / `.docx`.
- **[Glossário](features/glossary.md)** — aplica terminologia consistente em todas as traduções.

!!! tip "Modo Vertex AI para Gemini"
    Utilizadors enterprise podem trocar chamadas Gemini da API Developer
    para **Vertex AI** em **Definições → LLM** — aponte para seu
    projeto e região GCP, opcionalmente forneça um caminho JSON de
    service account. Veja
    [Provedores LLM](setup/llm-providers.md#google-gemini-recommended-for-first-time-setup).

!!! tip "Primeira vez aqui?"
    Comece com [Instalação](getting-started/installation.md), depois o
    [tutorial de primeira tradução de 5 minutos](getting-started/first-translation.md).
    Você terá um documento traduzido em menos de 10 minutos a partir
    de um clone novo.
