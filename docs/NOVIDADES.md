# Novidades: o que o Visão passou a fazer

Lista do que mudou nele, da mais nova para a mais antiga, para ele responder "o que tem de novo
em você?" e "o que você consegue fazer agora?" com fatos. Cada item aponta para o documento com os
detalhes. O que está ligado **agora** vem do manifesto de capacidades
(`core/identity/capabilities.py`), que entra em todo prompt; este arquivo conta a história.

## 23/11/2026

- **Provedor por tarefa, escolhido por regra no código**
  ([ADR-0022](decisions/0022-provedor-por-tarefa.md)).
  - Em Ajustes > Modelo, "Escolha do provedor" tem duas opções. **Ordem fixa** é a de antes:
    principal, reserva, segunda reserva. **Por tarefa** reordena os mesmos provedores pelo
    propósito da chamada.
  - A conversa e tudo que leva algo do dono vão primeiro no Claude, depois OpenAI e Gemini. Só a
    revisão do estudo, que leva apenas texto público, vai primeiro no Gemini grátis, porque o
    nível grátis dele pode usar o que recebe para melhorar os produtos do Google.
  - Nenhum modelo escolhe outro. O fallback em falha, os tetos pagos e o encaixe do prompt
    continuam iguais.
  - Um provedor sem cota fica pausado no banco, para a API e o worker juntos, até o reset que
    ele mesmo informou (meia-noite do Pacífico para a cota diária do Gemini). Antes eram 15
    minutos, e cada processo descobria por si.

- **Braço versão 3: desfazer, até os testes passarem, e todo comando no sandbox**
  ([BRACO.md](BRACO.md), itens 4, 8, 9 e 10).
  - Todo comando que uma tarefa roda no Mac fica no sandbox do Claude Code: grava só no projeto,
    não usa a rede e não lê as pastas de chaves.
  - O que a tarefa deixou rodando acaba junto com ela.
  - O braço tira uma foto do projeto antes e depois, e a lista de arquivos mudados vem dessa foto,
    não do relato do Claude. Na página Mac, **desfazer** volta esses arquivos sem chamar o Claude,
    e não mexe em nada se algum deles mudou de novo depois.
  - "Até os testes passarem" no pedido: o braço roda o comando de testes definido no
    `braco.json`, e enquanto falhar o Claude continua na mesma sessão. São até 3 tentativas, todas
    dentro da mesma aprovação e do mesmo limite de custo.

- **O anel no lugar do Ciclope** ([DESIGN.md](../DESIGN.md) §6, §8 passos 1 a 3).
  - O app inteiro usa as cores e as fontes do Muninn; vermelho só aparece em erro.
  - O anel mostra o que ele está fazendo: a hora local acesa quando parado, uma onda ouvindo, um
    rastro âmbar pensando (a onda segue o volume quando ele fala), o ponto subindo à falha
    quando ele abriu uma conversa que você não leu, a falha
    acesa quando algo espera o seu sim, o ponto vazado com a autonomia pausada e tudo apagado sem
    conexão.
  - Mac, e-mail, Caderno e projetos viraram ícones de traço, sem cor própria.
  - O Muninn aparece também no topo do Início e na ligação, com os estados do anel em volta, e a
    abertura do dia toca uma gênese curta dele (os traços nascendo do peito, o olho acendendo, o
    anel fechando) antes de escrever o nome.
  - O que ele está pensando, no Início, aparece como fala dele: itálico com um filete âmbar.
  - Os textos falam como ele: "Acompanhando 2 painéis", "Fala comigo…", "Acompanhar um preço".
    Saíram "vigilância", "Dê uma ordem" e "Sistemas prontos"; avaliar uma resposta é "Ajudou" ou
    "Não ajudou", sem emoji.

- **A entrada agora é o Muninn** (primeira tela da identidade nova, [DESIGN.md](../DESIGN.md) §8
  passo 4).
  - No lugar do Ciclope e de "Identifique-se.", o corvo dentro do anel de rastros e "Bem-vindo de
    volta.". A gênese roda uma vez ao abrir a tela; o formulário funciona desde o começo, e quem
    pediu menos movimento vê só o quadro final.
  - Enquanto confere a senha, um rastro âmbar percorre o anel.
  - O erro diz o que aconteceu: "E-mail ou senha não conferem." só quando é isso; servidor fora,
    demora ou muitas tentativas aparecem como tal, sem culpar a senha. Se o servidor não respondeu
    à última verificação, a tela avisa antes de você digitar.
  - O resto do app continua com a marca anterior até os passos 1 e 2 da migração.

- **Mais firme quando algo dá errado** (estudo comparativo com OpenClaw, Goose e OpenCode,
  [research/comparativo_agentes.md](research/comparativo_agentes.md)).
  - Um email ou evento aprovado sai uma vez só, mesmo com duas aprovações juntas. Pedido parado há
    mais de um dia vence. Se o servidor cair no meio do envio, ele avisa que não sabe se saiu e não
    reenvia ([GOOGLE.md](GOOGLE.md)).
  - A mesma mensagem enviada duas vezes recebe uma resposta só, e o que ela pedia (criar projeto,
    anotar) acontece uma vez. Duas mensagens ao mesmo tempo na mesma conversa são respondidas em
    fila ([ACOES.md](ACOES.md)).
  - Se o modelo falhar depois de ele já ter feito algo no app, a resposta diz o que foi feito em
    vez de só mostrar um erro.
  - **Braço do Mac, versão 2** ([BRACO.md](BRACO.md)):
    - o Claude Code roda isolado, e uma tarefa não consegue mudar as permissões, os hooks ou o
      `CLAUDE.md` das próximas;
    - o resultado fica guardado no Mac até o servidor receber;
    - uma tarefa cortada por um reinício volta como interrompida e não é refeita;
    - um Mac que some faz a tarefa falhar em minutos.

    Para valer no Mac, é preciso rodar o instalador de novo.

## 17/11/2026

- **Telas mais fáceis de usar e uma abertura.**
  - Os menus usam os mesmos nomes: Início, Chat e Projetos. O menu lateral só tem o que não está
    no topo (Caderno, Mac e Ajustes).
  - No projeto, a barra mostra o nome inteiro e tem uma seta para voltar. A mensagem de abertura
    não repete as anotações, que ficam no cartão de cima.
  - Botões e links com pelo menos 44 px para o dedo.
  - O botão de ligar, ao lado do campo de mensagem, virou uma onda de voz em vez de um ponto
    vermelho.
  - As sugestões de painel no Início dizem o que acontece ao tocar.
  - Abertura de 4 segundos, uma vez por dia: as partículas viram o orbe, "V.I.S.A.O."
    aparece ao lado com um cumprimento, e o app aparece. Um toque pula, e quem pediu menos
    movimento no aparelho não vê.
- **O projeto é o chat dele (como o Hark organiza).**
  - "Chat | Projetos" no topo.
  - Tocar num projeto abre o chat dele, que nasce com o que está anotado.
  - Em cima do chat fica um cartão com anotações, painéis, páginas e arquivos.
  - No computador, a lista de projetos fica ao lado.
  - Quando ele mexe num projeto pela conversa principal, a resposta traz "Abrir o projeto", e o
    que foi anotado aparece também no chat do projeto. [ACOES.md](ACOES.md).
- **Projeto com chat e painéis próprios.**
  - "Abrir o chat do projeto" abre sempre o mesmo chat.
  - Os painéis do projeto aparecem nele.
  - No chat do projeto, uma barra leva de volta à conversa principal, e "Conversa" em qualquer
    menu também volta.
  - Um "por favor" para a oferta dele ("quer que eu acrescente?") agora faz a ação.
  - "Não consigo acrescentar" é tirado da resposta, porque ele consegue. [ACOES.md](ACOES.md).
- **Ações no app pela conversa.**
  - Projetos: criar, renomear e apagar.
  - Anotar num projeto o que a conversa decidiu; uma linha com número que não apareceu na
    conversa não é gravada.
  - Pôr painel ou página num projeto; pausar, retomar e apagar painéis.
  - Apagar só depois do "sim, apaga".
  - As anotações voltam nas respostas quando o assunto volta.
  - Uma resposta que diz "anotei" ou "criei" sem ter feito perde essa frase.

  Veio do caso de 17/11, quando ele disse "Anotado" sem projeto nem anotação.
  [ADR-0021](decisions/0021-acoes-no-app-pela-conversa.md), [ACOES.md](ACOES.md).

## 16/11/2026

- **Localização para "perto de mim".** "Tem farmácia aberta aqui perto?":
  - com "Usar minha localização" ligado, ele abre o Google Maps onde o dono está e responde com
    nome, endereço e se está aberto;
  - a posição vai só com essa mensagem, o modelo nunca vê as coordenadas e nada as guarda;
  - sem a posição, ele pergunta o bairro.

  [ADR-0020](decisions/0020-localizacao.md), [LOCALIZACAO.md](LOCALIZACAO.md).
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
