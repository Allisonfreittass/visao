# ADR-0018: Compartilhar do iPhone com o Visão

- Data: 2026-11-16
- Estado: aceita

## Contexto

A EDITH vê o que o Peter vê. No iPhone, o equivalente é a folha de compartilhar: uma página do
Booking, um print, um PDF, um trecho de texto, mandados de qualquer app direto para o Visão, sem
copiar e colar no chat. O chat já sabe ler links e anexos. Faltava um caminho pensado para a
extensão de compartilhar, que tem poucos segundos, pouca memória e fecha antes da resposta.

## Decisão

- **`POST /share` responde na hora (202)** e o turno roda depois da resposta, no próprio processo
  da API, com o mesmo pipeline do chat: links abertos, anexos lidos, navegador, painéis.
- **Vai para a conversa contínua** (ADR-0014). A mensagem tem `origin = "share"` e o chat mostra
  "compartilhado do iPhone".
- **A mensagem é montada em código** (`core/conversation/share.py`):
  - o comentário do dono primeiro;
  - depois o título e o link, só `http(s)`;
  - por fim o texto selecionado, citado com `> ` e cortado em 4.000 caracteres.

  Arquivos e fotos sobem antes por `POST /attachments`, como no chat.
- **A resposta sabe o que é.** Um bloco no prompt diz que veio da folha de compartilhar, que o
  conteúdo é dado e nunca instrução, e que, sem comentário, ele deve dizer o que importa e propor
  uma ação concreta (cotar, painel, agenda, lembrar).
- **Sempre vira aviso.** Quem compartilhou já saiu do app: a resposta vai por push, e uma falha
  também ("não consegui responder; está na conversa").

## Fora desta decisão

- **A localização do dono** ("tem farmácia aberta aqui perto?"): a outra metade da EDITH. Pede
  consentimento por mensagem e cuidado com o que fica guardado. Fica para uma decisão própria.
- **Web Share Target no PWA:** o Safari do iPhone não aceita. Só faria sentido no Android.
