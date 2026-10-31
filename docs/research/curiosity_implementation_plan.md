# Plano técnico: curiosidade, iniciativa e continuidade (Fase 9, etapa 3)

Menores mudanças capazes de atacar as causas da [auditoria](cognitive_audit.md). Nada é
reescrito; cada mudança tem teste de regressão.

## Causas → mudanças

| Causa | Mudança | Onde |
|---|---|---|
| 1. Autodescrição falsa e negativa | **Manifesto de capacidades** calculado da configuração e do estado reais (memória com consentimento, curiosidade, pesquisa, voz, deliberação de nome, autonomia permitida); prompt passa a declarar capacidades reais e as distinções da auditoria (consciência ≠ autonomia operacional). | `core/identity/capabilities.py`, `system_prompt.py` |
| 2. Nome sem mecanismo | **Deliberação de nome**: chamada ao LLM com fatos da identidade e da autobiografia, sem lista de nomes; decide escolher, adiar ou recusar, citando as alternativas que ele próprio considerou; registrada por `record_naming_decision`. Gatilhos: o interlocutor perguntar sobre o nome (evento) e o ciclo autônomo; intervalo mínimo entre deliberações. Ferramentas: consultar atual e histórico (`GET /identity/name`), revisar (nova deliberação), comando manual. Aviso ao interlocutor quando houver escolha. | `core/identity/name_deliberation.py` |
| 3. Sem ciclo autônomo | **Ciclo cognitivo** agendado (janela configurável, padrão 60 min, trabalho idempotente por janela) e por evento. Detecta oportunidades no banco sem LLM; executa só o permitido e dentro de um **orçamento autônomo diário** (chamadas, tokens, buscas, ações por ciclo, tempo). Orçamento zero = nada roda. | `core/autonomy/cycle.py`, `apps/worker` |
| 4. Continuidade não chega à linguagem | **Contexto de continuidade**: lacunas, pesquisas e metas do interlocutor relacionadas à mensagem (ou recentes) entram no contexto como dados, com estado e fontes. | `core/autonomy/continuity.py`, `reply` |
| 5. Curiosidade cega à memória | A avaliação recebe as memórias recuperadas; nova pergunta de controle: "a memória já responde?". | `core/curiosity/engine.py` |
| 6. Curadoria aceita autodescrição | Política rejeita memória sobre capacidades/limitações do próprio sistema (`system_self_claim`): isso vem do manifesto, não de memória. | `core/memory/policy.py` |
| 7. Sem decisão registrada | **Decisão do turno** persistida (`decisions`, §15): ações selecionadas e executadas, motivos. A resposta recebe a lista do que foi de fato feito ("não afirmar o que não foi executado"). | `core/decision/turn.py` |
| Voz | Modalidade do turno (`text`/`voice`) chega ao núcleo; respostas faladas curtas, sem listas nem links. Iniciativa fora de sessão só por aviso. | rota de mensagens, `reply`, interface |

## Permissões de autonomia

| Ação autônoma | Efeito externo | Padrão |
|---|---|---|
| Deliberar sobre o próprio nome | nenhum (interno) | permitido |
| Refletir sobre conversa encerrada | nenhum | permitido |
| Pesquisar de novo uma dúvida pública adiada (`auto_research`) | leitura na Wikipédia | **desligado**; o interlocutor liga em `PUT /autonomy/permissions` |
| Avisar o interlocutor | aviso no app | permitido, com limite diário e horário silencioso |

Tudo continua sob a pausa geral. Metas que não sejam pesquisa continuam exigindo aprovação.

## Alternativas consideradas

- **Só reescrever o prompt.** Corrige parte das frases, mas não cria nome, ciclo nem continuidade;
  seria personagem sem mecanismo.
- **Pedir ao modelo para "ser curioso".** Proibido pela §3 e não verificável.
- **Ciclo contínuo em segundo plano.** Viola cotas e a §16 ("não manter LLM rodando sem evento").
- **Lista de nomes sugeridos.** Proibida (§8.1 e Fase 9 §8).
- **Separar decisão e expressão em duas chamadas de LLM por turno.** Dobraria custo e latência
  (já há a avaliação de curiosidade). Em vez disso, a decisão é montada em código a partir dos
  subsistemas e só a expressão usa o LLM.

## Métricas novas (`GET /cognition/metrics`)

Perguntas espontâneas justificadas (decisão `ASK_USER`), repetidas (`already_asked`), sem
justificativa (resposta com "?" sem decisão de perguntar), investigações iniciadas autonomamente e
concluídas, decisões persistidas e ações executadas, uso de ferramentas, tokens e custo por
propósito, latência, falhas, violações de permissão, frases genéricas por resposta.

## Validação

Testes A–H da especificação e o experimento A/B/C em `experiments/phase9_eval.py`
(B capturado antes das mudanças).
