---
description: Conecte o ElevenLabs ao AI Translate para TTS neural de alta qualidade — gere narrações em mais de 30 idiomas com fala realista e expressiva.
---

# ElevenLabs (TTS)

Síntese de voz neural premium. Usado pelas páginas
**[Gerar voz](../features/generate-voice.md)**,
**[Dublagem](../features/dubbing.md)** e
**[Tradução ao vivo](../features/live-translation.md)** quando você
escolhe ElevenLabs como método TTS.

## Obter uma chave de API

1. Cadastre-se em <https://elevenlabs.io>
2. Abra <https://elevenlabs.io/app/settings/api-keys>
3. Clique em **+ Create New Key**, dê um nome (ex. "ai-translate"),
   copie a chave (parece `sk_...`)

A camada gratuita te dá ~10.000 caracteres / mês, suficiente para
testar. Uso em produção começa por volta de $5/mês.

## Configurar no app

Em **Configurações → Serviço**:

1. Cole a chave em **Chave de API ElevenLabs** → **Salvar**
2. Digite seu **ID da voz** preferido em **ID da voz** (encontre IDs
   em <https://elevenlabs.io/app/voice-lab>; copie o ID da URL de
   uma voz). Deixe em branco para o ElevenLabs escolher um padrão.

Em **Configurações → Voz**:

1. Defina **Método TTS** como **ElevenLabs**
2. Escolha o **Modelo ElevenLabs**:

    | Modelo | Melhor para |
    |---|---|
    | `eleven_multilingual_v2` (padrão) | Uso geral, latência/qualidade balanceadas |
    | `eleven_v3` | Qualidade máxima (use para dublagens de produção) |
    | `eleven_flash_v2_5` | Menor latência (use para Tradução ao vivo) |

## O que ele alimenta

| Página | Use ElevenLabs quando |
|---|---|
| **Gerar voz** | Você quer narrações de qualidade premium a partir de arquivos de legenda |
| **Dublagem** | Você quer uma faixa de dublagem de alta qualidade em um vídeo traduzido |
| **Tradução ao vivo** | Você quer reprodução falada de legendas traduzidas em tempo real |

## Clonagem de voz

ElevenLabs suporta clonagem de voz personalizada (plano pago). Uma
vez que você tenha clonado uma voz no site do ElevenLabs, cole seu
ID de voz em **Configurações → Serviço → ID da voz** e o pipeline
de dublagem / geração de voz o usará.

## Ressalvas

!!! warning "Verificação pre-flight"
    As páginas Voz / Dublagem verificam se sua chave de API ElevenLabs
    está definida *antes* de começar o trabalho. Se estiver faltando,
    você receberá um diálogo amigável apontando para as Configurações,
    não uma tarefa parcialmente executada.

!!! tip "Modo Live cai automaticamente"
    Na página **Tradução ao vivo**, se você selecionou ElevenLabs mas
    não configurou uma chave, o app cai para **Edge TTS** (grátis) e
    anuncia o fallback no rótulo de status para que você possa
    consertar quando for conveniente.

!!! info "FFmpeg ainda necessário"
    ElevenLabs retorna bytes de áudio; o app ainda usa FFmpeg para
    converter entre formatos e combinar clipes com tempo em um
    arquivo. Veja [Configuração do FFmpeg](ffmpeg.md).

## Erros comuns

| Erro | Causa provável |
|---|---|
| `AUTH_ERROR` | Chave de API errada / expirada. Cole novamente em Configurações → Serviço. |
| `QUOTA_ERROR` | Limite de caracteres da camada gratuita atingido, ou plano pago esgotado. |
| `MODEL_NOT_FOUND` | O modelo ElevenLabs selecionado não está mais disponível; escolha outro em Configurações → Voz. |
