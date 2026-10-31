# 2026-10-31: Fase 6 (reflexão e desenvolvimento comportamental)

## Feito

- Migração `0008`: `message_feedback`, `behavior_observations`, `behavior_state_versions`
  (append-only), `lessons`, `conversations.last_reflected_at`.
- Métricas em código, estado versionado por interlocutor, reflexão com lições provisórias,
  rotas `/messages/{id}/feedback`, `/behavior/state`, `/behavior/state/revert`,
  `/behavior/report`, `/lessons`, `/conversations/{id}/reflect`; botões de retorno na interface.
- Testes: 268 no backend, 22 no frontend.

## Avaliação real (`results/behavior-20261031T121931Z.json`)

Mesmas 4 perguntas abertas, cada uma numa conversa nova, Nemotron 3.5 Super (API da NVIDIA).

| Fase | Versão | Palavras por pergunta | Média (3 válidas) | Frases médias |
|---|---|---|---|---|
| A, linha de base | 0 | 110, 187, 228, **6 (cortada)** | 175 | 8,2 |
| B, após 3 "muito longo" | 1 | 56, 59, 46, 51 | 53,7 (**−69%**) | 3,0 |
| C, revertido | 2 | 247, 147, 178, 341 | 190,7 (+9%) | 13,2 |

- Observável: B caiu para exatamente ~3 frases, o ajuste pedido.
- Atribuível: a versão 1 registra os 3 retornos que a causaram ("3x 'muito longo'").
- Reversível: C voltou à faixa da linha de base (o modelo-base varia muito entre execuções:
  341 palavras numa pergunta).

## Defeito encontrado

A 4ª resposta da linha de base foi "Inflação é o aumento generalizado e": o modelo de raciocínio
gastou o limite de 1024 tokens de saída e a resposta cortada foi entregue como completa.
Correção: respostas encerradas por limite (`finish_reason=length`) recebem
"[resposta interrompida pelo limite de tamanho]" e o uso fica `truncated`; limite local elevado a
3072. Teste de regressão adicionado.

## Não avaliado ainda

- Lições reais vindas de reflexão sobre uso real (só testadas com modelo falso).
- Estabilidade das adaptações ao longo de dias.
