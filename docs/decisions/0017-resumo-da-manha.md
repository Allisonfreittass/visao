# ADR-0017: Resumo da manhã

- Data: 2026-11-16
- Estado: aceita

## Contexto

O Visão puxa conversa solta durante o dia ([MIND.md](../MIND.md)). Faltava o que o JARVIS faz ao
abrir a manhã: uma mensagem só, na hora em que o dono acorda, com o que importa no dia. Hoje esses
fatos estão espalhados: na agenda do Google, nos painéis, no que espera aprovação, no que o Mac
terminou e no caderno de estudo.

## Decisão

- **Quando:** todo dia, no fim do horário silencioso do dono (`quiet_end`); sem horário
  silencioso, às 08:00. O ciclo cognitivo deixa o job `morning_briefing` do próximo dia na fila,
  de forma idempotente, e cada resumo marca o seguinte.
- **Ligado por padrão:** o dono pediu o resumo. Ele desliga em Ajustes
  (`autonomy_permissions.morning_briefing`) e pode pedir um na hora (`POST /autonomy/briefing`).
  A pausa global também o cala.
- **Fatos juntados em código** (`core/mind/briefing.py`), só o que houver:
  - a agenda de hoje e os assuntos de até 3 emails não lidos, só com a leitura em segundo plano
    do Google ligada, e nunca o corpo do email;
  - os painéis ativos, **conferidos na hora**, se a última conferência tem mais de 6 h. Essa
    conferência é a do dia: a das 9h vira um job que não faz nada, então não há gasto em dobro.
    Ela não manda aviso: o resumo é o aviso, e um painel abaixo da meta conta como avisado;
  - o que espera o sim do dono (Mac, metas, Google, oferta de painel);
  - o que o Mac terminou nas últimas 24 h;
  - o que ele estudou nas últimas 24 h;
  - os lembretes que ele mesmo marcou para hoje.
- **Sem nada novo, sem mensagem.** Um "bom dia" vazio é ruído.
- **O modelo escreve, o código confere.** Uma chamada (Haiku, orçamento da autonomia) escreve o
  resumo na voz dele, com a autodescrição e as regras do dono. Se a resposta trouxer um valor em
  reais que não está nos fatos, ou não vier, ou não houver orçamento, sai o texto montado em
  código, com os mesmos fatos.
- **Entrega:** uma mensagem na conversa contínua (`origin = initiative`), com push "Bom dia". Ela
  conta como abertura dele, então as regras de não insistir continuam valendo para o resto do dia.

## Fora desta decisão

- Previsão do tempo e notícias: não há fonte integrada.
- Horário escolhido à parte do horário silencioso: se fizer falta, vira um campo.
- Voz: o resumo falado quando o dono abre a ligação.
