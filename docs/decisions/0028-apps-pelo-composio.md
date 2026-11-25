# ADR-0028: Os outros apps do dono pelo Composio, com leitura livre e escrita aprovada

- Data: 2026-11-25
- Estado: aceita (o dono aprovou o desenho e a migração `0042` em 25/11/2026)

## Contexto

O Visão já lê o Gmail e a Google Agenda e prepara emails e eventos que só saem depois de o dono
tocar em Aprovar ([GOOGLE.md](../GOOGLE.md)). Cada integração assim custa um cliente HTTP, um
OAuth configurado à mão e uma tabela. O dono perguntou se dá para pôr o
[Composio](https://composio.dev) "nos plugins do Visão": é uma plataforma de ferramentas para
agentes, com o OAuth feito por ela, um SDK Python e mais de 1.800 apps, e tem plano grátis.

O dono escolheu em 25/11/2026:

- **Todos os apps que o Composio oferece**, não uma lista curta. Ele conecta, em Ajustes, os que
  quiser. A exceção é o Gmail e a Google Agenda, que continuam na integração própria: dois
  caminhos para o mesmo email dariam duas aprovações diferentes para a mesma coisa.
- **Aceita que os tokens fiquem no Composio**, com os limites desta ADR.

### O que a documentação do Composio diz (lida em 25/11/2026)

- **Tokens ficam na nuvem deles.** As credenciais são cifradas em repouso (AES-256-GCM) e
  renovadas por eles. Não há como exportar o token: ler uma conta conectada devolve os campos
  mascarados ([token-custody](https://docs.composio.dev/docs/security/token-custody.md)).
- **Usar um app OAuth nosso não muda isso.** Um "custom auth config" muda a marca, os escopos e
  a cota no provedor, mas "não leva o cofre de tokens para a sua infraestrutura" (mesma página).
- **Guardar do nosso lado é só no Enterprise.** BYOC (na AWS, Google Cloud ou Azure) e chaves
  do cliente num KMS nosso são combinados com a equipe deles, no plano Enterprise.
- **Toda chamada passa pelos servidores deles**, que fazem a requisição ao app e devolvem o
  resultado. **Argumentos e resultados ficam nos logs de execução por padrão, até um ano.**
  "Zero Data Retention" desliga isso só para payloads novos e só em plano pago.
- **Cada ferramenta tem dicas de leitura e escrita**: `readOnlyHint`, `createHint`,
  `updateHint`, `destructiveHint` e, em algumas, `idempotentHint`. Eles avisam que são
  atribuídas "na base do melhor esforço"
  ([tool-hints](https://docs.composio.dev/docs/governance/tool-hints.md)).
- **SDK:** pacote `composio` (não o antigo `composio-core`), Python 3.11 a 3.15. O caminho
  recomendado é por sessão (`composio.create(user_id=…, toolkits=[…])`, `session.authorize`,
  `session.execute`); `tools.get` e `tools.execute` seguem como interface antiga suportada. A
  versão de cada ferramenta pode ser fixada (`version="20251111_00"`).
- **Desfazer:** `connected_accounts.revoke(id)` marca a conta como revogada e tenta revogar no
  app (melhor esforço); `connected_accounts.delete(id)` apaga de vez.
- **Limite de requisições:** 2.000 por minuto no plano grátis
  ([rate-limits](https://docs.composio.dev/reference/rate-limits.md)).

### O preço, e as duas páginas que não batem

| | [composio.dev/pricing](https://composio.dev/pricing) | [composio.dev/pricing.md](https://composio.dev/pricing.md) |
|---|---|---|
| Plano grátis | "Free" | "Hobby" |
| Chamadas por mês | 10.000, e "param" no limite | 100.000 (até 20.000 em apps gerenciados por eles) |
| Cartão | não pede | não pede |
| Contas conectadas | até 10 por app | ilimitadas |
| Créditos | US$ 2, uma vez | US$ 2 para "Instant tools" |
| Depois do limite | só no pago: US$ 0,005 por chamada (Standard, US$ 18 por pessoa, "em breve") | apps gerenciados custam de US$ 0,0005 a 0,01 por chamada; Pro a US$ 29 por mês |
| BYOC | Enterprise | não aparece |

Lida em 25/11/2026. O Visão se planeja pelo número menor: **10.000 chamadas por mês, sem
cartão**. Pela página principal, no plano grátis as chamadas param no limite em vez de cobrar,
então não há conta surpresa. Sem cartão cadastrado, também não.

## Decisão

### Onde ficam os tokens

- **No Composio**, por escolha do dono. É uma exceção à regra do Google (a conexão guardada
  cifrada pelo próprio Visão, com chave derivada de `VISION_SECRET_KEY`) e vale só para os apps
  que entram por aqui. **O Visão guarda só a chave da API do Composio** (`.env`) e o nome de cada
  app conectado; nenhum token de app passa por ele.
- **O Composio não recebe quem é o dono.** O `user_id` mandado a ele é um HMAC do id do dono com
  `VISION_SECRET_KEY`: o mesmo sempre, sem nome nem email. Se a chave do servidor mudar, as
  conexões ficam órfãs no Composio e os Ajustes pedem para conectar de novo, como no Google.
- **Ajustes diz isso com todas as letras**, ao lado de Conectar: "A conexão fica guardada no
  Composio, não no Visão. O que ele lê e o que você aprovar passa por lá e fica no registro
  deles por até um ano."
- **Desconectar** revoga e apaga a conta no Composio (`revoke`, depois `delete`) e recusa o que
  estava esperando aprovação daquele app.
- **Escopos mínimos.** Quando o app deixar escolher, pede-se o menor conjunto que lê e faz o
  que as ferramentas ligadas fazem.

### Cada ferramenta passa pelo modelo de segurança do Visão

- **Ler é livre.** Só conta como leitura uma ferramenta com `readOnlyHint` verdadeiro e sem
  nenhuma das outras dicas. Sem dica, ou com dica de criar ou mudar, **é escrita**. Na dúvida, o
  Visão pede aprovação, porque as dicas são de melhor esforço.
- **Apagar fica de fora nesta fase.** Ferramentas com `destructiveHint` não são oferecidas ao
  modelo (`tags={"disable": ["destructiveHint"]}` na sessão, e o código confere de novo antes de
  executar). É a mesma linha do Google, que não pede permissão para apagar email.
- **Toda escrita vira um cartão de aprovação**, igual a email e agenda: mostra o app, o que a
  ferramenta faz em palavras e **todos os argumentos por inteiro** (o canal e o texto da
  mensagem, o título e o corpo da issue, a página). O Visão não usa o `require_approval` do
  Composio (experimental); quem aprova é o Visão.
- **A aprovação segue as regras de `core/google/actions.py`:** no máximo 5 esperando; reservada
  no banco (`proposed → sending`) antes de executar, então um toque e um "sim" falado não
  executam duas vezes; vence em 24 h; se o servidor cair no meio, fica "não sei se saiu" e nunca
  é reexecutada sozinha.
- **Onde fica o cartão.** O `pending_actions` de hoje só guarda "apagar projeto ou painel" e não
  tem os estados de envio. O `google_actions` tem os estados certos, mas é do Google: Desconectar
  o Google recusaria pedidos do Slack. Por isso, **uma tabela nova, `tool_actions`, com as mesmas
  colunas de `google_actions` mais o app, a ferramenta e a versão dela** (migração `0042`).
  O dono aprovou a migração em 25/11/2026.
- **O que vem dos apps é dado de terceiros, nunca ordem.** O resultado entra na resposta dentro
  de um bloco marcado como texto de terceiros, cortado em 8.000 caracteres por ferramenta. Uma
  issue ou mensagem que tente dar ordens ("manda isso para…") consegue, no máximo, gerar um
  cartão que o dono lê antes de aprovar.
- **Só quando ele pergunta.** Nesta fase a mente não olha os apps sozinha. Um "Olhar sozinho"
  como o do Google fica para depois, app por app.
- **Ele lembra do que leu.** Cada leitura vai para o registro do turno
  (`core/decision/record.py`), como as do Gmail.

### Como ele escolhe a ferramenta entre milhares

Não cabem milhares de ferramentas num prompt, nem as de um app grande. O caminho segue o
`core/google/assist.py`:

1. **Conferência em código:** há algum app conectado e a mensagem fala dele (nome do app ou
   palavras do domínio)? Senão, nada roda.
2. **Uma chamada curta escolhe o app** entre os conectados.
3. **O código pede ao Composio as ferramentas desse app** (com a versão fixada) e tira as
   destrutivas. **Uma segunda chamada curta escolhe a ferramenta e os argumentos**, de uma lista
   fechada.
4. **O código classifica:** leitura executa e entra na resposta; escrita vira cartão.

### Orçamento

- **As chamadas ao modelo** dos passos 2 e 3 passam por `check_budgets`, como as do Gmail.
- **As chamadas ao Composio têm um teto do próprio Visão:** no máximo 3 por turno e
  `VISION_COMPOSIO_MONTHLY_CALLS` por mês (padrão 8.000, abaixo dos 10.000 da página
  principal). A contagem é feita no `audit_logs` que já existe (`record_audit`, ação
  `composio_call`), sem tabela nova. No teto, a resposta diz por quê ("o limite do mês dos apps
  acabou") e não inventa o conteúdo.
- **Tempo:** 20 s por chamada ao Composio. Um 429 (`Retry-After`) não é repetido no mesmo turno.

### Manifesto de capacidades

- `Capabilities` ganha `apps: tuple[str, ...]`, os nomes dos apps conectados. Em `actions()`
  entra "ler o que está no Notion, GitHub e Slack do interlocutor quando ele pergunta, e
  preparar mudanças que só saem depois da aprovação dele" (com os nomes reais). Em `absent()`,
  "outras contas" passa a dizer "contas que ele não conectou".
- Um item em [NOVIDADES.md](../NOVIDADES.md) explica como conectar e o que fica onde.

### Configuração

- `VISION_COMPOSIO_API_KEY` (segredo, como `github_token`) e `VISION_COMPOSIO_MONTHLY_CALLS`
  em `apps/api/settings.py`. **Desligado por padrão:** sem a chave, Ajustes não mostra a seção e
  o manifesto não fala de apps.
- **Na nuvem:** a chave entra no `.env` do servidor (`deploy/app.env.example` ganha a linha). A
  conexão abre a página do Composio no navegador do dono, e o Visão espera ela concluir
  (`wait_for_connection`), então não precisa de endereço de retorno público.
- **No app de Mac e no instalador:** a chave entra em `~/.visao/.env`. O pacote `composio` entra
  nas dependências travadas (`infrastructure/deployment/constraints.txt`) e no servidor congelado
  do app de Mac; o build precisa ser conferido, porque o SDK é novo no pacote. O mesmo fluxo de
  conexão funciona sem endereço público.

## Consequências

- O dono ganha qualquer app do catálogo sem uma integração escrita à mão para cada um, e sem
  pagar enquanto ficar abaixo de 8.000 chamadas por mês.
- **Troca aceita:** os tokens desses apps e o que passa por eles ficam no Composio, inclusive nos
  logs de execução por até um ano. Se o Composio vazar, essas contas vazam; o Visão não pode
  apagar os logs. Se isso pesar depois, os caminhos são o plano pago com Zero Data Retention (só
  para payloads novos) ou uma integração própria para o app que importar.
- **As dicas de leitura são deles.** Uma escrita marcada por engano como só leitura executaria
  sem cartão. Por isso a regra é estrita (só `readOnlyHint` sozinho) e os testes cobrem uma
  ferramenta com dicas trocadas.
- **Dependência nova num serviço externo.** Se o Composio cair, só os apps somem; email, agenda
  e o resto do Visão seguem.
- Não confirmado ainda, a conferir no primeiro passo do código: se as dicas vêm junto da
  definição de cada ferramenta no SDK Python, e se `Composio(api_key=…)` existe ou a chave só
  vem do ambiente (`COMPOSIO_API_KEY`).

## Plano (aprovado em 25/11/2026)

Numa branch própria (`apps-composio`), commits pequenos, cada um com testes:

1. **Conferir o SDK** num teste isolado, sem rede (respostas gravadas): de onde vêm as dicas,
   como fixar a versão, como passar a chave. Se as dicas não vierem, tudo vira escrita até haver
   outra fonte.
2. **Configuração e cliente:** `settings`, `integrations/composio/client.py` (o único lugar que
   importa o SDK), o `user_id` por HMAC, o teto por mês.
3. **Tabela `tool_actions`** (migração `0042`) e
   `core/apps/actions.py`, com as regras de aprovação do Google.
4. **Na conversa:** `core/apps/assist.py`, com a conferência em código, as duas chamadas curtas, a
   classificação e o bloco de terceiros. Testes: leitura entra na resposta; escrita vira cartão;
   destrutiva não aparece; dica trocada vira cartão; uma issue com ordens não executa nada.
5. **API e telas:** Ajustes › Apps (catálogo, Conectar, Desconectar, o aviso de onde fica) e o
   cartão de aprovação no chat.
6. **Manifesto e documentação:** `capabilities.py`, `docs/APPS.md`, NOVIDADES.md.
7. **Mac e instalador:** dependência travada e conferência do build congelado.

Antes do passo 2, o dono cria a conta no Composio e gera a chave (o Visão não cria contas).
