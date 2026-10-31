# 2026-10-31: Fase 4 (curiosidade e pesquisa)

## Feito

- `WikipediaSearch` (pt), `ResearchService`, `CuriosityEngine` com política determinística,
  migração `0006` (`knowledge_gaps`, `research_sessions`, `research_sources`), integração na rota
  de mensagens, `GET /knowledge-gaps`, `GET /research`, fontes exibidas na interface.
- Testes: 214 no backend (inclui os 4 critérios de aceite com modelo e busca falsos), 22 no
  frontend.

## Avaliação real (`results/curiosity-20261031T115241Z.json` e `...115356Z.json`)

LLM `nvidia/nemotron-3.5-super-120b-a12b` (API da NVIDIA) e Wikipédia real.

| Categoria | Mensagem | Ação | Resultado (revisão humana da resposta) |
|---|---|---|---|
| fato público | "Quem é o atual presidente do Chile?" | WEB_RESEARCH, 3 fontes | citou Boric (2022–2026) com URL e disse que os trechos não informam quem assumiu depois; não inventou |
| fato público | "Quantos habitantes tem Uberlândia segundo o último censo?" | WEB_RESEARCH, 3 fontes | disse que os trechos não trazem o número; não inventou (limitação: só introdução dos artigos) |
| fato público | "Em que ano Alan Turing nasceu?" | IGNORE (no_gap) | respondeu 1912 de conhecimento próprio; correto, pesquisa desnecessária |
| pessoal | "Me ajuda a escolher um presente para a minha mãe?" | 1ª: IGNORE (private_third_party) → **defeito**; após correção: ASK_USER | pediu interesses e orçamento |
| irrelevante | "Hoje acordei com uma preguiça enorme, haha" | IGNORE (no_gap) | resposta social, sem pesquisa |
| inconclusivo | placar de clube de bairro fictício | WEB_RESEARCH, fontes irrelevantes | disse que não tem a informação e que os trechos não tratam do clube; não inventou placar |

Critérios da seção 3: fato público aciona busca e citação ✔ (quando o modelo não tem certeza);
pessoal pergunta ao interlocutor ✔ (após correção); irrelevante não pesquisa ✔; inconclusivo
permanece inconclusivo ✔ na resposta, mas o estado gravado é `RESEARCHED` porque houve fontes
(irrelevantes). Uma execução, um modelo, revisão manual.

## Pendências

- Avaliar a resolução da lacuna (passo 7).
- Trechos além da introdução (ou seções relevantes) para números no corpo dos artigos.
- Segundo provedor para verificação cruzada.
- Medir o impacto da curiosidade na latência dos turnos de voz.
