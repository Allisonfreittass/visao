# Painéis vivos no Início

Depois de uma cotação ao vivo ([NAVEGADOR.md](NAVEGADOR.md)), ele oferece deixar o resultado
num painel no Início que se atualiza sozinho. A oferta já existe (Fase 1); o painel nativo, a
recotação diária e os avisos são a Fase 3.

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

Enquanto o painel nativo não existe, aprovar escreve uma **página** ([ARTEFATOS.md](ARTEFATOS.md))
com o título da cotação ("Combo Santiago"), feita a partir das páginas lidas ao vivo nessa
conversa. Cada decisão fica na auditoria (`panel_offer.approve` / `panel_offer.reject`, com `via`
toque, voz ou texto).

| Peça | Onde |
|---|---|
| Quando oferecer, meta, "sim" curto, aceitar | [`core/panels/offers.py`](../core/panels/offers.py) |
| No turno (bloco da oferta, aprovação por texto) | [`core/decision/pipeline.py`](../core/decision/pipeline.py) |
| `GET /panels/offers`, `POST /panels/offers/{id}/{approve,reject}` | [`apps/api/routes/panels.py`](../apps/api/routes/panels.py) |
| Tabela `panel_offers` (com RLS no esquema privado) | migração `0027` |
| Cartão no web e no iPhone | `apps/web/src/App.tsx`, `VisaoKit/Pending.swift` |

## O painel vivo (Fase 3, ainda não feito)

Card nativo no Início com o total em destaque, a distância da meta, os itens (voo, hospedagem),
a hora da última conferência e a variação. Recotação uma vez por dia no worker, dentro do
orçamento e das regras de autonomia, e aviso só em mudança relevante. Nenhum preço sem uma página
lida que o sustente. Detalhes no ADR da Fase 3.
