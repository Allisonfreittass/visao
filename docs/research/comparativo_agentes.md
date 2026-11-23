# O que o Visão aprende com OpenClaw, Goose e OpenCode

Data: 23/11/2026. Base do Visão: `098f568`. Versões estudadas (clone raso do dia):

| Projeto | O que é | Licença | Commit |
|---|---|---|---|
| [OpenClaw](https://github.com/openclaw/openclaw) | assistente pessoal sempre ligado, em vários canais (WhatsApp, Telegram…) | MIT | `314ae9ae9` |
| [Goose](https://github.com/block/goose) | agente de uso geral da Block, centrado em extensões MCP | Apache-2.0 | `059fee2` |
| [OpenCode](https://github.com/sst/opencode) | agente de código com servidor e clientes (terminal, web) | MIT | `9ae270f` |

**Método.** Cada repositório foi lido por um agente separado, que conferiu no código do Visão o
que já existe antes de propor qualquer coisa. Nada dos três foi executado nem instalado. As falhas
do Visão listadas abaixo foram conferidas de novo no código, com o arquivo e a linha. O que não
foi conferido está marcado como **(a conferir)**. Daqui só saem ideias; nenhum trecho de código
foi copiado. Se algum for copiado no futuro, a licença pede crédito.

## Conclusão

Nenhum dos três tem o que faz o Visão ser o Visão:

- a decisão do que acontece fica no código, e o modelo só escreve;
- a memória é curada por uma política determinística;
- o orçamento trava quando acaba (fail-closed);
- a iniciativa tem freios: horário de silêncio, duas aberturas sem resposta, limite por dia.

Nos três, o modelo faz o que as ferramentas dele permitem. O OpenClaw diz isso com todas as
letras no `SECURITY.md`.

**O ganho está na robustez de operação**: o que acontece quando a rede cai no meio, quando o
modelo falha depois de já ter agido, quando a mesma aprovação chega duas vezes, quando o processo
reinicia. Os três apanharam disso em produção e têm regras claras para cada caso. O estudo achou
**dez falhas reais** desse tipo no Visão. Elas vêm primeiro.

## 1. Falhas encontradas no Visão

**Corrigidas em 23/11/2026:** F1, F2 e F3, cada uma com um teste que falha no código anterior
(`tests/integration/test_google.py`, `tests/integration/test_turn_once.py`,
`tests/unit/test_turn_lock.py` e, no PostgreSQL, `tests/integration/test_hardening_postgres.py`).

| # | O que pode acontecer | Onde | Ideia de |
|---|---|---|---|
| F1 | **Email ou evento enviado duas vezes.** `approve()` confere `status == "proposed"` sem travar a linha, envia e só depois muda o estado. Um toque em Aprovar junto com um "sim" falado, ou dois aparelhos, mandam duas vezes. A proposta também nunca expira. | `core/google/actions.py:160` | OpenClaw |
| F2 | **Turno repetido.** A mensagem não tem id do cliente e nada impede dois turnos ao mesmo tempo na mesma conversa. Se o celular reenviar numa rede ruim, as ações do turno (criar projeto, anotar) podem acontecer duas vezes. | `MessageIn` em `apps/api/routes/conversations.py:159`; não há trava em `run_turn` | OpenClaw |
| F3 | **Ação feita sem aviso.** As ações do turno rodam antes da resposta. Se o modelo falha depois, a API devolve erro 502 e a pessoa não fica sabendo que o projeto foi criado. Se ela tentar de novo, a ação se repete. | `core/decision/pipeline.py:270` | OpenClaw |
| F4 | **Resultado do Mac perdido.** No braço, o envio do resultado fica no mesmo `try` que a execução. Se a rede cair depois que o Claude Code terminou, o resultado é descartado. O servidor só marca a tarefa como falha depois de 3 h, embora o braço desista em 30 min. | `arm/visao_braco.py:212-233`; `STALE_RUNNING` em `core/arm/service.py:28` | OpenCode |
| F5 | **O braço pode ampliar as próprias permissões.** Com `Edit`/`Write` liberados no projeto, uma tarefa pode escrever `.claude/settings*.json` (regras e hooks) ou `.mcp.json`, e isso vale para as tarefas seguintes. O `CLAUDE.md` do projeto também é lido, o que abre caminho para injeção. Não foi conferido se o próprio Claude Code protege esses arquivos **(a conferir)**. | `NEVER` em `arm/visao_braco.py:52` | OpenCode |
| F6 | **Prompt grande demais ou resposta vazia derrubam o turno.** O fallback só passa para o próximo provedor em 429 e 5xx, então um "prompt too long" (400) de um provedor com janela menor vira erro. Uma resposta vazia vira 502, sem nova tentativa. | `_should_fall_back` em `integrations/llm/fallback.py:26`; `EmptyReplyError` em `core/conversation/service.py:340` | Goose, OpenCode |
| F7 | **Uma página pode fechar o bloco de dados.** O texto lido vai dentro de `<link url="…">…</link>`. Uma página que contenha `</link>` seguido de texto falso de sistema sai do bloco. Tokens de chat do Qwen (`<|im_start|>`) também não são removidos. | `core/conversation/links.py:109` | OpenClaw |
| F8 | **Cota esgotada descoberta várias vezes.** A pausa de um provedor sem cota fica na memória de cada processo e dura sempre 15 min. A API e o worker descobrem cada um por si. A hora de reset que o provedor informa já é lida, mas não é usada para a pausa. | `fallback.py:23,57`; `reset_at` em `integrations/llm/openai_compatible.py:175` | OpenClaw |
| F9 | **Status ao vivo pode sumir depois de um restart.** Os ids dos eventos SSE recomeçam em 1 a cada processo. Um cliente que volta com um `Last-Event-ID` antigo e maior pula os eventos do turno novo (o lado do web não foi conferido). | `core/conversation/progress.py:83` | OpenCode |
| F10 | **Memória baseada só no que o Visão disse.** A política só exige uma fala da pessoa como evidência para memória `relational`. Memórias `episodic` e `semantic` podem nascer apenas de respostas do assistente, inclusive das que resumiram uma página ou um email. | `core/memory/policy.py:114` | OpenClaw |

Três lacunas menores:

- O custo das tarefas do Mac é gravado (`core/arm/service.py:258`), mas não entra em nenhum total
  do orçamento.
- Não há cache de prompt: nenhum `cache_control`, e o preço não separa leitura e escrita de cache.
- Quando o timeout do braço mata o Claude Code, processos filhos podem continuar rodando, porque o
  `Popen` não abre um grupo de processos **(a conferir)**.

## 2. O que fazer, em três ondas

Esforço: **P** (horas), **M** (um ou dois dias), **G** (uma semana ou mais, com ADR).

### Onda 1: corrigir as falhas (sem ADR, só código e testes)

1. **Aprovação que só vale uma vez e tem validade** (F1). Ideia do OpenClaw. **P**
   - Trocar a leitura por uma reserva atômica:
     `UPDATE … SET status='sending' WHERE id=:id AND status='proposed' AND created_at > now()-24h RETURNING *`.
   - Ao subir a API ou o worker, o que ficou em `sending` vira `unknown`, com o aviso "pode ter
     saído; confira em Enviados". Nunca reenviar sozinho.
   - Conferir de novo a janela do evento no momento da aprovação.
   - Usar o mesmo padrão em `pending_actions` e na aprovação de tarefas do Mac.
2. **Cada mensagem roda uma vez só** (F2). Ideia do OpenClaw. **P–M**
   - `client_message_id` em `MessageIn`, gerado pelo web uma vez por envio, com índice único
     `(conversation_id, client_message_id)`. Um reenvio devolve o turno já feito.
   - `pg_advisory_xact_lock` por conversa em volta de `run_turn`.
3. **Quando o modelo falha depois de agir, o código responde** (F3). Ideia do OpenClaw. **P**
   - Pegar o `LLMError` em `pipeline.py` quando já existem ações ou propostas no turno.
   - Gravar uma mensagem montada só com os fatos do `TurnPlan`, por exemplo: "Criei o projeto
     «Chile» e deixei o email para você aprovar. Não consegui escrever o resto agora."
   - É a regra "ele só diz que fez o que fez", agora escrita pelo código.
4. **Braço mais firme** (F4, F5). Ideias do OpenCode. **P–M**
   - Rodar o Claude Code isolado:
     - `--setting-sources` sem as configurações do projeto;
     - `--settings '{"disableAllHooks":true}'`;
     - `--strict-mcp-config`;
     - `Edit(.claude/**)`, `Write(.claude/**)` e `Write(.mcp.json)` em `NEVER`.

     Os nomes dos flags vêm da documentação do Claude Code e precisam ser testados na versão
     instalada.
   - Guardar o resultado num arquivo local antes de enviar e reenviar até receber 2xx. No
     servidor, `finish()` passa a aceitar a repetição sem efeito.
   - O heartbeat informa a tarefa em andamento, e `STALE_RUNNING` cai para o timeout mais uma
     margem.
   - Abrir um grupo de processos e matá-lo inteiro no timeout.
   - Somar `cost_usd` ao orçamento do dia.
5. **Modelo: estouro de contexto, resposta vazia e cota** (F6, F8). Ideias de Goose, OpenCode e
   OpenClaw. **P–M**
   - Reconhecer "prompt too long" por uma lista curta de padrões e criar o tipo
     `LLMError("context_length")`. Diante dele: refazer o `fit()` com 70% do limite e tentar mais
     uma vez.
   - Resposta vazia: tentar uma vez no próximo provedor, dentro do orçamento.
   - Gravar a pausa por provedor no banco (como o ledger), com a duração vinda do reset informado
     pelo provedor. Enquanto o principal estiver pausado, o worker adia o trabalho autônomo para
     não gastar a cota gratuita que a conversa vai precisar.
   - Repetir chamadas avulsas (resumos, classificação) só quando o provedor claramente não as
     executou: 429, 503/529 ou conexão que não chegou a sair. Respeitar `x-should-retry`.
6. **Um só envelope para conteúdo de fora** (F7). Ideia do OpenClaw. **P**
   - Criar `core/untrusted.py` com `wrap(fonte, texto, meta)`.
   - O envelope usa marcadores com um código aleatório por bloco, neutraliza imitações dos
     marcadores (inclusive com caracteres parecidos ou invisíveis) e remove tokens de chat
     (ChatML/Qwen, Llama, Mistral).
   - Frases suspeitas vão para o `audit_logs`; não são bloqueadas.
   - Links, Gmail, navegador, estudo e GitHub passam a usar esse envelope.
7. **Ids de evento que sobrevivem a restart** (F9). Ideia do OpenCode. **P**
   - Começar o contador em `time.time_ns() // 1000`.

### Onda 2: melhorias (médias, algumas pedem ADR curta)

8. **Memória com origem** (F10). Ideia do OpenClaw. **M**
   - Cada mensagem ganha `provenance` (dono / agente / externo / iniciativa), preenchida a partir
     do `TurnPlan`.
   - A política recusa com o motivo `external_only` quando nenhuma evidência vem da pessoa.
   - O curador pode dizer `replaces`, e o registro antigo ganha `valid_until`. Assim "mora em SP"
     deixa de conviver com "mudou para Curitiba".
   - `POST /memory/forget?conversation_id=…`, com prévia do que vai sair.
9. **Resumos de trecho que guardam o que ficou em aberto.** Goose e OpenCode chegaram à mesma
   ideia. **P–M**
   - Acrescentar a `segments.py` os campos `pedidos_em_aberto` e `prometido_pelo_visao`.
   - Cada item precisa ser trecho exato do segmento, conferido no código, como já se faz com
     nomes e números.
   - Esses campos alimentam a continuidade e o resumo da manhã.
10. **Um portão único de políticas.** Ideia do Goose, sem os defeitos dele. **M**
    - Criar `core/policies/gate.py`: toda ação, email, tarefa do Mac e futura ferramenta passa
      por inspetores que respondem Permitir, Perguntar ou Negar.
    - Regras de combinação:
      - o mais restritivo vence;
      - um erro de inspetor conta como Negar;
      - um classificador pode subir para Perguntar, nunca conceder.
    - Inspetores:
      - **permissão:** as permissões fixas do dono;
      - **contaminação:** se o turno leu conteúdo de fora, toda ação para fora vira Perguntar;
      - **destino:** um destinatário ou domínio que a pessoa nunca escreveu vira Perguntar;
      - **repetição.**
11. **Revisor independente para propostas que nasceram sozinhas.** Ideia do Goose. **P–M**
    - Antes de uma proposta vinda de um pensamento, email ou página virar card, uma chamada barata
      vê só as palavras da pessoa e a ação proposta.
    - Bloqueio, erro ou resposta ilegível descartam a proposta ou marcam o card como "suspeito".
    - Nunca aprova nada. O custo sai do orçamento da autonomia.
12. **Corpus de injeção no CI.** Ideia do Goose. **P–M**
    - `experiments/eval_injection.py` com emails, páginas e compartilhamentos hostis.
    - O teste exige zero ações executadas e nenhuma proposta para destinatários novos.
    - Usa respostas gravadas do modelo no CI, e o modelo real quando o modelo for trocado.
13. **Avisar o dono quando um job morre.** Ideia do OpenClaw. **P**
    - Um aviso de sistema por `(tipo de job, tipo de erro)`, no máximo um por dia.
    - Fica fora da cota de 5 avisos do amigo e fora da voz dele.
14. **Braço: desfazer, perfis e fechamento.** Ideias do OpenCode. **M**
    - **Desfazer:** foto do projeto antes e depois da tarefa, num git separado que não mexe no
      `.git` do projeto. Os arquivos mudados entram no resultado como fato apurado pelo braço, em
      vez de depender do relato do Claude. Um botão "Desfazer" vira uma tarefa aprovada que o
      braço executa sem o Claude.
    - **Perfis em `braco.json`:**
      - `olhar` (só leitura) para o que o Visão propõe;
      - `mexer` para o que você escreve com `/mac`.

      O Mac continua decidindo o limite.
    - **Fechamento:** ao bater o limite de turnos ou de custo, uma chamada final sem ferramentas
      responde "o que fiz / o que falta".
    - **"Recusar com ajuste":** um campo de nota que gera uma proposta revista, que de novo
      precisa de aprovação.
15. **`visao doctor`.** Ideia do OpenClaw. **P**
    - Um comando de autoconferência que checa:
      - Postgres preso ao loopback;
      - portas do container do navegador;
      - força da chave e da criptografia do Google;
      - chaves VAPID;
      - logs sem conteúdo sensível;
      - modelo pequeno com leitura de web ou Gmail ligada.
16. **Cache de prompt.** Ideia do OpenCode. **M**
    - Pôr as partes estáveis do system prompt primeiro (identidade, regras, capacidades) e as que
      mudam depois (memória, hora, fatos do turno).
    - Separar no `Pricing` o preço de leitura e o de escrita de cache, e reservar sempre pelo
      pior caso.
    - Só vale nos provedores que oferecem cache.

### Onda 3: capacidades novas (grandes, cada uma com ADR)

17. **Cliente MCP com catálogo fechado.** Ideia do Goose, com proteções que ele não tem. **G**
    - Só servidores remotos (HTTP). Nada de `npx` no servidor.
    - O dono liga cada ferramenta e diz a classe dela (leitura / para fora / destrutiva). A classe
      nunca vem da anotação do servidor.
    - As ferramentas ligadas entram na lista fechada que `core/actions.py` já usa:
      - leitura roda direto;
      - para fora vira proposta;
      - o resultado entra como dado de terceiros, com tamanho limitado.
    - **Guardar uma impressão (hash) do nome, da descrição e do schema de cada ferramenta.** Se o
      servidor mudar algo, a ferramenta é desligada até nova aprovação.
    - Isso refina o ADR-0009 sem quebrá-lo: o modelo continua escolhendo só dentro de uma lista
      que o código montou.
18. **"Quando eu falar de X, me lembra de Y."** Ideia do OpenClaw. **M**
    - Gatilhos por palavra conferidos no código antes da resposta, sem chamada ao modelo.
    - Limites: no máximo 1 vez a cada 24 h, 3 disparos no total, validade de 90 dias.
    - Só é cancelado quando a pessoa pede explicitamente.
    - Pela regra do projeto, ganha uma linha em `capabilities.actions()` e um item em
      `docs/NOVIDADES.md`.
19. **Metas com critério de sucesso verificável.** Ideia do Goose. **M**
    - Uma lista fechada de critérios conferidos em código: `painel_abaixo_de`, `fontes_concordam>=2`,
      `testes_do_braco_passam`, `data_passou`.
    - O ciclo fecha a meta por esse critério, não pelo julgamento do modelo.
    - Novas tentativas do braço ficam dentro da mesma aprovação e do mesmo orçamento.
20. **Turno em passos ordenados.** Ideia do Goose. **G**, refatoração gradual.
    - O `run_turn` (~800 linhas) vira uma lista de passos testáveis um a um com o
      `FakeLLMProvider`.
    - Cada capacidade passa a se registrar ali.
21. **Telegram ou WhatsApp como canal.** Ideia do OpenClaw. **G**, só se você quiser.
    - O Web Push já resolve o alcance.
    - Se vier: o dono é fixado pelo id numérico; quem não for o dono não recebe nada; as mensagens
      do canal caem na conversa contínua; nenhuma aprovação vale por texto do canal.

## 3. O que não copiar

- **Loja de skills ou plugins que rodam código** (OpenClaw). O próprio OpenClaw diz que um plugin
  malicioso instalado pelo dono está "fora do escopo". Além disso, isso empurraria o Visão para ser
  um agente genérico.
- **Ordens permanentes escritas no prompt** (OpenClaw). É autoridade definida por texto, e no
  Visão as políticas ficam no código.
- **Silêncio decidido em texto livre** (OpenClaw). O modelo responde `NO_REPLY`, e o código precisa
  de dezenas de casos especiais para reconhecer isso. O JSON mais a decisão em código do Visão é
  melhor.
- **Confiar na anotação do servidor MCP** (Goose). O Goose libera sozinho qualquer ferramenta que o
  servidor diga ser `readOnly`, e um servidor malicioso pode simplesmente mentir.
- **Deixar um classificador conceder permissão** (Goose). Ele pode subir o nível para Perguntar,
  nunca para Permitir.
- **Inspetor que deixa passar quando dá erro** (Goose). Os inspetores de segurança, o revisor e a
  checagem de malware do Goose deixam passar em caso de erro. No Visão, todo portão trava, como o
  orçamento.
- **Modo "automático" para o que roda sozinho** (Goose). As receitas agendadas do Goose aprovam
  todas as ferramentas.
- **Retomar sozinho trabalho com efeito externo depois de um restart** (OpenCode). O OpenCode
  admite que efeitos podem se repetir. No Visão, retomar só avisa ou oferece continuar.
- **Lista de comandos permitidos junto com permissão de editar** (OpenCode e o próprio braço).
  `Bash(npm run *)` mais `Edit` permite reescrever o `package.json` e rodar qualquer coisa.
  Prefira comandos exatos (`Bash(make test)`) até existir o usuário separado no Mac (fase 3 do
  braço).
- **Ruminação.** O OpenClaw precisou escrever "não repita tarefas antigas" no prompt de
  iniciativa. O `core/mind/think.py` continua de propósito a partir de `last_thoughts`, então vale
  ficar de olho no mesmo problema.
- **A maquinaria inteira.** O OpenClaw tem cerca de 52 mil arquivos, e o OpenCode tem um módulo de
  compactação de 1.259 linhas sobre o framework Effect. O que vale copiar são as regras
  (idempotência, reserva atômica, origem da memória), não o código.

## 4. O que o Visão já faz melhor

- **Ações decididas em código**, com lista fechada e `deeds_guard`. Nos três, o limite é o que o
  modelo e as ferramentas permitem.
- **Orçamento que trava** (`integrations/llm/budget.py`). Nenhum dos três tem limite de gasto
  local com reserva antes da chamada.
- **Fallback no meio da conversa.** O Goose só troca de provedor ao iniciar a sessão.
- **Resumos conferidos no código** (nenhum nome, número ou link que não esteja no trecho). OpenClaw
  e OpenCode confiam no modelo, no máximo com uma auditoria feita por outro modelo.
- **Memória com evidência e política versionada.** No OpenClaw, o agente escreve `MEMORY.md`
  direto quando a pessoa pede.
- **Freios na iniciativa.** O OpenClaw tem um job a cada 30 minutos e confia no modelo para ficar
  calado.
- **Braço só de saída**, sem porta aberta, com token revogável e lista de permissões no Mac.
- **Equivalentes, sem nada a copiar:** a fila de jobs com lease, fencing e dead-letter, e a busca
  com DNS fixado contra SSRF.

## 5. Limites deste estudo

- **Leitura, não execução.** Nenhum dos três foi rodado. Partes do OpenClaw (a política de
  failover e os gatilhos por assunto) foram tiradas da documentação dele, não do código.
- **Falhas confirmadas por leitura.** As falhas F1 a F10 foram confirmadas lendo o código do
  Visão, mas nenhuma foi reproduzida num teste. O primeiro passo de cada correção é escrever o
  teste que falha.
- **Flags do Claude Code.** Os nomes citados no item 4 precisam ser testados na versão instalada
  no Mac.
- **Foto do momento.** Os três projetos mudam todo dia. O estudo vale para os commits da tabela
  do topo.
