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
