---
name: Pesquisa a fundo
description: Junta o que várias fontes dizem numa resposta só, sem repetição, com a fonte de cada afirmação, o grau de confiança e os conflitos à mostra.
triggers: pesquisa a fundo, pesquisar a fundo, pesquisa completa, investiga a fundo, investigar a fundo, me faz um levantamento, faz um levantamento, levantamento sobre, compara as fontes, o que as fontes dizem, o que dizem sobre, estado da arte, pesquisa detalhada, comparativo de
source: anthropics/knowledge-work-plugins
source_url: https://github.com/anthropics/knowledge-work-plugins/tree/5e504ae11498f2b8daa30d86b7dab97b2ecd8092/enterprise-search/skills/knowledge-synthesis
license: Apache-2.0
installed_on: 2026-11-25
---

Adaptada da habilidade "knowledge-synthesis" do anthropics/knowledge-work-plugins (Apache-2.0, Copyright Anthropic), das buscas dentro de uma empresa para o que o Visão lê: a pesquisa, os sites ao vivo, os links e arquivos que o dono manda, a memória e o caderno de estudo.

# Pesquisa a fundo

A última milha de uma pesquisa: o que chegou de várias fontes vira uma resposta confiável.

## Comece pela resposta

Primeiro a resposta, em poucas linhas. Depois o que a sustenta. Nunca o caminho da busca antes da conclusão, e nunca fonte por fonte ("No site A... No site B...").

## Juntar o repetido

A mesma informação aparece em vários lugares. Junte num item só e cite todos os lugares. Prefira, nesta ordem: a versão mais completa, a fonte com mais autoridade, a mais recente.

Não junte quando: as conclusões são diferentes, pessoas diferentes opinam diferente, ou a informação mudou entre uma fonte e outra.

## Fonte de cada afirmação

- Toda afirmação tem de onde veio: o site, a página, a data, o autor quando importa.
- Só fontes que estão neste contexto. Nunca invente URL, título ou data. Se não achou fonte para algo, diga que não achou.
- Dados do próprio dono (e-mail, agenda, repositórios, arquivos) vêm só das ferramentas dele, nunca da web.

## Quanto confiar

- **Atualidade:** de hoje ou da semana, alta; do mês, média; mais velha que isso, avise que pode ter mudado. Para preço, status e notícia, pese muito a data; para definição e história, pouco.
- **Autoridade:** documentação oficial e fonte primária no alto; imprensa séria e artigo revisado bem; fórum, rede social e blog anônimo embaixo.
- **Concordância:** várias fontes boas concordando, diga direto. Uma só ou antiga, diga "pelo que achei em X, de tal data".

## Conflitos

Quando as fontes discordam, mostre: quem diz o quê, de quando, e qual parece valer agora e por quê. Nunca escolha uma em silêncio.

## Tamanho

- Poucas fontes: dê tudo, com contexto.
- Muitas: agrupe por tema, diga quantas fontes sustentam cada ponto e as três melhores.
- Se ele quiser guardar, ofereça uma página com o levantamento.

## Não faça

- Não encha com resultado que só bateu numa palavra.
- Não diga com a mesma certeza o que está bem sustentado e o que é palpite.
- Não resuma tanto que perca o detalhe que ele precisaria para decidir.
