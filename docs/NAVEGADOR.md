# Páginas ao vivo (navegador de verdade)

Quando a mensagem é sobre algo que muda com o tempo (passagens, hotéis, preços, disponibilidade,
cotações, horários), ele abre os sites num Chromium de verdade, lê o que eles mostram agora e
responde a partir disso, dizendo em que site viu e de quando é. No chat aparece "Navegando por
google.com" enquanto ele lê, e os sites entram nas fontes como "ao vivo". O que ele leu fica
guardado para as páginas que ele escreve depois ([ARTEFATOS.md](ARTEFATOS.md)).

## Como decide

1. Um filtro de palavras (preço, passagem, voo, hotel, disponível, cotação...) evita gastar uma
   chamada em conversa comum.
2. Uma chamada curta ao modelo planeja até 4 endereços, com modelos que funcionam:
   Google Voos (`/travel/flights?q=Flights to SCL from CNF on 2027-10-01 through 2027-10-08`) e
   Google Hotéis (`/travel/search?q=hotéis em … datas`). Sem endereço certo, ele usa a busca que já
   existe (Tavily/web) para achar páginas. Faltando a data ou a origem, não navega e pergunta.
3. O navegador abre as páginas; o texto vai junto da mensagem como dado de terceiros.

Testado em 13/11/2026: Google Voos e Google Hotéis devolvem preços reais. A busca do Google,
o Google Shopping, o Mercado Livre e o DuckDuckGo recusam navegador automático (pedem
verificação ou respondem 403); ele reporta isso e não insiste.

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
com `playwright run-server`): **sem segredos, sem banco e numa rede (`browsing`) só com a API**.
Se uma página maliciosa explorar o Chromium, ela fica presa num container sem nada de valor. A
API só conecta (`VISION_BROWSER_WS_URL=ws://browser:3000/`). A versão do container tem de ser a
mesma do pacote `playwright` do `pyproject.toml`. O container usa até 1 GB de memória.

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
