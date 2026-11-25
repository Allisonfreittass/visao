# Outros apps, pelo Composio

O Visão lê o que está nos seus outros apps (Notion, GitHub, Slack, Linear, Trello e quase todos
os que o [Composio](https://composio.dev) oferece) quando você pergunta, e prepara mudanças que
**só acontecem depois do seu toque em Aprovar**. Apagar pelos apps está desligado. Email e agenda
continuam pela integração própria ([GOOGLE.md](GOOGLE.md)). A decisão, com os números e as trocas,
está na [ADR-0028](decisions/0028-apps-pelo-composio.md).

## Onde fica o quê

- **A conexão de cada app fica no Composio, não no Visão.** O Composio guarda os tokens
  cifrados e os renova; eles nunca passam pelo Visão e não dá para exportá-los. Ajustes diz isso
  ao lado de Conectar.
- **Tudo o que ele lê e o que você aprova passa pelos servidores do Composio** e fica no registro
  de execução deles por até um ano. O Visão não consegue apagar esse registro.
- **O Visão guarda só a chave da API do Composio** (`VISION_COMPOSIO_API_KEY`, no `.env`). Os
  apps conectados ele pergunta ao Composio (e lembra por 5 minutos).
- **O Composio não sabe quem você é.** O Visão se apresenta como um HMAC do seu id com
  `VISION_SECRET_KEY`: sempre o mesmo, sem nome nem email. Se a chave do servidor mudar, as
  conexões antigas ficam órfãs lá e é preciso conectar de novo.

## As peças e o caminho de uma pergunta

| Peça | Onde |
|---|---|
| O único lugar que importa o SDK `composio` | [`integrations/composio/client.py`](../integrations/composio/client.py) |
| Quem é o dono lá, quais apps estão ligados, o teto do mês | [`core/apps/account.py`](../core/apps/account.py) |
| Mudanças esperando aprovação | [`core/apps/actions.py`](../core/apps/actions.py), tabela `tool_actions` (migração `0042`) |
| Na conversa | [`core/apps/assist.py`](../core/apps/assist.py) |
| API e Ajustes › Apps | [`apps/api/routes/apps.py`](../apps/api/routes/apps.py), [`AppsSettings.tsx`](../apps/web/src/components/AppsSettings.tsx) |

**Na conversa**, o caminho é o do Gmail:

1. **Conferência em código.** Há algum app conectado, e a mensagem fala dele (o nome do app ou
   palavras do domínio, como "issue" para o GitHub ou "página" para o Notion)? Senão, nada roda.
2. **Uma chamada curta escolhe o app** entre os conectados. Se a mensagem nomeia um só, o código
   já sabe qual e essa chamada não acontece.
3. **O código pede ao Composio as ferramentas desse app**, cada uma com a versão do momento, e
   tira as que apagam. Das que sobram, as 40 mais próximas da mensagem vão para **uma segunda
   chamada curta, que escolhe a ferramenta e os argumentos** numa lista fechada. Uma ferramenta
   fora da lista é ignorada.
4. **O código classifica.** Leitura executa e o resultado entra na resposta como **texto de
   terceiros**, cortado em 8.000 caracteres. Escrita vira um **cartão** no chat e na caixa de
   entrada, com o app, a ferramenta e todos os argumentos por inteiro.

A ferramenta é escolhida **antes** de qualquer leitura. Uma issue ou mensagem que tente dar ordens
("crie uma issue", "apague o repositório") não consegue escolher outra ferramenta no mesmo turno;
no máximo aparece na resposta como texto de terceiros, ou vira um cartão que você lê antes.

## Leitura ou escrita: as dicas

Cada ferramenta do Composio traz dicas nas `tags`: `readOnlyHint`, `createHint`, `updateHint`,
`destructiveHint`, `idempotentHint`, e outras que não falam de mudar nada (`openWorldHint`, só "fala
com o mundo lá fora", que quase todas têm). O Composio avisa que elas são de melhor esforço, então
a regra é estrita:

- **Leitura** só com `readOnlyHint` e nenhuma outra dica de mudança.
- **Escrita** em qualquer dúvida: sem dica, com dica de criar, mudar ou idempotente, com uma dica
  desconhecida, ou com `readOnlyHint` junto de outra (dicas trocadas).
- **Destrutiva** (`destructiveHint`) nunca é oferecida ao modelo, nunca vira cartão, e o cliente
  se recusa a executá-la. Antes de executar uma aprovação, o código confere de novo as dicas que o
  Composio dá naquela hora.

## A aprovação

As regras são as de email e agenda (`core/google/actions.py`):

- No máximo 5 pedidos esperando.
- **Executa uma vez só.** A primeira aprovação reserva o pedido no banco (`proposed → sending`)
  antes de chamar o Composio; um toque e um "pode fazer" falado ao mesmo tempo não executam duas
  vezes.
- Roda **na versão da ferramenta que estava no cartão**, guardada no pedido.
- Só roda se o app ainda estiver conectado e se o teto do mês deixar.
- Vence em 24 h. Se o servidor cair no meio, fica "não sei se saiu" e nunca é reexecutado sozinho;
  a conversa pede para você conferir no app.
- O resultado volta para a conversa, com a etiqueta "nos apps" (e o link, quando o app devolve um).
- Desconectar um app recusa o que esperava dele, e só dele.

## Orçamento

- **As duas chamadas curtas ao modelo** passam por `check_budgets`, como as do Gmail.
- **O Composio tem um teto do Visão:** no máximo 3 execuções por turno e
  `VISION_COMPOSIO_MONTHLY_CALLS` por mês (padrão 8.000, abaixo das 10.000 do plano grátis). Conta
  cada execução, de leitura ou aprovada, de todos os apps juntos, no `audit_logs` (ação
  `composio_call`, só o app, a ferramenta e o tipo, nunca os argumentos ou o resultado). A conta é
  feita antes da chamada sair. Listar o catálogo e as ferramentas não conta. Ajustes mostra quanto
  já foi no mês.
- No teto, a resposta diz "o limite do mês dos apps acabou" e não inventa o conteúdo; uma escrita
  aprovada não executa.
- **20 s por chamada**, sem repetir nada. Um 429 (limite do Composio) encerra as leituras daquele
  turno.

## Configurar

1. Crie a conta em [composio.dev](https://composio.dev) (o plano grátis não pede cartão) e gere uma
   chave de API do projeto no painel. **O Visão não cria contas.**
2. No `.env` do servidor (na nuvem, `deploy/app.env.example`; no Mac e no instalador,
   `~/.visao/.env`):

   ```bash
   VISION_COMPOSIO_API_KEY=...
   VISION_COMPOSIO_MONTHLY_CALLS=8000
   ```

3. Reinicie o Visão. Em **Ajustes › Integrações › Apps**, toque em **Ver os apps**, ache o app e
   toque em **Conectar**. Abre a página do Composio para você entrar no app; o Visão espera você
   terminar (até 2 minutos), sem precisar de endereço de retorno público.

Sem a chave, nada disso aparece: nem a seção em Ajustes, nem os apps no que ele diz que sabe fazer.

Apps que o Composio não conecta com a entrada dele (pedem credenciais próprias) aparecem no
catálogo desabilitados.

## O que ainda não faz

- **Olhar sozinho.** A mente não olha os apps sem você perguntar. Um "Olhar sozinho" como o do
  Google fica para depois, app por app.
- **Apagar** qualquer coisa pelos apps.
- **Gmail e Google Agenda pelo Composio**: ficam de fora de propósito, para não haver dois caminhos
  (e duas aprovações) para o mesmo email.

## Detalhes do SDK

Conferidos sem rede, com respostas gravadas, em
[`tests/unit/test_composio_sdk.py`](../tests/unit/test_composio_sdk.py) (composio 0.35.0):

- O Visão usa `tools.get_raw_composio_tools` e `tools.execute` (a interface que dá as ferramentas
  com as `tags`), não as sessões do Composio. A escolha da ferramenta e a aprovação são do Visão;
  o `require_approval` do Composio não é usado.
- A chave vai em `Composio(api_key=...)`. A versão vai em cada execução (`version=...`); executar
  sem versão é "latest", que o SDK recusa.
- Conectar usa `connected_accounts.link` e `wait_for_connection` (o `initiate` antigo foi
  aposentado pelo Composio para o OAuth deles). Desconectar é `revoke`, depois `delete`.
- A telemetria de uso do SDK é desligada em toda chamada (é uma variável de contexto, então
  desligar só ao criar o cliente não cobriria as outras threads).
