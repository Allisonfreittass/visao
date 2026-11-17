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

**Regras:**
- **Anotações:** uma linha por fato, com os valores como apareceram na conversa. Um número que
  não apareceu não é anotado. Você edita as anotações na tela do projeto, em Editar.
- **As anotações voltam:** na conversa contínua, quando o assunto bate ("e o voo da JetSMART?"),
  as anotações do projeto vão junto com a resposta.
- **Ele só diz que fez o que fez.** Se a resposta disser "anotei" ou "criei" sem ter feito, a
  frase é tirada antes de chegar a você.
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

## Peças

| Peça | Onde |
|---|---|
| Ler o pedido, fazer, confirmar, a lista para a resposta | [`core/actions.py`](../core/actions.py) |
| Tirar "anotei" quando nada foi feito | [`core/conversation/deeds_guard.py`](../core/conversation/deeds_guard.py) |
| Anotações nas respostas | `notes_block` em [`core/projects.py`](../core/projects.py) |
| Tabelas | `projects.notes`, `artifacts.project_id`, `pending_actions` (migração `0033`) |
| Tela do projeto no web | `ProjectsView.tsx` |
