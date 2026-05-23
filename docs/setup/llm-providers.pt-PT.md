---
description: "Configure provedores de LLM para tradução: Google Gemini (recomendado), endpoints compatíveis com OpenAI, ou qualquer provedor personalizado com chave de API."
---

# Provedores LLM

O pipeline de tradução chama um Large Language Model para a
tradução real. Você pode configurar um ou muitos; o seletor de
modelo por funcionalidade permite que cada página use um diferente.

## Google Gemini (recomendado para definição inicial) {: #google-gemini-recommended-for-first-time-setup }

A camada gratuita é generosa e boa o suficiente para a maioria do
uso pessoal.

1. Vá para <https://aistudio.google.com/apikey>
2. Clique em **Create API key** (faça login com sua conta Google)
3. Copie a chave (parece `AIza...`)
4. No app desktop: **Definições → LLM → Chave de API Gemini** →
   cole → **Guardar**
5. Escolha um modelo padrão no menu suspenso **Modelo Gemini
   padrão**. A linha do Google tende a parecer:

    - Variantes **Flash** (ex. `gemini-2.5-flash`) — rápido, camada
      gratuita generosa, boa qualidade. Ponto de partida
      recomendado.
    - Variantes **Pro** — mais lento, qualidade superior, mais caro.
    - **Flash-lite** — mais rápido, mais barato, qualidade inferior.

    Os nomes exatos dos modelos disponíveis dependem do que o Google
    lançou para sua conta; escolha um cujo nome contenha `flash`
    para um padrão equilibrado.

Pronto. A chave é armazenada no chaveiro do seu SO, não em texto
puro.

### Modo Vertex AI (empresarial)

Dentro do bloco de definição do Gemini, um par de rádios permite
alternar de **Developer API** para **Vertex AI** — os mesmos modelos
Gemini, faturados via sua conta GCP, com controles a nível
organizacional (VPC-SC, logs de auditoria, residência regional de
dados).

1. Em **Definições → LLM**, mude o rádio Gemini de **Developer
   API** para **Vertex AI**
2. Preencha:
    - **Project** — seu ID de projeto GCP
    - **Location** — uma região Vertex (padrão `us-central1`)
    - **Credentials path** *(opcional)* — caminho para um ficheiro
      JSON de chave de service account. Deixe em branco para usar
      as Application Default Credentials
      (`gcloud auth application-default login`)
3. **Guardar**. O menu suspenso de modelos repopula a partir do
   Vertex assim que o projeto estiver definido.

A atualização OAuth é tratada automaticamente pelo `google-genai`.
O caminho JSON da service account é armazenado em texto puro de
propósito (o *caminho* não é um segredo — o conteúdo do ficheiro é,
e ele permanece no disco onde a melhor prática documentada do
Google o mantém).

## OpenAI / Compatível com OpenAI

Qualquer coisa que exponha uma API REST compatível com OpenAI
funciona — o próprio OpenAI, Anthropic via [proxy LiteLLM](https://docs.litellm.ai),
Ollama local, LM Studio, vLLM, Together.ai, Groq, e assim por
diante.

Em **Definições → LLM**:

1. Clique em **Add Custom Provider**
2. Preencha:
    - **Name** — um rótulo como "OpenAI" / "Local Ollama" /
      "Anthropic"
    - **API endpoint** — a URL base (ex. `https://api.openai.com/v1`
      ou `http://localhost:11434/v1` para Ollama)
    - **API key** — deixe em branco para endpoints locais não
      autenticados
    - **Models** — lista separada por vírgulas (ex. `gpt-4o-mini,
      gpt-4o, gpt-3.5-turbo`)
3. Clique em **Save**.

Os provedores personalizados são armazenados como um blob JSON no
chaveiro do SO (chaves de API incluídas).

## Trocar modelo padrão

O menu suspenso **Modelo Gemini padrão** em **Definições → LLM**
define um fallback usado por cada página de funcionalidade que não
tem seu próprio seletor.

Páginas com seu próprio seletor de modelo:

- **Traduzir texto** — `aba de definições Traduzir texto → Modelo padrão`
- **Traduzir documento** — escolhe por tarefa; cai para o padrão
- **Legenda / Voz / Dublagem / Live / Extrair texto** — cada uma
  tem seu próprio padrão por funcionalidade na sua aba de
  Definições

Isso permite misturar e combinar: Flash grátis para live, Pro para
grandes documentos, Ollama local para dados sensíveis.

## Onde as chaves são armazenadas

| SO | Armazenamento |
|---|---|
| **macOS** | Chaveiro (login keychain) |
| **Windows** | Gerenciador de Credenciais |
| **Linux (GNOME)** | Secret Service (gnome-keyring / KWallet) |
| **Linux (sem daemon)** | Cai para INI em texto puro em `~/.config/ai-translate/settings.ini` |

O valor INI de fallback é migrado para o chaveiro na primeira leitura
sempre que um chaveiro se torna disponível — sem passo manual.

## Instalação headless / servidor

Sem uma sessão de desktop, você ainda pode definir chaves via o CLI
`keyring` do Python (após `uv sync`):

```bash
# Gemini
uv run keyring set ai-translate llm/gemini_api_key

# Provedores personalizados (cole o blob JSON — veja a UI de Definições para o esquema)
uv run keyring set ai-translate llm/custom_providers
```

Ou defina as mesmas chaves INI diretamente em `settings.ini` — o
app as migra para o chaveiro na primeira leitura. O ficheiro está
em:

- **Linux** — `~/.config/ai-translate/settings.ini`
- **macOS** — `~/Library/Preferences/ai-translate/settings.ini`
- **Windows** — `%APPDATA%\ai-translate\settings.ini`

## Testando sua definição

Verificação rápida:

```bash
uv run ait --version
echo "Hello world." > /tmp/x.txt
uv run ait /tmp/x.txt --target Portuguese --quiet
cat /tmp/x_translated__pt.txt
```

Se você ver "Olá mundo." — você terminou.

## Erros comuns

| Erro | Causa provável |
|---|---|
| `AUTH_ERROR` | Chave de API errada / expirada. Cole novamente em Definições. |
| `QUOTA_ERROR` | Solicitações-por-dia da camada gratuita excedidas. Espere, ou pague. |
| `MODEL_NOT_FOUND` | A lista `models` do provedor personalizado não inclui o modelo solicitado. |
| `VISION_NOT_SUPPORTED` | O modelo que você escolheu não pode fazer entrada de imagem. Use uma variante `flash` / `pro` / `vision`. |

Veja [Solução de problemas](../troubleshooting.md) para mais.
