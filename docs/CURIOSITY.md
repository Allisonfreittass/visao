# Curiosidade como mecanismo

> Estado: **Fase 4 implementada** (`core/curiosity/engine.py`, política `2026-10-31.2`).
> Desligada por padrão (`VISION_CURIOSITY_ENABLED`). `PROPOSE_GOAL` depende de metas (Fase 5)
> e ainda não é oferecida. Avaliação real: `docs/research-log/2026-10-31-fase-4-curiosidade.md`.

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

## Implementação

- **Pré-filtro determinístico:** cumprimentos, agradecimentos e mensagens com menos de 2 palavras
  não são avaliados (custo zero).
- **Avaliação:** uma chamada ao LLM por turno não trivial devolve JSON com `gap`, `trigger`,
  `depends_on` (`public_fact`/`personal`/`none`), `about_private_person`, `question`,
  `hypothesis`, `search_query` e escores 0–1 de incerteza, valor, urgência e risco. Falha ou
  JSON ilegível: a conversa segue sem curiosidade.
- **Política (em código, sem modelo), na ordem:** sem lacuna → `IGNORE no_gap`; valor < 0,4 →
  `IGNORE low_value`; pessoal → `ASK_USER` (ou `IGNORE already_asked` se pergunta parecida já foi
  feita na conversa); sobre pessoa privada → `IGNORE private_third_party`; risco ≥ 0,7 →
  `IGNORE risk`; fato público → `WEB_RESEARCH`, ou `DEFER research_budget` sem orçamento.
- **Efeito na resposta:** `ASK_USER` acrescenta a pergunta ao contexto da resposta (uma vez,
  de forma natural); `WEB_RESEARCH` acrescenta as fontes como dados, com instrução de citar URLs,
  não afirmar além dos trechos e declarar incerteza.
- **Estados:** `ASKED`, `RESEARCHED` (houve fontes, o que **não** significa resolvido),
  `INCONCLUSIVE` (sem fontes ou erro), `DEFERRED`, `IGNORED`.
- **Limites:** 20 pesquisas/dia por usuário, 5 por conversa, 3 resultados por pesquisa
  (`VISION_RESEARCH_*`); orçamentos de LLM em US$ valem também para a avaliação.
- **Auditoria:** `GET /knowledge-gaps` e `GET /research`, só do próprio usuário.

Lacuna conhecida: o passo 7 (avaliar se a lacuna foi de fato resolvida) não é feito; exigiria
outra chamada ao LLM por turno pesquisado.

## Critérios de aceite

- Fato público aciona busca com citações.
- Pergunta pessoal aciona pergunta ao interlocutor.
- Caso irrelevante não aciona pesquisa.
- Resultado inconclusivo é reportado como inconclusivo.
- Orçamento esgotado degrada para `DEFER`, sem erro e sem loop.
