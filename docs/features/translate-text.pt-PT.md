---
description: Traduza instantaneamente trechos de texto em 45+ idiomas com AI Translate — cole, digite ou fale; suporta modo edição, reprodução TTS e troca de idiomas.
---

# Traduzir texto

Tradução LLM instantânea com auto-detecção, troca de idiomas, saída em
streaming e reprodução TTS. Melhor para trechos curtos, uso estilo
chat e teste da sua definição LLM.

## Passo a passo

1. Clique em **Traduzir texto** na barra lateral.
2. Digite ou cole seu texto fonte no painel esquerdo.
3. O idioma **Origem** se auto-detecta enquanto você digita (com `langdetect`).
4. Escolha um idioma **Destino** no dropdown direito.
5. Clique em **Traduzir** (ou pressione `Ctrl+Enter`).
6. A tradução flui em streaming token por token no painel direito.

## O que você obtém

- **Saída em streaming** — a tradução aparece conforme o LLM a gera,
  sem esperar pela resposta inteira.
- **Auto-detecção de origem** — o seletor de origem atualiza em tempo
  real. Clique para sobrescrever.
- **Modo edição** — clique no painel direito para editar a tradução
  manualmente. Pressione `Esc` para cancelar uma tradução em
  andamento; pressione novamente para sair do modo edição.
- **Reuso de histórico** — cada tradução é guarda. Clique em uma
  entrada no painel Histórico de tradução de texto abaixo para
  recarregar ambos os painéis; edições atualizam a entrada original
  em vez de criar uma duplicata.
- **Reprodução TTS** — clique em **Ouvir** ao lado de qualquer painel
  para ouvi-lo lido em voz alta. Honra sua escolha em
  **Definições → Voz → Método TTS** — Edge TTS (padrão),
  ElevenLabs, Google Cloud TTS, Gemini TTS ou **Piper TTS**
  (totalmente offline). Com Piper selecionado, o botão Ouvir executa
  o mesmo pre-flight da página Voz: uma voz por idioma faltando
  mostra um diálogo modal com botão **Abrir Definições** para
  baixá-la. Hits de cache pulam o pre-flight inteiramente.
- **Seletor de modelo por funcionalidade** — quando há mais de um LLM
  configurado, um dropdown permite escolher um modelo Flash rápido
  para velocidade ou um modelo Pro mais pesado para qualidade,
  apenas para esta página.

## Atalhos

| Atalho | Ação |
|---|---|
| `Ctrl+Enter` | Traduzir |
| `Ctrl+L` | Trocar origem ↔ destino |
| `Esc` | Cancelar tradução em andamento, ou sair do modo edição |
| `Ctrl+F` | Foco em busca do histórico |

## Dicas

!!! tip "Idiomas RTL"
    Traduções para **árabe**, **hebraico** ou **persa** renderizam
    automaticamente da direita para esquerda no painel de saída. O
    mesmo manejo RTL é levado para a saída de ficheiro em todos os
    formatos da página [Traduzir documento](translate-document.md)
    (PDF, DOCX, PPTX, XLSX, ODF, RTF, HTML, EPUB, ASS/SSA), e o persa
    recebe uma voz `fa-IR` nativa para reprodução Edge TTS.

!!! tip "Cache do botão Ouvir"
    Na primeira vez que você clica em Ouvir para um par (texto,
    idioma) dado, o áudio é sintetizado e cacheado em disco.
    Reproduções seguintes são instantâneas. O cache é apagado na
    inicialização do app, então cada sessão começa nova.

!!! tip "Onde as chaves vão"
    A página Traduzir texto lê as mesmas entradas de keychain do
    resto do app — veja [Provedores LLM](../setup/llm-providers.md).
