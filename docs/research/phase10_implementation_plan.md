# Fase 10A — Plano incremental e decisões de autorização

31/10/2026 · America/Sao_Paulo · **Proposta, nenhuma implementação executada.** Base `afc2295b8d631e8cb793100a6a92e216bd89230e`, auditada localmente conforme evidência fornecida. A nuvem não revalidou o repositório privado nem escreveu no Mac/repositório remoto.

## Resultado do estudo e decisão recomendada

Concluir 10A como diagnóstico/pesquisa/proposta. Não declarar 10B–10F prontas. A arquitetura atual suporta extensão incremental; preservar identidade, banco privado, monólito, estudos/retomadas, curiosidade, memória e autonomia da Fase 9. As primeiras mudanças devem tratar invariantes de segurança e consistência; PWA, push, estados e voz dependem delas.

O estudo tem limites explícitos: sem nova auditoria privada remota, benchmark de LLM, medição de hardware/fatura ou ensaio físico iPhone. As referências por SHA são evidência fornecida; as fontes públicas foram verificadas, com nível de acesso descrito nos documentos. Essas lacunas impedem prometer desempenho/custo operacional, mas não impedem concluir os seis entregáveis de 10A.

## Pacote e rastreabilidade dos requisitos

| Documento em docs/research/ | Conteúdo / requisito coberto |
| --- | --- |
| [phase10_current_state.md](phase10_current_state.md) | Auditoria consolidada, I/G/T/H1, arquitetura atual, 38 referências, testes e X1–X4 |
| [phase10_literature_review.md](phase10_literature_review.md) | Cinco níveis conceituais, dez fontes, teorias/objeções, oito estados funcionais, automodelo e hipóteses refutáveis |
| [phase10_multidevice_architecture.md](phase10_multidevice_architecture.md) | IDs, sessão/turno/evento, outbox, replay, PWA/iOS/Mac, SSE/WS, voz, handoff e notificações |
| [phase10_privacy_budget.md](phase10_privacy_budget.md) | Permissões, ameaças, retenção, BudgetGuard, fontes de custos e limites de zero adicional |
| [phase10_implementation_plan.md](phase10_implementation_plan.md) | Ordem mínima, critérios, rollback e autorizações separadas |
| [phase10_evaluation_plan.md](phase10_evaluation_plan.md) | Controles A–J, amostras/limiares, instrumentação, reprodução X1–X4 e resultados não medidos |

A atualização pública sobre Web Push declarativo está registrada na arquitetura: service worker é requisito do caminho tradicional proposto, não de toda modalidade Apple atual. Nenhuma escolha de transporte foi convertida em alteração de produção.

## Sequência proposta e dependências

| Etapa | Mudança mínima proposta / pontos atuais | Pré-condição | Aceite para revisão | Rollback e limite |
| --- | --- | --- | --- | --- |
| 10A, esta entrega | Somente seis documentos e ZIP; auditoria fornecida e fontes públicas | Base congelada | Arquivos íntegros, links internos resolvidos, resultados e hipóteses separados | Sem código/produção alterados; consolidação local documentada abaixo |
| 10B.0 P0, fila | queue.py claim/fail/complete/renew: limite de tentativas e geração/fencing | Autorização local e fixtures PostgreSQL descartáveis | X1/X2 reprovam comportamento antigo e passam novo; stale writer afeta zero linhas; sem duplicar worker | Patch reversível local; não commitar/push. Antes de futuro rollout, jobs em voo exigem compatibilidade de lease |
| 10B.1 P0, orçamento | Fallback e pontos de chamada existentes: allowlist por dimensão, validade de gratuidade, reserva atômica/circuit breaker | 10B.0; desenho de ledger revisado | H/X3: zero tentativa paga/desconhecida, concorrência não excede saldo; modo degradado | Flag de nova admissão em ambiente de teste; não “rollback” para fallback pago em produção sem decisão humana |
| 10B.2 P0, sessão/turnos | Auth/security/deps, conversations/service, session.ts/App: device/session revogáveis, client_turn_id, serialização e sequência | 10B.0/1, contrato de autenticação e CSRF aprovado | A/G/I locais, dois owners, logout/revoke, retry idêntico e conflito de payload | Não revalidar sessão revogada por rollback; compatibilidade de clientes planejada; segredo não migra para URL |
| 10B.3 P1, eventos/continuidade/PWA | Transação domínio+outbox, snapshot/cursor, resync, timers adaptativos; shell/manifest | 10B.2; política de retenção e watermark | A/B/I, replay sem lacunas/duplicação, background sem polling; sem cache privado | Desativar novo cliente/stream em teste; preservar eventos/dados, cache versionado; sem SSE permanente |
| 10C P1, push opt-in | Estender notify existente com preferências por device/categoria e Delivery | 10B.3; teste físico e autorização de notificação separados | G, dedup, quota global, silêncio/timezone, 404/410, revogação; preview genérico | Desligar novo dispatcher por flag futura autorizada; não apagar estado existente ou reativar subscription revogada |
| 10D P1, estados/SelfModel | Visão derivada de Capabilities/Identity/Decision/jobs/usage; oito estados só onde acrescentam decisão | 10B.1/2 e corpus E/F | E/F/J demonstram efeito/refutação; fatos vs hipóteses; sem nova identidade ou memória global privada | Remover consumo da visão/estado por flag; preservar evidência e versões; sem reset de identidade |
| 10E P1, voz/UX | Corrigir lifecycle/busyRef e contrato; avaliar STT/TTS recursos/latência | P0 + medições, consentimento físico e provedor elegível | B/G físicos, fim de sessão e callback tardio, nenhuma reabertura remota; WER/latência registrados | Manter STT/TTS desabilitados no deploy até nova aprovação; fallback texto, não troca paga |
| 10F, avaliação | Comparativo e segurança/custo/recursos A–J | Intervenções locais autorizadas e estáveis | Relatório com N, negativos, incerteza e custo; regressão bloqueia promoção | Rejeitar intervenção sem ganho; preservar baseline e fixtures |

10F começa como avaliação local a cada incremento; não é necessário esperar toda a sequência para descobrir falhas. 10D pode ser estudada em fixtures em paralelo lógico, mas sua integração não antecede os gates P0. Nenhum novo loop autônomo, scheduler ou engine de curiosidade faz parte da proposta.

## Evolução de código existente: contenção de escopo

O mecanismo diário já existe em dois módulos e uma proposta por dia. A avaliação real observada foi no_change, não autopatch publicado. X4 revela limite da evidência de AST e teste isolado. Não ampliar arquivos editáveis, frequência, permissões ou deploy automático. Fase 10A apenas registra risco. Hardening futuro precisa de autorização específica, limites de entrada e runtime, provas de rejeição e observabilidade. Não executar a função adversarial X4. Não confundir container de teste sem rede com sandbox da função futura dentro da API.

## Contratos e decisões antes do primeiro patch

1. Confirmar se o produto continuará pessoal/single-user ou atenderá mais usuários; mesmo no primeiro caso manter isolamento e papéis globais corretos.
2. Aprovar a política de uma execução por conversa, com 409 e reenvio explícito para intenção simultânea diferente; retries do mesmo ID recuperam estado canônico.
3. Aprovar sessões revogáveis e estudo do cookie same-origin com CSRF/Origin, sem trocar JWT próprio por Supabase Auth automaticamente.
4. Aprovar fail-closed financeiro para novas chamadas propostas: ausência de evidência válida de preço zero resulta em adiamento. O usuário pode preferir perder disponibilidade a autorizar cobrança; default permanece zero.
5. Aprovar retenção piloto sugerida (áudio zero, logs 7 dias, eventos/entregas 30 dias) antes de qualquer aplicação; histórico existente não será apagado por esta proposta.

Estes são pontos de decisão, não perguntas que bloqueiam a entrega 10A. Onde ainda falta escolha, os documentos contêm defaults conservadores revisáveis. Custos da conta real e capacidade de impor teto de infraestrutura continuam pendentes de leitura autorizada posterior.

## Migrações, deploy e rollback: gates separados

Não há migrações criadas nesta entrega. Uma futura implementação local pode exigir modelo de sessão, turno, evento, ledger e delivery; desenho físico deve reutilizar entidades quando possível, manter `visao` privado, índices por owner/cursor e constraints transacionais. Nenhum motivo para mover para public, adicionar pgvector/Redis ou criar projeto Supabase.

**Gate local:** checkout isolado após autorização, verificar diferença entre HEAD e SHA auditado, ler instruções locais, implementar somente escopo aprovado e rodar offline/fakes com PostgreSQL descartável se disponível. Não usar credenciais de produção. Se PostgreSQL local não estiver disponível, marcar a prova de concorrência bloqueada; não substituí-la por SQLite “verde”. Não commitar/push/PR no escopo recomendado inicial.

**Gate migração/produção:** apresentar diff concreto, compatibilidade de clientes/jobs em voo, plano de dados, backup realmente disponível no plano e ensaio de restore local. Schema em fase expand/contract quando necessário, sem remoção destrutiva na primeira publicação. Rollback de código não desfaz migração. Sessões revogadas, consentimentos e tombstones precisam continuar respeitados após rollback. Não fazer restore remoto ou migração sem aprovação específica.

**Gate publicação:** nova autorização explícita após artefatos revisáveis e testes. CD atual dispara em push main inclusive para docs; por isso não sincronizar estes arquivos via push por implicação. Separar permissão de commit/push de permissão de deploy: no fluxo atual, push main pode equivaler a disparar deploy. Eventual filtro de workflow é outra mudança aprovada, não atalho nesta rodada.

Plano futuro de publicação deve definir versão/artefato, janela, health/readiness, smoke de owner/session/turno, rollback ensaiado e condições de abortar (duplicação, vazamento, custo não autorizado ou captura incorreta). Não chamar isso de rollback validado enquanto só existir controlador com mocks. Um rollback operacional futuro exige autorização para atuar no ambiente; aqui só se descreve o procedimento.

## Perguntas de aprovação propostas para a próxima rodada

**Aprovação 1 — implementação local limitada (recomendada):** autorizar somente 10B.0 e 10B.1 em checkout isolado, corrigindo tentativas/fencing e preparando BudgetGuard com fakes e testes locais. Sem inferência real, sensores, alteração de conta, migração de produção, commit/push/PR ou deploy. Se modelos locais de teste exigirem alterações de schema, somente banco descartável e artefatos revisáveis; qualquer migração do produto exige inclusão explícita no escopo antes de ser criada.

**Aprovação 2 — continuidade local, posterior:** após revisão da primeira, autorizar sessão/device/turnos/outbox/PWA com modelos e migrações locais revisáveis, testes de isolamento e replay. Ainda sem produção ou push real. Decidir cookie/CSRF e política de 409 antes de implementar o contrato.

**Aprovação 3 — ensaio físico e/ou provedor, posterior:** especificar aparelho/iOS, sessão curta com microfone, notificações de teste, endpoint/modelo com evidência de custo zero, limites e dados sintéticos. Não está autorizada agora e não decorre da aprovação local.

**Aprovação 4 — produção/deploy, independente:** somente após diffs, resultados, migrações e rollback concretos, autorizar expressamente o SHA/artefato e operações de banco/Cloudflare/push necessários. Permissão local não autoriza esse gate. Nenhum gasto novo sem decisão separada.

## Aceite de 10A

Há evidências fixadas do estado atual; distinção entre função e consciência; protocolo de continuidade entre devices; limites iOS/background/voz; proposta sem novo serviço pago; testes com critérios que podem falhar; preservação incremental das fases e lista de decisões humanas. Os seis arquivos completam o estudo no escopo fornecido. Limitações de revalidação, custo e aparelho permanecem visíveis e não são promovidas a resultados. A tarefa em nuvem não realizou a sincronização. A consolidação local posterior está registrada na nota abaixo.

## Consolidação local — 01/11/2026

Os seis documentos foram reunidos em `docs/research/` e copiados para o pacote de entrega local. A auditoria original do estado atual foi preservada por conter evidências mais detalhadas; os outros cinco documentos vieram da tarefa em nuvem e passaram por revisão local de conteúdo, referências e escopo. HEAD permanece no SHA auditado. Os resultados de testes continuam sendo os da etapa local de 31/10/2026; não houve nova execução das suítes nem dos experimentos nesta consolidação. Nenhuma implementação, migração, commit, push ou publicação foi realizada.
