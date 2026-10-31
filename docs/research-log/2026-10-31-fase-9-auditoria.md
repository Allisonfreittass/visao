# 2026-10-31: Fase 9 (auditoria cognitiva e curiosidade autônoma)

## Feito

- Auditoria experimental de 15 componentes, com evidência de código e do `dev.db`:
  [cognitive_audit.md](../research/cognitive_audit.md).
- Plano: [curiosity_implementation_plan.md](../research/curiosity_implementation_plan.md).
- Implementado:
  - manifesto de capacidades;
  - camada de decisão (`run_turn`, tabela `decisions`, migração `0009`);
  - deliberação de nome;
  - continuidade entre sessões;
  - ciclo autônomo com orçamento;
  - permissão `auto_research`;
  - curiosidade que lê memórias (política `.3`);
  - recusa de autoafirmações na memória (política `.2`);
  - modalidade de voz;
  - rotas `/identity/name`, `/autonomy/permissions`, `/decisions`, `/cognition/metrics`.
- Testes: 21 novos (A–H). Suíte: 289 passando, 1 ignorado; frontend com 22 testes.

## Avaliação A/B/C

Detalhes em [curiosity_evaluation.md](../research/curiosity_evaluation.md).

- **B (antes):** "Não tenho a capacidade de escolher um nome… pode me chamar por qualquer nome
  que preferir". No dia 2, negou ter memória.
- **C (depois):**
  - disse que deliberar sobre o nome está entre suas ações;
  - deliberou de verdade e adiou, com alternativas próprias;
  - o ciclo retomou a pesquisa adiada sem mensagem nova;
  - no dia 2, citou a data e a fonte.

## Defeitos encontrados durante a auditoria

- A curadoria guardou como memória do usuário a frase falsa "o assistente não guarda memória das
  conversas". Agora isso é recusado como `system_self_claim`. A memória antiga continua no
  `dev.db` até o dono apagar.
- Os detectores do placar não pegavam "qualquer nome que preferir". Foram ampliados, e A/B/C
  foram repontuados com os mesmos detectores (`experiments/phase9_report.py`).

## Pendências

- Uma escolha real de nome com histórico.
- Várias execuções por configuração.
- Uma conversa por voz com microfone real.
- Uso contínuo implantado, para medir as métricas da §17 ao longo do tempo.
