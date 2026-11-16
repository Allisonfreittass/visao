# ADR-0016: Painel de olho perto da meta, e aviso urgente abaixo dela

- Data: 2026-11-16
- Estado: aceita
- Amplia: [ADR-0012](0012-paineis-vivos.md)

## Contexto

O painel vivo (ADR-0012) já tinha a meta do dono e avisava quando o total passava para baixo dela.
Mas havia três falhas:
- **Uma conferência por dia, às 9h.** Um preço que cai às 15h e volta antes das 9h do dia seguinte
  nunca é visto.
- **Aviso perdido.** O aviso de meta dividia com a "queda de 10%" o limite de um por dia, e era
  descartado no horário silencioso sem nova tentativa.
- **Aviso só na passagem.** Ele só saía quando o total cruzava a meta entre duas conferências. Se
  o total ficava conhecido já abaixo da meta, por exemplo quando um preço "a confirmar" aparecia,
  nada era dito.

"Me avisa se ficar abaixo de R$ 2.000" é o pedido mais direto que um dono faz a um painel, e
precisa funcionar como a FRIDAY: olhar mais de perto quando está perto, e avisar na hora.

## Decisão

### Frequência pela distância da meta

- **Longe da meta:** uma conferência por dia, às 9h, como antes.
- **Perto da meta:** total até `VISION_PANEL_NEAR_GOAL_PERCENT` (15%) acima dela, ou já abaixo.
  A próxima conferência é em `VISION_PANEL_NEAR_GOAL_EVERY_HOURS` (3 h).
  - Uma conferência que cairia no horário silencioso espera ele acabar.
  - Nunca vai além das 9h do dia seguinte.
- **Uma conferência que falha** (site, robô, orçamento, pausa) volta para a regra diária.

A frequência sai do último total conhecido, em código (`near_goal`, `check_after` em
`core/panels/service.py`).

### Jobs que mudaram de hora

Cada job leva a hora para a qual foi marcado (`payload.at`). Editar, pausar, retomar ou mudar de
frequência marca uma hora nova no painel (`next_check_at`). Um job cuja hora não bate com a do
painel não faz nada (`skipped: moved`), e assim não sobra conferência em dobro.

### O aviso urgente

- **Abaixo da meta é urgente.** Ele sai uma vez cada vez que o total fica abaixo da meta, por
  estado (`panels.goal_alerted_at`) e não por passagem:
  - o primeiro total conhecido abaixo da meta já avisa;
  - o total voltar para cima da meta limpa o estado;
  - ficar abaixo de novo avisa de novo, mesmo no mesmo dia.
- **O aviso urgente passa por cima do limite de um aviso por dia,** mas não do horário silencioso.
  Dentro dele, o estado fica vazio, e a conferência marcada para o fim do horário silencioso avisa
  se o total ainda estiver abaixo.
- **Queda grande e item que sumiu** continuam avisos comuns, com o limite de um por dia.
- **Quando o chat já disse** que está abaixo da meta, ao criar ou editar o painel, o estado é
  marcado na hora e não vem aviso repetido. A conferência feita durante uma edição nunca manda
  aviso: a resposta diz o resultado.

### "Me avisa se ficar abaixo de R$ X" é meta

`offers.goal_from` lê, em código, frases de aviso com um valor em dinheiro: "me avisa se cair pra
5 mil", "me alerta quando chegar a R$ 4.800". Valem as regras de sempre: o valor nunca vem do
modelo e precisa ter dinheiro à vista. O contexto decide o que a frase faz:
- **Sozinha, ou quase** (até 3 palavras além dela, sem pergunta): muda a meta do painel.
- **Dentro de um pedido de cotação novo:** vira a meta dessa cotação, não a do painel antigo.

### O card

- `watch_every_hours` (3, ou `null` quando é uma vez por dia) vai no `GET /panels`, por acréscimo.
- O web mostra "perto da meta: confiro a cada 3 h" ao lado da hora da última conferência.

## Custo

Cada conferência continua sendo 1 chamada de extração no orçamento da autonomia, com o Haiku a
menos de US$ 0,001. Perto da meta, são até ~5 por dia por painel, fora do horário silencioso; com
3 painéis, ~15 chamadas, dentro das 200 por dia da autonomia em produção.

## Fora desta decisão

- **Aviso que acorda no horário silencioso.** O dono pode encurtar o horário silencioso.
- **Frequência por painel escolhida pelo dono.** Se fizer falta, vira um campo no `spec`.
- **Prioridade especial no iPhone** (`time-sensitive` do APNs). O Web Push já sai com
  `Urgency: high`. O app nativo decide isso no lado dele.
