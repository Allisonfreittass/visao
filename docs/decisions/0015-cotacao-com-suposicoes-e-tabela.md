# ADR-0015: Cotar com suposições declaradas e responder com uma tabela de opções

- Data: 2026-11-16
- Estado: aceita

## Contexto

Em 16/11/2026, na viagem a Santiago:
- "Estou querendo ir em agosto e ficar 10 dias lá" parou para perguntar a cidade de saída;
- "o preço sobe muito se eu pegar aulas?" nem navegou, porque o plano só pensava em voo e hotel.

O Hark, na mesma viagem, sem origem nem datas, escolheu Guarulhos e uma janela em agosto. Ele
cotou e mostrou 5 combos (companhia + hospedagem + datas + total do casal), do mais barato ao mais
caro, com um custo escondido ("a JetSMART não inclui mala de mão") e uma data vizinha mais
barata. Copiamos o comportamento, não a marca nem o visual. **Não copiamos a oferta de reservar:**
o Visão nunca compra nem reserva, por desenho.

## Decisão

### Qualquer preço concreto é ao vivo

O planejador (`core/browse.py`, `INSTRUCTIONS`) diz `browse: true` para o preço, a
disponibilidade ou o horário de qualquer coisa concreta e identificável: aula, aluguel, ingresso,
passeio, transfer, restaurante, produto. Quando não há endereço certo, ele usa `search`. Para
completar a pergunta, usa a conversa recente. As instruções trazem exemplos, incluindo as três
mensagens reais de 16/11; a do meio, de opinião, não navega.

### Suposições em vez de travar

- **Origem:** sai de onde o dono mora.
  - A cidade vem do perfil e da memória curada, e só com o consentimento da memória. Ela é
    encontrada por uma frase como "moro em…", e não pelo modelo (`core/travel_origins.py`).
  - Os aeroportos de cada lugar vêm de uma tabela no código. Para o sul de Minas, por exemplo,
    são GRU, VCP e CNF. O planejador recebe essa lista em `home` e usa o primeiro.
  - Sem cidade conhecida, ele pergunta a origem.
- **Datas:** com mês e duração, usa até 2 janelas (começo e metade do mês), dentro de
  `VISION_BROWSER_MAX_PAGES`. Só com o mês, usa a duração dita na conversa ou 7 noites.
- **Pessoas:** o que a conversa disse; na dúvida, 2 adultos.
- O plano devolve `assumed` (`origem`, `datas`, `pessoas`), que fica no registro do turno
  (`browsed.assumed` em `decisions`), na oferta de painel (`panel_offers.assumed`) e no painel
  (`spec.assumed`, que o card mostra como "Considerando: …").
- A resposta abre declarando as suposições numa frase e termina perguntando se o dono quer
  ajustar.
- `missing` fica só para o que não dá para supor, como o destino.

### A tabela de opções

- **Extração:** depois de abrir páginas com preço, fora da ligação por voz, o turno chama a
  extração estruturada dos painéis (`core/panels/extract.py`, ADR-0012). Cada preço já é
  conferido contra a página lida.
- **Montagem** (`core/panels/quote.py`), toda em código:
  - combina voo e hospedagem da mesma janela e soma o total do grupo;
  - ordena da mais barata à mais cara, com até 5 linhas;
  - escreve no máximo uma frase de datas vizinhas, quando uma janela sai pelo menos 10% mais
    barata;
  - escreve no máximo uma frase do que o total não inclui: o que a página disse
    (`not_included`, conferido palavra por palavra contra o texto dela) e o deslocamento até o
    aeroporto suposto.
  - O modelo não escreve nenhum número da tabela.
- **Na mensagem:** a tabela vai em `messages.quote_table` (migração `0030`). O texto dela também é
  a última bolha (`parts`), como texto de reserva, para o app do iPhone já instalado não quebrar.
  O formato está em [COTACAO_TABELA.md](../COTACAO_TABELA.md).
- **A resposta** é avisada de que a tabela vai abaixo dela. Ela não repete a tabela e nunca
  oferece reservar ou comprar.
- **A oferta de painel** continua no fim, como na Fase 3, e o painel guarda as suposições.

## Consequências

- **Custo:** uma chamada de extração a mais por cotação com preços (Haiku, até 4 páginas de 7 mil
  caracteres) e até 4 páginas abertas (2 janelas × voo e hotel). Ver [COSTS.md](../COSTS.md).
- **Suposição errada:** a pessoa corrige ("saio de Confins"), e o próximo plano usa o que ela
  disse. A suposição sempre vem dita, nunca escondida.
- **Lugar fora da tabela:** a origem é perguntada, como antes. Para cobrir uma cidade nova, basta
  uma linha em `core/travel_origins.py`.
- **App do iPhone:** sem atualizar, mostra a tabela em texto. Para desenhá-la, precisa ser
  atualizado pelo agente do Mac.
