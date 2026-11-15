# ADR-0011: Streaming da resposta por SSE, com a checagem das regras mantida

- Data: 2026-11-15
- Estado: aceita

## Contexto

No chat de texto, a resposta aparecia inteira de uma vez, depois de o app consultar `/progress` a
cada 0,9 s. Mesmo uma resposta rápida parecia lenta. Já existia streaming, mas só na ligação por
voz: o provedor da Anthropic manda o texto aos poucos para `progress.draft`
(`integrations/llm/base.py`, `drafting`), e o iPhone lê o rascunho no `/progress` para falar
frase por frase. Nessa ligação, a checagem das regras do dono é pulada (commit `04abafa`).

No texto, cada resposta passa pela checagem das regras do dono (`_obey_rules` em
`core/conversation/service.py`): uma segunda chamada curta devolve "obedece" ou uma reescrita.
O código recusa a reescrita se ela ficar mais longa ou trouxer link, número, nome ou ação novos.
Se o texto aparecer enquanto é escrito, a pessoa pode ler uma versão que depois é reescrita.

## Decisão

### Servidor

- **Eventos do turno:** o registro em memória do turno (`core/conversation/progress.py`) passa a
  guardar uma lista de eventos numerados: `step`, `delta`, `replace`, `sources`, `action`,
  `done` e `error`. O número de cada evento vem de um contador do processo, sempre crescente.
  Ele serve de `id` no SSE, e o cliente retoma com `Last-Event-ID` depois de uma queda de rede.
  Um turno terminado continua legível por 30 s, como o `/progress`.
- **Endpoint:** `GET /conversations/{id}/stream` (`text/event-stream`), com autenticação no
  cabeçalho, como as outras rotas.
  - Serve o turno em andamento. Se ainda não houver um, espera até 15 s ele começar (o app abre o
    stream e manda a mensagem logo em seguida).
  - Fecha depois do `done` ou do `error`, e manda um comentário a cada 15 s para a conexão não
    cair.
  - Ler o stream conta como "o dono está olhando", do mesmo jeito que consultar o `/progress`,
    para o aviso no celular.
- **O POST continua igual:** `POST /conversations/{id}/messages` segue sendo o caminho que cria
  as mensagens e devolve a resposta final. O stream só mostra o que acontece. Se o stream cair, o
  turno continua e a mensagem é salva. O `/progress` também continua, como plano B e para a Live
  Activity e os avisos.
- **Texto aos poucos:** o rascunho passa a ser pedido também no texto. Cada vez que ele cresce,
  vira um `delta`.
  - O marcador de página `[[página: …]]` e o que vem depois nunca saem.
  - A quebra de bolha `[[+]]` sai como parágrafo, e um marcador incompleto no fim do pedaço fica
    retido até fechar.
  - Um provedor que não faz streaming manda o texto inteiro num `delta` só, no fim, e o cliente
    funciona igual.
  - O `/progress` só mostra o `draft` na voz, como antes.

### A checagem das regras do dono: opção (a), stream e depois `replace`

O texto vai saindo enquanto é escrito. No fim, o servidor manda o texto final:
- Se a checagem não mudou nada, vai só o que faltava, como `delta`.
- Se mudou, vai um evento `replace` com a versão final inteira, e o cliente troca o texto com uma
  transição curta. A versão final é a que fica salva e a que o POST devolve.

Por que (a):
- **A checagem continua igual**, com o mesmo prazo de 4 s e as mesmas recusas.
- **Uma reescrita só pode cortar ou reformular**, nunca acrescentar: o código recusa link, número,
  nome ou ação novos. Então o `replace` nunca mostra algo que a pessoa não leu antes; no máximo
  tira um trecho.
- **A checagem roda poucas vezes:** só com regras do dono, texto não trivial e fora da voz. A
  troca é rara.
- **(b) checar por trechos** mudaria a natureza da checagem (ela julga a resposta inteira, como
  "não termine toda resposta com pergunta") e custaria uma chamada por trecho.
- **(c) desligar o streaming quando há regras** tiraria a fluidez justamente de quem mais usa o
  app.

### Orçamento

- **A reserva continua antes da chamada:** `GuardedLLMProvider.reserve` com o pior caso, e o
  acerto pelo custo real no fim do stream (`get_final_message`).
- **Parar (×) no meio do stream:** o provedor confere a cada pedaço se o dono pediu para parar
  (`drafting(..., stop=progress.cancelled)`). Se pediu, fecha o stream e falha com o tipo
  `cancelled`.
  - O razão trata `cancelled` como trata `timeout`: o consumo real não é conhecido, então a
    reserva fica cobrada (estado `unknown`) e não volta. Essa regra já existia para timeout.
  - O `model_usage` registra a chamada com resultado `cancelled`.
  - Nenhuma mensagem do assistente é salva, e o stream manda `error` com `cancelled`.
- **Queda do cliente** (fechar o app, perder a rede): não afeta o turno. A chamada termina, é
  acertada pelo custo real e a mensagem é salva; o app a encontra ao voltar (POST, `/messages` ou
  `Last-Event-ID`).
- **Timeout do provedor no meio do stream:** segue a regra que já existia (reserva `unknown`,
  cobrada). O stream manda `error` e nenhuma mensagem fica pela metade no banco.

### Proxy

No Caddy, a rota do stream fica fora da compressão (`encode` com um matcher que exclui
`*/stream`) e tem `flush_interval -1` no `reverse_proxy`. A resposta traz
`Cache-Control: no-cache` e `X-Accel-Buffering: no`. A Cloudflare não segura respostas
`text/event-stream`. Isso precisa ser conferido em produção depois do deploy, com
`curl -N` (ver [STATUS.md](../STATUS.md)).

### Clientes

- **Web:** `fetch` com `ReadableStream`, não `EventSource`, porque `EventSource` não manda o
  cabeçalho de autenticação. O parser de SSE é testado no vitest. Se o stream falhar, o app volta
  ao `/progress`.
- **iPhone:** `URLSession.bytes(for:)`, com o parser testado no XCTest. No `ChatStore`, o stream
  substitui o polling com o app em primeiro plano. Em segundo plano fica o caminho de hoje (Live
  Activity e push).
- **Revelação suave:** o texto que chega em rajadas é soltado num ritmo constante, de 30 a 60
  caracteres por segundo, acelerando para nunca ficar mais de cerca de 1 s atrás. Com Reduzir
  Movimento ligado, o texto entra direto.

## Alternativas descartadas

- **WebSocket:** precisaria de outra rota no Caddy e na Cloudflare, de autenticação própria e de
  reconexão feita à mão. O SSE é HTTP comum e já tem retomada (`Last-Event-ID`).
- **Stream no próprio POST:** misturaria criar a mensagem com mostrá-la. Uma queda de rede no meio
  perderia a resposta final, que hoje chega inteira no POST.
- **Redis ou fila para os eventos:** a API roda num processo só, como o `/progress`. Se um dia
  houver mais de um processo, essa decisão precisa ser revista (os dois dependem disso).

## Consequências

- **Mesma dependência do `/progress`:** a API precisa continuar num processo só, porque os eventos
  vivem na memória dele.
- **O texto do chat aparece aos poucos**, e a versão salva é sempre a conferida.
- **Nenhuma dependência nova**, nem no servidor nem nos clientes.
