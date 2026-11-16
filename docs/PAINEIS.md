# Painéis vivos no Início

Depois de uma cotação ao vivo ([NAVEGADOR.md](NAVEGADOR.md)), ele oferece deixar o resultado num
painel no Início que se confere sozinho uma vez por dia e avisa quando algo importante muda
([ADR-0012](decisions/0012-paineis-vivos.md)).

## A oferta (Fase 1)

1. Num turno em que ele abriu pelo menos uma página com preço, a resposta termina com uma pergunta
   curta: "Quer que eu deixe isso num painel no Início e confira o preço todo dia?". Se você citou
   um orçamento ("até R$ 6 mil"), a oferta diz a meta. O valor é lido **no código**, das suas
   palavras, e só com dinheiro à vista (R$, mil, reais); "até agosto" não é meta.
2. Embaixo da resposta aparece o cartão **Painel no Início**, no mesmo padrão das aprovações de
   Mac, email e agenda. Também aparece no Início e é lido em voz na ligação ("pode criar").
3. Aprovam a oferta: um toque em **Aprovar**, ou uma resposta afirmativa curta logo em seguida
   ("pode", "por favor", "quero", "sim, por favor"). Só vale para a oferta feita pela **última**
   resposta: um "pode" sobre outra coisa nunca aprova um cartão antigo. "Não", "agora não" e
   "depois" não aprovam.
4. Uma cotação nova na mesma conversa substitui a oferta anterior (`superseded`).

Aprovar cria o painel na hora, antes da resposta, então "o Combo Santiago está no Início" é
verdade quando é dito. Criar o painel **é aprovar a conferência diária**. Fica na auditoria como
`panel.create`, com `recurring_check: daily` e o `via` (toque, voz ou texto).

| Peça | Onde |
|---|---|
| Quando oferecer, meta, "sim" curto, aceitar | [`core/panels/offers.py`](../core/panels/offers.py) |
| No turno (bloco da oferta, aprovação por texto) | [`core/decision/pipeline.py`](../core/decision/pipeline.py) |
| `GET /panels/offers`, `POST /panels/offers/{id}/{approve,reject}` | [`apps/api/routes/panels.py`](../apps/api/routes/panels.py) |
| Tabela `panel_offers` (com RLS no esquema privado) | migração `0027` |
| Cartão no web e no iPhone | `apps/web/src/App.tsx`, `VisaoKit/Pending.swift` |

## O painel

Desde 16/11/2026, um painel nascido de uma cotação com suposições guarda o que foi suposto
(`spec.assumed`), e o card mostra "Considerando: Guarulhos (GRU)… · 2 adultos". A cotação no chat
já vem com uma tabela de até 5 opções ([COTACAO_TABELA.md](COTACAO_TABELA.md)); a oferta de painel
continua no fim dela.

**No Início** (web e iPhone, cards nativos), cada painel mostra:
- o título e o total para o grupo, em destaque;
- a distância da meta ("R$ 555 acima da meta de R$ 6.000", ou abaixo, em verde);
- a variação desde a conferência anterior;
- cada item (voo, hospedagem) com o provedor, o trecho ou o bairro, as datas, as conexões e o
  preço;
- a hora da última conferência.

Tocar abre o histórico, os links dos sites, **Pausar** e **Apagar**. No lugar de logos, a inicial
do provedor (não há fonte de logos com licença clara). **Criar um novo painel** abre o chat com
"Quero acompanhar…".

**De onde vêm os números:**
- Uma chamada curta extrai os itens das páginas lidas, em JSON validado
  (`core/panels/extract.py`). O código confere cada um:
  - item que não aponta para uma página lida agora é descartado;
  - preço que não aparece no texto daquela página vira "a confirmar".
- O total e a distância da meta são calculados no servidor (`core/panels/model.py`). Faltando um
  preço, o total fica "a confirmar".
- A meta é o seu número, lido nas suas palavras.

**Nunca há preço inventado, nem preço velho como atual:**
- o card diz "conferido hoje, 10:14";
- ou "conferido em 13/11, 10:14 · não conferido hoje", com o motivo.

## Editar pela conversa

"Troca o hotel pra Lastarria", "muda a meta pra R$ 5.500" ou "melhora esse painel" editam o
**mesmo** painel:
- uma chamada curta devolve só o que muda (validado); a meta vem das suas palavras;
- a versão anterior fica em `panel_versions`;
- se a mudança afeta a busca (bairro, datas, pessoas), ele confere os preços de novo na hora;
- a resposta diz em uma ou duas bolhas o que mudou.

## A conferência diária

- **Quando:** o worker roda o job `panel_recheck` às 9h do seu horário, todo dia.
- **O que abre:** Google Voos e Google Hotéis, montados do `spec` em código, sem chamada de
  planejamento (`core/panels/urls.py`).
- **Custo:** uma chamada de extração, que conta como **autônoma** (propósito `panel_recheck`, no
  teto diário de chamadas e de dólares da autonomia).

Quando não confere:

| Situação | O que acontece |
|---|---|
| Autonomia pausada | não confere; o card diz "a autonomia está pausada" |
| Sem orçamento no dia | não confere; o card mantém a última conferência, com a hora |
| Site pediu verificação de robô | "não consegui conferir hoje"; tenta amanhã; nunca contorna |
| Datas da viagem passaram | o painel expira e sai do Início |
| Limite de painéis ativos | aprovar não cria; a resposta diz para pausar ou apagar um |

**Avisos** (Web Push):
- só quando o total ficou abaixo da meta, caiu mais que `VISION_PANEL_ALERT_DROP_PERCENT` (10%)
  ou um item sumiu;
- no máximo um por painel por dia, e fora do horário silencioso.

**Limites** (`.env.example`):
- `VISION_PANELS_MAX_ACTIVE`, padrão 3;
- `VISION_PANEL_MAX_PAGES`, padrão 2 páginas por conferência.

**Rede:** o worker entrou na rede `browsing` para alcançar o container `browser`, que continua sem
segredos e sem banco.

## Sugestões

Sem pendências nem painéis, o Início mostra até 3 sugestões tiradas em código dos títulos das
conversas recentes (sobre viagem ou preço) e dos projetos. Tocar põe a frase no chat. Assuntos
sensíveis (saúde, religião, sexualidade, política, finanças pessoais, documentos) ficam de fora.

## Peças

| Peça | Onde |
|---|---|
| Esquemas, total e meta | [`core/panels/model.py`](../core/panels/model.py) |
| Extração conferida | [`core/panels/extract.py`](../core/panels/extract.py) |
| Criar, conferir, avisar, expirar, cartão | [`core/panels/service.py`](../core/panels/service.py) |
| Editar pela conversa | [`core/panels/editing.py`](../core/panels/editing.py) |
| Sugestões | [`core/panels/suggestions.py`](../core/panels/suggestions.py) |
| `GET/PATCH/DELETE /panels`, `/panels/suggestions` | [`apps/api/routes/panels.py`](../apps/api/routes/panels.py) |
| Job `panel_recheck` | [`apps/worker/handlers.py`](../apps/worker/handlers.py) |
| Tabelas `panels`, `panel_snapshots`, `panel_versions` | migração `0029` |
| Cards no web e no iPhone | `PanelsBoard.tsx`, `PanelCards.swift` |
| Páginas gravadas para os testes | `tests/fixtures/panels/` (texto no formato que o Google mostra, escrito à mão, não baixado) |
