# Product

<!-- impeccable:product-schema 1 -->

## Platform

adaptive

Web/PWA (`apps/web`, React + Vite) e app nativo do iPhone (`apps/ios`). A marca é a mesma nos
dois; no iPhone, navegação, controles e tipografia seguem as convenções do iOS.

## Users

- **Principal: uma pessoa só, o dono.** Uso pessoal, no computador (web) e no iPhone. Chama o
  Visão por voz (ligação sem as mãos) ou texto para código, ideias, email, agenda e trabalho no
  Mac. Não é produto de equipe.
- **Secundário: quem lê o repositório.** O repositório é público (README em PT e EN, licença
  MIT, benchmarks). Recrutadores e devs que avaliam o projeto são um público real; o produto
  também é vitrine do trabalho. O site pessoal (`site/`, "Rastros") é outro produto e fica fora
  deste registro.

## Product Purpose

Um agente pessoal que se pode chamar, que ajuda com código e ideias, lembra só do que a pessoa
autoriza e puxa conversa quando tem algo que vale dizer ("o amigo para quem eu ligo").

Por baixo, é uma pesquisa sobre arquitetura cognitiva persistente em torno de um LLM
substituível: o modelo só existe durante uma chamada; o que o faz continuar (memória,
interesses, reflexão, metas, orçamento) mora no código em volta.

## Positioning

**V.I.S.A.O.: Virtual Intelligence with Supervised Autonomy & Opt-in memory.**

- **Autonomia supervisionada.** Ele propõe; a pessoa aprova. Toda ação externa (email, agenda,
  trabalho no Mac) vira um cartão de aprovação dentro da conversa.
- **Memória opt-in e curada** por política determinística, com proveniência, exportação e
  exclusão. Saúde, religião, política, finanças e terceiros ficam de fora.
- **Nasce sem nome e decide quem é** (`chosen_name = null`); a identidade cresce de forma
  versionada e reversível.
- **Honesto sobre o que é:** não alega consciência, sentimentos nem vida, e essas regras ficam
  fora de tudo o que ele pode reescrever.

## Operating Context

- **Superfícies:** Início (o que ele pensou, pedidos, painéis), Chat, Projetos (cada projeto é
  o chat dele), Caderno, Ligação, Integrações (Mac, email, agenda), Ajustes.
- **Ele fala primeiro:** pensa entre conversas e abre o papo, respeitando horário de silêncio,
  pausa geral, conversa em andamento e limite diário; Web Push com o app fechado.
- **Ligação por voz** com a tela acesa e interrupção por voz.
- **Braço do Mac:** `/mac <projeto> <pedido>` roda o Claude Code isolado num projeto liberado.
- **Páginas que ele escreve** (planos, comparativos) com datas, fontes e "a confirmar".
- **Navegador de leitura** para preços e horários ao vivo; só lê, sem login nem compra.
- **Status ao vivo** do passo atual enquanto trabalha.

## Capabilities and Constraints

- O que está ligado agora vem do manifesto `core/identity/capabilities.py`; a história fica em
  `docs/NOVIDADES.md`. Toda capacidade nova entra nos dois.
- Orçamento por chamada com razão que falha fechado; nenhuma chamada ao modelo sem reserva.
- Conteúdo externo (emails, páginas, anexos) é dado, nunca ordem.
- Hospedagem: plano grátis da AWS até 22/04/2027; migração para a Oracle antes disso.
- Interface em português do Brasil.

## Brand Commitments

- **Nome:** Visão / V.I.S.A.O. Identidade visual atual: "Muninn" (aprovada em 23/11/2026),
  detalhada em [DESIGN.md](DESIGN.md) e `brand/muninn/`.
- **Voz:** português simples e direto; honesto sobre o que foi conferido e quando ("não
  conferido hoje", "a confirmar").
- **A interface transmite:** presença calma, não vigilância; honestidade; controle (aprovar,
  recusar, guardar ou não uma memória, sempre a um toque).
- **Fora de escopo:** personagem fofo, mascote com rosto, efeitos que distraem do conteúdo,
  linguagem de vigia ("vigilância", "dê uma ordem").

## Evidence on Hand

- Capturas com dados de demonstração: `docs/assets/inicio.webp`, `docs/assets/conversa.webp`,
  `docs/assets/entrar.webp`, `docs/assets/celular.webp`.
- Benchmarks no README: memória curada 8/8, passiva 6/8, sem memória 1/8; −69% de palavras após
  retorno com adaptação, desfazer volta à linha de base.
- Pesquisa comparativa: `docs/research/comparativo_agentes.md` (OpenClaw, Goose, OpenCode).
- Não há usuários além do dono, depoimentos, clientes nem preço. Não inventar.

## Product Principles

1. **Ele propõe, a pessoa decide.** Nenhuma ação externa sem aprovação visível e a um toque.
2. **Só lembra o que foi autorizado**, e mostra de onde veio cada lembrança.
3. **Dizer o que foi conferido e quando;** o que falta fica marcado como "a confirmar".
4. **Presença, não vigilância.** Iniciativa com limites claros (silêncio, pausa, limite diário).
5. **Nada que ele não seja.** Sem alegar consciência; tudo reversível e versionado.

## Accessibility & Inclusion

- Alvos de toque com pelo menos 44 px.
- `prefers-reduced-motion` respeitado (a abertura não aparece; movimento vira quadro final).
- Texto secundário com contraste 7:1 sobre o fundo.
- Uso por voz sem as mãos é um caminho de primeira classe, não um extra.
