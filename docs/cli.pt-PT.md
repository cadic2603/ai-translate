---
description: Use a interface de linha de comando ait para traduzir ficheiros sem interface — suporta PDFs, documentos Office, legendas e 45+ idiomas a partir de um script ou job CI.
---

# Linha de comando (`ait`)

Tradução headless — o mesmo pipeline do app desktop, sem display
necessário. Útil para CI, jobs em lote, servidores e fluxos
scriptados.

## Início rápido

```bash
ait report.docx --target French
```

A saída fica ao lado da fonte como
`report_translated_<src>_<tgt>.docx`.

## Receitas comuns

### Vários ficheiros

```bash
ait *.pdf --target Japanese
```

A expansão glob é trabalho do shell (Unix). No Windows / `cmd.exe`,
liste os ficheiros explicitamente ou use PowerShell:

```powershell
ait (Get-ChildItem *.pdf) --target Japanese
```

### Diretório de saída personalizado

```bash
ait report.docx --target French --output ./translated/
```

O diretório é criado se não existir. Se não puder ser criado
(permissão negada, etc.) você recebe um erro claro e código de saída
2 — sem execução parcial.

### Especificar idioma fonte

```bash
ait letter.txt --target German --source "English (US)"
```

A correspondência da fonte é case-insensitive. "Chinese" sozinho
imprime uma dica:

```bash
ait letter.txt --target Chinese
# Error: unknown target language 'Chinese'.
# Did you mean one of: Chinese (Simplified), Chinese (Traditional)?
```

### Escolher um modelo específico

```bash
ait big-doc.pdf --target French --model "Gemini:gemini-2.5-pro"
# Ou qualquer outro Provider:model_name registado na aba LLM do app desktop.
```

O formato é estritamente `Provider:model_name`. Dois pontos faltando
→ saída 2 com mensagem clara em vez de silenciosamente cair de volta
ao modelo Gemini padrão.

### Opções Office

```bash
ait deck.pptx --target Vietnamese \
    --translate-images \
    --translate-comments \
    --translate-shapes \
    --translate-notes
```

`--translate-images` requer OCR configurado (veja
[Motores OCR](setup/ocr-engines.md)).

### Auto-conversão de formatos legacy

```bash
ait old-doc.doc --target French --convert-legacy
```

O pipeline converte `.doc` → `.docx` primeiro (melhor fidelidade),
traduz a cópia moderna, reconverte. Mesma coisa para `--convert-odf`
e `.odt` / `.ods` / `.odp`.

### Silencioso / verboso

```bash
ait report.docx --target French --quiet      # apenas erros
ait report.docx --target French --verbose    # firehose DEBUG completo
```

Modo padrão imprime um banner e progresso por tarefa em stderr;
detalhes completos (dumps de body HTTP, logs de retry) ficam no
diretório de logs do app da plataforma independente da verbosidade
do console (veja
[Solução de problemas → Onde estão os logs?](troubleshooting.md#where-are-the-logs)
para o caminho no seu OS).

### Listar idiomas suportados

```bash
ait --list-languages
```

Imprime todos os 45 idiomas suportados. Útil para encadear em loops shell.

### Versão

```bash
ait --version
# ait 0.1.0
```

## Códigos de saída

| Código | Significado |
|---|---|
| `0` | Todas as tarefas bem-sucedidas |
| `2` | Erro de argumento (idioma desconhecido, alvo faltando, modelo malformado, saída não gravável, extensão de ficheiro não suportada) |
| `3` | LLM não configurado |
| `4` | Falha parcial (algumas bem-sucedidas, outras não) |
| `5` | Todas falharam |
| `130` | Interrompido (`Ctrl+C`) |

## Cancelamento

`Ctrl+C` uma vez — cancelamento cooperativo. O checkpoint da tarefa
atual é guardado, o pipeline sai limpo no próximo limite de polling.

`Ctrl+C` novamente — interrupção dura. Use com moderação; ficheiros
parciais podem ficar em estado meio-escrito.

## Referência completa de flags

```bash
ait --help
```

Mostra cada flag com seu padrão. O mesmo conteúdo resumido aqui:

| Flag | Padrão | Notas |
|---|---|---|
| `--target / -t LANG` | _obrigatório_ | Case-insensitive |
| `--source / -s LANG` | auto-detecção | Case-insensitive |
| `--output / -o DIR` | pai da fonte | Criado se faltando |
| `--model / -m PROVIDER:MODEL` | padrão desktop | Formato estrito |
| `--ocr-method METHOD` | `TesseractOCR` | `Tesseract`, `EasyOCR`, `Google Cloud OCR` |
| `--translate-images` | desligado | Requer OCR configurado |
| `--translate-comments` | desligado | Comentários Office |
| `--translate-shapes` | desligado | Formas / caixas de texto |
| `--translate-notes` | desligado | Notas do orador PowerPoint |
| `--translate-sheet-names` | desligado | Abas de planilha Excel |
| `--convert-legacy` | desligado | `.doc`/`.xls`/`.ppt` → formato moderno |
| `--convert-odf` | desligado | `.odt`/`.ods`/`.odp` → OOXML |
| `--keep-history` | desligado | Manter entradas de histórico após conclusão |
| `--quiet / -q` | desligado | Apenas erros no console |
| `--verbose / -v` | desligado | Firehose DEBUG |
| `--list-languages` | — | Imprime 45 idiomas e sai |
| `--version` | — | Imprime versão e sai |

## Dicas

!!! tip "Configure uma vez, use em todo lugar"
    O CLI compartilha suas chaves de API e definições com o app
    desktop — configure tudo uma vez na GUI, depois automatize com
    `ait` a partir daí.

!!! tip "Cache de endpoint cold-start"
    Para cada par `(endpoint, modelo)`, a escolha
    chat-vs-responses-API e a variante de payload funcionante são
    persistidas em `llm_endpoint_cache.json` no diretório cache do OS
    (`~/.cache/ai-translate/` no Linux,
    `~/Library/Caches/ai-translate/` no macOS,
    `%LOCALAPPDATA%\ai-translate\cache\` no Windows). Invocações CLI
    cold-start pulam inteiramente o probe de auto-detecção após a
    primeira chamada bem-sucedida — útil ao scriptar contra deployments
    Azure / vLLM / OpenRouter / Anthropic / DeepSeek que precisam de
    tuning de payload específico ao provedor. O cache é seguro
    multi-processo e multi-thread (read-merge-write sob RLock com
    rename atômico).

!!! tip "Streams de saída"
    Modo padrão imprime o banner, lista de tarefas em fila, e progresso
    por tarefa em **stdout** (line-buffered para entrelaçar corretamente
    com erros); mensagens de erro e registos de log vão para
    **stderr**. Combine com `--quiet` para suprimir stdout inteiramente
    para piping limpo:

    ```bash
    ait --list-languages | grep -i japanese    # dados em stdout
    ait file.txt --target French --quiet 2> errors.log
    ```
