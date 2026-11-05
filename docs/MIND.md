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

## Aprender com a conversa

Inspirado no Hermes Agent. Memórias recuperadas só aparecem quando a mensagem casa com elas, então
ele podia falar com você sem o seu retrato na frente. Agora existem duas anotações curtas, sempre no
prompt (`core/mind/notes.py`), versionadas e com limite de tamanho, que forçam escolher o que importa:

- **Perfil** (1400 caracteres): quem você é.
- **Regras** (1000 caracteres): como te tratar, vindas das suas correções.

`core/mind/review.py` relê a conversa em segundo plano, num job do worker, sem atrasar a resposta: a
cada `VISION_MIND_REVIEW_TURNS` turnos, na hora depois de uma correção ("para de", "muito longo"), e
quando uma conversa curta fica parada por 15 min. Toda mudança precisa citar mensagens suas, e isso é
conferido em código: nem as falas dele nem o que ele leu na web podem mudar o que ele acha de você.
Saúde, religião, política, finanças e terceiros ficam de fora, como na memória.

Tudo depende do consentimento de memória. `DELETE /memory` apaga também as duas anotações, e a
exportação as inclui. Na aba Estudos dá para desfazer ou apagar cada uma; apagar uma memória isolada
não muda o perfil, então um fato errado se corrige dizendo a ele ou apagando a anotação.

### Obedecer às regras

Só escrever a regra no prompt não bastou: com "não termine toda resposta com pergunta" no fim do
prompt, 7 de 8 respostas ainda terminavam em pergunta. Por isso, quando há regras, a resposta pronta
passa por uma conferência curta antes de ser gravada (`_obey_rules` em
`core/conversation/service.py`, `model_usage.purpose = "rule_check"`). O mesmo modelo rápido devolve
`{"obeys": true}` ou `{"obeys": false, "rewrite": "..."}`, e só o texto final vira mensagem.

Ela nunca derruba o turno: erro do modelo, JSON ruim, resposta cortada, reescrita vazia, orçamento
esgotado ou mais de 4 s mantêm a resposta original, e o motivo fica em `outcome`/`error_kind`.
Respostas de menos de 40 caracteres sem pergunta e respostas cortadas não passam por ela.

A reescrita não pode acrescentar nada, e isso é conferido em código: link, número, nome ou ação em
primeira pessoa ("pesquisei", "li") que não estavam na resposta fazem ela ser recusada, assim como
crescer demais, virar outra resposta ou transformar pergunta em afirmação ("o churrasco rolou?"
virando "o churrasco rolou."). Nomes vindos das regras ou da sua mensagem são aceitos. Com a mente
desligada ou sem consentimento de memória não há regras, logo não há conferência.

Um pedido explícito na mensagem vence a regra. A conferência custa em geral 0,5 a 1 s a mais, e ela
ainda erra: `model_usage` com `purpose = "rule_check"` mostra quantas foram reescritas ou recusadas.

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
