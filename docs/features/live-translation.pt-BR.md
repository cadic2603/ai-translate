---
description: "Tradução de fala em tempo real: transcreva e traduza microfone ou áudio do sistema ao vivo com backends Whisper ou Soniox."
---

# Tradução ao vivo

Legendas e traduções em tempo real do microfone, áudio do sistema, ou
ambos — com uma janela de overlay sempre no topo opcional para que as
legendas fiquem sobre o que você está assistindo.

## O que dá pra fazer com isso

- **Legendas de reuniões ao vivo** — legenda uma chamada de Zoom /
  Meet / Teams em outro idioma sem entrar como um bot tradutor.
- **Aprendizado de idioma em tempo real** — legenda conteúdo em
  idioma estrangeiro (filmes, podcasts, palestras) com seu idioma
  nativo como faixa de tradução.
- **Legendas em todo o sistema** — capture o áudio do sistema para
  legendar YouTube / Netflix / qualquer coisa que toque nos seus
  alto-falantes.

## O que você precisa

- **FFmpeg** no `PATH` — veja [Configuração do FFmpeg](../setup/ffmpeg.md).
- Um backend STT, um destes:
    - **faster-whisper** — local, offline, gratuito, padrão
    - **Soniox** — nuvem, pago, diarização de falantes em tempo real. Veja [Configuração do Soniox](../setup/soniox.md).

- Para **captura de áudio do sistema**, o backend correto por SO é
  auto-selecionado: Linux usa `parec` (PulseAudio / PipeWire), Windows
  usa loopback WASAPI nativo (sem software extra na maioria dos casos),
  macOS usa `ffmpeg -f avfoundation` contra um dispositivo de loopback
  virtual (BlackHole / Loopback / etc.). Um banner de aviso inline com
  links de instalação clicáveis aparece se algo estiver faltando. Veja
  [Configuração → Áudio do sistema](../setup/system-audio.md) para
  instruções completas de instalação por SO.

## Passo a passo

1. Clique em **Tradução ao vivo** na barra lateral.
2. Configure uma vez em **Configurações → Live**:

    - **Idioma de origem** (idioma falado)
    - **Idioma de destino** (ou deixe em branco para apenas transcrição)
    - **Fonte de áudio**: Microfone / Áudio do sistema / Ambos
    - **Método STT**: Whisper / Soniox

3. De volta à página Live, clique em **Iniciar** (`Ctrl+Enter`).
4. A transcrição preenche o painel principal cartão por cartão. A
   janela **Overlay** flutuante também mostra legendas (arraste-a
   para onde quiser).
5. Clique em **Parar** para terminar a sessão.

## A visualização de transcrição

Escolha um layout na barra de ferramentas:

- **Ambos empilhados** — original + tradução, um acima do outro
- **Ambos lado a lado** — original à esquerda, tradução à direita
- **Apenas original** / **Apenas tradução**

Os botões da barra de ferramentas usam sufixos **`ON`** / **`OFF`**
para estado à primeira vista — ex. `TTS ON`, `TTS OFF`,
`Timestamps ON`, `Overlay OFF`.

Alterne **timestamps** com o ícone do relógio. Alterne a **reprodução
TTS** das linhas traduzidas com o ícone do alto-falante. Respeita sua
escolha em **Configurações → Voz → Método TTS** — Edge TTS (padrão),
ElevenLabs, Google Cloud TTS, Gemini TTS, ou **Piper TTS**
(totalmente offline). Com Piper selecionado, vozes faltantes por
idioma **caem silenciosamente para Edge TTS** no meio do stream — não
há pre-flight modal nesta página, já que bloquear o fluxo ao vivo
com um diálogo de download seria pior que o fallback.

## A janela overlay

Uma janela de ferramenta arrastável, redimensionável e sempre no topo.
Atalhos:

| Atalho | Ação |
|---|---|
| `Ctrl+[` / `Ctrl+]` | Diminuir / aumentar opacidade |
| `Ctrl+Seta` | Mover o overlay |
| `Ctrl+0` / `Ctrl+9` | Aumentar / encolher |

Posição, tamanho, opacidade e tamanho da fonte persistem entre
sessões.

### Sincronização ao vivo com as configurações

Os controles de tamanho da fonte e opacidade funcionam nos dois
sentidos: arrastar o controle deslizante **Tamanho da fonte** ou
**Opacidade** em **Configurações → Tradução ao Vivo →
Configuração de sobreposição** atualiza a sobreposição aberta em
tempo real e, inversamente, pressionar `+` / `-` / `Ctrl+[` /
`Ctrl+]` dentro da sobreposição atualiza os controles deslizantes
em Configurações. Nenhuma reinicialização da sobreposição
necessária.

### Espaço reservado de estado vazio

Antes que qualquer áudio seja capturado, a sobreposição mostra um
espaço reservado ("Pressione Iniciar..." inativo / "Ouvindo..."
após clicar em Iniciar) que reflete o estado vazio da janela
principal — a alternância permanece sincronizada com o
indicador de status em execução. O espaço reservado se adapta à
largura × altura atual da sobreposição para permanecer legível
em qualquer tamanho de janela.

### Modo de legendas mínimas

A caixa de seleção **Mostrar legendas mínimas** em Configurações
→ Tradução ao Vivo → Configuração de sobreposição oculta as
etiquetas de tempo e orador na sobreposição mantendo-as visíveis
na janela principal. Útil quando a sobreposição é compartilhada
com um público (modo apresentador / compartilhamento de tela)
mas você deseja manter os metadados completos na sua visualização
de trabalho. A alternância é apenas para a sobreposição — não
altera sua preferência de "Etiquetas de orador" para a janela
principal.

## Salvar a transcrição

Clique em **Salvar transcrição** para exportar a sessão para um
arquivo `.txt` com timestamps, falantes, linhas originais e linhas
traduzidas.

## Escolhendo um backend STT

| Backend | Melhor para | Custo | Latência |
|---|---|---|---|
| **Whisper** (local) | Offline, sensível à privacidade | Gratuito | Média (~1 s após fim de frase) |
| **Soniox** | Reuniões com múltiplos falantes | Pago (~$0,005 / min) | Baixa (tempo real) |

## Ressalvas

!!! warning "Seleção de microfone"
    A entrada de microfone sempre usa o **dispositivo padrão do SO**
    — não há seletor no app (o sounddevice expõe plugins ALSA virtuais
    demais para ser útil, e o SO já é dono da UI de microfone padrão).
    Defina seu microfone preferido nas configurações de som do SO antes
    de começar.

!!! warning "Backpressure de TTS"
    A fila TTS é limitada às 3 frases mais recentes — o áudio em fila
    mais antigo é descartado se a síntese ficar para trás. Isso mantém
    a reprodução falada próxima das legendas na tela.

!!! tip "ElevenLabs sem chave"
    Se você definiu o método TTS para ElevenLabs mas nenhuma chave de
    API está configurada, a página Live cai automaticamente para Edge
    TTS e anuncia o fallback no rótulo de status.

## Atalhos

| Atalho | Ação |
|---|---|
| `Ctrl+Enter` | Iniciar / Parar |
| `Ctrl+K` | Limpar log (com confirmação) |
| `Ctrl+[` / `Ctrl+]` | Ajustar opacidade do overlay |
