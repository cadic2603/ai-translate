---
description: Converta legendas em áudio falado com Edge TTS, ElevenLabs, Google Cloud TTS, Gemini TTS ou Piper TTS offline — preserva o timing SRT para geração de voz com qualidade de dublagem.
---

# Gerar voz (TTS)

Sintetize arquivos de legenda (com timing) ou texto arbitrário em
áudio MP3 / WAV. Cinco backends TTS: Edge TTS (gratuito), ElevenLabs
(alta qualidade), Google Cloud TTS, Gemini TTS (camada gratuita) e
Piper TTS (offline).

## O que você precisa

- **FFmpeg** no `PATH` — veja [Configuração do FFmpeg](../setup/ffmpeg.md).
- Um backend TTS, um destes:
    - **Edge TTS** — gratuito, sem chave, padrão. Usa as vozes na
      nuvem do Microsoft Edge.
    - **ElevenLabs** — pago, qualidade máxima. Veja [Configuração do ElevenLabs](../setup/elevenlabs.md).
    - **Google Cloud TTS** — pago, muito bom. Veja [Configuração do Google Cloud](../setup/google-cloud.md).
    - **Gemini TTS** — camada gratuita, vozes pré-construídas
      naturais. Reutiliza sua chave API do Gemini existente da aba
      LLM — sem configuração extra.
    - **Piper TTS** — TTS neural totalmente offline. Sem chave de API,
      sem chamadas de rede — as vozes são arquivos ONNX de
      ~25–60 MB baixados uma vez via **Configurações → Voz → Piper
      TTS → Baixar vozes agora**. 32 dos 45 idiomas do app têm uma
      voz Piper hoje; idiomas sem cobertura Piper caem silenciosamente
      para Edge TTS no momento da síntese.

## Passo a passo

1. Clique em **Gerar voz** na barra lateral.
2. Solte um ou mais arquivos de legenda `.srt` / `.vtt` /
   `.ass` / `.ssa`.
3. Escolha o **Idioma** (auto-detectado a partir do nome do arquivo
   de legenda quando possível — ex. `_translated_en_pt.srt` é
   detectado como português).
4. Escolha o **Gênero da voz** — `Feminino` ou `Masculino`.
5. Escolha o **Formato de saída** — `.mp3` (padrão) ou `.wav`.
6. Clique em **Gerar** (ou `Ctrl+Enter`).
7. **Abra** a linha quando concluído — toca no seu app de áudio
   padrão.

## Saída

Você obtém um único arquivo de áudio com as faixas de voz
posicionadas no timestamp de cada legenda. Lacunas silenciosas
preenchem o tempo entre cues para que o áudio permaneça em
sincronia com o timing original.

## Escolhendo um backend TTS

| Backend | Custo | Vozes | Notas |
|---|---|---|---|
| **Edge TTS** | Gratuito | Centenas, todos os idiomas principais | Padrão. Sem configuração. |
| **ElevenLabs** | Pago (~$5/mês camada de entrada) | Vozes neurais premium, clonagem de voz | Qualidade máxima. ID da voz é definido em Configurações → Serviço. |
| **Google Cloud TTS** | Pago (~$4/M caracteres; 1 M grátis / mês) | Vozes WaveNet / Studio em 50+ idiomas | Vozes WaveNet fortes para idiomas europeus. Por padrão o servidor escolhe uma voz com base em idioma + gênero. |
| **Gemini TTS** | Camada gratuita (cotas Developer API se aplicam) | Vozes pré-construídas naturais em 24+ idiomas — `Kore` (feminino padrão) / `Puck` (masculino padrão) | Reutiliza sua chave API do Gemini da aba LLM. Saída por chamada limitada a ~30 s; textos longos divididos automaticamente em limites de frase. |
| **Piper TTS** | Gratuito, **offline** | Vozes neurais em 32 dos 45 idiomas do app | Sem chave, sem rede. Voz por idioma baixada sob demanda em **Configurações → Voz → Piper TTS → Baixar vozes agora** (~25–60 MB cada). Pre-flight pega uma voz faltante antes do trabalho começar. |

Mude em **Configurações → Voz → Método TTS**.

## Especificidades do Piper TTS

Piper é o único backend TTS totalmente offline no app. Algumas
coisas a saber:

- **Diálogo da biblioteca de vozes** — abra via **Configurações →
  Voz → Piper TTS → Baixar vozes agora**. Cada linha de idioma
  mostra um botão de download `Voz feminina` e / ou `Voz masculina`
  (alguns idiomas são de gênero único). As vozes vêm do catálogo
  HuggingFace
  [rhasspy/piper-voices](https://huggingface.co/rhasspy/piper-voices).
- **Cobertura** — 32 dos 45 idiomas do app têm uma voz Piper. Os 13
  sem cobertura (bielorrusso, bengali, chinês (tradicional), croata,
  estoniano, hebraico, japonês, khmer, coreano, lituano, malaio,
  mongol, tailandês) caem silenciosamente para Edge TTS no momento
  da síntese, então a síntese nunca falha duramente em uma voz
  faltante.
- **Resolução de gênero** — quando você escolhe `Feminino`, o motor
  primeiro tenta a voz feminina para esse idioma; se apenas uma voz
  masculina existir, ele usa essa em vez (e vice-versa). Registrado
  no nível INFO.
- **Portão pre-flight** — antes de uma execução de Voz começar, a
  página verifica que a voz Piper por idioma está em disco. Se
  faltando, você obtém um diálogo modal com um botão **Abrir
  Configurações** que te leva direto para a biblioteca de vozes
  para baixá-la sem perder sua fila.

## Especificidades do Gemini TTS

Gemini TTS usa `gemini-2.5-flash-preview-tts` via a Developer API.
Algumas coisas a saber:

- **Seleção de voz** é por gênero hoje — Feminino mapeia para
  `Kore`, Masculino para `Puck`. Ambas são vozes claras, neutras que
  funcionam em vários idiomas sem soar muito caracterizadas.
- **Limite de comprimento de saída** — cada chamada API Gemini
  retorna no máximo ~30 s de fala. O app divide o texto de entrada
  abaixo de `_GEMINI_TTS_MAX_BYTES` (~2000 bytes ≈ 30 s) em limites
  de frase, então concatena os pedaços via FFmpeg. Você não vai
  encontrar truncamento em texto de legenda normal.
- **Formato de áudio** — Gemini emite PCM bruto a 24 kHz mono
  s16le; o app transcoda por pedaço para MP3 (ou WAV se você
  escolheu) para que o arquivo final corresponda ao seu formato de
  saída selecionado.
- **Vertex AI ainda não é suportado para TTS** — mesmo se sua aba
  LLM estiver configurada para Vertex, Gemini TTS ainda precisa de
  uma chave API Developer. O app levanta `AUTH_ERROR` antecipadamente
  se faltando.

## Modelos ElevenLabs

Três modelos são expostos:

| Modelo | Latência | Qualidade | Usar para |
|---|---|---|---|
| `eleven_multilingual_v2` (padrão) | Média | Alta | TTS geral |
| `eleven_v3` | Média | Máxima | Studio / produção |
| `eleven_flash_v2_5` | Baixa | Boa | Tempo real / modo Live |

Configure em **Configurações → Voz → Modelo ElevenLabs**.

## Dicas

!!! tip "Re-gerar"
    Clique direito em uma linha → **Re-gerar** para trocar gênero da
    voz / método TTS / formato sem reexecutar a tradução.

!!! tip "Verificações pre-flight"
    A página valida a chave API ElevenLabs (quando selecionada) e a
    disponibilidade do FFmpeg antes de começar. Você verá um diálogo
    amigável se algo estiver faltando.

!!! warning "Stop é atômico"
    Aperte **Stop** durante a síntese e você não ficará com um MP3
    semi-escrito no diretório de saída — o arquivo é escrito em uma
    localização temporária primeiro, depois movido para o lugar
    apenas em sucesso.

## Atalhos

| Atalho | Ação |
|---|---|
| `Ctrl+Enter` | Gerar |
| `Ctrl+O` | Procurar |
| `Ctrl+F` | Focar busca de histórico |
