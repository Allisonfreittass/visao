# Tabela de opções da cotação: o formato

Depois de uma cotação ao vivo com preços conferidos, a resposta do Visão leva uma tabela de
opções ([ADR-0015](decisions/0015-cotacao-com-suposicoes-e-tabela.md)). Este documento é o
contrato para os clientes. O web já desenha a tabela
(`apps/web/src/components/QuoteTable.tsx`). O app do iPhone (`apps/ios`) implementa depois,
pelo agente do Mac.

## Onde vem

Num campo novo da mensagem, `quote_table`, em `MessageOut`. Ele chega:
- em `POST /conversations/{id}/messages`, em `assistant_message`;
- em `GET /conversations/{id}/messages`;
- no evento `done` do stream (`GET /conversations/{id}/stream`, ADR-0011).

Mensagens sem tabela têm `quote_table: null`, ou o campo simplesmente não vem num servidor
antigo.

## O texto de reserva (por que um app antigo não quebra)

O texto da tabela também é **a última bolha** de `parts` e o **fim** de `content`:

```json
{
  "content": "Considerei saída de Guarulhos, para dois. Quer ajustar?\n\nSantiago, 10 noites em agosto de 2027 · 2 pessoas\n1. JetSMART + Hostel Providencia · 14–24 ago · R$ 3.300\n...",
  "parts": [
    "Considerei saída de Guarulhos, para dois. Quer ajustar?",
    "Santiago, 10 noites em agosto de 2027 · 2 pessoas\n1. JetSMART + Hostel Providencia · 14–24 ago · R$ 3.300\n..."
  ],
  "quote_table": { "...": "..." }
}
```

- **Um app que não conhece `quote_table`** mostra as bolhas como sempre, e a última é a tabela
  em texto, uma linha por opção.
- **Um app que conhece** procura em `parts` a bolha igual a `quote_table.text` (de trás para
  frente) e desenha a tabela no lugar dela. As outras bolhas ficam como estão.
- **Na ligação por voz** não vem tabela.

## O objeto

```json
{
  "version": 1,
  "title": "Santiago, 10 noites em agosto de 2027",
  "travelers": 2,
  "rows": [
    {
      "option": "JetSMART + Hostel Providencia",
      "dates": "14–24 ago",
      "total": "3300.00",
      "total_text": "R$ 3.300",
      "currency": "BRL",
      "sites": ["google.com"]
    }
  ],
  "notes": [
    "Saindo em 14–24 ago, o voo cai para R$ 3.400.",
    "Fica de fora do total: bagagem de mão (JetSMART) e o deslocamento do sul de Minas até GRU."
  ],
  "assumed": { "origem": "Guarulhos (GRU), saindo do sul de Minas", "pessoas": "2 adultos" },
  "text": "Santiago, 10 noites em agosto de 2027 · 2 pessoas\n1. ..."
}
```

| Campo | O que é |
| --- | --- |
| `version` | `1`. Um campo novo no futuro sobe a versão, e um cliente que não a conhece usa `text`. |
| `title` | O que foi cotado, curto, sem preço. |
| `travelers` | Para quantas pessoas é o total. |
| `rows` | De 1 a 5 opções, da mais barata à mais cara. A primeira é a mais barata. |
| `rows[].option` | Companhia + hospedagem, ou só o item. |
| `rows[].dates` | Como a página mostrou ("14–24 ago"). Pode vir vazio. |
| `rows[].total` | O total do grupo, como decimal em texto, para ordenar ou comparar. |
| `rows[].total_text` | O mesmo total pronto para mostrar ("R$ 3.300"). Mostre este. |
| `rows[].sites` | De onde vieram os preços dessa linha. |
| `notes` | No máximo duas frases prontas: uma de datas vizinhas e uma do que o total não inclui. |
| `assumed` | O que a cotação supôs em vez de perguntar. Pode vir vazio. |
| `text` | A mesma tabela em texto puro: o texto de reserva. |

## Regras para quem desenha

- **Números só do servidor.** Não some, não converta e não recalcule. Use `total_text`.
- **Sem HTML.** Todos os campos são texto puro: desenhe como texto, nunca como marcação.
- **Legível no iPhone:** três colunas (Opção, Datas, Total), com o total alinhado à direita e em
  números tabulares, e a primeira linha em destaque. As `notes` vão abaixo da tabela, em texto
  menor. O web mostra as suposições numa linha "Considerando: …".
- **Nunca um botão de reservar ou comprar.** O Visão só avisa e manda o link do site.
- **Fontes:** os preços continuam com o site e a hora na pílula de fontes da mensagem, como já é.
