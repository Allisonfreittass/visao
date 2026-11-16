# ADR-0013: A resposta nunca nega o navegador, conferida em código

- Data: 2026-11-16
- Estado: aceita

## Contexto

Em 16/11/2026, com o navegador funcionando em produção e a linha dele nas capacidades do prompt,
duas respostas sobre a viagem a Santiago negaram o que ele consegue fazer:
- às 11:35, com o plano pedindo a cidade de saída (`browse_needs_details`, com o `ask_block` no
  prompt), a resposta disse "eu te ajudo a organizar o que pedir à agência ou pesquisar nos
  sites", como se a pesquisa fosse tarefa do dono;
- às 11:37, com o plano dizendo não, a resposta disse "Como não tenho preços atuais, não consigo
  dar um número confiável".

Uma linha no prompt não bastou, como já tinha acontecido com as regras do dono ("7 de 8 respostas
quebraram"). Para as regras, a solução foi uma conferência depois da escrita (`_obey_rules`, em
`core/conversation/service.py`), e o stream mostra a versão final com um `replace` (ADR-0011).

## Decisão

- **Padrões em código** (`core/conversation/browser_guard.py`): dois grupos em pt-BR.
  - Negar a capacidade: "não tenho preços atuais", "não tenho acesso a sites", "não consigo
    consultar ao vivo", "não consigo cotar".
  - Empurrar a pesquisa: "pesquisar nos sites", "consulte nos sites", "pedir à agência".

  Os padrões são estreitos de propósito. "O preço pode mudar até você comprar", "confira no site
  antes de pagar", "não consigo reservar" e "tentei ver ao vivo e não consegui" passam.
- **Onde roda:** no `reply()`, logo depois de a resposta ser escrita e dividida em bolhas, no mesmo
  lugar da checagem das regras. Só roda com o navegador configurado e fora da ligação por voz,
  porque na voz a frase é falada enquanto é escrita.
- **Reescrita:** se um padrão bate, a regra `browser_guard.RULE` entra na mesma chamada curta das
  regras do dono, com o mesmo prazo de 4 s. Com regras do dono, não há chamada a mais. Sem regras,
  a chamada só acontece quando um padrão bate, então uma resposta que não nega não custa nada. As
  recusas de sempre continuam: a reescrita não pode trazer link, número, nome ou ação novos.
- **Conferência da reescrita:** o código confere de novo. Se ainda negar, seja porque a checagem
  disse "obedece", falhou ou teve a reescrita recusada, as frases que negam saem e entra uma frase
  verdadeira no lugar, escolhida pelo pipeline:
  - o que falta para buscar, quando o plano listou (`asks_for`);
  - "Tentei ver os preços ao vivo agora e não consegui", quando o plano falhou ou nenhuma página
    abriu;
  - "Consigo ver os preços de agora nos sites: quer que eu olhe?", nos outros casos.

  Tirar uma frase nunca acrescenta uma afirmação.
- **Registro:** o turno ganha a ação `browser_denial_fixed` em `decisions`, com `rewritten` ou
  `stripped`.
- **Stream:** a versão final sai pelo `progress.final`, como a das regras. O cliente recebe um
  `replace` e troca o texto, sem mudar o protocolo.

## Consequências

- A pessoa pode ver por um instante a frase que nega antes do `replace`, como acontece com as
  regras (ADR-0011).
- Na ligação por voz não há conferência. Lá vale só a capacidade no prompt.
- Uma negação dita de outro jeito escapa dos padrões. Cada caso real novo vira um padrão e um
  teste em `tests/unit/test_browser_guard.py`.
- Custo: no máximo uma chamada curta a mais, e só nos turnos em que a resposta negou.
