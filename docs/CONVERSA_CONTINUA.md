# Conversa contínua: como funciona e o contrato para os apps

Cada dono tem **uma conversa contínua**, que o app abre por padrão, como o chat do Hark
([ADR-0014](decisions/0014-conversa-continua.md)). As outras conversas continuam existindo, como
arquivo, e os **Projetos** continuam servindo para separar um assunto de propósito.

## O que o modelo lê

- **O trecho aberto inteiro:** tudo depois do último trecho resumido, e nunca menos que as 8
  últimas mensagens.
- **Os resumos de trechos antigos:** sempre o mais recente, mais os que combinam com o assunto da
  mensagem, até 3. Com "lembra quando…", são até 6.
- **A memória curada**, como sempre.
- **O registro do que ele fez** cobre os últimos 7 dias. O resto fica em `decisions` e na Bancada.

O `fit()` continua garantindo o limite por chamada.

## Quando um trecho fecha

Um trecho fecha numa pausa de mais de 3 horas, na virada do dia no fuso do dono, ou ao passar de
40 mensagens. Depois de cada turno da contínua, a API enfileira o job `segment_summary`. O worker
fecha o que estiver vencido e escreve o título, o resumo (até 600 caracteres) e as
palavras-chave. A chamada usa o Haiku com raciocínio desligado e conta no orçamento da autonomia.

O resumo é conferido em código: não pode trazer link, número ou nome que não esteja nas mensagens
do trecho. Um trecho que não deu para resumir fica `failed`, sem orçamento ou com resposta
recusada, e as mensagens dele continuam indo cruas enquanto couberem.

## API (tudo por acréscimo: um app antigo continua funcionando)

### `GET /conversations/continuous`

Devolve a conversa contínua do dono e cria a conversa na primeira vez:

```json
{ "id": "…", "created_at": "…", "title": null, "project_id": null, "continuous": true }
```

`GET /conversations` traz a contínua primeiro e as outras depois, das mais novas para as mais
antigas. Todas têm o campo `continuous`. A contínua não entra em projeto:
`PUT /conversations/{id}/project` responde 409.

### `GET /conversations/{id}/messages?limit=100&before={message_id}`

- **Sem parâmetros:** a conversa inteira, como antes. Um app que não pagina continua funcionando,
  mas na contínua isso cresce sem fim, então pagine.
- **Com `limit` (1 a 500):** as últimas `limit` mensagens, da mais antiga para a mais nova.
- **Com `before`:** as `limit` mensagens antes dessa. É assim que se carrega para trás. Veio menos
  que `limit`: não há mais nada.

Uma mensagem que responde a outra fora da página continua trazendo `reply_to`.

### `GET /conversations/{id}/segments`

Os trechos fechados, do mais antigo para o mais novo:

```json
[
  {
    "id": "…",
    "title": "Viagem a Santiago",
    "started_at": "2026-11-14T13:00:00Z",
    "ended_at": "2026-11-14T15:40:00Z",
    "first_message_id": "…",
    "last_message_id": "…",
    "messages": 24,
    "status": "summarized"
  }
]
```

`status: "failed"` vem com `title` vazio: mostre só o dia.

## No chat (o que o web faz, e o iPhone deve fazer igual)

- **Abrir a contínua:** ao entrar, o app abre a contínua (`GET /conversations/continuous`). No
  menu ela aparece como "Conversa", no topo.
- **Carregar para trás:** o app carrega as últimas 100 mensagens e mostra "Carregar mensagens
  anteriores" quando veio uma página cheia. Ao recarregar, depois de enviar ou de um aviso,
  ele pede `limit = max(100, quantas já estão na tela)`.
- **Divisões:** um separador a cada dia novo ("Hoje", "Ontem", "14/11") e no começo de cada trecho
  resumido, com o título ("Viagem a Santiago · Ontem"). O resumo em si não aparece no chat: ele é
  para o modelo.
- **O resto do chat** continua como numa conversa comum: stream, bolhas, tabela de cotação,
  responder arrastando.
