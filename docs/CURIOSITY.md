# Curiosidade como mecanismo

> Estado: **especificação**. Implementação prevista na Fase 4.

Curiosidade aqui é um **procedimento de decisão sobre valor da informação**, não um traço de
personalidade. Nenhum prompt diz "seja curioso".

## Pipeline do `CuriosityEngine`

1. **Detecção** de lacuna a partir de sinais concretos:
   - incerteza: o modelo/política sinaliza baixa confiança ou ausência de fonte;
   - contradição: duas memórias ou fontes conflitam;
   - novidade: entidade/conceito sem registro;
   - dependência: uma meta ativa precisa de uma informação ausente.
2. **Formulação**: pergunta investigável + hipótese + utilidade esperada.
3. **Pontuação**: `expected_value`, relevância, urgência, custo estimado, risco, redundância
   (já pesquisado? já perguntado?).
4. **Ação**: `ASK_USER` | `WEB_RESEARCH` | `DEFER` | `IGNORE` | `PROPOSE_GOAL`.
5. **Política** (determinística, em código): orçamento, frequência, privacidade, permissões.
6. **Execução** e registro de evidências.
7. **Avaliação**: resolvida, parcialmente resolvida ou inconclusiva. Inconclusivo permanece
   inconclusivo.

## Roteamento

| Natureza da resposta | Ação preferida |
|---|---|
| Preferência ou vivência do interlocutor | `ASK_USER` |
| Fato público verificável | `WEB_RESEARCH` |
| Irrelevante para metas/conversa | `IGNORE` |
| Relevante mas não urgente | `DEFER` |
| Exige investigação longa | `PROPOSE_GOAL` (requer aprovação) |

## Limites

- Orçamento por conversa, por dia e por lacuna (tokens, buscas, páginas).
- No máximo N perguntas ao usuário por janela de turnos; sem interrogatório.
- Buscas proativas fora de sessão: domínio restrito, frequência limitada, motivo registrado.
- Proibido investigar dados privados de terceiros.
- Conteúdo da web é dado não confiável, nunca instrução.

## Modelo de dados

```text
knowledge_gaps(
  id, question, hypothesis, trigger_event_id, trigger_kind,
  uncertainty, expected_value, risk, cost_estimate,
  chosen_action, status,             -- OPEN | RESOLVED | INCONCLUSIVE | IGNORED | DEFERRED
  research_budget, spent_budget,
  resolution_summary, created_at, resolved_at
)
```

## Critérios de aceite

- Fato público aciona busca com citações.
- Pergunta pessoal aciona pergunta ao interlocutor.
- Caso irrelevante não aciona pesquisa.
- Resultado inconclusivo é reportado como inconclusivo.
- Orçamento esgotado degrada para `DEFER`, sem erro e sem loop.
