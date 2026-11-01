# Fase 10B.0–10B.1 — Correções locais da fila e admissão de orçamento

Relato da etapa local anterior à autorização de publicação; atualização de validação ao final.

Data: 01/11/2026. Base: `afc2295b8d631e8cb793100a6a92e216bd89230e`.

## Escopo e resultado

Implementação local autorizada após a entrega dos seis documentos da Fase 10A. Trabalho em checkout isolado, sem alterar o código da cópia principal e sem commit, push, PR, migração, serviço novo, inferência real ou deploy. Não foram lidas credenciais de produção. Nenhuma alteração em Cloudflare ou Supabase.

Cópia de trabalho: `/Users/allisonfreitas/Documents/Codex/2026-10-31/referenced-chatgpt-conversation-this-is-an/work/visao-phase10-local`.

Os dois achados reproduzidos receberam correções e testes de regressão: recuperação de jobs respeita o limite de tentativas e o fallback recusa preços positivos antes de despachar. A admissão de chamadas na fábrica da API/worker exige evidência válida de gratuidade e reserva persistente compartilhada. A validação em PostgreSQL real ainda está pendente; não se recomenda publicação neste estado de verificação.

## Fila

- `claim_next` filtra `attempts < max_attempts` também na recuperação de lease expirado. Trabalho elegível esgotado vai a `DEAD`, sem nova execução.
- Cada claim recebe token aleatório novo em `locked_by`, aproveitando a coluna existente. O prefixo identifica o worker; o sufixo distingue execuções mesmo com nome, relógio e número de tentativa repetidos.
- O runner captura um `Lease` imutável antes de executar o handler. Rollback ou refresh do objeto não substitui esse token pelo da execução nova.
- `complete`, `fail`, `defer` e `renew` exigem esse lease e atualizam condicionalmente por ID, estado, token e validade. Escrita rejeitada retorna falso, gera log operacional sem conteúdo e o runner informa `lease_lost`.
- Cancelamento libera a posse e impede conclusão posterior. Adiamento mantém a política anterior de devolver a tentativa; o próximo claim recebe outro token.
- Uma recusa de admissão não tratada pelo handler é adiada em 15 minutos, sem gastar tentativa. Handlers com tratamento interno próprio continuam respeitando seus mecanismos existentes; não foi reescrita a autonomia.

Limite: isso protege as mutações da fila, não desfaz inferência ou efeitos de domínio já confirmados pelo handler. Exatamente uma execução de efeitos externos continua dependendo de idempotência própria. `renew` está disponível, mas não foi instalado heartbeat automático. Um handler que ultrapasse a validade perde o direito de concluir a fila; não há cancelamento remoto garantido.

## Orçamento

`integrations/llm/budget.py` introduz admissão antes da chamada. A fábrica em `apps/api/llm.py` envolve o provedor principal e cada reserva com o guard. Adaptadores HTTP construídos pela fábrica usam `max_retries=0`: cada chamada admitida corresponde a uma tentativa de transporte; fallback precisa de nova reserva. O adaptador genérico mantém seus testes e sua capacidade explícita de retry quando utilizado fora da fábrica.

O fallback também recusa preços positivos ou desconhecidos por comparação com zero. Não existe opção de habilitar cobrança neste incremento: `llm_max_paid_spend_usd` aceita apenas zero.

### Evidência de gratuidade

`VISION_LLM_FREE_GRANTS` é uma lista configurada pelo operador, vazia por padrão. Cada entrada exige nome do provedor, endpoint HTTPS e modelo exatos, URL da evidência, verificação e expiração com fuso, validade de no máximo sete dias e preço explicitamente zero em todas as dimensões suportadas: input, output, cache, áudio, ferramentas, roteamento e plataforma. Não há endpoint para o modelo criar ou modificar essa autorização. URLs não podem conter credenciais, query ou fragmento.

Esta evidência é uma declaração revisada pelo operador, não um verificador automático de contratos ou faturamento. Não foi criada autorização real nesta rodada. Preço zero configurado ou nome contendo “free” não libera chamada.

### Reserva e falha conservadora

O ledger reutiliza `system_flags`, chave `llm_budget_v1`, sem novo modelo ou migração. Todas as instâncias usam o mesmo registro. No PostgreSQL, inicialização com `ON CONFLICT DO NOTHING` e transação curta com bloqueio de linha; no SQLite de teste, `BEGIN IMMEDIATE`. Nenhum lock SQL permanece aberto durante inferência.

Antes do envio, reservar chamada, teto de tokens e vaga de concorrência. Limites globais iniciais: 30 chamadas/dia, 10/hora, 60.000 tokens de entrada/dia, 15.000 de saída/dia, até 32.768 de entrada e 4.096 de saída por chamada e uma chamada em voo. São configurações locais do desenho, não medições nem ajustes de produção. Os controles existentes de autonomia/conversa continuam adicionais; quotas transacionais por proprietário/finalidade ficam para a etapa de continuidade.

Reservas não utilizadas integralmente permanecem contabilizadas. Falhas conhecidas liberam a vaga sem devolver a quota. Timeout, rede, resposta ambígua e interrupção inesperada conservam a vaga como `unknown`. Crash após reservar também conserva a vaga; reinício ou mudança do dia não a apagam. Isso pode suspender novas inferências até revisão operacional: disponibilidade foi sacrificada para não presumir que uma chamada remota terminou. Não foi criado botão ou rotina automática de reset.

Circuit breaker persistente: três falhas, 15 minutos de espera e uma sonda após expiração. Banco indisponível ou falha na reconciliação bloqueiam chamadas posteriores sem fingir consumo zero. Custo informado diferente de zero, tokens negativos ou uso acima do reservado congelam novas admissões e rejeitam a resposta.

Limite de tokens: entrada usa proxy conservador de bytes serializados mais margem de 1.024, não tokenizer universal. A reconciliação cobra excesso observado e congela o ledger, mas não desfaz uso já ocorrido. A garantia anterior à requisição é de reserva do teto estimado; um teto exato exige tokenizer/contrato validado do modelo. Custo de hospedagem e cobrança externa não são controlados pelo ledger. Nenhuma garantia de gratuidade permanente foi inventada.

## Verificação realizada

Na cópia isolada, com a virtualenv existente e sem instalar dependências:

- `python -m pytest -q --tb=short`: **426 passaram, 7 pulados**, 12,01 s na execução final.
- `ruff check .`: passou.
- `ruff format --check .`: passou, 214 arquivos.
- `git diff --check`: passou.

Os seis novos testes PostgreSQL e o teste preexistente de migração foram pulados por ausência de `VISION_TEST_DATABASE_URL`. Docker está instalado, mas seu daemon não está ativo; não foi iniciado. Não foi encontrado PostgreSQL local disponível. Sucesso em SQLite não substitui prova de concorrência no PostgreSQL.

Casos novos incluem limite após crash; rejeição de complete/fail/defer/renew antigos; refresh após troca de posse; defer/reclaim com relógio e tentativa iguais; cancelamento e renovação; runner adiando orçamento; autorização expirada, futura, incompleta ou de modelo/endpoint diferente; fallback pago não invocado; fallback elegível com nova reserva; limite de payload/tokens; reinício e crash sem refund; resposta com custo/uso indevido; erro do banco e reconciliação; circuit breaker persistente e sonda única.

A corrida de orçamento testada em SQLite usa 100 tentativas concorrentes por conexões independentes e admite exatamente cinco para o teto configurado de cinco. Isso testa reserva, sem 100 inferências. Os testes PostgreSQL preparados repetem a corrida, claims concorrentes e quatro operações de posse antiga em schema local descartável. Exigem URL de loopback cujo nome de banco contenha `test`, criam somente schema com nome aleatório e removem esse schema ao terminar. Não foram executados nesta entrega.

Frontend e Cloudflare não foram modificados. Não foram repetidas suas suítes. Não houve teste físico, ativação de sensor, modelo real ou medição de faturamento.

## Antes de qualquer publicação

1. Executar os sete testes pendentes em PostgreSQL local descartável e revisar eventuais diferenças.
2. Revisar evidência real de gratuidade e limites. Sem grants, esta versão bloquearia novas inferências ao ser publicada; não publicar esperando manter o comportamento atual automaticamente.
3. Planejar parada/expiração dos jobs em voo: workers antigos não conhecem fencing. Misturar versões não fornece a proteção nova.
4. Revisar a política de reservas `unknown`, observabilidade e recuperação operacional antes de liberar uso real. Não liberar vaga desconhecida por conveniência nem apagar o ledger para contornar quota.
5. Apresentar diff e plano operacional para autorização de publicação separada. Não há commit ou push; CD não foi disparado. Reverter apenas o código para a versão anterior também reabriria fallback pago e mutações sem fencing.

## Referências técnicas

O desenho usa operações descritas na documentação oficial: [SQLAlchemy — PostgreSQL INSERT ON CONFLICT](https://docs.sqlalchemy.org/en/20/dialects/postgresql.html#insert-on-conflict-upsert), [SQLAlchemy — transações SQLite](https://docs.sqlalchemy.org/en/20/dialects/sqlite.html#transactions-with-sqlite-and-the-sqlite3-driver) e [PostgreSQL — bloqueios explícitos](https://www.postgresql.org/docs/current/explicit-locking.html). Essas referências sustentam a escolha das primitivas; não substituem os testes PostgreSQL pendentes.

## Atualização — publicação autorizada e validação PostgreSQL

Após a entrega local, o usuário autorizou a publicação. O ambiente Colima já instalado foi iniciado e um PostgreSQL 16 descartável foi criado a partir da imagem pgvector já disponível, com porta de loopback aleatória. Todos os testes passaram: **438 passaram, nenhum pulado**, em 14,83 s. Isso inclui os seis novos testes de concorrência/fencing em PostgreSQL e a migração preexistente. O banco temporário será removido ao terminar a validação. Nenhum teste de migração foi apontado para produção.

A integração Cloudflare também foi ajustada para encaminhar as nove novas configurações do guard ao Container. Seus **9 testes e o typecheck passaram**. Ruff check e format passaram. O adapter passou a considerar também `usage.cost` do provedor: preço configurado zero não oculta custo positivo informado; valores não finitos, negativos ou inválidos são rejeitados. Cinco regressões adicionais cobrem essa leitura.

O catálogo oficial de modelos foi consultado nesta rodada e confirmou prompt/completion zero para `nvidia/nemotron-3.5-super-vl:free`. A documentação oficial descreve a variante `:free` como sem custo, desde que não se inclua modelo pago na lista de fallback. Este payload utiliza somente mensagens textuais e nenhum plugin, ferramenta, cache explícito ou áudio. Somente esse endpoint/modelo recebeu grant. O fallback NVIDIA fica sem grant e é recusado antes de rede. Não houve nova contratação.

Grant verificado em `2026-11-01T19:48:16+00:00`, com expiração em `2026-11-08T19:48:16+00:00`. A evidência deve ser renovada após conferência antes desse prazo; sem renovação, novas inferências são recusadas, preservando dados e leitura de histórico. Esta publicação não cria rotina automática que renove a própria autorização.

O procedimento de publicação usa o CI/CD existente: pausar autonomia e verificar ausência de jobs em execução; commitar somente arquivos revisados, sem coautor; push normal sem força; aguardar CI e CD; verificar SHA, readiness, resposta sintética de custo zero e ledger; restaurar a preferência anterior de autonomia. Pausa humana feita durante a manutenção é respeitada. Se a verificação falhar, manter a pausa e investigar; o CD já possui rollback de saúde.

Essa autorização substitui a restrição anterior de não publicar para este incremento. Não abrange fases posteriores de sessão/PWA/push/voz ou mudança de plano. Não se alterou schema nem se ampliaram os arquivos que o autoeditor pode modificar.

Fontes da atualização: [variante gratuita OpenRouter](https://openrouter.ai/docs/guides/routing/model-variants/free), [catálogo de modelos](https://openrouter.ai/api/v1/models) e [uso/custo informado](https://openrouter.ai/docs/cookbook/administration/usage-accounting). Resultado de publicação e SHA serão registrados na entrega final, após conferência.

### Adequação do teto de saída para produção

O primeiro smoke real respondeu OK, custo informado zero, ledger sem chamadas em voo ou congelamento. A interação percorreu três chamadas internas e reservou 11.264 tokens de saída. O teto de piloto de 15.000 deixaria menos que o máximo de 4.096 de uma nova chamada de estudo. Para preservar a operação dentro de limites explícitos, a configuração de produção passa a reservar até **60.000 tokens de saída por dia**; o default local continua 15.000. Permanecem 30 chamadas/dia, 10/h, 60.000 tokens de entrada/dia, 4.096 de saída por chamada, concorrência um, controles adicionais de autonomia e gasto pago máximo zero. Nenhuma autorização de endpoint pago foi adicionada. Não houve reset ou redução dos contadores já registrados; eles continuam consumindo a cota do dia. Trata-se de ajuste de quota do endpoint gratuito já verificado, sem mudança de plano ou compra de créditos.
