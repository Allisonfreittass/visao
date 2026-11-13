# Páginas (artefatos)

Peça "monta uma página com o roteiro", "faz um comparativo para eu guardar": a resposta chega na
hora dizendo o que vai ter, e embaixo dela aparece um cartão **Criando a página…**. Quando fica
pronta, o cartão vira **Abrir**: a página abre por cima do chat, com **Copiar link**, **Nova aba** e
**Apagar**. Se você saiu do app enquanto ela era escrita, chega um aviso no celular.

## Como ele decide

Quem decide é a própria resposta: quando a pessoa pede algo para ver ou guardar, ela termina com
uma linha `[[página: Título]]`. O servidor tira essa linha do texto, registra a página como
pendente e, depois de entregar a resposta, faz uma chamada separada e mais longa ao modelo
(`VISION_ARTIFACT_MAX_OUTPUT_TOKENS`, padrão 4096, dentro do teto por chamada do orçamento).

O material dessa chamada é a conversa (com o texto dos arquivos recentes), as pesquisas feitas
nela (título, link, trecho e data de cada fonte) e as páginas que você mandou nesta mensagem. A
instrução manda usar só fatos do material, escrever "a confirmar" no que faltar, marcar
estimativas, dar a data dos preços e listar as fontes.

A página só é tão boa quanto o material: com a pesquisa de hoje (web, Wikipédia, links que você
manda), ele não consulta preços ao vivo em sites de passagem ou hotel. Isso é o navegador na
nuvem, um passo seguinte.

## Segurança

A página é escrita por um modelo a partir de conteúdo de terceiros, então é tratada como não
confiável:

| Proteção | Como |
|---|---|
| Não lê a sua sessão | servida com `Content-Security-Policy: sandbox` sem `allow-same-origin`: origem opaca, sem acesso ao login do app, nem aberta direto numa aba |
| Nada de código | sem `allow-scripts`: nenhum JavaScript roda (interatividade só com `<details>` e âncoras) |
| Não vaza dados | `default-src 'none'`; imagens só de `upload.wikimedia.org` e `images.unsplash.com`, fontes só do Google Fonts, sem formulários; um texto escondido numa página pesquisada não consegue mandar a conversa para outro endereço por uma imagem |
| Link secreto | `/api/p/<token>` com 24 bytes aleatórios; quem tem o link abre. `noindex`, `no-referrer` |
| Some quando você apaga | **Apagar** remove a página e o link para de funcionar na hora |

No Caddy, o `Referrer-Policy` geral só é aplicado quando a resposta não traz o seu
(`?Referrer-Policy`), para a página manter o `no-referrer`.

## Peças

| Peça | Onde |
|---|---|
| Marcador, material, instrução, conferência do HTML | [`core/conversation/artifacts.py`](../core/conversation/artifacts.py) |
| Tabela `artifacts` | migração `0022` |
| `GET /artifacts`, `GET/DELETE /artifacts/{id}`, `GET /p/{token}`, geração em segundo plano | [`apps/api/routes/artifacts.py`](../apps/api/routes/artifacts.py) |
| Cartão e visualizador | `apps/web/src/components/ArtifactCard.tsx` |
