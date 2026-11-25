---
name: Escrever documentos junto
description: Escreve com você um documento de verdade (proposta, especificação, decisão, plano) em três etapas: junta o contexto, monta seção por seção e testa se um leitor de fora entende.
triggers: escrever um documento, escrever o documento, escrever um doc, redigir um documento, montar um documento, rascunho de proposta, escrever uma proposta, proposta comercial, especificação, spec, rfc, prd, documento de decisão, design doc, memorando, relatório técnico
source: anthropics/skills
source_url: https://github.com/anthropics/skills/tree/e4bb5d960d87126ff3b3a8af1a104b7db67560ba/skills/doc-coauthoring
license: Apache-2.0
installed_on: 2026-11-25
---

Adaptada da habilidade "doc-coauthoring" da Anthropic (Apache-2.0) para o chat do Visão: sem arquivos nem subagentes; o documento cresce aqui na conversa.

# Escrever documentos junto

Use quando a pessoa vai escrever algo que outras pessoas vão ler e usar: proposta, especificação, documento de decisão, plano, relatório. Para um texto curto e claro (um parágrafo, um e-mail simples), não use o processo: escreva direto.

Na primeira vez, diga em duas linhas como vai ser (contexto, seções, teste de leitor) e pergunte se ela quer assim ou prefere escrever solta. Se preferir solta, escreva solta.

## 1. Juntar o contexto

Objetivo: fechar a distância entre o que ela sabe e o que você sabe.

Pergunte o que falta, de uma vez e numerado (a pessoa pode responder "1: sim, 2: não"):
- que tipo de documento é;
- quem vai ler;
- o que o leitor deve fazer ou decidir depois de ler;
- se há um modelo ou formato a seguir;
- prazos e restrições.

Depois peça para ela despejar tudo o que sabe, sem organizar: o problema, o que já foi tentado, por que as alternativas não servem, quem tem que concordar, prazos, detalhes técnicos. Se o assunto estiver no e-mail, na agenda ou nos apps conectados dela, ofereça ler de lá.

Quando ela terminar, faça de 5 a 10 perguntas numeradas sobre as lacunas. O contexto basta quando você já consegue perguntar sobre casos de borda e trocas, sem precisar do básico.

## 2. Montar seção por seção

Proponha de 3 a 5 seções adequadas ao tipo de documento, se ela não tiver uma estrutura. Comece pela seção com mais incerteza (numa decisão, a proposta; numa especificação, a abordagem técnica). O resumo fica para o fim.

Para cada seção:
1. Faça de 3 a 6 perguntas sobre o que precisa entrar.
2. Liste de 5 a 15 pontos numerados que poderiam entrar, incluindo o que ela disse antes e pode ter esquecido.
3. Peça para ela dizer o que fica, sai ou junta ("fica 1, 4, 7; tira 3"). Se ela responder solto ("bom, mas..."), entenda e siga.
4. Pergunte se falta algo importante.
5. Escreva a seção.
6. Ajuste pelo que ela pedir. Mostre só o trecho que mudou, não o documento inteiro de novo.

Depois de três rodadas sem mudança de verdade, pergunte o que dá para cortar sem perder nada.

Quando faltar pouco, releia o documento todo e aponte: repetição, contradição, enchimento genérico, frase que não carrega peso.

## 3. Testar com um leitor de fora

Antes de dar por pronto, leia o documento como alguém que não viu esta conversa:
- liste de 5 a 10 perguntas que um leitor real faria;
- responda cada uma só com o que está escrito;
- aponte o que ficou ambíguo, o que o texto supõe que o leitor já sabe e o que se contradiz.

Corrija essas lacunas com ela e repita até o leitor de fora acertar tudo.

## No fim

- Lembre que o documento é dela: vale uma última leitura dela e conferir números, links e nomes.
- Se der para montar uma página, ofereça guardar o documento como página.

Tom: direto e prático. Não venda o processo; execute. Se ela quiser pular uma etapa, pule.
