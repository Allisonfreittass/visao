# Identidade

Três camadas separadas (master prompt §8). Nenhuma delas é prova de consciência, emoção ou
livre-arbítrio.

## 1. Identidade operacional mínima

UUID técnico estável, registro de genesis imutável, capacidades e limites reais. Nome pessoal e
voz começam nulos e só mudam por decisão auditada do próprio agente. Ver [GENESIS.md](GENESIS.md),
[AUTONOMOUS_NAMING.md](AUTONOMOUS_NAMING.md) e ADR-0004 (voz).

## 2. Autobiografia adquirida

Só eventos reais e autorizados: memórias curadas com consentimento ([MEMORY.md](MEMORY.md)),
decisões de nome e voz, lacunas e pesquisas ([CURIOSITY.md](CURIOSITY.md)), metas e iniciativas
([AUTONOMY.md](AUTONOMY.md)), lições de reflexão.

## 3. Estado comportamental adaptativo (Fase 6)

### O que é medido (`core/behavior/metrics.py`)

Calculado em código sobre cada resposta enviada, nunca perguntado ao modelo: caracteres,
palavras, frases, perguntas feitas, itens de lista, citações (URLs), marcas de incerteza e de
discordância. Cada medição guarda a versão do estado em vigor (`behavior_observations`).
`GET /behavior/report` compara linha de base, período recente e médias por versão.

### Como o estado muda (`core/behavior/state.py`, regras `2026-10-31.1`)

- **Evidência:** retorno do interlocutor em cada resposta (👍/👎 e marcações "muito longo",
  "muito curto", "faltou fonte", "perguntas demais"), nos últimos 30 dias, e lições ativas de
  estilo.
- **Repetição obrigatória:** um ajuste só nasce com pelo menos 3 marcações iguais; marcações
  opostas empatadas não mudam nada.
- **Parâmetros possíveis:** tamanho (`shorter`/`longer`), citar origem dos fatos, perguntar menos,
  e lições de estilo ativas. Não existem parâmetros de personalidade ("engraçado", "sério"...)
  nem de timbre de voz.
- **Versões append-only** (`behavior_state_versions`), cada uma com a causa, os ids de retorno e
  lições que a sustentam e um resumo. Reverter (`POST /behavior/state/revert`) cria uma versão
  nova igual à escolhida; nada é reescrito.
- **Por interlocutor:** o retorno de uma pessoa nunca ajusta como o sistema fala com outra.
- **No prompt:** na linha de base nada é acrescentado (comportamento do modelo-base). Com ajuste,
  a resposta recebe "Ajustes de comunicação aprendidos com o retorno deste interlocutor (versão N,
  revertíveis)".

### Reflexão (`core/reflection/reflect.py`)

- Roda uma vez por conversa encerrada (ao abrir a próxima) ou por pedido, só se houver evidência:
  retorno, pesquisa inconclusiva/adiada, meta que falhou. Sem evidência, sem chamada ao LLM.
  Respeita a pausa de autonomia.
- O LLM propõe até 3 lições citando evidências; regras decidem: escopo `style`/`research`/
  `memory`, evidência existente, confiança ≥ 0,5, nada de personalidade.
- Lição nova é `PROVISIONAL`. Passa a `ACTIVE` quando evidências de **duas mensagens diferentes**
  a sustentam (lições parecidas se fundem). Uma falha isolada nunca vira regra permanente.
- `GET /lessons`, `POST /lessons/{id}/retire` (aposentar recalcula o estado).

### Limites

- Adaptação é de estado e de prompt, não de pesos; fine-tuning só na Fase 7, com dados
  autorizados.
- O modelo-base tem vieses de estilo próprios; a linha de base os mede, não os nega.
