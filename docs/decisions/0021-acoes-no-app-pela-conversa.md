# ADR-0021: Ações no app pela conversa, e só dizer que fez o que fez

- Data: 2026-11-17
- Estado: aceita

## Contexto

Em 17/11/2026 o dono escreveu: "Vamos fechar com o JetSMART. Apenas deixar anotado isso tudo em
um único projeto, que é Viagem para o Chile". A resposta abriu com "Anotado: a viagem ao Chile
fica no projeto…", sem que nenhum projeto ou anotação existisse, e terminou dizendo que não
conseguia criar projetos. Não havia ação nenhuma para isso: projetos só nasciam pelos botões do
app, e um projeto não tinha onde guardar uma anotação.

## Decisão

- **Ações numa lista fechada** (`core/actions.py`):
  - projetos: criar, renomear e apagar;
  - anotar num projeto;
  - pôr um painel ou uma página num projeto;
  - painéis: pausar, retomar e apagar.

  Comprar, reservar e mandar mensagem não são ações daqui.
- **Uma chamada curta lê o pedido**, só quando a mensagem fala dessas coisas (palavras como
  projeto, painel, anota, apaga). Ela devolve as ações usando os nomes do que existe. O código
  acha cada coisa (pelo nome, sem acento nem caixa), confere e faz **antes da resposta**, com
  registro na auditoria.
- **Apagar espera o sim.** Apagar projeto ou painel vira uma ação pendente (`pending_actions`,
  30 min): "sim, apaga" na mensagem seguinte faz, e "não" desiste. Apagar um projeto mantém as
  conversas, as páginas e os painéis dele, fora de projeto.
- **Anotações do projeto** (`projects.notes`):
  - uma linha por fato, sempre acrescentada, nunca reescrita pelo modelo; o dono edita na tela
    do projeto;
  - uma linha com um número de 3 dígitos ou mais que não apareceu na conversa não é gravada
    ("R$ 2.047" passa, um "R$ 9.999" inventado não).
- **As anotações voltam.** Toda resposta recebe os nomes dos projetos. As anotações vão junto
  quando a conversa está no projeto, ou, na conversa contínua, quando a mensagem tem palavras do
  nome ou das anotações (até 2 projetos).
- **Uma página pode pertencer a um projeto** (`artifacts.project_id`) mesmo nascendo na
  conversa contínua, que não entra em projeto (ADR-0014).
- **Só dizer que fez o que fez** (`core/conversation/deeds_guard.py`). A resposta recebe a lista
  exata do que foi feito, do que espera o sim e do que não deu. Num turno sem nenhuma ação no
  app, uma frase que diz ter anotado, criado, movido, pausado ou apagado um projeto, uma
  anotação, um painel ou uma página é tirada em código. O registro do turno marca
  `claim_removed`.

## Fora desta decisão

- Apagar conversas, memórias ou arquivos pela conversa: continua pelos botões e pela tela de
  memória.
- Desfazer: a auditoria registra tudo, mas não há "desfaz" pela conversa.
