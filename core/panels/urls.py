"""The pages a panel opens each day, built from its spec in code (the same Google Flights and
Google Hotels templates the browse planner uses, docs/NAVEGADOR.md): no planning call needed."""

from urllib.parse import quote

from core.panels.model import Spec

FLIGHTS = "https://www.google.com/travel/flights?q={q}&hl=pt-BR&curr={currency}"
HOTELS = "https://www.google.com/travel/search?q={q}&hl=pt-BR&curr={currency}"


def _place(code: str | None, name: str | None) -> str | None:
    return code or name


def flights(spec: Spec) -> str | None:
    origin = _place(spec.origin_code, spec.origin)
    destination = _place(spec.destination_code, spec.destination)
    if not origin or not destination or spec.depart is None:
        return None
    q = f"Flights to {destination} from {origin} on {spec.depart.isoformat()}"
    if spec.back:
        q += f" through {spec.back.isoformat()}"
    if spec.travelers > 1:
        q += f" for {spec.travelers} adults"
    return FLIGHTS.format(q=quote(q), currency=spec.currency)


def hotels(spec: Spec) -> str | None:
    if spec.depart is None or spec.back is None:
        return None
    kind = "hostels" if any("hostel" in p.lower() for p in spec.preferences) else "hotéis"
    where = " ".join(x for x in (spec.hotel_area, spec.destination) if x)
    q = (
        f"{kind} em {where} {spec.depart:%d/%m/%Y} a {spec.back:%d/%m/%Y} "
        f"para {spec.travelers} {'pessoa' if spec.travelers == 1 else 'pessoas'}"
    )
    return HOTELS.format(q=quote(q), currency=spec.currency)


def for_spec(spec: Spec, max_pages: int) -> list[str]:
    wanted = []
    if "flight" in spec.include:
        wanted.append(flights(spec))
    if "hotel" in spec.include:
        wanted.append(hotels(spec))
    return [u for u in wanted if u][:max_pages]
