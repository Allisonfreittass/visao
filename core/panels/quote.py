"""The table of options under a live quote (docs/decisions/0015).

Hark, on the same trip, answered with 5 combos (airline + stay + dates + total for the couple),
from the cheapest, a hidden cost ("JetSMART não inclui mala de mão") and a neighbor date ("saindo
em 11/08, o voo cai para…"). Here the same comes out of the items the extraction already checked
against the pages (core/panels/extract.py): every price is in a page read now, the totals are
summed in code, and the two sentences are written in code from what the pages said. The model
writes no number of the table.

The table travels as data (`messages.quote_table`) for the apps that know it, and as plain text
(`text`, its own bubble at the end of the reply) for the ones that do not: an app already
installed shows the text and never breaks. Format: docs/COTACAO_TABELA.md.
"""

import re
from datetime import date
from decimal import Decimal

from core.panels.model import Item, Spec
from core.panels.offers import money
from core.travel_origins import Home

MAX_ROWS = 5
# A window this much cheaper than the dearest one earns the neighbor-date sentence.
NEIGHBOR_SHARE = Decimal("0.90")
MONTHS = (
    "janeiro fevereiro março abril maio junho julho agosto setembro outubro novembro dezembro"
).split()
_DIGITS = re.compile(r"\d+")
_IATA = re.compile(r"\b[A-Z]{3}\b")
_PEOPLE = re.compile(r"\d+")


def _window(item: Item) -> tuple[str, ...]:
    return tuple(_DIGITS.findall(item.dates))


def travelers(spec: Spec | None, assumed: dict[str, str]) -> int:
    """The party: what the extraction read in the conversation, else what the plan assumed."""
    if spec is not None and spec.travelers > 1:
        return spec.travelers
    found = _PEOPLE.search(assumed.get("pessoas", ""))
    if found and 1 <= int(found.group(0)) <= 9:
        return int(found.group(0))
    return spec.travelers if spec is not None else 2


def title(spec: Spec | None, hint: str) -> str:
    """ "Santiago, 10 noites em agosto de 2027", or the planner's short name."""
    if spec is None or not spec.destination:
        return hint or "Cotação"
    parts = [spec.destination]
    nights = spec.nights()
    if nights:
        parts.append(f"{nights} noites" + (f" em {_month(spec.depart)}" if spec.depart else ""))
    elif spec.depart:
        parts.append(_month(spec.depart))
    return ", ".join(parts)


def _month(day: date) -> str:
    return f"{MONTHS[day.month - 1]} de {day.year}"


def _rows(items: list[Item], party: int) -> list[dict]:
    priced = [i for i in items if i.cost(party) is not None]
    if not priced:
        return []
    currency = priced[0].currency
    priced = [i for i in priced if i.currency == currency]
    flights = [i for i in priced if i.kind == "flight"]
    stays = [i for i in priced if i.kind == "hotel"]
    one_window = len({_window(f) for f in flights}) <= 1
    rows: list[tuple[Decimal, str, str, list[Item]]] = []
    if flights and stays:
        for flight in flights:
            for stay in stays:
                fw, sw = _window(flight), _window(stay)
                if fw and sw and fw != sw and not one_window:
                    continue
                cost = flight.cost(party) + stay.cost(party)  # type: ignore[operator]
                option = f"{flight.provider} + {stay.provider}"
                rows.append((cost, option, flight.dates or stay.dates, [flight, stay]))
    else:
        for item in flights or stays:
            option = item.provider + (f" ({item.where})" if item.where else "")
            rows.append((item.cost(party), option, item.dates, [item]))  # type: ignore[arg-type]
    rows.sort(key=lambda r: r[0])
    seen: set[tuple[str, str]] = set()
    table = []
    for cost, option, dates, sources in rows:
        if (option, dates) in seen:
            continue
        seen.add((option, dates))
        table.append(
            {
                "option": option[:120],
                "dates": dates[:60],
                "total": str(cost.quantize(Decimal("0.01"))),
                "total_text": money(cost),
                "currency": currency,
                "sites": list(dict.fromkeys(s.site for s in sources if s.site)),
            }
        )
        if len(table) == MAX_ROWS:
            break
    return table


def neighbor_sentence(items: list[Item], party: int) -> str:
    """One sentence when one of the windows tried is clearly cheaper for the flight."""
    cheapest: dict[tuple[str, ...], Item] = {}
    for flight in (i for i in items if i.kind == "flight" and i.cost(party) is not None):
        key = _window(flight)
        if key not in cheapest or flight.cost(party) < cheapest[key].cost(party):  # type: ignore[operator]
            cheapest[key] = flight
    if len(cheapest) < 2:
        return ""
    ordered = sorted(cheapest.values(), key=lambda f: f.cost(party))  # type: ignore[arg-type, return-value]
    low, high = ordered[0], ordered[-1]
    if low.cost(party) > high.cost(party) * NEIGHBOR_SHARE:  # type: ignore[operator]
        return ""
    return f"Saindo em {low.dates}, o voo cai para {money(low.cost(party))}."  # type: ignore[arg-type]


def costs_sentence(items: list[Item], assumed: dict[str, str], home: Home | None) -> str:
    """One sentence with what the totals leave out: what the pages said, and the trip to the
    airport when the origin was assumed from where the owner lives. Nothing else."""
    left_out = list(
        dict.fromkeys(
            f"{i.not_included} ({i.provider})" for i in items if i.not_included and i.provider
        )
    )[:2]
    code = _IATA.search(assumed.get("origem", ""))
    if home is not None and code and code.group(0) in home.airports:
        left_out.append(f"o deslocamento do {home.label} até {code.group(0)}")
    if not left_out:
        return ""
    joined = left_out[0] if len(left_out) == 1 else ", ".join(left_out[:-1]) + " e " + left_out[-1]
    return f"Fica de fora do total: {joined}."


def build(
    items: list[Item],
    spec: Spec | None,
    *,
    hint: str = "",
    assumed: dict[str, str] | None = None,
    home: Home | None = None,
) -> dict | None:
    """The table, or None when no option has a price a page shows."""
    assumed = assumed or {}
    party = travelers(spec, assumed)
    rows = _rows(items, party)
    if not rows:
        return None
    notes = [
        n for n in (neighbor_sentence(items, party), costs_sentence(items, assumed, home)) if n
    ]
    head = f"{title(spec, hint)} · {party} {'pessoa' if party == 1 else 'pessoas'}"
    lines = [head]
    lines += [
        f"{n}. {r['option']} · {r['dates']} · {r['total_text']}"
        if r["dates"]
        else f"{n}. {r['option']} · {r['total_text']}"
        for n, r in enumerate(rows, 1)
    ]
    lines += notes
    return {
        "version": 1,
        "title": title(spec, hint),
        "travelers": party,
        "rows": rows,
        "notes": notes,
        "assumed": assumed,
        "text": "\n".join(lines),
    }


def reply_block(table: dict) -> str:
    """For the reply: the table goes below it, so the reply only introduces it."""
    cheapest = table["rows"][0]
    return (
        f"Abaixo da sua resposta vai uma tabela com {len(table['rows'])} opção(ões) desta "
        f"cotação, da mais barata à mais cara, montada a partir das páginas lidas (a mais barata: "
        f"{cheapest['option']}, {cheapest['total_text']} no total para {table['travelers']}). Não "
        "repita a tabela nem as frases de datas e custos que vão com ela. Na resposta: no máximo "
        "duas frases curtas antes da tabela, e nunca ofereça reservar ou comprar (você só avisa e "
        "manda o link do site)."
    )
