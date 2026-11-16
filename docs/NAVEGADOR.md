# Páginas ao vivo (navegador de verdade)

Quando a mensagem é sobre algo que muda com o tempo (passagens, hotéis, preços, disponibilidade,
cotações, horários), ele abre os sites num Chromium de verdade, lê o que eles mostram agora e
responde a partir disso, dizendo em que site viu e de quando é. No chat aparece "Cotando voos",
"Olhando hotéis" ou "Lendo latam.com" enquanto ele lê, e os sites entram nas fontes como "ao vivo". O que ele leu fica
guardado para as páginas que ele escreve depois ([ARTEFATOS.md](ARTEFATOS.md)).

## Como decide

1. Um filtro de palavras (preço, passagem, voo, hotel, cotar, orçamento, diárias, ida e volta...)
   evita gastar uma chamada em conversa comum. "Agora", "hoje", "tempo real" e "ao vivo" sozinhos
   não bastam: contam quando a conversa recente (as mesmas 6 mensagens que o planejador lê) é sobre
   preço ou viagem. Nessa conversa, uma resposta curta com o que faltava ("saindo de BH, 10 a 20
   de agosto") ou um "e em tempo real?" também passam.
2. Uma chamada curta ao modelo planeja até 4 endereços, com modelos que funcionam:
   Google Voos (`/travel/flights?q=Flights to SCL from CNF on 2027-10-01 through 2027-10-08`) e
   Google Hotéis (`/travel/search?q=hotéis em … datas`). Sem endereço certo, ele usa a busca que já
   existe (Tavily/web) para achar páginas. Faltando algo essencial, o plano diz o quê (`"missing": ["origem", "datas"]`): ele não navega, a
   pesquisa genérica da curiosidade também não roda, e a resposta recebe um bloco dizendo que ele
   **consegue** ver os preços de agora e deve perguntar só o que falta (nunca "não tenho acesso a
   sites ao vivo"). Quando a pessoa responde com os dados, o planejador junta com o pedido de
   antes e navega.
3. O navegador abre as páginas; o texto vai junto da mensagem como dado de terceiros.

Testado em 13/11/2026: Google Voos e Google Hotéis devolvem preços reais. A busca do Google,
o Google Shopping, o Mercado Livre e o DuckDuckGo recusam navegador automático (pedem
verificação ou respondem 403); ele reporta isso e não insiste.

**Quando um site recusa o robô** (401, 403, 429 ou pedido de prova de humano), ele tenta outro
site no lugar, uma vez só: primeiro um resultado da busca que sobrou e, se não sobrar nenhum, um
segundo plano que já sabe quais sites recusaram (uma chamada a mais ao modelo, dentro do
orçamento). Uma página que só quebrou (fora do ar, vazia) não troca de site. Os sites que
recusaram nos últimos 30 dias vão no plano seguinte como `refused`, para ele nem tentar, e os
resultados de busca deles são descartados antes de abrir. Caso real de 16/11/2026: tracxn.com e
rocketreach.co responderam 403 e nada mais foi tentado.

## A resposta nunca nega o navegador

Com o navegador configurado, a resposta é conferida em código depois de escrita
([ADR-0013](decisions/0013-nunca-negar-o-navegador.md), `core/conversation/browser_guard.py`).
Frases como "não tenho preços atuais" ou "pesquisar nos sites" fazem a resposta passar pela
mesma checagem curta das regras do dono. Se a reescrita ainda negar, a frase sai e entra uma
frase verdadeira: o que falta, "tentei ver ao vivo agora e não consegui" ou "consigo ver os
preços de agora nos sites". Fica registrado como `browser_denial_fixed` em `decisions`. Na
ligação por voz não há essa conferência.

## Quando desiste, fica registrado

Depois que o planejamento roda, ele nunca desiste em silêncio. Cada saída sem páginas vira uma
ação `browse_skipped` em `decisions`, com o motivo:

| Motivo | O que aconteceu |
| --- | --- |
| `planner_error` | o provedor falhou na chamada do plano |
| `planner_invalid_json` | o plano voltou sem um JSON legível |
| `planner_truncated` | o plano foi cortado no limite de tokens (agora 800) |
| `planner_declined` | o plano achou que não precisava abrir páginas, sem listar o que falta (o `why` dele vai junto) |
| `budget` | um site recusou e o orçamento do dia não deixou planejar outro (vai com `retry: true`) |
| `no_addresses` | o plano não trouxe endereço nem termo de busca que servisse |

Numa pergunta de preço, a resposta recebe um aviso. Se o plano falhou, ele diz que tentou ver ao
vivo e não conseguiu agora. Se o plano disse não, ele pode oferecer olhar nos sites. Nos dois
casos, nunca diz que não tem navegador. Uma mensagem que nem passou pela checagem de palavras
(`candidate()`) não gera registro, senão toda conversa encheria `decisions`.

Caso real de 16/11/2026: "o preço sobe muito se eu pegar aulas?" teve o plano dizendo não, e a
resposta foi "não tenho preços atuais", com o navegador funcionando. O plano agora também trata
preço de algo específico (aula, passeio, ingresso, aluguel) como busca ao vivo.

## Depois de ler preços: a oferta de painel

Quando ele abriu pelo menos uma página com preço (R$, US$, €...), a resposta termina oferecendo
deixar a cotação num painel no Início que confere o preço todo dia. Se você disse um orçamento
("até R$ 6 mil"), a oferta já cita a meta, lida no código a partir das suas palavras. Aprovando, o
painel aparece no Início e é conferido todo dia pelo worker, que também usa este navegador. Ver
[PAINEIS.md](PAINEIS.md).

Todo preço que ele der vem com o site e a hora em que foi lido, mesmo na resposta mais curta. Essa
exigência fica no bloco do navegador, fora do arquivo de estilo que a evolução de código pode
reescrever.

## Fontes sem relação saem antes

As fontes da pesquisa genérica (curiosidade) passam por um filtro barato, sem chamada ao modelo
([`core/research/relevance.py`](../core/research/relevance.py)): fica a fonte cujo título e trecho
dividem pelo menos duas palavras de assunto com a pergunta. As que saem não chegam ao prompt da
resposta, então não podem ser citadas. Caso real (14/11/2026): "Cecília Meireles · Wikipédia" e
"AM Best Affirms Credit Ratings of Chubb Seguros" saíram; a matéria sobre custos no Chile ficou.

## O que ele nunca faz

- Login, cadastro, carrinho, pagamento ou enviar formulário: só abre e lê.
- Contornar CAPTCHA ou "não sou um robô": para e diz que o site pediu verificação.
- Abrir endereço interno: só HTTPS público, checado em cada requisição da página (o documento,
  scripts, redirecionamentos), não só no primeiro endereço.
- Guardar cookies entre sites: cada página abre num contexto novo e limpo. Imagens, vídeos e
  fontes nem carregam.

## Onde roda

Em produção, o Chromium roda no container `browser` do
[`deploy/docker-compose.yml`](../deploy/docker-compose.yml) (`mcr.microsoft.com/playwright:v1.62.0`
com `playwright run-server`): **sem segredos, sem banco e numa rede (`browsing`) só com a API e o worker** (o worker confere os
painéis do Início).
Se uma página maliciosa explorar o Chromium, ela fica presa num container sem nada de valor. A
API só conecta (`VISION_BROWSER_WS_URL=ws://browser:3000/`). A versão do container tem de ser a
mesma do pacote `playwright` do `pyproject.toml`. O container fica limitado a 700 MB de memória (o servidor tem 2 GB, sem swap).

Localmente, `VISION_BROWSER_EXECUTABLE_PATH` aponta para um Chromium e a API o abre ela mesma.
Sem nenhum dos dois, não há páginas ao vivo e ele não diz que consegue.

| Peça | Onde |
|---|---|
| Quando e onde navegar, o bloco para o modelo | [`core/browse.py`](../core/browse.py) |
| Chromium, filtro de requisições, verificação de robô | [`integrations/browser/playwright_browser.py`](../integrations/browser/playwright_browser.py) |
| Tabela `browse_visits` | migração `0023` |

## Limite honesto

Ele lê o que a página mostra em texto. Tabelas montadas em gráfico, preços que só aparecem
depois de clicar ou rolar, e sites que bloqueiam robôs ficam de fora. O Hark faz mais (clica,
preenche, compra com aprovação); aqui é só leitura, de propósito.
