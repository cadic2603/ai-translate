---
description: Traduza PDFs, Word, Excel, PowerPoint, ODF, EPUB, HTML, JSON, YAML, SRT e mais de 30 outros formatos de ficheiro preservando formatação e layout.
---

# Traduzir documento

Traduza ficheiros completos — Office, PDF, EPUB, texto simples,
legendas, formatos de localização e mais — com a formatação preservada.

## Formatos suportados

| Categoria | Extensões |
|---|---|
| Office | `.docx`, `.xlsx`, `.pptx`, `.odt`, `.ods`, `.odp`, `.doc`, `.xls`, `.ppt` |
| PDF | `.pdf` |
| Texto & web | `.txt`, `.md`, `.rst`, `.html`, `.htm`, `.xhtml`, `.xml`, `.rtf`, `.json`, `.csv` |
| eBooks | `.epub` |
| Legendas | `.srt`, `.vtt`, `.ass`, `.ssa` |
| Localização | `.po`, `.pot`, `.xliff`, `.xlf`, `.yaml`, `.yml`, `.properties`, `.strings` |

## Passo a passo

1. Clique em **Traduzir documento** na barra lateral.
2. Arraste ficheiros (ou clique em **Procurar**). Pastas também
   funcionam — ficheiros suportados dentro são pegos recursivamente.
3. Escolha **Origem** (ou deixe em `Detecção automática`) e **Destino**.
4. Clique em **Traduzir** — ou pressione `Ctrl+Enter`.
5. A tabela de histórico abaixo mostra o progresso por ficheiro
   (Pendente → Traduzindo → Concluído / Falhou). A barra lateral
   mostra um spinner enquanto qualquer tarefa está ativa.
6. Clique em **Abrir** em uma linha para abrir o ficheiro traduzido.
   Clique com o botão direito para opções: retraduzir, pausar, tentar novamente,
   eliminar.

## Onde os ficheiros terminam

Por padrão, os ficheiros traduzidos são guardados ao lado do original com
um sufixo `_translated_<src>_<tgt>`:

```
~/Documents/relatorio.docx
~/Documents/relatorio_translated_en_pt.docx     ← aqui
```

Mude isso em **Definições → Geral → Caminho de armazenamento de
traduções** para um diretório personalizado.

## Limites e proteções

- **Limite de 100 ficheiros por arrastar** — arraste mais e você
  receberá uma notificação. Traduza em lotes.
- **Detecção de duplicados** — arraste um ficheiro já na fila e você
  verá uma notificação (o duplicado é descartado, não adicionado duas
  vezes).
- **Auto-retomada** — saia do app enquanto traduções estão rodando e
  elas retomarão no próximo lançamento (tarefas Pendente / Traduzindo).

## Opções específicas do Office

A aba Tradução em **Definições** expõe estas alternâncias para
ficheiros Office:

| Opção | O que faz |
|---|---|
| **Traduzir imagens incorporadas** | Roda OCR + visão LLM em imagens dentro de `.docx` / `.xlsx` / `.pptx` e re-insere a imagem traduzida. Requer OCR configurado. |
| **Traduzir comentários** | Comentários / notas de revisão são traduzidos junto com o texto do corpo. |
| **Traduzir formas & caixas de texto** | Captura texto que vive em formas, balões e caixas de texto flutuantes. |
| **Traduzir notas do apresentador** | As notas do apresentador do PowerPoint são traduzidas. |
| **Traduzir nomes das planilhas** | As etiquetas das abas de planilhas Excel são traduzidas. |
| **Auto-converter legado** | `.doc` / `.xls` / `.ppt` são convertidos para OOXML moderno antes da tradução (melhor fidelidade). |
| **Auto-converter ODF** | `.odt` / `.ods` / `.odp` são convertidos para OOXML antes da tradução. |

Toda a tradução Office preserva a formatação por run: negrito,
itálico, sublinhado, tachado, tamanho da fonte, cor, hiperlinks,
cabeçalhos, rodapés, notas de rodapé, notas finais, tudo isso.

### Tradução de imagens incorporadas: pular-com-aviso + cache

Quando **Traduzir imagens incorporadas** está ativado, cada
imagem incorporada passa por OCR → visão LLM → reinjeção
processada. Dois comportamentos que vale a pena conhecer:

- **Pular-com-aviso**: se uma imagem falhar ao traduzir
  (demasiado grande, corrompida, o modelo de visão rejeita
  o formato, etc.) o documento mesmo assim é concluído —
  a imagem quebrada permanece no idioma original, um aviso
  é registado em `app.log` e o ciclo continua com a
  imagem seguinte. Apenas erros fatais de LLM
  (`AUTH_ERROR`, `QUOTA_ERROR`, `VISION_NOT_SUPPORTED`)
  param a pipeline imediatamente, pois também bloqueiam
  todas as imagens restantes. O banner informativo acima
  da caixa de verificação **Traduzir imagens incorporadas**
  documenta a política inline.
- **Cache por imagem**: traduções de imagens bem-sucedidas
  são persistidas no diretório de armazenamento interno da
  tarefa com chave SHA256 dos bytes de origem. Em nova
  tentativa, as imagens já traduzidas atingem o cache em
  vez de executar novamente OCR + LLM — o trabalho pago
  não é repetido. Imagens duplicadas (um logótipo da
  empresa em cada diapositivo) são traduzidas uma vez e
  reutilizadas N − 1 vezes.

O ficheiro de saída só aparece na pasta de saída
escolhida em caso de **sucesso** — traduções parciais de
execuções canceladas ou com falha permanecem confinadas
ao diretório de armazenamento interno da tarefa, pelo
que a sua pasta de saída nunca acumula documentos
órfãos traduzidos a meio.

## Especificidades de PDF

PDFs usam um motor de extração-sobreposição: o texto original é
redigido no lugar e o texto traduzido sobreposto nas mesmas caixas,
mantendo o layout visual. O checkpoint por página significa que uma
execução pausada / bloqueada retoma de onde parou, não da página 1.

O que é traduzido:

- Texto do corpo (com detecção de alinhamento — esquerda / centro /
  direita / justificado)
- Marcadores / sumários (entradas de TOC)
- Campos de formulário (entradas de texto, listas suspensas, caixas
  de listagem)
- Hiperlinks (retângulo do link atualizado para envolver o novo texto)
- Imagens incorporadas (quando **Traduzir imagens incorporadas** está
  ligado)
- Comentários / anotações de PDF

Para PDFs escaneados (sem camada de texto incorporada), o OCR roda
automaticamente por página. Configure seu motor OCR em
**Definições → OCR**.

## Saída da direita para a esquerda

Traduções para **árabe**, **hebraico** ou **persa** renderizam como
RTL nativamente em todo formato de saída — `dir="rtl"` injetado em
sobreposições de PDF, HTML e capítulos EPUB (com
`page-progression-direction="rtl"` no OPF do EPUB para que Apple Books
e Kindle virem páginas na direção correta); DOCX `<w:bidi/>` +
`<w:rtl/>`, PPTX `rtl="1"`, visualização de planilha XLSX da direita
para a esquerda, ODT/ODS/ODP `style:writing-mode="rl-tb"`, RTF
`\rtldoc` e espelhamento de códigos de alinhamento ASS/SSA (`\an1` ↔
`\an3`, `\an4` ↔ `\an6`, etc.). Alinhamentos centrais não são
tocados.

## Atalhos

| Atalho | Ação |
|---|---|
| `Ctrl+Enter` | Iniciar tradução |
| `Ctrl+O` | Procurar ficheiros |
| `Ctrl+F` | Focar busca de histórico |
| `Ctrl+P` | Pausar a fila ativa |
| `Ctrl+G` | Continuar (retomar) a fila ativa |
| `Delete` | Eliminar entradas de histórico selecionadas |

`Ctrl+P` / `Ctrl+G` são suprimidos quando um campo de entrada de
texto tem o foco, para não colidirem com a digitação.

## Quando as coisas falham

Uma tarefa que falhou mostra um status vermelho com um código de erro
e uma mensagem localizada — veja o [guia de solução de problemas](../troubleshooting.md)
para os comuns (`AUTH_ERROR`, `QUOTA_ERROR`, `FFMPEG_NOT_FOUND`,
etc.).
