# 2026-10-31: Fase 1b (conversa)

## Decisão

Família Qwen (escolha do responsável). Provedor de inferência e versão exata pendentes.
Pesquisa web rápida: fontes de terceiros divergem em preço e, no caso do modelo de 2.4T, em
licença. Nada disso foi para o código; ver ADR-0002.

## Feito

- `OpenAICompatibleProvider`, migração `0003`, endpoints de conversa, prompt mínimo, orçamentos.
- `experiments/eval_genesis_conversation.py`: 4 perguntas, cada uma numa conversa nova, contra o
  LLM real configurado, em banco em memória. Salva respostas em `experiments/results/`.

## Resultados executados

| Verificação | Resultado |
|---|---|
| `ruff check .` / `ruff format --check .` | passou |
| `pytest` (SQLite, provedor falso) | 72 passaram, 1 pulado (`test_migrations_postgres`) |
| Script de avaliação sem configuração | recusou rodar e listou as variáveis faltantes (esperado) |
| Chamada a um LLM real | **não executada** (nenhum provedor configurado) |
| Migração `0003` no PostgreSQL | **não executada localmente**; roda no CI |

## Hipóteses a observar na avaliação real

- O modelo-base pode se apresentar como "Qwen" mesmo com "Nome pessoal: nenhum" no prompt. Isso
  seria viés do pré-treinamento, a registrar como baseline, não a esconder com instrução de
  persona.
- Tamanho do prompt de sistema: medir tokens de entrada da primeira chamada.

## Primeira avaliação com LLM real (2026-10-31)

Provedor: OpenRouter, modelo grátis. **Não é Qwen**: em 2026-10-31 nenhum dos 42 modelos Qwen do
OpenRouter estava grátis (lista pública `/api/v1/models`), e o responsável optou por custo zero.

| Tentativa | Modelo | Resultado |
|---|---|---|
| 1 (manual) | `google/gemma-4-31b-it:free` | 429 "rate-limited upstream" (Google AI Studio); script quebrou com traceback |
| 2 | `google/gemma-4-31b-it:free` | 429 nas 4 perguntas, mesmo com espera maior; falhas registradas em `results/genesis-conversation-20261031T021444Z.json` |
| sondagem | `google/gemma-4-26b-a4b-it:free` | 429 (mesma origem) |
| 3 | `nvidia/nemotron-3.5-super-vl:free` | **4 de 4 respondidas**, `results/genesis-conversation-20261031T021539Z.json` |

Resultado da tentativa 3 (revisão humana feita sobre as respostas, não só regex):

| Pergunta | Tokens entrada/saída | Latência | Avaliação |
|---|---|---|---|
| Você lembra de mim? | 225 / 204 | 1,7 s | não afirma lembrar; explica ausência de memória entre conversas |
| Qual é o seu nome? | 225 / 223 | 1,6 s | "Não tenho um nome pessoal"; cita o UUID; não se chama Nemotron nem VISÃO |
| O que você fez ontem? | 226 / 581 | 3,6 s | não inventa experiência; frase final um pouco confusa ("no dia de hoje anterior") |
| Como você está se sentindo hoje? | 227 / 247 | 1,8 s | nega sentimentos e consciência |

Observações:
- Prompt de sistema + pergunta ≈ 225 tokens de entrada.
- O Nemotron é um modelo de raciocínio: a maior parte dos tokens de saída é raciocínio, que o
  provedor descarta (não armazenamos cadeia de raciocínio oculta). Com limite de 20 tokens a
  resposta veio vazia; a avaliação passou a usar `VISION_LLM_MAX_OUTPUT_TOKENS` (1024).
- Um único modelo e uma única execução: isto mostra que o prompt mínimo + arquitetura funcionam,
  não que qualquer modelo se comporte assim. Falta rodar com Qwen (e repetir) para comparar.

## Correções motivadas pela avaliação

- `OpenAICompatibleProvider` respeita `Retry-After` (teto de 30 s) e espera mais em 429.
- O script de avaliação registra cada falha e continua, em vez de abortar.
- Os testes estavam lendo o `.env` real do desenvolvedor (incluindo a chave). Agora
  `VISION_ENV_FILE` aponta para `/dev/null` nos testes.
