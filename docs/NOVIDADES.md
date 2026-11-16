# Novidades: o que o Visão passou a fazer

Lista do que mudou nele, da mais nova para a mais antiga, para ele responder "o que tem de novo
em você?" e "o que você consegue fazer agora?" com fatos. Cada item aponta para o documento com os
detalhes. O que está ligado **agora** vem do manifesto de capacidades
(`core/identity/capabilities.py`), que entra em todo prompt; este arquivo conta a história.

## 16/11/2026

- **Backup do banco.** Toda madrugada, uma cópia do schema `visao`:
  - conferida antes de ser guardada;
  - criptografada com uma chave que só o dono tem;
  - guardada 14 dias no servidor, com cópia opcional no R2.

  `make backup-verify` restaura a cópia num Postgres temporário. Se o backup falhar, o resumo da
  manhã avisa primeiro. [ADR-0019](decisions/0019-backup-do-banco.md), [BACKUP.md](BACKUP.md).
- **Compartilhar do iPhone.** De qualquer app, pela folha de compartilhar: uma página, um
  trecho de texto, fotos, prints ou PDFs vão direto para a conversa contínua, e a resposta chega
  como aviso. Sem comentário, ele diz o que importa e propõe uma ação. O conteúdo compartilhado é
  dado, nunca instrução. [ADR-0018](decisions/0018-compartilhar-do-iphone.md),
  [COMPARTILHAR.md](COMPARTILHAR.md).
- **Resumo da manhã.** Todo dia, quando o horário silencioso do dono acaba, uma mensagem com:
  - a agenda do dia;
  - os painéis conferidos na hora;
  - o que espera o sim dele;
  - o que o Mac terminou, o que foi estudado e o que foi marcado para hoje.

  Os valores são conferidos em código. Sem nada novo, não sai nada. Ele desliga ou pede um na
  hora em Ajustes. [ADR-0017](decisions/0017-resumo-da-manha.md),
  [RESUMO_DA_MANHA.md](RESUMO_DA_MANHA.md).
- **Painel de olho perto da meta.**
  - Com o total até 15% acima da meta, ou já abaixo dela, o painel é conferido a cada 3 horas,
    fora do horário silencioso, em vez de uma vez por dia.
  - Ficar abaixo da meta é aviso urgente: sai na hora, mesmo que outro aviso já tenha saído no
    dia, uma vez cada vez que o preço fica abaixo.
  - "Me avisa se ficar abaixo de R$ X" define a meta.

  [ADR-0016](decisions/0016-painel-de-olho-perto-da-meta.md), [PAINEIS.md](PAINEIS.md).
- **Uma conversa só, sem lista de conversas.**
  - A conversa com o dono é contínua, como um chat único.
  - O trecho recente vai inteiro para o modelo; os trechos antigos fecham numa pausa de 3 h, na
    virada do dia ou a cada 40 mensagens, e viram resumos curtos, conferidos para não trazer link,
    número ou nome que não estava nas mensagens.
  - Conversas separadas só existem dentro de Projetos.
  - As 8 conversas antigas foram apagadas a pedido do dono, depois de uma última curadoria da
    memória (19 memórias novas, a maioria sobre a viagem a Santiago).

  [ADR-0014](decisions/0014-conversa-continua.md), [CONVERSA_CONTINUA.md](CONVERSA_CONTINUA.md).
- **Cotação com suposições e tabela de opções.**
  - Qualquer preço concreto é buscado ao vivo: passagem, hotel, aula, aluguel, ingresso, passeio.
  - Faltando a origem, ele usa a cidade onde o dono mora e os aeroportos dela.
  - Faltando as datas, usa uma janela no mês dito. Faltando as pessoas, 2 adultos.
  - O que foi suposto é dito no começo da resposta.
  - Com preços lidos, o sistema monta embaixo da resposta uma tabela de até 5 opções com o total
    do grupo. Ela é montada em código, nunca pelo modelo.
  - Ele nunca reserva nem compra.

  [ADR-0015](decisions/0015-cotacao-com-suposicoes-e-tabela.md),
  [COTACAO_TABELA.md](COTACAO_TABELA.md).
- **Pesquisa livre.** Com a permissão `auto_research`, ele pesquisa e retoma pesquisas sem pedir
  aprovação, e elas não aparecem mais no cartão "esperando você".
- **Sem limite diário no chat.** Um dia de muita conversa não para no meio. O que sobra é o teto
  mensal e o limite por chamada. Para caber nesse limite, a resposta tira o histórico mais antigo
  e corta páginas anexadas, em vez de falhar. [COSTS.md](COSTS.md).
- **Nunca negar o navegador.** Uma resposta que diz "não tenho acesso a sites" ou manda o dono
  pesquisar sozinho é reescrita, ou a frase é tirada, antes de chegar a ele.
  [ADR-0013](decisions/0013-nunca-negar-o-navegador.md).
- **Quando um site recusa (403), ele tenta outro.** Um site que recusou fica evitado por 30
  dias. Quando a busca ao vivo não acontece, o motivo fica registrado (`browse_skipped`), e a
  resposta diz que tentou. [NAVEGADOR.md](NAVEGADOR.md).
- **Toda mensagem que ele puxa toca o celular.** O que pode esperar fica para depois, em vez de
  sair como mensagem silenciosa. [MIND.md](MIND.md).

## Como ele deve usar isto

- Perguntado sobre o que sabe fazer, responder pelo manifesto de capacidades e, para detalhes,
  por estes documentos, dizendo de onde tirou.
- Não prometer o que não está na lista: comprar, reservar, fazer login ou acessar outras contas
  continuam fora do alcance.
- Quando algo daqui mudar o jeito de ele se apresentar, ele pode reescrever a própria
  autodescrição.
