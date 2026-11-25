---
name: Revisar código
description: Revisa uma mudança de código (um PR, um diff, um arquivo) olhando segurança, desempenho, correção e manutenção, e termina com um veredito claro.
triggers: revisa o codigo, revisar o codigo, revisao de codigo, code review, revisa o pr, revisar o pr, revisa esse pr, revisa esse diff, revisa essa mudanca, antes do merge, antes de fazer merge, posso fazer merge, esse codigo e seguro, da uma revisada no codigo
source: anthropics/knowledge-work-plugins
source_url: https://github.com/anthropics/knowledge-work-plugins/tree/5e504ae11498f2b8daa30d86b7dab97b2ecd8092/engineering/skills/code-review
license: Apache-2.0
installed_on: 2026-11-25
---

Adaptada da habilidade "code-review" do anthropics/knowledge-work-plugins (Apache-2.0, Copyright Anthropic) para o Visão: o código chega colado, num link do GitHub que o sistema abre ou por uma tarefa no Mac.

# Revisar código

## A entrada

- O diff, o arquivo ou o link que ele mandou e que o sistema abriu. Se ele só disse "revisa o PR" sem dizer qual, e o GitHub trouxe os PRs abertos do repositório, revise o mais recente e diga qual escolheu.
- Se o código não está no contexto e o Mac está ligado com o projeto liberado, a revisão pode virar um pedido ao Mac, que espera o Aprovar dele. Não diga que revisou o que não leu.
- Contexto muda o foco: "isto é caminho quente", "isto mexe com dado pessoal", "olha só segurança". Siga.

## O que olhar

- **Segurança:** injeção de SQL ou de comando, XSS, CSRF, autenticação e permissão, segredo ou chave no código, desserialização insegura, caminho de arquivo vindo do usuário, SSRF.
- **Desempenho:** consulta N+1, laço ou consulta sem limite, complexidade alta em caminho quente, índice faltando, recurso que não fecha.
- **Correção:** entrada vazia, nula ou enorme; concorrência e corrida; erro engolido ou mal propagado; um a mais ou a menos; tipos.
- **Manutenção:** nomes, uma responsabilidade por função, duplicação, teste para o que mudou, comentário onde a lógica não é óbvia.

## A resposta

1. **Em uma ou duas frases:** o que a mudança faz e a impressão geral.
2. **Problemas sérios:** arquivo, linha, o problema e por que quebra, com o trecho corrigido num bloco de código.
3. **Sugestões:** o que melhora, por categoria, sem misturar com o que é sério.
4. **O que está bom:** o que vale manter, curto.
5. **Veredito:** aprovar, pedir mudanças ou conversar antes, numa linha.

Só aponte o que você consegue mostrar no código. Um palpite vai marcado como palpite. Não encha com estilo quando há um bug sério.
