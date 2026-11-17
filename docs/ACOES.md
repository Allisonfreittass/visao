# O que ele faz no app pela conversa

Peça na conversa, e ele faz antes de responder
([ADR-0021](decisions/0021-acoes-no-app-pela-conversa.md)):

| Você diz | Ele faz |
|---|---|
| "cria o projeto Viagem para o Chile" | cria o projeto |
| "deixa anotado isso tudo no projeto Viagem para o Chile" | cria o projeto, se não existir, e anota uma linha por fato decidido na conversa |
| "renomeia o projeto do Chile para Chile 2027" | renomeia |
| "põe o painel de Santiago no projeto do Chile" | o painel aparece na tela do projeto |
| "põe a página do roteiro no projeto" | idem, para uma página |
| "pausa o painel" / "retoma o painel" | pausa ou retoma a conferência |
| "apaga o projeto do Chile" / "apaga o painel" | pergunta antes; só apaga com o seu "sim, apaga" |

**Um "sim" para a oferta dele também vale.** Quando ele pergunta "quer que eu acrescente essas
informações?", um "por favor" faz a ação.

## O projeto é o chat dele

Desde 17/11/2026, a organização segue o que o Hark faz (o comportamento, não o visual):

- **"Chat | Projetos" no topo.** "Chat" é sempre a conversa principal. "Projetos" fica marcado
  enquanto você está num projeto.
- **Tocar num projeto abre o chat dele**, sem página intermediária. Ele é sempre o mesmo chat e
  nasce com uma mensagem dizendo o que o projeto guarda ("Aqui fica tudo de «…». O que está
  anotado até agora: …").
- **No topo do chat do projeto** ficam o nome e um cartão que abre e fecha: "3 anotações ·
  1 painel". Aberto, ele mostra as anotações (com Editar), os painéis do projeto como no Início,
  as páginas, os arquivos, Renomear e Apagar projeto. "Conversa principal" volta.
- **No computador**, a coluna da esquerda vira a lista de projetos enquanto você está num
  projeto. **No celular**, "‹ Projetos" volta para a lista.
- **Da conversa principal:** quando ele cria ou anota um projeto, a resposta traz o botão "Abrir
  o projeto «…» →". O que ele anota dali também aparece no chat do projeto ("Anotei: …"), então
  o chat do projeto é o registro dele.

**Regras:**
- **Anotações:** uma linha por fato, com os valores como apareceram na conversa. Um número que
  não apareceu não é anotado. Você edita as anotações na tela do projeto, em Editar.
- **As anotações voltam:** na conversa contínua, quando o assunto bate ("e o voo da JetSMART?"),
  as anotações do projeto vão junto com a resposta.
- **Ele só diz que fez o que fez.** Se a resposta disser "anotei" ou "criei" sem ter feito, a
  frase é tirada antes de chegar a você. "Não consigo acrescentar" também sai, porque ele
  consegue; "não consigo comprar" fica, porque é verdade.
- **Fora daqui:** comprar, reservar e mandar mensagem.

## API (por acréscimo)

- **Projeto:** `GET /projects` e `GET /projects/{id}` trazem `notes` (texto, uma linha `- ` por
  fato), `notes_updated_at` e `panels` (a contagem). O detalhe traz também
  `panel_list: [{id, title, status}]`.
- **Páginas:** `page_list` inclui as páginas postas no projeto pela conversa.
- **Editar:** `PATCH /projects/{id}` aceita `{"name"}`, `{"notes"}` ou os dois. Só o que vier
  muda.
- **Apagar:** `DELETE /projects/{id}` mantém as conversas, as páginas e os painéis, fora de
  projeto.
- **Chat do projeto:** `GET /conversations/project/{project_id}` devolve o chat do projeto. Na
  primeira vez, ele é criado com uma mensagem de abertura (`origin: "project"`).
- **Mensagens:** cada uma traz `project_id` quando a resposta mexeu num projeto. O app mostra
  "Abrir o projeto". Migração `0034`.
- **Painéis:** `GET /panels` traz `project_id` em cada painel.

## Peças

| Peça | Onde |
|---|---|
| Ler o pedido, fazer, confirmar, a lista para a resposta | [`core/actions.py`](../core/actions.py) |
| Tirar "anotei" quando nada foi feito | [`core/conversation/deeds_guard.py`](../core/conversation/deeds_guard.py) |
| Anotações nas respostas | `notes_block` em [`core/projects.py`](../core/projects.py) |
| Tabelas | `projects.notes`, `artifacts.project_id`, `pending_actions` (migração `0033`) |
| Tela do projeto no web | `ProjectsView.tsx` |
