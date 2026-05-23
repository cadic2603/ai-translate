---
description: Conecte o Google Cloud ao AI Translate para Vision OCR, Speech-to-Text e Text-to-Speech — configure uma chave de API e habilite os serviços relevantes.
---

# Google Cloud (Vision OCR / Speech-to-Text / Text-to-Speech)

Uma única chave de API do Google Cloud alimenta três backends
opcionais:

- **Vision OCR** — motor OCR pago (1.000 grátis / mês)
- **Speech-to-Text v1** — STT pago (60 minutos / mês grátis)
- **Text-to-Speech v1** — TTS pago (1 M de caracteres / mês grátis
  para WaveNet)

Você só precisa habilitar as APIs que realmente usar.

## Obter uma chave de API

1. [Crie um projeto Google Cloud](https://console.cloud.google.com/projectcreate)
2. Abra a biblioteca de API: <https://console.cloud.google.com/apis/library>
3. Habilite qualquer um destes:
    - [Vision API](https://console.cloud.google.com/apis/library/vision.googleapis.com)
    - [Speech-to-Text API](https://console.cloud.google.com/apis/library/speech.googleapis.com)
    - [Text-to-Speech API](https://console.cloud.google.com/apis/library/texttospeech.googleapis.com)
4. [Crie uma chave de API](https://console.cloud.google.com/apis/credentials):
   clique **+ Create Credentials → API key**
5. Copie a chave (parece `AIza...`).

!!! tip "Restrinja a chave"
    Na página de detalhes da chave de API, em **API restrictions**,
    restrinja a chave apenas às APIs que você habilitou. Dessa forma
    uma chave vazada não pode acumular contas em serviços que você
    não pretendia usar.

## Configurar no app

Em **Configurações → Serviço**:

1. Cole em **Chave de API Google Cloud** → **Salvar**

Esta única chave agora está disponível para todos os três serviços
do Google.

## Habilitar cada serviço

### Vision OCR

Em **Configurações → OCR → Método OCR = Google Cloud OCR**.

É isso — vai usar a mesma chave do Serviço.

### Speech-to-Text

Em **Configurações → Legenda → Método STT = Google Cloud** (para as
páginas Legenda / Voz) ou **Configurações → Live → Método STT =
Google Cloud** (para a página Live).

Em **Configurações → Legenda → Modelo STT Google**, escolha o
modelo de reconhecimento:

| Modelo | Melhor para |
|---|---|
| `latest_long` (padrão) | Áudio de formato longo (entrevistas, palestras) |
| `latest_short` | Comandos de voz, frases curtas |
| `phone_call` | Áudio telefônico (8 kHz) |
| `medical_dictation` / `medical_conversation` | Áudio do domínio médico |

### Text-to-Speech

Em **Configurações → Voz → Método TTS = Google Cloud TTS**.

Por padrão o servidor escolhe uma voz com base em idioma e gênero —
é tudo o que a maioria dos usuários precisa. Fixar uma voz Google
específica (ex. `en-US-Chirp3-HD-Charon`, `vi-VN-Wavenet-A`) é
suportado pelo motor mas ainda não exposto como campo de
Configurações; pode ser definido editando
`voice/google_tts_voice_name` em `settings.ini` diretamente. Os IDs
de voz estão listados em
<https://cloud.google.com/text-to-speech/docs/voices>.

## Erros comuns

| Erro | Causa provável |
|---|---|
| `AUTH_ERROR` | Chave errada / expirada. Cole novamente em Configurações → Serviço. |
| `API not enabled` | Você não habilitou a API específica (Vision / Speech / TTS) neste projeto Cloud. |
| `QUOTA_ERROR` | Limite da camada gratuita atingido para esta API. Espere, ou atualize a cobrança. |
| `INVALID_ARGUMENT_ERROR` | Nome da voz não existe no idioma que você escolheu. |

## Proteção de custos

!!! warning
    Todas as três APIs do Google são pós-pagas — uma vez que você
    excede a camada gratuita começa a ser cobrado sem parar.
    Configure um [alerta de orçamento](https://console.cloud.google.com/billing/budgets)
    no projeto Cloud antes de fazer trabalho de alto volume.
