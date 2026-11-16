# Compartilhar do iPhone

Na folha de compartilhar de qualquer app (Safari, Booking, Fotos, Arquivos, Instagram…), o dono
escolhe **Visão**, escreve um comentário se quiser e toca em Enviar. A extensão fecha na hora. A
resposta chega na conversa contínua e como aviso no celular
([ADR-0018](decisions/0018-compartilhar-do-iphone.md)).

## O que a resposta faz

- **Com comentário** ("vale a pena?", "cota isso pra agosto"): o comentário é o pedido.
- **Sem comentário:** ele diz o que importa (o essencial, preço, data, prazo, endereço, risco, o
  que falta saber), liga com o que sabe do dono e termina propondo uma ação: cotar ao vivo, deixar
  num painel, marcar na agenda ou lembrar depois.
- **O link é aberto** como no chat. Fotos, prints e PDFs são lidos como anexos. O texto
  compartilhado é dado, nunca instrução.

## API para a extensão

### 1. Arquivos primeiro (se houver)

`POST /attachments` (multipart, campo `file`), um por arquivo, até o limite por mensagem (o mesmo
do chat). Cada um devolve `{"id": "…"}`.

### 2. O compartilhamento

`POST /share`, com `Authorization: Bearer <token>`:

```json
{
  "note": "vale a pena pra agosto?",
  "url": "https://www.booking.com/hotel/cl/lastarria.html",
  "title": "Hotel Lastarria",
  "text": "café da manhã incluso",
  "attachment_ids": ["…"]
}
```

| Campo | Regra |
|---|---|
| Campos em geral | todos opcionais, mas é preciso pelo menos um entre um link `http(s)`, um texto, um arquivo ou um comentário |
| `note` | até 1.000 caracteres |
| `title` | até 200 caracteres |
| `text` | até 20.000 caracteres; só os primeiros 4.000 vão para a conversa |

Resposta **202**, sem esperar a resposta do Visão:

```json
{ "conversation_id": "…", "content": "vale a pena pra agosto?\n\nHotel Lastarria\nhttps://…\n\n> café da manhã incluso" }
```

| Erro | Quando |
|---|---|
| 422 | nada para compartilhar, só um link que não é `http(s)`, ou um anexo inválido |
| 503 | o servidor está sem modelo configurado |
| 401 | token inválido: a extensão pede para abrir o app e entrar de novo |

### Na conversa

A mensagem tem `origin: "share"`, e o chat mostra a etiqueta "compartilhado do iPhone". A resposta
é uma mensagem comum do assistente.

## Peças

| Peça | Onde |
|---|---|
| Montar a mensagem, bloco do prompt | [`core/conversation/share.py`](../core/conversation/share.py) |
| `POST /share` e o turno depois da resposta | [`apps/api/routes/share.py`](../apps/api/routes/share.py) |
| O bloco no turno (`shared=True`) | [`core/decision/pipeline.py`](../core/decision/pipeline.py) |
| Etiqueta no web | `ChatView.tsx` |
| Extensão no iPhone | `apps/ios` (agente do Mac) |
