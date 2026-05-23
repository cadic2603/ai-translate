---
description: Traduza seu primeiro documento com AI Translate em 5 minutos — arraste e solte um PDF, escolha um idioma de destino e descarregue a cópia traduzida.
---

# Sua primeira tradução

Uma execução rápida de ponta a ponta — menos de 5 minutos depois que
a definição estiver feita.

!!! abstract "Antes de começar"
    Você precisa ter terminado a [instalação](installation.md) e
    configurado uma chave de API LLM. O nível gratuito do Google
    Gemini é suficiente para uma primeira tentativa.

## Traduzir um documento Word

1. Inicie o app desktop:

    ```bash
    uv run python -m src.main
    ```

2. Clique em **Traduzir documento** na barra lateral esquerda.

3. Arraste qualquer ficheiro `.docx` para a zona de soltar — ou clique
   em **Procurar** para escolher um.

4. O ficheiro aparece na fila. Escolha um idioma de destino no topo:

    - Origem: `Detecção automática` (padrão — geralmente correto)
    - Destino: ex. `Francês`, `Vietnamita`, `Japonês`, `Chinês (Simplificado)`

5. Clique em **Traduzir** (ou pressione `Ctrl+Enter`).

6. Observe a barra de progresso na tabela de histórico na parte
   inferior da página. Quando chegar a 100%, clique em **Abrir** na
   linha para abrir o ficheiro traduzido — guardado ao lado do original
   com sufixo `_translated_<src>_<tgt>`.

## O que acabou de acontecer

- Seu `.docx` foi clonado em uma pasta de armazenamento por tarefa
  para que o original não seja tocado.
- O texto foi extraído, agrupado em chunks amigáveis ao LLM, traduzido,
  e então reinjetado no documento com toda a formatação preservada
  (negrito, itálico, fontes, cores, cabeçalhos, notas de rodapé,
  hyperlinks…).
- Uma entrada de histórico foi escrita em um banco SQLite para que
  você possa reabrir, reexecutar ou retraduzir o ficheiro depois.

## Tente agora as vitórias rápidas

=== "Traduzir texto plano"

    Vá para **Traduzir texto** na barra lateral. Cole qualquer coisa,
    escolha um destino, pressione Enter. Saída em streaming, troca de
    idiomas (`Ctrl+L`), modo de edição, reprodução TTS.

=== "Gerar legendas"

    **Gerar legenda** — solte um `.mp4`. Você receberá um `.srt` no
    idioma de origem. (Para traduzir _e_ dublar o vídeo, use a página
    Dublagem em vez disso.)

=== "Tradução de microfone ao vivo"

    **Tradução ao vivo** — escolha microfone ou áudio do sistema,
    escolha um destino, Iniciar. Uma janela overlay flutuante mostra
    legendas em tempo real.

## Para onde agora

- Veja o [índice de funcionalidades](../index.md#headline-features) para o que cada página faz.
- Conecte [mais provedores](../setup/llm-providers.md) (endpoints personalizados, ElevenLabs, Soniox, Google Cloud).
- Experimente o [CLI](../cli.md) para execuções em lote / scriptadas.
