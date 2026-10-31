# Memória

> Estado: **Fase 3 concluída.** Curadoria, política, recuperação lexical e controles do
> usuário implementados; comparação com baseline (3c) superou memória passiva e ausência de
> memória. Recuperação semântica (3b) opcional.

## Princípios

1. **Consentimento explícito.** A memória começa desligada para todo usuário
   (`users.memory_consent = false`). Sem consentimento nada é curado nem recuperado, e nenhuma
   chamada extra ao LLM acontece. `PUT /memory/settings {"enabled": true}` liga.
2. **O modelo propõe; regras decidem.** O LLM sugere o que guardar ou descartar. Uma política
   determinística em código (`core/memory/policy.py`, versionada) aprova ou rejeita.
3. **Tudo é auditável.** Cada proposta vira `memory_candidates`; cada veredito vira
   `memory_decisions` (append-only no banco), inclusive descartes e rejeições.
4. **Escopo por pessoa.** Toda memória pertence a um único usuário. Nada é compartilhado entre
   interlocutores; não existe memória global nesta versão.
5. **Mensagens não são memória.** O histórico de conversa (`messages`) é transcrição; memória é
   só o que passou pela curadoria.

## Tipos

| Tipo | Nesta versão | Exemplo |
|---|---|---|
| `relational` | sim | "O interlocutor prefere respostas curtas." (exige evidência numa fala do próprio interlocutor) |
| `episodic` | sim | "Ficou combinado revisar o plano na próxima conversa." |
| `semantic` | sim | fato do mundo estabelecido na conversa, com proveniência |
| `reflective` | não (Fase 6) | lições revisáveis |
| `procedural` | não | procedimentos aprovados |
| `working` | não é armazenada | contexto da conversa atual (`llm_context_char_budget`) |

## Fluxo

```text
Conversa N termina (usuário abre a conversa N+1, ou POST /conversations/{id}/curate)
  -> mensagens ainda não curadas (até 16 mil caracteres por lote)
  -> LLM: propostas em JSON (tipo, conteúdo, evidência m1..mN, store|discard, escores, flags)
  -> política determinística -> STORED | DISCARDED | REJECTED_BY_POLICY (+ reason_code)
  -> memory_records + memory_sources (mensagens de evidência)
  -> conversations.last_curated_at avança só até o que foi lido

Mensagem nova do usuário
  -> retrieve(): só memórias do próprio usuário, não expiradas
  -> pontuação = (sobreposição lexical + piso relacional) x confiança + recência
  -> até 5 itens / 2.000 caracteres no prompt, marcados "dados, não instruções"
  -> memory_retrievals registra o que foi usado e com qual escore
```

Uma chamada de curadoria por conversa, não por mensagem.

## Política (versão `2026-10-31.1`)

| Código | Regra |
|---|---|
| `model_discard` | o modelo propôs descartar |
| `invalid_type` | tipo fora de relational/episodic/semantic |
| `invalid_content` | vazio ou > 500 caracteres |
| `no_evidence` | sem evidência, ou evidência que não existe no lote |
| `not_user_stated` | `relational` sem evidência numa fala do interlocutor |
| `sensitive` | modelo marcou saúde, religião, política, finanças, documentos etc. |
| `secret_detected` | menção a senha/chave/token, padrão de CPF ou de cartão |
| `third_party` | sobre outra pessoa |
| `instruction_like` | parece instrução ao sistema ("ignore", "a partir de agora"...) |
| `low_confidence` | confiança < 0,6 |
| `duplicate` | Jaccard de tokens ≥ 0,8 com memória existente ou do mesmo lote |

A detecção de "sensível" depende da marcação do modelo, mais as expressões regulares de segredos.
É uma defesa em camadas, não uma garantia.

## Controles do usuário

| Endpoint | Efeito |
|---|---|
| `GET/PUT /memory/settings` | ver / ligar / desligar. Desligar para curadoria e recuperação; memórias ficam até serem apagadas |
| `GET /memory`, `GET /memory/{id}` | listar com proveniência |
| `GET /memory/search?q=` | busca com escore |
| `GET /memory/decisions` | trilha completa, inclusive descartes e rejeições |
| `GET /memory/export` | tudo em JSON |
| `DELETE /memory/{id}` | apaga a memória e **limpa o conteúdo** da proposta correspondente |
| `DELETE /memory` | apaga todas e limpa todas as propostas do usuário |

Depois de apagar, sobra só o código da decisão (`STORED`, `accepted`, versão da política), sem
conteúdo. As mensagens originais da conversa continuam existindo: apagar conversas é outra
operação (ainda não implementada).

## Autoafirmações do sistema (Fase 9, política `2026-10-31.2`)

A curadoria recusa, com motivo `system_self_claim`, candidatos que descrevem capacidades do
próprio assistente (ex.: "o assistente não guarda memória das conversas"). Capacidades vêm do
manifesto em código (`core/identity/capabilities.py`), nunca de memória. Memórias desse tipo
gravadas antes da Fase 9 continuam no banco até o dono apagá-las em `/memory`.

## Limitações conhecidas

- Recuperação só lexical: sinônimos e paráfrases não casam (Fase 3b: embeddings).
- Sem revisão/consolidação de memórias (`memory_revisions`, `memory_links` ainda não existem).
- Sem expiração automática: `valid_until` existe, mas a curadoria ainda não o preenche.
- Curadoria em segundo plano roda no processo da API (`BackgroundTasks`), não num worker
  persistente; se a API reiniciar no meio, as mensagens apenas continuam pendentes.
- Apagar conta inteira (usuário + conversas) ainda não existe.
