# Resumo da manhã

Todo dia, quando o seu horário silencioso acaba (08:00 por padrão), ele manda na conversa uma
mensagem com o que importa no dia, com aviso no celular
([ADR-0017](decisions/0017-resumo-da-manha.md)).

## O que entra (só o que houver)

| Item | De onde vem |
|---|---|
| Agenda de hoje e assuntos de emails não lidos | Google, só com a leitura em segundo plano ligada; nunca o corpo do email |
| Painéis | conferidos na hora, se a última conferência tem mais de 6 h; um painel abaixo da meta vem primeiro |
| Esperando seu sim | tarefas do Mac, metas, emails e eventos preparados, oferta de painel |
| O Mac terminou | tarefas concluídas ou que falharam nas últimas 24 h |
| Estudei | estudos prontos nas últimas 24 h, com o primeiro achado |
| Marquei para hoje | os lembretes que ele mesmo marcou para o dia |

Sem nada novo, não manda nada.

## Regras

- **Ligado por padrão.** Desliga em Ajustes > Autonomia > Resumo da manhã, onde também há
  **Mandar agora**, que pede um na hora, mesmo com o diário desligado.
- **Pausa global:** nenhum resumo.
- **Valores conferidos:** ele escreve com a própria voz, mas uma resposta com um valor em reais que
  não está nos fatos é recusada. Nesse caso, ou sem orçamento, sai o texto montado em código.
- **Um aviso só:** a conferência dos painéis feita para o resumo não manda push. O resumo é o
  aviso, e a conferência das 9h daquele dia não roda de novo.
- **Custo:** 1 chamada do Haiku por dia (`morning_briefing`, orçamento da autonomia), mais a
  extração dos painéis, que é a conferência do dia que já existia.

## API (por acréscimo)

- `GET /autonomy/permissions` traz `morning_briefing` (padrão `true`).
- `PUT /autonomy/permissions` aceita `{"morning_briefing": false}`. Os campos são opcionais: só o
  que vier muda.
- `POST /autonomy/briefing` (202) pede um resumo agora: `{"queued": true}`, ou `false` com a
  autonomia pausada.

No iPhone, a mesma chave e o mesmo botão em Ajustes. A mensagem chega como qualquer outra da
conversa contínua.

## Peças

| Peça | Onde |
|---|---|
| Fatos, texto, conferência, entrega | [`core/mind/briefing.py`](../core/mind/briefing.py) |
| Agendar o próximo | `_plan_mornings` em [`core/autonomy/cycle.py`](../core/autonomy/cycle.py) |
| Job `morning_briefing` | [`apps/worker/handlers.py`](../apps/worker/handlers.py) |
| Chave e "Mandar agora" | [`apps/api/routes/cognition.py`](../apps/api/routes/cognition.py), `SettingsView.tsx` |
