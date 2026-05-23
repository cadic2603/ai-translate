---
description: "Perguntas comuns sobre AI Translate: formatos de ficheiro suportados, recursos gratuitos vs pagos, uso offline, escolhas de provedor LLM e seleção de motor OCR."
---

# Perguntas frequentes

## Geral

### Funciona offline?

Em grande parte sim. Especificamente:

- **A tradução** precisa de um LLM. A API Gemini gratuita é online;
  **Ollama / LM Studio local** através das definições de Provedor
  Personalizado é completamente offline.
- **OCR** com **Tesseract** ou **EasyOCR** é offline.
- **STT** com **Whisper** (padrão) é offline.
- **TTS** com **Edge TTS** (padrão) é online; **ElevenLabs** /
  **Google Cloud TTS** / **Gemini TTS** são online (gratuitos ou pagos);
  **Piper TTS** é TTS neural completamente offline — sem chave, sem
  chamadas de rede uma vez baixada a voz por idioma (ficheiro ONNX de
  ~25–60 MB) via **Definições → Voz → Piper TTS → Descarregar vozes agora**.

Para um setup totalmente air-gapped: Provedor Personalizado → LLM
local, Tesseract ou EasyOCR para OCR, Whisper para STT, e Piper TTS
para saída de voz.

### Onde meus ficheiros traduzidos são guardados?

Ao lado do original por padrão, com sufixo `_translated_<src>_<tgt>`
(ex. `report_translated_en_fr.docx`). Sobrescreva por funcionalidade
em **Definições → Geral → Caminho de armazenamento de traduções**.

### Onde minhas definições são armazenadas?

Ficheiro INI em:

| OS | Caminho |
|---|---|
| **Linux** | `~/.config/ai-translate/settings.ini` |
| **macOS** | `~/Library/Preferences/ai-translate/settings.ini` |
| **Windows** | `%APPDATA%\ai-translate\settings.ini` |

Chaves de API ficam no chaveiro do OS (não no INI). O histórico de
tradução fica em um BD SQLite no diretório de dados.

### Como meus dados são manipulados?

- **Local-first** — texto nunca deixa sua máquina a menos que você
  esteja chamando um serviço LLM / OCR / STT / TTS na nuvem.
- **Sem telemetria** — o app não chama de volta. A única requisição
  de saída que o app faz por si só é a verificação opcional de
  atualização do GitHub Releases (toggle em
  **Definições → Geral**); backends de nuvem só chamam seus
  respectivos vendedores.
- **Chaves de API** — armazenadas no chaveiro do seu OS. O fallback
  do chaveiro do app desktop é um INI em texto plano quando nenhum
  daemon de chaveiro está disponível.

### Posso traduzir um Google Doc / página Notion?

Não diretamente. Exporte para `.docx` primeiro, traduza, depois
importe o ficheiro traduzido de volta. Mesma coisa para Notion (exporte
como Markdown / HTML), Confluence (exporte como `.docx`), etc.

## Escolhendo modelos / motores

### Qual modelo LLM devo usar?

Para a maioria dos utilizadors:

- **Qualquer variante Gemini Flash** — camada gratuita, rápido,
  surpreendentemente bom. Use para traduções diárias. Os nomes parecem
  `gemini-2.5-flash`, `gemini-3-flash-preview`, etc., dependendo do
  que está disponível.
- **Qualquer variante Gemini Pro** — pagamento por token, qualidade
  superior. Use para documentos importantes (legais, técnicos, voltados
  ao cliente).
- **Ollama local** com um modelo 7B-13B — quando você precisa de
  offline / privacidade.

O seletor de modelo por funcionalidade significa que você pode usar
um modelo rápido para tradução estilo chat e reservar o caro para
documentos.

### Qual motor OCR devo usar?

- **Tesseract** para texto impresso limpo nos scripts principais.
  Gratuito, offline, rápido.
- **EasyOCR** para scripts não-latinos (CJK especialmente) e imagens
  mais ruidosas.
- **Google Cloud Vision** para escrita à mão, scripts mistos, e a
  maior precisão quando você puder pagar.

### Qual método STT devo usar?

- **Whisper local** para offline / privacidade.
- **Soniox** para gravações multi-falantes — labels de falante fazem
  round-trip no seu SRT.
- **Google Cloud STT** para áudio telefônico / médico (seus modelos
  de domínio são bons).
- **Gemini Live** para tradução speech-to-speech em tempo real.

### Qual backend TTS?

- **Edge TTS** para vozes gratuitas de alta qualidade.
- **ElevenLabs** para vozes premium / com marca / clonadas.
- **Google Cloud TTS** para vozes WaveNet em idiomas long-tail onde
  Edge tem cobertura rala.
- **Gemini TTS** para vozes prebuilt naturais gratuitas reusando sua
  chave de API Gemini existente.
- **Piper TTS** quando você precisa de saída de voz **offline /
  air-gapped**. Trade-off: cada idioma precisa de um download único de
  voz de ~25–60 MB via **Definições → Voz → Piper TTS → Descarregar
  vozes agora**, e 13 dos 45 idiomas do app não têm voz Piper (esses
  caem silenciosamente para Edge TTS).

## Workflow

### Como traduzo uma pasta inteira?

Solte a pasta na drop zone de **Traduzir documento**. Ficheiros
suportados dentro (recursivamente) entram na fila; tudo o mais é
silenciosamente ignorado. Há um cap de 100 ficheiros por drop; lotes
maiores → divida em múltiplos drops.

### Posso pausar e retomar traduções?

Sim. Saia do app a qualquer momento — tarefas Pending / Translating
retomam no próximo lançamento. O checkpointing por tarefa significa
que a página 47 de 100 de um PDF não é refeita quando você retoma.

### Posso editar uma tradução à mão?

Para **Traduzir texto** — sim, clique no painel direito e digite. A
edição guarda automaticamente no registo de histórico da entrada.

Para **Traduzir documento** — abra o ficheiro traduzido no seu editor
habitual (Word, LibreOffice, etc.) e edite lá. O app não faz
round-trip das edições de volta no histórico.

### Posso traduzir em massa uma lista de strings?

Use o CLI:

```bash
ait *.txt --target French
```

Ou para strings in-process (ex. strings UI extraídas do código),
chame a ferramenta MCP `translate_text` com uma lista, ou use a API
Python diretamente:

```python
from src.core.llm_engine import translate_text
out = translate_text(texts=["Hello", "World"], target_lang="French")
```

## Glossário

### Por que o LLM não está usando meu glossário?

Três coisas para verificar:

1. O conjunto está **ativo** (checkbox marcado).
2. O termo fonte no seu glossário aparece de fato no texto fonte (a
   compressão por chamada só envia ao LLM as entradas que correspondem
   ao texto do batch — economiza tokens, mas significa que um termo
   fonte com erro de digitação é invisível).
3. O modelo é forte o suficiente — `flash-lite` às vezes ignora dicas
   que `flash` e `pro` honram.

### Termos do glossário são pareados independente de acentos?

Sim. Tanto a busca do glossário quanto a barra de busca na página
Glossário usam uma função de normalização que remove acentos e case.
Então `cafe`, `Café` e `CAFE` todos correspondem a uma entrada cuja
fonte é `Café`.

## Privacidade

### Vocês coletam dados de uso?

Não. O app não tem SDK de analytics. A verificação opcional de
atualização consulta um único endpoint GitHub Releases na inicialização;
é togglable em **Definições → Geral**.

### Minhas chaves de API estão seguras?

São armazenadas no chaveiro do seu OS (Keychain no macOS, Credential
Manager no Windows, Secret Service no Linux). Outros processos não
podem lê-las sem sua permissão explícita. O fallback (quando nenhum
daemon de chaveiro está disponível — tipicamente servidores Linux
headless) é um INI em texto plano sob o diretório de definição do
seu utilizador; nesse modo as chaves são protegidas por permissões de
ficheiro mas não criptografadas.
