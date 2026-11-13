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

## Peças

- [`core/conversation/progress.py`](../core/conversation/progress.py): cada passo chama
  `progress.step(...)`; a rota de mensagem abre `progress.tracking(conversa)` em volta do turno.
  Fica só no processo da API, fora do banco (é uma vista ao vivo, não um registro; o registro é o
  plano do turno).
- `GET /conversations/{id}/progress`: o app consulta a cada 0,9 s enquanto espera, **só com a tela
  visível**.

## Aviso no celular

Se o app estava acompanhando o turno e parou de consultar por mais de 6 s (tela bloqueada, app
fechado, aba escondida), a resposta também vai como notificação (Web Push, se ativado em Ajustes),
abrindo a conversa ao tocar. Um turno que ninguém acompanhou (app antigo, script) nunca gera
aviso. É resposta ao que você acabou de pedir, então não conta no limite de mensagens que ele puxa
sozinho.

O cartão com barra de progresso na tela de bloqueio do iPhone (Live Activity) só existe para app
nativo de iOS; o Visão é um PWA, então lá chega uma notificação comum quando termina.
