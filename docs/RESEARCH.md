# Pesquisa na internet

> Estado: **Fase 4**: um provedor, Wikipédia em português (`integrations/search/wikipedia.py`),
> usado pelo `CuriosityEngine` ([CURIOSITY.md](CURIOSITY.md)).

## Provedor atual

| | |
|---|---|
| Fonte | API oficial `https://pt.wikipedia.org/w/api.php` (busca + introdução do artigo) |
| Custo | grátis, sem chave |
| Identificação | `User-Agent` descritivo, conforme a política da Wikimedia |
| Limites | timeout 10 s, resposta ≤ 2 MB, até 3 resultados, cache de 1 h por consulta |
| Proveniência guardada | URL, título, trecho (≤ 700 caracteres), data da última alteração da página, horário da coleta, posição no ranking |

## Segurança

- **Sem SSRF:** só o host fixo da API é contatado; nenhuma URL vinda de página ou de modelo é
  aberta; redirecionamentos não são seguidos; resultados com URL fora de `pt.wikipedia.org` são
  descartados.
- **Conteúdo é dado, não instrução:** os trechos entram no prompt marcados como dados recuperados,
  com caracteres de controle removidos; nada é executado.
- **Nada vira memória automaticamente:** resultados ficam em `research_sources`; só a curadoria
  (Fase 3) pode transformar algo em memória.
- **Privacidade:** a política não pesquisa pessoas privadas que não sejam o interlocutor.

## Epistemologia

- Resposta deve distinguir o que a fonte diz do que permanece incerto ("pesquisei e encontrei
  X, mas Y permanece incerto").
- Uma fonte enciclopédica única não é certeza; fatos sensíveis a tempo podem estar desatualizados
  (a data de alteração da página vai junto ao trecho).
- Sem fontes relevantes: dizer que não encontrou; nunca inventar.

## Limitações conhecidas

- Só a introdução dos artigos: números que ficam no corpo (ex.: população de um município) não
  chegam ao modelo.
- Uma só fonte; não há verificação cruzada por fontes independentes.
- Sem notícias recentes nem páginas fora da Wikipédia. Provedores gerais (Brave Search, Tavily
  etc.) exigem conta e chave; a interface `SearchProvider` já permite acrescentá-los.
