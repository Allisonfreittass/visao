# Modo compacto: a conversa cabe no limite de qualquer modelo

Um turno da conversa manda ao modelo de 11 a 17 mil tokens: quem ele é, as regras, o seu perfil,
memórias, o que ele está pensando, estudos, o que ficou em aberto e o histórico. O Groq grátis
aceita uns 8 mil por pedido, contando a resposta, e devolvia `413` (grande demais): você ficava sem
resposta (caso real, 21/11/2026).

Agora cada modelo recebe a maior versão do prompt que cabe no limite dele. Modelo sem limite
conhecido (o Claude, por exemplo) recebe tudo, como antes.

## As versões, da completa à mínima

`reply` em `core/conversation/service.py` monta cinco níveis:

| Nível | O que sai | Num turno de teste |
|---|---|---|
| 0 | nada | ~11 mil tokens |
| 1 | histórico antigo: ficam uns 6 mil caracteres de mensagens recentes | ~6,8 mil |
| 2 | contexto opcional: pensamentos, interesses, o que está em aberto, temperamento, estudos, investigações anteriores, trechos do próprio código, projeto e anotações; o resumo das conversas antigas encolhe | ~4,9 mil |
| 3 | memórias recuperadas, ajustes de comunicação, histórico do nome e do Mac; perfil e autodescrição cortados em 500 caracteres; resumo antigo sai | ~3,5 mil |
| 4 | histórico: fica só a sua mensagem e a anterior; página anexada cortada em 2 mil caracteres | ~2,9 mil |

Nunca sai, em nível nenhum: quem ele é, as regras de verdade, as regras que você deu, o que foi
feito neste turno (para ele não afirmar nem negar uma ação errado), a hora no seu relógio e a sua
mensagem. O que é opcional é decidido no pipeline (`optional` em `core/decision/pipeline.py`).

## Como cada modelo escolhe

`FittingProvider` (`integrations/llm/fitting.py`) envolve cada modelo da cadeia:

- **Limite configurado** (opcional): `VISION_LLM_MAX_REQUEST_TOKENS`,
  `VISION_LLM_FALLBACK_MAX_REQUEST_TOKENS` e `VISION_LLM_FALLBACK2_MAX_REQUEST_TOKENS`, prompt e
  resposta juntos. Ex.: `8000` para o Groq grátis.
- **Limite aprendido**: sem configuração, o primeiro `413` traz o número ("Limit 8000") e o pedido
  é refeito na hora com a versão que cabe. O número fica guardado enquanto o processo roda, então
  os próximos pedidos já saem do tamanho certo.
- A resposta pedida também encolhe: no máximo um quarto do limite (2 mil num limite de 8 mil).
- Se nem a versão mínima couber, o erro segue para o próximo modelo da lista
  (`too_large` em `integrations/llm/fallback.py`).

A contagem é uma estimativa conservadora (bytes ÷ 3), sem o tokenizador de cada modelo: ela erra
para o lado de mandar menos.

## O preço

Num modelo pequeno ele fica mais esquecido: lembra menos da conversa antiga, de você e do que estava
pensando. Responde, mas com menos contexto. Quando um modelo grande voltar, recebe tudo de novo. Só
a conversa usa os níveis; o pensamento e as revisões em segundo plano continuam com o prompt
inteiro.
