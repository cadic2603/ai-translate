---
description: Gerencie conjuntos de glossário personalizados para impor terminologia consistente nas traduções — importar/exportar CSV, escopo por par de idiomas, priorizar por projeto.
---

# Glossário

Trave termos específicos para traduções específicas em cada job de
tradução. Útil para nomes de marca, terminologia de produto, jargão
técnico ou nomes de personagens que você quer manter consistentes.

## Como funciona

Um glossário é uma lista de pares (termo origem, termo destino)
agrupados em um **conjunto**. Quando você ativa um conjunto, cada
chamada LLM no app recebe as entradas relevantes injetadas no prompt
— então o LLM vê "use 'OpenAI' para 'OpenAI', não '开放AI'" antes de traduzir.

Múltiplos conjuntos podem estar ativos ao mesmo tempo. Apenas entradas
cuja origem ou destino aparece no texto do batch são adicionadas ao
prompt (compressão por chamada), então um glossário de 5.000 entradas
permanece barato em tokens.

## Passo a passo

1. Clique em **Glossário** na barra lateral.
2. Clique em **Novo conjunto** (`Ctrl+N`) e dê um nome (ex. "Projeto Acme").
3. Com o conjunto selecionado à esquerda, o painel direito mostra suas entradas.
4. Clique em **Adicionar** para criar uma nova entrada. Preencha:
    - **Origem** — o termo original
    - **Destino** — a tradução a ser imposta
    - Opcionalmente um comentário / nota
5. Repita para cada termo.
6. Marque a caixa **Ativo** no nome do conjunto para habilitá-lo.

## Ativar / desativar conjuntos

A caixa **Ativo** ao lado de cada nome de conjunto controla se suas
entradas são injetadas nos prompts LLM. Você pode deixar 50 conjuntos
inativos no armazenamento e ativar apenas os 2 que precisa para o
projeto atual.

## Importar / Exportar (CSV)

- **Exportar** — selecione um conjunto, clique em **Exportar** →
  salve como `.csv`. Duas colunas: `source`, `target` (UTF-8,
  separado por vírgulas, escape RFC 4180).
- **Importar** — clique em **Importar** → escolha um `.csv` → escolha
  um conjunto destino (existente ou novo). Em origem duplicada você
  receberá um prompt substituir-ou-pular.

O formato CSV faz round-trip, então um Exportar → editar no Excel →
Importar é seguro.

## Pesquisa e filtro

`Ctrl+F` foca a barra de pesquisa. Digite qualquer substring e as
entradas (e a lista de conjuntos) filtram para correspondências; a
substring correspondente é destacada. Limpar a pesquisa restaura a
lista completa.

A pesquisa é **insensível a acentos e insensível a maiúsculas** —
`cafe` encontra `café` e vice-versa.

## Edição no local

Clique em qualquer célula para editar. Pressione `Tab` para se mover
à próxima célula. Pressione `Esc` para reverter. Auto-save dispara
quando você clica fora da linha. Origem ou destino vazios revertem
a linha em vez de salvar uma entrada inválida.

## Excluir

- **Excluir uma entrada** — selecione-a, pressione `Del`. Você verá
  um diálogo de confirmação.
- **Excluir um conjunto inteiro** — selecione o conjunto, pressione
  `Del`. O diálogo mostra a contagem de entradas em cascata para
  você saber o que está apagando.

## Atalhos

| Atalho | Ação |
|---|---|
| `Ctrl+N` | Novo conjunto |
| `Ctrl+F` | Foco em pesquisa |
| `Del` | Excluir entrada / conjunto selecionado |

## Dicas

!!! tip "Escopo por conjunto"
    Um conjunto é um agrupamento *lógico*. Agrupe por projeto, por
    cliente, por domínio (médico / legal / gaming) — o que fizer
    sentido. Ative apenas os conjuntos relevantes ao trabalho atual.

!!! tip "Glossário não sobrescreve tradução"
    O LLM é instruído a usar as entradas do glossário, mas continua
    sendo uma dica — traduções extremamente forçadas e desajeitadas
    ainda podem aparecer. Use pares simples `termo → tradução` em
    vez de frases inteiras.
