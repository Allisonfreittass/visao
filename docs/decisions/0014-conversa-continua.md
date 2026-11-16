# ADR-0014: Uma conversa contínua, com o passado resumido em trechos

- Data: 2026-11-16
- Estado: aceita (aprovada pelo dono em 16/11/2026; implementada no mesmo dia, ver
  [CONVERSA_CONTINUA.md](../CONVERSA_CONTINUA.md))

## Contexto

Hoje cada conversa começa do zero. O que passa de uma para outra é só a memória curada
(`core/memory`), que guarda fatos e preferências, não o fio da conversa. O dono quer como no Hark:
um chat só, que continua de onde parou, sem precisar abrir conversas novas.

Uma conversa única no desenho atual não funciona, por três motivos:
- **Contexto:** a resposta recebe as últimas `VISION_LLM_CONTEXT_CHAR_BUDGET` letras (24 mil). O
  que passa disso some, sem resumo. Desde 16/11/2026, o `fit()` (`core/conversation/service.py`)
  ainda tira as mensagens mais antigas quando o pedido passa do limite por chamada. Numa conversa
  sem fim, ele esqueceria quase tudo.
- **Registro do que ele fez:** `core/decision/record.py` monta "o que você fez nesta conversa"
  por conversa. Esse registro é o que impede que ele negue uma leitura do Gmail que fez de
  verdade. Numa conversa sem fim, ele cresceria até não caber.
- **Coisas presas à conversa:** título, projeto, páginas, painéis de origem, pesquisas e o
  `KnowledgeGap` apontam para `conversation_id`.

## Decisão

### 1. A conversa contínua

- Cada dono tem uma conversa marcada como **contínua** (`conversations.continuous`, no máximo uma
  por dono, numa migração nova com RLS). O app abre nela por padrão: no web, o menu mostra
  "Conversa" no topo e as outras abaixo, como arquivo.
- **Os Projetos continuam** para separar um assunto de propósito. Uma conversa dentro de um
  projeto segue como hoje, com começo e fim.
- Conversas antigas não são juntadas automaticamente. Ficam como arquivo e continuam abrindo e
  sendo lidas como estão.

### 2. Trechos e resumos

- A conversa contínua é dividida em **trechos**, numa tabela nova `conversation_segments`, com
  dono, conversa, primeira e última mensagem, título curto, resumo, palavras-chave e o período.
- **Um trecho fecha** quando a conversa fica parada por mais de 3 horas, na virada do dia no
  fuso do dono, ou quando passa de cerca de 40 mensagens. O worker fecha o trecho por um job da
  fila (`segment_summary`), dentro do orçamento da autonomia, e escreve:
  - um **título** de 2 a 4 palavras ("Viagem a Santiago");
  - um **resumo** de até 600 caracteres, só com o que foi dito e feito;
  - as **palavras-chave**.

  O resumo é conferido como as outras saídas: sem link, número ou nome que não esteja nas
  mensagens do trecho.
- **O que a resposta recebe:**
  1. o trecho aberto, inteiro, até o limite de hoje;
  2. até 3 resumos de trechos antigos, escolhidos pelas palavras-chave da mensagem atual, com o
     mais recente como desempate;
  3. a memória curada, como hoje;
  4. o `fit()`, que continua garantindo o limite por chamada. Os resumos saem antes do trecho
     aberto.
- O dono pode pedir "lembra quando falamos de X?". A busca nos resumos é a mesma, com mais
  resumos permitidos.

### 3. O registro do que ele fez

- Na contínua, o registro (`conversation_block`) passa a cobrir **os últimos 7 dias**, mais as
  ações dos trechos escolhidos no passo 2. O resto continua no banco (`decisions`) e na Bancada.
- A correção de negação falsa (`false_denials`, `correction_block`) vale para as mensagens que
  vão no contexto, como hoje.

### 4. No chat

- **Divisões visuais:** um cabeçalho por trecho ("Hoje", "Ontem", "Viagem a Santiago · 14/11")
  e uma rolagem que carrega para trás aos poucos (`GET /conversations/{id}/messages?before=`).
- **Pesquisas, páginas e painéis** seguem apontando para a conversa. Na contínua, também apontam
  para o trecho, para a Bancada agrupar.

### 5. Clientes

- **Web:** este repositório faz, junto com o servidor.
- **iPhone (`apps/ios`):** o agente do Mac faz depois. A API muda só por acréscimo: um campo
  `continuous` na conversa, a lista de trechos e a paginação. Um app que não conhece nada disso
  continua funcionando como hoje, com a contínua aparecendo como uma conversa comum.

## Consequências

- Uma chamada curta a mais por trecho fechado, pelo worker, com o Haiku: bem menos de US$ 0,001
  por trecho, no orçamento da autonomia.
- Um resumo pode perder um detalhe. O original continua no banco, e "lembra quando…" pode abrir
  o trecho inteiro.
- Lacunas e pesquisas da curiosidade, que hoje contam por conversa, passam a contar por trecho
  na contínua.

## Ordem de implementação, depois da aprovação

1. Migração e modelo (`continuous`, `conversation_segments`), com testes de RLS no `db-test`.
2. Fechar trechos e resumir no worker, com testes do resumo conferido.
3. Montagem do contexto (trecho aberto, resumos e memória) e registro de 7 dias, com testes.
4. API: paginação e trechos. Web: abrir na contínua e mostrar as divisões.
5. Doc do formato para o `apps/ios`.
