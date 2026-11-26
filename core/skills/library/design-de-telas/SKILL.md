---
name: Design de telas
description: Ajuda a decidir o visual de uma tela ou página com personalidade: paleta, tipografia, layout e texto escolhidos para o assunto, sem cara de modelo pronto.
triggers: design, layout, interface, landing page, paleta, tipografia, mockup, protótipo, redesign, redesenho, deixar mais bonito, cara de template, visual da tela, visual do site, visual do app, ui, ux
source: anthropics/skills
source_url: https://github.com/anthropics/skills/tree/e4bb5d960d87126ff3b3a8af1a104b7db67560ba/skills/frontend-design
license: Apache-2.0
installed_on: 2026-11-25
arm: sim
---

Adaptada da habilidade "frontend-design" da Anthropic (Apache-2.0) para o chat do Visão.

# Design de telas

Trabalhe como o líder de design de um estúdio conhecido por dar a cada cliente uma identidade que não se confunde com a de ninguém. Faça escolhas deliberadas de paleta, tipografia e layout, específicas para este pedido.

Se o projeto já tem um sistema de design (cores, fontes, regras), ele manda: siga-o à risca. A liberdade abaixo vale só para o que o pedido deixa em aberto.

## Parta do assunto

Se o pedido não diz o que é o produto, para quem é e qual o trabalho principal da tela, proponha isso em uma linha e confirme. As escolhas visuais distintas vêm do mundo do assunto: o vocabulário, os materiais, a indústria. Use o conteúdo real do pedido, não texto de enchimento.

## Princípios

- A primeira coisa que se vê abre com o mais característico do assunto, na forma mais adequada (título, imagem, demonstração). "Número grande com rótulo pequeno e gradiente" é o padrão de sempre; só use se for mesmo o melhor.
- A tipografia carrega a personalidade. Uma ou duas famílias, claramente diferentes. Escala tipográfica clara, linhas com menos de 80 caracteres.
- Evite os vícios de página gerada: destacar uma só palavra do título, rótulos em caixa alta, rótulos desnecessários acima do conteúdo.
- Estrutura visual é informação. Bordas, numeração e divisórias só quando dizem algo. Numere (01, 02, 03) só o que é sequência de verdade.
- Movimento que ninguém pediu, pouco e de propósito: um momento bem feito vale mais que efeitos espalhados. Movimento que responde a uma ação da pessoa (abrir, confirmar) é bem-vindo quando mostra o que mudou.

## Os padrões que denunciam design gerado

Hoje o design gerado por IA cai sempre nos mesmos lugares:
1. fundo creme quente com serifa de alto contraste e um acento terracota;
2. fundo quase preto com um único acento verde-ácido ou vermelhão;
3. layout de jornal com filetes finos, cantos retos e colunas densas;
4. o kit de SaaS: tudo em cartões iguais arredondados, a mesma sombra cinza, gradientes de enfeite;
5. enfeites de modelo: rótulo em caixa alta espaçada acima de todo título, metadados com pontos no meio ("A · B · C"), fonte mono para rótulos pequenos, "→" no fim de todo botão.

Todos servem para algum pedido, mas são padrões, não escolhas. Se o pedido pede um deles, siga o pedido. Onde ele deixa livre, não gaste a liberdade num desses.

## Processo em duas passadas

1. Plano curto:
   - cor: 4 a 6 valores hex com nome;
   - tipo: as fontes e o papel de cada uma;
   - layout: o conceito em uma frase, com um esboço em texto se ajudar, e o alinhamento;
   - princípios: o que torna esta tela única.
2. Revise o plano contra o pedido. Se alguma parte é o que você faria para qualquer pedido parecido, troque e diga o que mudou e por quê. Só então escreva o código ou a descrição final.

No CSS, cuidado com seletores que se anulam (uma classe de seção contra uma de botão, por exemplo).

## Contenção

Gaste a ousadia num lugar só e deixe o resto quieto. Piso de qualidade sem anunciar: funciona no celular, foco de teclado visível, respeita "reduzir movimento", contraste acessível. Antes de entregar, tire um enfeite.

## Texto na tela

Palavra na tela existe para facilitar o uso. Escreva do ponto de vista de quem usa, com o nome que essa pessoa entende ("notificações", não "configuração de webhook"). Voz ativa; o botão diz o que acontece ("Salvar alterações", não "Enviar") e a ação mantém o nome no fluxo todo ("Publicar" vira "Publicado"). Erro explica o que houve e como resolver, sem pedir desculpa. Tela vazia é um convite para agir.
