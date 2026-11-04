# Mente: o que faz ele continuar entre uma conversa e outra

Um LLM, com 120 B de parâmetros ou mais, só existe durante uma chamada: recebe texto, devolve texto
e para. Iniciativa não vem do tamanho do modelo; vem do que roda em volta dele. Esta camada dá a ele
um estado que persiste e um laço que roda sem mensagem. Ligada com `VISION_MIND_ENABLED=true`.

## O laço

A cada ciclo do worker (`VISION_AUTONOMY_CYCLE_MINUTES`), `core/mind/think.py` pensa uma vez, no
máximo a cada `VISION_MIND_THINK_MINUTES` (três vezes menos no horário silencioso):

1. Lê a autodescrição, os últimos pensamentos, interesses, memórias, a conversa recente e o que
   estudou, e continua de onde parou.
2. Reforça, cria ou enfraquece interesses (`interests`). Eles decaem sozinhos sem novo estímulo.
3. Guarda o que quer perguntar: isso entra nas próximas respostas.
4. Decide se tem algo que valha dizer agora.
5. Pode reescrever como se descreve (`self_versions`, no máximo a cada 6 h, versionado).

O estudo (`core/study/service.py`) parte dos interesses, com intervalo de
`VISION_STUDY_INTERVAL_MINUTES`. Sem um interesse ou memória ligando o tema à pessoa, ele não
estuda: antes o padrão era "organização do conhecimento" e por isso ele estudava coisas sem relação.

## Puxar conversa

`core/mind/initiative.py` grava uma mensagem real no chat (`messages.origin = "initiative"`); a
interface busca a cada 15 s e fala em voz alta se as respostas faladas estiverem ligadas. Ele fica
quieto no horário silencioso, com a autonomia pausada e enquanto você está conversando (15 min),
para depois de 2 aberturas sem resposta até você responder, e manda no máximo
`VISION_MIND_INITIATIVES_PER_DAY` por dia. O que ele quis dizer e não pôde fica no pensamento.

## Internet

Wikipédia pt e en, arXiv e páginas via Hacker News (`integrations/search/open_web.py`), todas APIs
públicas gratuitas. Como roda na sua máquina, `integrations/search/fetch.py` só abre HTTPS em
endereços públicos, revalidados em cada redirecionamento: uma página nunca alcança `localhost` nem
a sua rede. O que vem da web entra como dado, e ele não tem ferramenta além de falar com você.

## Velocidade

Quase todo o tempo de resposta era raciocínio interno do modelo: 284 tokens contra 25 para a mesma
frase. A conversa desliga isso (`VISION_LLM_FAST_EXTRA_BODY`, 0,8 a 2,5 s por turno) e o worker
mantém, porque pensar sozinho pode demorar. Cloudflare não acelera nada: o modelo roda na
OpenRouter/NVIDIA dos dois jeitos. Um MacBook Air M1 de 8 GB não roda um modelo de 120 B.

## O que ele não pode reescrever

- As regras de verdade em `core/identity/system_prompt.py`: não inventar ações, fontes ou memórias.
- Código: ele muda o próprio comportamento por dados versionados, não executando código gerado por
  ele numa máquina que guarda suas chaves e lê a internet.
- Custo: `VISION_LLM_TRUST_ZERO_PRICE` aceita preço zero configurado, mas qualquer custo informado
  pelo provedor congela o razão.

## Ver e desfazer

Aba Estudos, painel da mente; `GET /mind`; `POST /mind/self/revert` desfaz uma autodescrição.
