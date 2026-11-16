# Status ao vivo e aviso quando termina

Enquanto ele responde, o chat mostra o passo atual no lugar de "Pensando", e um detalhe numa pílula
embaixo quando há (o termo pesquisado, os sites, os arquivos). Só aparece o que de fato está rodando:

| Passo | Quando |
|---|---|
| Pensando | começo de todo turno |
| Lendo `arquivo` / Olhando a foto | a mensagem veio com anexos |
| Abrindo `site` | a mensagem tem links |
| Olhando sua agenda / Procurando no seu Gmail | o Google está conectado e a pergunta é sobre isso |
| Pesquisando “termo” (na web, na Wikipédia…) | o motor de curiosidade decidiu pesquisar |
| Lendo o próprio código | a pergunta é sobre ele mesmo |
| Escrevendo a resposta | a chamada ao modelo que gera a resposta |
| Conferindo as suas regras | há regras suas a checar na resposta |
| Conferindo a resposta | sem regras suas, a resposta negou o navegador ([ADR-0013](decisions/0013-nunca-negar-o-navegador.md)) |

## A resposta aparecendo aos poucos (stream)

Desde 15/11/2026 o app abre `GET /conversations/{id}/stream` (SSE) junto com o envio e recebe o
turno ao vivo ([ADR-0011](decisions/0011-streaming-da-resposta.md)):
- os mesmos passos desta tabela, um por vez, na bolha que respira;
- o texto conforme é escrito, solto num ritmo constante;
- no fim, a versão conferida pelas regras do dono e pela regra de nunca negar o navegador
  (`replace`, se a checagem mudou algo) e um `done` com a mesma resposta do POST.

Se o stream cair, o app retoma de onde parou (`Last-Event-ID`). Se não der para abrir, volta a
consultar o `/progress` como antes. O POST continua sendo quem cria a resposta.

**Conferir em produção depois do deploy** (o Caddy não pode segurar os eventos):

```bash
curl -N -H "Authorization: Bearer $TOKEN" https://SEU-DOMINIO/api/conversations/ID/stream
```

Com uma mensagem sendo respondida nessa conversa, os eventos devem aparecer um a um, não todos no
fim.

## Peças

- [`core/conversation/progress.py`](../core/conversation/progress.py): cada passo chama
  `progress.step(...)`; a rota de mensagem abre `progress.tracking(conversa)` em volta do turno.
  Fica só no processo da API, fora do banco (é uma vista ao vivo, não um registro; o registro é o
  plano do turno).
- `GET /conversations/{id}/stream`: os mesmos passos e o texto como eventos numerados
  (`core/conversation/progress.py` guarda a lista; um turno terminado fica 30 s legível).
- `GET /conversations/{id}/progress`: plano B do stream, e o caminho da ligação por voz e da Live
  Activity; consultado a cada 0,9 s, **só com a tela visível**.

## Aviso no celular

Se o app estava acompanhando o turno e parou de consultar por mais de 6 s (tela bloqueada, app
fechado, aba escondida), a resposta também vai como notificação (Web Push, se ativado em Ajustes),
abrindo a conversa ao tocar. Um turno que ninguém acompanhou (app antigo, script) nunca gera
aviso. É resposta ao que você acabou de pedir, então não conta no limite de mensagens que ele puxa
sozinho.

O cartão com barra de progresso na tela de bloqueio (Live Activity) existe no app nativo do iPhone
([APP_IOS.md](APP_IOS.md), Etapa 7). No web, que é um PWA, chega uma notificação comum quando
termina.
