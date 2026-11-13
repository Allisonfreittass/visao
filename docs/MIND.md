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

### Com o app fechado (Web Push)

Uma abertura que passou por todas essas regras também vai como aviso para os aparelhos que você
assinou (`core/initiatives/push.py`, tabela `push_subscriptions`, migração `0015`). Nada de
regra nova: se ele não pode falar no chat, não avisa. Tocar no aviso abre a conversa certa
(`/?c=<id>`).

- Opt-in por aparelho, em Ajustes → "Avisos neste aparelho". No iPhone, só com o app na
  tela de início (iOS 16.4+).
- Chaves VAPID: `python -m apps.api.cli webpush-keys`, depois `VISION_WEBPUSH_PUBLIC_KEY`,
  `VISION_WEBPUSH_PRIVATE_KEY` e `VISION_WEBPUSH_SUBJECT` (URL https do app ou `mailto:`). Sem as
  três, os avisos ficam desligados e o resto funciona igual.
- O conteúdo vai cifrado para as chaves do navegador (aes128gcm): o serviço de push só entrega.
  O servidor só envia para os serviços de push conhecidos (Google, Mozilla, Apple, Microsoft),
  nunca para um endereço digitado.
- Aparelho que o serviço diz não existir mais (404/410) é esquecido; um que falha 5 vezes seguidas
  também. Falha no aviso nunca impede a mensagem no chat.
- Quem envia é o processo que roda a mente: hoje o worker local. Com ele parado, não há abertura
  nem aviso.

## Ele decide quando falar

Em cada rodada ele tem três saídas: falar agora, deixar para uma hora melhor, ou ficar quieto.

- **Hora no seu relógio.** Todo horário que ele vê e diz está no seu fuso (`users.timezone`, por
  padrão `America/Sao_Paulo`, o horário de Brasília): `now_local`, a hora de cada mensagem, o que
  ficou em aberto e as datas que ele manda para a agenda do Google. Antes ele recebia UTC, três
  horas adiantado, e perguntou "como foi?" antes de o compromisso acontecer.
- **Deixar para depois** (`core/mind/intentions.py`, tabela `intentions`, migração `0020`): ele
  marca um lembrete para si mesmo com hora ("21:30, perguntar como foi o Hyrox"). Na hora, um job
  (`mind_think`) acorda uma rodada de pensamento fora do ciclo, com o contexto daquele momento, e
  ele decide de novo: fala, remarca ou deixa passar. Se você já tocou no assunto, deixa passar.
  Até 8 lembretes pendentes, até 30 dias à frente; uma hora dentro do silêncio vai para o fim dele.
- **Toda abertura toca o celular.** Ele já escolheu entre tocar ou só deixar no chat, e marcava
  tudo como "pode esperar": nenhum aviso chegava. Agora o que pode esperar vai para "deixar para
  depois", e o que ele manda toca, dentro dos limites abaixo.
- **Pensar depois da conversa.** Uns 17 minutos depois da sua última mensagem roda uma rodada de
  pensamento, sem esperar o próximo ciclo: é quando o "depois te pergunto" ganha um horário.
- Na conversa ele também sabe a hora e vê o que marcou para retomar.

O que continua fora da decisão dele, porque é seu: horário de silêncio, pausa da autonomia, não
interromper enquanto você conversa (15 min), parar depois de 2 aberturas sem resposta e o máximo
por dia. Ele vê o motivo quando não pode falar (`speaking`) e pode remarcar; se tentou falar na
hora errada, o lembrete é adiado em 20 minutos, por até 12 horas.

## O que ficou em aberto

Um modelo só existe durante uma chamada: entre uma e outra ele é o que aparece no contexto. Por
isso cada rodada de pensamento e cada resposta recebem o que está em aberto entre vocês
(`core/mind/agenda.py`): o que o Mac está rodando, o que terminou nas últimas 24 h (e se você já
falou depois disso), o que espera o seu sim e as últimas mensagens que ele puxou, cada uma marcada
como respondida ou não (resposta em até 24 h). "Te aviso quando terminar" deixou de ser só texto.

## Perguntas com memória

O que ele quer perguntar vira uma fila curta (`owner_questions`, migração `0018`,
`core/mind/questions.py`): no máximo 3 esperando, cada uma some depois de 3 dias sem caber na
conversa, e nada parecido com o que já foi perguntado nos últimos 30 dias entra de novo. Quando a
resposta ou uma abertura faz a pergunta, ela fica "perguntei"; a sua mensagem seguinte é guardada
como resposta, só com consentimento de memória, e apaga junto com a memória (`DELETE /memory`).

## Temperamento

Ninguém sabe se um sistema assim sente alguma coisa, então ele nunca diz que sente. O que ele tem
são tendências calculadas em código do que aconteceu, cada uma com o motivo
(`core/mind/temperament.py`), e elas mudam o que ele faz:

| Estado | Sobe quando | Efeito |
|---|---|---|
| reserva | as últimas mensagens que ele puxou ficaram sem resposta | fala menos, não cobra |
| cautela | você corrigiu (frases de correção, avaliação negativa) ou uma tarefa no Mac falhou, em 72 h | confere mais; com cautela alta, nenhuma proposta no Mac |
| confiança | tarefas no Mac deram certo, propostas dele foram aprovadas, elogios, em 7 dias | sugere o próximo passo; baixa, no máximo 1 proposta por dia |
| vontade | você conversou bastante nos últimos 2 dias | aprofunda |

Os traços (curiosidade, humildade, cuidado, franqueza) andam pouco, com os mesmos sinais de 30
dias. Arrogância e egoísmo aparecem só como o que ele evita. Humildade não é concordar com tudo: o
prompt pede que ele discorde quando achar que você está errado. Na conversa, ele pode falar de como
está como tendência ("fiquei mais cauteloso com isso desde ontem"), nunca como algo vivido. Tudo
aparece no Caderno.

## Internet

**No estudo, em segundo plano:** Wikipédia pt e en, arXiv e páginas via Hacker News
(`integrations/search/open_web.py`), todas APIs públicas gratuitas, consultadas em paralelo.

**Na conversa:**
- **Links que você manda** são abertos antes da resposta (`core/conversation/links.py`, até 2 por
  mensagem). Um repositório do GitHub é lido pela API (`integrations/github/reader.py`): descrição,
  linguagens, últimos commits, a lista de arquivos, o README, até 3 arquivos de configuração e o
  arquivo do link, se for um. Públicos funcionam sem chave (60 leituras por hora); com
  `VISION_GITHUB_TOKEN` (só leitura) abrem também os privados. Outras páginas passam pelo mesmo
  leitor seguro do estudo. O que não abriu é dito como não aberto, e ele não pode fingir que leu.
- **Pesquisa:** quando a curiosidade decide pesquisar um fato público, a busca vai para a web
  aberta pelo Tavily (`VISION_TAVILY_API_KEY`, plano grátis de 1000 buscas por mês) junto com a
  Wikipédia; sem a chave, Wikipédia e arXiv. As fontes aparecem embaixo da resposta.

A busca da própria Anthropic ficou de fora de propósito: ela devolve páginas de tamanho
imprevisível dentro da chamada, e o razão de gastos congela tudo quando uma chamada passa do que
reservou. Aqui o tamanho de cada página e de cada resultado é limitado no código.

Como roda no servidor, `integrations/search/fetch.py` só abre HTTPS em endereços públicos,
revalidados em cada redirecionamento: uma página nunca alcança `localhost`, a rede interna nem o
endereço de metadados da nuvem. O que vem da web entra como dado, num bloco que manda ignorar
qualquer ordem escrita dentro dele.

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
