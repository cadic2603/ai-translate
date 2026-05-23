---
description: Extraia texto de imagens e capturas de ecrã usando motores OCR (Tesseract, EasyOCR, Google Vision) ou visão LLM — saída para TXT ou DOCX.
---

# Extrair texto

Tire o texto de imagens — recibos, capturas de ecrã, documentos
fotografados, páginas escaneadas, qualquer coisa. Saída para `.txt`
(simples) ou `.docx` (parágrafos formatados).

Esta página **não traduz** — apenas extrai. Encaminhe a saída para
Traduzir documento se quiser também traduzir.

## Dois métodos de extração

| Método | Melhor para |
|---|---|
| **OCR** | Alto volume / lote / sensível ao custo (grátis ou quase grátis por imagem) |
| **Visão LLM** | Preservação de layout, scripts mistos, imagens de baixa qualidade, escrita à mão |

Escolha o padrão em **Definições → Extrair texto → Método de extração**.

## Motores OCR (método OCR)

| Motor | Custo | Offline | Idiomas | Notas |
|---|---|---|---|---|
| **Tesseract** | Grátis | Sim | 100+ | Padrão. Requer instalação no sistema. |
| **EasyOCR** | Grátis | Sim (após download do modelo) | 80+ | Melhor para scripts não-latinos. ~1 GB de modelos. |
| **Google Cloud Vision** | Pago (1.000 grátis / mês) | Não | 60+ | Maior precisão. |

Configure em **Definições → OCR**.

## Passo a passo

1. Clique em **Extrair texto** na barra lateral.
2. Solte um ou mais ficheiros de imagem (`.png`, `.jpg`, `.jpeg`,
   `.bmp`, `.webp`, `.tiff`, `.tif`).
3. Escolha o **Idioma fonte** (ajuda o OCR a escolher o modelo certo).
4. Escolha o **Formato de saída** — `.txt` ou `.docx`.
5. Clique em **Extrair** (ou `Ctrl+Enter`).
6. **Abra** a linha quando terminar.

## Quando usar qual

- **Recibo / fatura denso em texto** → Tesseract é rápido e preciso.
- **Notas manuscritas fotografadas** → visão LLM vence de longe.
- **Painéis de mangá / quadrinhos** → EasyOCR (lida bem com texto CJK vertical).
- **Formulário com muitos campos pequenos** → Google Cloud Vision
  tende a preservar limites de campos melhor que os outros.

## Dicas

!!! tip "OCR ou LLM, não ambos"
    A página escolhe um método e o executa. Para comparar saídas,
    execute a mesma imagem duas vezes com métodos diferentes.

!!! tip "Diálogo Definição necessária"
    Se você escolher OCR mas nenhum motor OCR estiver configurado
    (ou LLM mas nenhuma chave LLM estiver configurada), a página
    mostra um único diálogo "Definição necessária" que liga
    diretamente à aba Definições relevante.

## Atalhos

| Atalho | Ação |
|---|---|
| `Ctrl+Enter` | Extrair |
| `Ctrl+O` | Procurar |
| `Ctrl+F` | Foco em busca do histórico |
