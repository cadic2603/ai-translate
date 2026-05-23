---
description: Configure o Soniox para transcrição de fala em tempo real na página Live do AI Translate — suporta diarização de falantes, termos de glossário e tradução ao vivo.
---

# Soniox (STT)

Transcrição de fala em tempo real via a API WebSocket do Soniox.
Usado pelas páginas **[Legenda](../features/generate-subtitle.md)** e
**[Tradução ao vivo](../features/live-translation.md)** quando você
escolhe Soniox como método STT.

## Por que Soniox

- **Tempo real** — os tokens chegam enquanto o falante ainda está
  falando.
- **Diarização de falantes** — rótulos de falante por token
  (ex. _Falante 1: Oi…_).
- **Tradução em stream** — Soniox pode traduzir enquanto transcreve,
  economizando uma viagem LLM extra.
- **Multi-idioma** — auto-detecta o idioma de origem mesmo no meio
  do stream.

## Obter uma chave de API

1. Cadastre-se em <https://console.soniox.com>
2. Abra **API keys** → **Create new API key**
3. Copie (parece `Bearer ...`; copie apenas o token sem o prefixo
   `Bearer `).

O preço é medido por minuto de áudio (~$0,005 / minuto no momento da
escrita) — veja <https://soniox.com/pricing>.

## Configurar no app

Em **Definições → Serviço**:

1. Cole a chave em **Chave de API Soniox** → **Guardar**

Em **Definições → Live** *(para tradução ao vivo)* ou
**Definições → Legenda** *(para geração de legenda)*:

1. Defina **Método STT** como **Soniox**

## O que ele alimenta

| Página | Use Soniox quando |
|---|---|
| **Legenda** | Gravações multi-falante (entrevistas, painéis, reuniões) onde você quer rótulos de falante no SRT |
| **Tradução ao vivo** | Legendagem de reuniões em tempo real, especialmente com múltiplos falantes |

## Termos de glossário

O WebSocket do Soniox aceita um glossário de termos para influenciar
o reconhecimento. O app encaminha automaticamente suas entradas de
glossário ativas — nomes de marcas / nomes próprios / jargão são
reconhecidos com mais confiabilidade.

## Resguardas

!!! warning "Apenas online"
    Soniox é apenas cloud; se seu áudio é sensível (médico, jurídico),
    use Whisper (local) em vez disso.

!!! info "Reconexão"
    O WebSocket se reconecta automaticamente em falhas transitórias
    com backoff exponencial. Sessões longas permanecem conectadas
    através de breves interrupções de rede.

## Erros comuns

| Erro | Causa provável |
|---|---|
| `AUTH_ERROR` | Chave de API errada / expirada. Cole novamente em Definições → Serviço. |
| `QUOTA_ERROR` | Limite do plano excedido. |
| `CONNECTION_ERROR` | Rede bloqueada / firewall. Tente novamente de uma rede diferente. |
