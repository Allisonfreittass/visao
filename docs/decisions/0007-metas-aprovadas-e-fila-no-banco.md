# ADR-0007: Metas com aprovação explícita e fila de trabalhos no banco

- Data: 2026-10-31
- Estado: aceita

## Contexto

Seções 9, 14, 16 e 17 do master prompt: metas persistentes com ciclo de vida, iniciativas por
eventos reais, propostas sem permissão implícita, worker resiliente (idempotência, retries,
dead-letter, retomada), notificações com horário silencioso e botão de pausa geral.

## Decisão

- **Fila no PostgreSQL** (`scheduled_jobs`) com captura otimista por `UPDATE ... WHERE status`
  em vez de `SELECT ... FOR UPDATE SKIP LOCKED`: portável (mesmo comportamento no SQLite dos
  testes) e suficiente para o volume previsto. Sem Redis (ADR-0001).
- **Ciclo de vida explícito** com transições validadas e `goal_events` append-only no banco.
- **Aprovação humana obrigatória** para metas propostas pelo agente; permissões restritas a uma
  lista fixa e conferidas de novo na execução.
- **Primeira iniciativa = retomar pergunta sem resposta**, com o LLM julgando se as fontes
  respondem antes de avisar: evita notificação inútil.
- **Pausa geral** em `system_flags`, consultada pelo worker, pela proposta de metas e pela criação
  de avisos.

## Alternativas consideradas

- Celery/RQ + Redis: mais peças para operar no Lightsail pequeno sem ganho no volume atual.
- Aprovação automática de metas "seguras": viola "propostas não conferem permissões".
- Notificar sempre que houver fontes: na avaliação real, as fontes vinham irrelevantes com
  frequência; o aviso seria ruído.

## Consequências

- Captura otimista pode disputar o mesmo trabalho entre workers; o perdedor tenta o próximo.
  Para muitos workers, migrar para `SKIP LOCKED` no PostgreSQL.
- Avisos só no app até haver HTTPS (push no iPhone).
- A avaliação de lacunas pelo modelo varia entre execuções (mesma pergunta: lacuna numa,
  "sem lacuna" noutra), o que afeta quantas iniciativas são propostas.
