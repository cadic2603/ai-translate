---
description: Exponha o AI Translate como ferramentas Model Context Protocol para que Claude Desktop, Claude Code e outros clientes MCP possam traduzir texto, ficheiros e áudio.
---

# Servidor MCP (`ait-mcp`)

Expõe o pipeline de tradução como ferramentas **Model Context
Protocol** para que agentes de IA como Claude Desktop e Claude Code
possam dirigi-lo diretamente — "Traduza este PDF para o francês" se
torna uma chamada de ferramenta, não um copy-paste.

## O que fica exposto

Nove ferramentas:

| Ferramenta | Propósito |
|---|---|
| `translate_text` | Traduzir uma lista de strings |
| `translate_document` | Enfileirar tarefas de tradução de ficheiros (retorna IDs de tarefa) |
| `get_task_status` | Polling do status da tarefa |
| `cancel_task` | Cancelamento cooperativo de tarefas em andamento |
| `extract_image_text` | OCR ou visão LLM |
| `transcribe_audio` | Áudio → SRT |
| `synthesize_speech` | Texto → MP3 / WAV |
| `query_glossary` | Listar conjuntos / entradas de glossário |
| `list_languages` | Todos os 45 idiomas suportados |

## Executar o servidor

```bash
ait-mcp                       # transporte stdio (padrão para agentes desktop)
ait-mcp --transport sse       # Server-Sent Events para clientes web
ait-mcp --transport sse --port 9000
```

`stdio` é o que qualquer cliente MCP espera, a menos que você tenha
configurado SSE explicitamente.

## Adicionar ao Claude Desktop

1. Abra o Claude Desktop → **Settings → Developer → Edit Config**
2. Adicione esta entrada sob `mcpServers`:

    ```json
    {
      "mcpServers": {
        "ai-translate": {
          "command": "uv",
          "args": ["run", "--project", "/absolute/path/to/ai-translate", "ait-mcp"]
        }
      }
    }
    ```

    Substitua `/absolute/path/to/ai-translate` pelo caminho do repo clonado.

3. Saia e reabra o Claude Desktop. O ícone do martelo agora deve
   mostrar "ai-translate" com todas as 9 ferramentas. Tente:

    > "Traduza este PDF (`/home/me/report.pdf`) para o francês — guarde
    > a saída ao lado da fonte."

## Adicionar ao Claude Code

`~/.config/claude-code/mcp_servers.json` (ou `claude mcp add` de
dentro do Claude Code):

```json
{
  "ai-translate": {
    "command": "uv",
    "args": ["run", "--project", "/absolute/path/to/ai-translate", "ait-mcp"]
  }
}
```

Reinicie o Claude Code. As mesmas 9 ferramentas se tornam invocáveis.

## Adicionar a outros clientes MCP

Qualquer cliente compatível com MCP assume uma forma similar:

- **Command** — `uv run --project /path/to/ai-translate ait-mcp`
- **Transport** — stdio (padrão)

Para clientes baseados em HTTP / SSE, execute
`ait-mcp --transport sse --port 9000` e aponte o cliente para
`http://localhost:9000`.

## Garantias de validação

Cada ferramenta retorna a mesma forma em erros para que os agentes
possam lidar com falhas de maneira consistente:

| Entrada ruim | Resposta da ferramenta |
|---|---|
| Idioma desconhecido | `ValueError: Unknown … language '<input>'. Call list_languages to see supported values.` |
| LLM não configurado | `RuntimeError: LLM is not configured. Run the desktop app and set up your API key…` |
| Tipo de ficheiro não suportado | `ValueError` listando extensões permitidas |
| `model="…"` malformado (sem `:`) | `ValueError` em vez de usar silenciosamente o padrão |
| IDs de tarefa desconhecidos em `cancel_task` | Retornados no array `unknown` — sem erro |
| FFmpeg faltando em `transcribe_audio` | `RuntimeError: FFmpeg is required…` (re-empacotado da tag `FFMPEG_NOT_FOUND` crua do motor) |

Os agentes que chamam essas ferramentas podem confiar nesses contratos.

## Concorrência

`translate_document` executa o pipeline em uma thread daemon. Cada
batch recebe seu próprio evento de cancelamento, então cancelar um
batch não perturba outro. O servidor MCP rastreia pipelines ativos
em um mapa local do processo (limpo automaticamente quando o pipeline
termina).

## Casos de uso

- **"Traduza os docs desta codebase para vietnamita"** — aponte o
  agente para a pasta docs, ele faz batch de chamadas
  `translate_document` e faz polling de `get_task_status` até cada
  uma terminar.
- **"Quais idiomas vocês suportam?"** — o agente chama
  `list_languages`, lê a resposta.
- **"Traduza este recibo japonês"** — o agente chama
  `extract_image_text` na foto, depois `translate_text` no resultado.
- **"Gere legendas vietnamitas para esta gravação do Zoom"** — o
  agente chama `transcribe_audio` para obter um SRT no idioma fonte,
  depois `translate_text` em cada cue para localizar, e remonta o SRT.

!!! note "Dublagem de vídeo não é uma ferramenta MCP"
    O pipeline completo STT → traduzir → TTS → mux (a página
    **Dublagem** do app desktop) só está disponível via GUI agora.
    Do MCP você pode compor o equivalente sozinho com
    `transcribe_audio` + `translate_text` + `synthesize_speech`, mas
    precisará lidar com o passo de mux com timing (FFmpeg) externamente.

## Dicas

!!! tip "Configure uma vez, agentes funcionam em todo lugar"
    O servidor MCP compartilha chaves de API e definições com o
    app desktop e o CLI. Configure seu LLM / OCR / TTS uma vez na
    GUI, então qualquer agente que fala com `ait-mcp` herda a mesma
    definição.

!!! tip "Cache de endpoint cold-start"
    Para cada par `(endpoint, modelo)`, a escolha
    chat-vs-responses-API e a variante de payload funcionante são
    persistidas em `llm_endpoint_cache.json` no diretório cache do OS
    (`~/.cache/ai-translate/` no Linux,
    `~/Library/Caches/ai-translate/` no macOS,
    `%LOCALAPPDATA%\ai-translate\cache\` no Windows). Processos
    `ait-mcp` frescos pulam totalmente o probe de auto-detecção após
    a primeira chamada bem-sucedida — agentes que spawn o servidor
    sob demanda não pagam os round-trips de detecção de variantes em
    cada invocação. O cache é seguro multi-processo e multi-thread
    (read-merge-write sob RLock com rename atômico).

!!! tip "Seletor de modelo por ferramenta"
    As ferramentas `translate_text` e `translate_document` aceitam
    um parâmetro `model` opcional — agentes podem escolher um modelo
    rápido para turnos rápidos e um mais pesado para saída de produção
    sem precisar que o utilizador reconfigure o app desktop.

!!! warning "Pipelines de longa duração"
    `translate_document` retorna imediatamente com IDs de tarefa.
    Espera-se que o agente faça polling de `get_task_status` até que
    cada tarefa atinja `Done` ou `Failed`. Não espere síncronamente
    dentro da chamada de ferramenta; isso arrisca o timeout do
    cliente MCP disparar.
