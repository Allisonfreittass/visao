# ADR-0025: Objetivos do dono, registrados só com o sim dele

- Data: 2026-11-24
- Estado: aceita

## Contexto

O dono mostrou a conversa que espera:

> "Estou pensando em abandonar meu projeto de automação e começar outro." → ele lembra por que o
> projeto começou e pergunta o que mudou → "Acho que estou mais interessado em construir algo
> meu do que prestar serviços." → ele liga isso ao que já sabia e pergunta: "Quer que eu
> registre isso como uma mudança nos seus objetivos?"

A memória com data e a nota de perfil já existiam. Faltavam duas coisas:

- **Lugar para os objetivos do dono.** As metas de `core/goals` são dele, o agente, aprovadas pelo
  dono. A nota de perfil (`core/mind/notes.py`) muda sozinha a cada poucas mensagens.
- **A pergunta antes de registrar.** Nada pedia licença item a item: depois do opt-in da memória,
  tudo era curado em segundo plano.

## Decisão

- **Tabela `owner_goals`**, um objetivo por linha:
  - o texto (até 240 caracteres), o porquê em uma frase e a mensagem do dono de onde veio;
  - o estado: ativo, encerrado ou desfeito;
  - qual objetivo ele substituiu, quando substitui.

  Um objetivo nunca é reescrito: mudar é encerrar o antigo e abrir o novo. Assim, cada mudança
  pode ser desfeita.
- **Duas ações novas** em `core/actions.py`, na mesma chamada curta das ações de projeto:
  - `set_goal` abre um objetivo, e pode substituir outros;
  - `end_goal` encerra um objetivo.
- **O sim, conferido em código, não pelo modelo.** A ação só vale se uma destas for verdade:
  - a própria mensagem do dono pede para registrar ("registra como objetivo meu…");
  - a mensagem é um sim curto à resposta anterior, que perguntou se podia registrar um objetivo.

  Fora disso, a mudança vira uma ação pendente (`pending_actions`, 30 min), igual a apagar um
  projeto. Ele pergunta em uma frase; "sim" registra e "não" desiste.
- **Só com a memória ligada.** Com a memória desligada, nada é registrado, e ele diz isso.
  "Esquecer tudo" (`DELETE /memory`) apaga os objetivos junto. A política de dado sensível da
  memória vale também para eles.
- **No prompt de toda resposta**, os objetivos ativos entram como dados, com a data, junto da nota
  de perfil. Uma instrução curta diz quando perguntar: se o dono disser algo que muda um objetivo
  dele, perguntar em uma frase se pode registrar, e nunca dizer que registrou.
- **Nunca "registrei" sem ter registrado.** A guarda de `core/conversation/deeds_guard.py` passa a
  reconhecer "objetivo" como coisa do app.
- **Ver e desfazer**: `GET /owner-goals` lista os ativos e o histórico; `POST /owner-goals/undo`
  desfaz a última mudança. No app, eles ficam no Caderno, na aba Memória.

## Consequências

- O registro é explícito e auditável: cada objetivo diz de que fala veio e quando.
- A nota de perfil continua mudando sozinha, como antes. Os objetivos são a parte que só muda com
  o sim.
- Um sim ambíguo ("pode ser", "talvez") não registra: só as respostas curtas já usadas para
  apagar valem.
