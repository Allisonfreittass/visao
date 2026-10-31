# ADR-0006: Curiosidade por política determinística e pesquisa na Wikipédia

- Data: 2026-10-31
- Estado: aceita

## Contexto

A seção 3 do master prompt pede curiosidade como mecanismo (detectar lacuna, formular pergunta,
pontuar valor/custo/risco, escolher entre perguntar, pesquisar, adiar, ignorar ou propor meta),
sem prompt de persona, com orçamento e sem pesquisa compulsiva. A seção 4 pede pesquisa com
proveniência, proteção contra SSRF e prompt injection, e honestidade sobre incerteza.

## Decisão

- Mesmo padrão da memória (ADR-0003): **o modelo avalia, regras em código decidem**, com versão
  de política. Pré-filtro determinístico para turnos triviais.
- Avaliação **antes** da resposta, na mesma rota da conversa: a pergunta ou as fontes entram como
  contexto da resposta daquele turno.
- **Wikipédia pt** como primeiro provedor: oficial, grátis, sem chave, host fixo. Provedores
  gerais ficam para quando houver decisão sobre conta/custo.
- Desligado por padrão: custa uma chamada a mais por turno não trivial (latência e cota).

## Alternativas consideradas

- **Deixar o LLM chamar uma ferramenta de busca quando quiser:** mais natural, mas a decisão de
  pesquisar fica no modelo e não em regra auditável; e o provedor ainda não faz tool calling.
- **Avaliar depois da resposta:** não ajudaria a resposta do turno.
- **Raspagem de buscadores (DuckDuckGo, Google):** viola termos de uso e é frágil.

## Consequências

- Turnos de voz ficam mais lentos com curiosidade ligada (uma chamada a mais ao LLM).
- O caso "presente para a minha mãe" mostrou que a regra de terceiros não pode bloquear perguntas
  ao próprio interlocutor; a ordem das regras foi corrigida (política `.2`) com teste de regressão.
- A resolução real da lacuna não é avaliada; `RESEARCHED` significa "houve fontes".
