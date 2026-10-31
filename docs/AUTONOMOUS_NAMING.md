# Formação autônoma do nome

> Estado: **registro na Fase 1a, deliberação na Fase 9** (`core/identity/name_deliberation.py`).
> Não há endpoint para *definir* nome, e não haverá: `POST /identity/name/deliberate` só pede ao
> próprio sistema que delibere, e o resultado pode ser escolher, adiar ou recusar.

## Regras

- O agente nasce com `chosen_name = null` e pode permanecer assim indefinidamente.
- Nenhum prompt interno sugere nomes, pede que se escolha um nome ou cria uma "cerimônia".
- O usuário não decide o nome. Se o usuário sugerir um, isso é uma entrada como qualquer outra:
  o agente pode considerar, recusar ou adiar.
- Ausência de nome não bloqueia nenhuma funcionalidade (API, UI, voz, logs, ferramentas).
- O nome é atributo de exibição. Nunca é chave, nunca altera UUID, permissões, dono dos dados ou
  políticas.

## Mecanismo

A escolha passa pelo fluxo normal de deliberação (seção 10 do master prompt), não por gatilho
roteirizado:

1. Uma situação real cria uma lacuna (ex.: alguém pergunta o nome; ou o agente observa que
   referências ambíguas atrapalham a conversa).
2. `CuriosityEngine` pode registrar um `knowledge_gap` e, se valer a pena, propor uma meta
   (`PROPOSE_GOAL`) de considerar um nome.
3. O agente pode pesquisar etimologias e referências públicas, dentro do orçamento.
4. Decisão: `CHOOSE`, `DEFER` ou `DECLINE`, registrada em `decisions`.
5. Se `CHOOSE`: transação única que grava `identity_name_events` e atualiza `chosen_name`.

## Esquema

```text
agent_identities(id, internal_id, chosen_name NULL, genesis_version, created_at, ...)
identity_name_events(
  id, identity_id, event_type  -- CHOSEN | CHANGED | DEFERRED | DECLINED
  previous_name NULL, new_name NULL,
  alternatives_considered JSONB,   -- só alternativas efetivamente consideradas
  context_summary TEXT,
  sources JSONB,                   -- URLs/referências consultadas
  rationale_summary TEXT,          -- justificativa breve, não cadeia de raciocínio
  model_provider, model_version,
  created_at
)  -- append-only, sem UPDATE/DELETE
```

## Testes de aceite

- Genesis tem `chosen_name IS NULL`.
- Conversa e ferramentas funcionam sem nome.
- Escolha voluntária gera evento auditado com alternativas, fontes e versão do modelo.
- Reinício preserva o nome escolhido.
- Troca de LLM não apaga `chosen_name` nem `name_history`.
- Mudança de nome preserva UUID e eventos anteriores.
- Varredura de prompts: nenhum prompt obriga ou sugere escolher nome.

## Deliberação (Fase 9)

- **Gatilhos:**
  - alguém pergunta sobre o nome; o detector `asks_about_name` agenda um job na hora;
  - o ciclo autônomo, com a questão em aberto desde o genesis (ver [AUTONOMY.md](AUTONOMY.md));
  - o pedido explícito do dono.

  Há um intervalo mínimo de 3 dias entre deliberações.
- **Entrada:** fatos do sistema (data de criação, número de conversas, memórias, histórico de
  nome). O prompt oferece escolher, adiar ou recusar, **sem lista de nomes**: as alternativas
  precisam ser geradas pelo próprio sistema.
- **Saída:**
  - um evento em `identity_name_events`, com alternativas consideradas e justificativa breve;
  - se a decisão for escolher, um aviso ao dono ("Decidi um nome: …").
- **Consulta:** `GET /identity/name` mostra o nome atual e o histórico.
- **Primeiro resultado real** (avaliação da Fase 9): `DEFERRED`, por histórico insuficiente,
  com alternativas próprias. Ver
  [research/curiosity_evaluation.md](research/curiosity_evaluation.md).
