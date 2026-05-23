---
description: Diagnostique problemas do AI Translate — fontes faltando, erros de FFmpeg, problemas do conversor LibreOffice, falhas de definição OCR e autenticação da API LLM.
---

# Solução de problemas

Erros comuns, o que significam e como corrigi-los.

## Erros de definição

### "LLM is not configured"

Você ainda não adicionou uma chave de API. Abra o app desktop →
**Definições → LLM** → cole uma chave. Veja
[Provedores LLM](setup/llm-providers.md) para o guia completo.

### `AUTH_ERROR`

A chave de API LLM está errada ou expirou.

- **Gemini** — gere uma nova chave em
  <https://aistudio.google.com/apikey>, recole em
  **Definições → LLM**.
- **Provedor personalizado** — verifique que a chave é válida (curl
  o endpoint manualmente com o mesmo header
  `Authorization: Bearer …`). Se o endpoint mudou, atualize também o
  campo **Endpoint API**.

### `QUOTA_ERROR`

Você atingiu um limite da camada gratuita ou do plano pago.

- **Camada gratuita Gemini** — a quota de requisições diária varia
  por modelo (veja <https://ai.google.dev/gemini-api/docs/rate-limits>).
  Espere um dia, ou faça upgrade para pago.
- **OpenAI / outros** — verifique seu dashboard de cobrança. Muitos
  provedores têm "spend caps" que pausam requisições quando você os atinge.

### `MODEL_NOT_FOUND`

O nome do modelo que você escolheu não está disponível.

- Provedores personalizados — certifique-se que o modelo está na lista
  **Models** separada por vírgulas em **Definições → LLM**.
- Lista Gemini integrada — troque para um modelo documentado em
  **Definições → LLM → Modelo Gemini padrão**.

### `VISION_NOT_SUPPORTED`

Você escolheu um modelo não-vision e tentou traduzir uma imagem / PDF
escaneado. Troque para um modelo cujo nome contenha `flash`, `pro` ou
`vision` (ex. `gpt-4o` para OpenAI, qualquer variante Gemini Flash ou
Pro atual para Gemini).

## Erros de áudio / vídeo

### `FFMPEG_NOT_FOUND`

FFmpeg não está no PATH. Veja [Definição FFmpeg](setup/ffmpeg.md)
para o comando de instalação do seu OS.

O servidor MCP reembrulha isso como: *"FFmpeg is required to decode
this audio/video file but is not installed or not on PATH."*

### Página Live não mostra legendas

- **Fonte de áudio errada** — abra **Definições → Live → Fonte de
  áudio** e certifique-se que corresponde ao que você realmente quer
  (Microfone / Sistema / Ambos).
- **Mic mutado** — verifique definições de som do OS; o app usa
  seu dispositivo de entrada padrão.
- **Áudio do sistema não configurado** — veja
  [Captura de áudio do sistema](setup/system-audio.md) para os passos
  de loopback macOS / Windows.

### Saída de voz silenciosa / vazia

- **ElevenLabs sem chave** — a página Voice mostra um diálogo amigável
  pre-flight; se passou, o ficheiro pode ser bytes vazios. Verifique
  **Definições → Service → ElevenLabs API key**.
- **Erro de rede Edge TTS** — Edge TTS requer internet; se seu firewall
  bloqueia `speech.platform.bing.com`, troque para ElevenLabs, Google
  Cloud TTS, ou **Piper TTS** (completamente offline).

### Diálogo "Piper voice not installed"

As páginas Voice / Dubbing / Translate Text verificam pre-flight que
a voz Piper para seu idioma alvo está em disco antes de qualquer
worker começar. Se não estiver, você verá um modal com botão
**Abrir Definições**.

Para descarregar a voz:

1. Clique em **Abrir Definições** no diálogo (ou abra
   **Definições → Voz** manualmente).
2. Certifique-se que **Método TTS** está em **Piper TTS**.
3. Clique em **Descarregar vozes agora** para abrir o diálogo da biblioteca
   de vozes.
4. Encontre a linha do seu idioma alvo, depois clique em **Female
   voice** ou **Male voice** ao lado. As vozes são ficheiros ONNX de
   ~25–60 MB descarregados do HuggingFace; uma vez por idioma.
5. Feche o diálogo e re-execute seu job de tradução / voice / dub.

Se seu idioma alvo não está na lista, ele não tem cobertura Piper —
o motor cai silenciosamente para Edge TTS na hora da síntese, então
você não precisa descarregar nada de fato. Os 13 idiomas sem vozes Piper
hoje: bielorrusso, bengali, chinês (tradicional), croata, estoniano,
hebraico, japonês, khmer, coreano, lituano, malaio, mongol, tailandês.

A página **Tradução ao vivo** é o único lugar que *não* mostrará este
diálogo — interromper um stream ao vivo com modal seria pior que o
fallback, então casos de voz faltando ali vão silenciosamente para
Edge TTS.

## Erros de tradução de documento

### Tradução PDF falha em uma página específica

PDFs usam checkpointing por página — páginas bem-sucedidas não são
refeitas. A página falhada loga um stack em `app.log`; culpados comuns:

- A página é uma **digitalização sem camada de texto** e OCR não está
  configurado. Configure **Definições → OCR** (veja
  [Motores OCR](setup/ocr-engines.md)).
- A página contém **layout matemático complexo** que o LLM bagunçou.
  Tente um modelo mais forte (uma variante Pro em vez de Flash).

### Tradução Office quebra a formatação

- **Formatos modernos** (`.docx`, `.xlsx`, `.pptx`) — a formatação é
  preservada por run via round-trip HTML. Se você ver tags `<b>`
  perdidas na saída, o LLM não as fechou — re-execute com um modelo
  mais forte.
- **Formatos legacy** (`.doc`, `.xls`, `.ppt`) — ative
  **Definições → Tradução → Auto-convert legacy** para fidelidade
  muito melhor. O pipeline converte para `.docx` primeiro, traduz,
  reconverte.

### Fila de tradução para no meio do batch

Saia do app e verifique o banco de dados:

```bash
sqlite3 ~/.local/share/ai-translate/translator.db \
  "SELECT id, status, error_code, file_name FROM history WHERE status NOT IN ('Done', 'Failed') ORDER BY created_at DESC LIMIT 10;"
```

Linhas `Translating` que não foram tocadas em minutos significam que
um worker crashou silenciosamente. Re-lance o app desktop — auto-retoma
tarefas Pending / Translating na inicialização.

## Problemas transversais

### Múltiplos ficheiros de uma vez traduzidos silenciosamente como um

Solte um ficheiro de cada vez, OU verifique a coluna **Files** no
cabeçalho da fila — deve mostrar a contagem que você soltou. O cap de
100 ficheiros mostra uma notificação quando excedido.

### Sidebar mostra um spinner para sempre

Indica que um worker ainda está marcado como em execução. Saia do app
limpamente (sem SIGKILL) — os hooks de cleanup autouse resetam as
flags. Se um SIGKILL deixou estado preso, limpe os workers DB
manualmente:

```bash
sqlite3 ~/.local/share/ai-translate/translator.db \
  "UPDATE history SET status='Failed', error_code=99 WHERE status IN ('Pending', 'Translating');"
```

### Onde estão os logs? {: #where-are-the-logs }

| OS | Caminho |
|---|---|
| **Linux** | `~/.local/state/log/ai-translate/app.log` |
| **macOS** | `~/Library/Logs/ai-translate/app.log` |
| **Windows** | `%LOCALAPPDATA%\ai-translate\logs\app.log` |

Logs sempre capturam DEBUG+ independente da verbosidade do console.
Saída do console é INFO+ por padrão; passe `--verbose` para o CLI
para espelhar o log de ficheiro completo em stdout.

## Ainda preso?

- Veja a [FAQ](faq.md) para perguntas a nível de design.
- Abra um issue em <https://github.com/cadic2603/ai-translate/issues>
  com: OS, versão Python, o comando que falha, o trecho relevante do
  `app.log`, e uma descrição do que você esperava.
