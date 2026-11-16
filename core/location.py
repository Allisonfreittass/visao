"""Where the owner is right now, for "is there a pharmacy open near here?" (docs/LOCALIZACAO.md,
ADR-0020).

The phone sends its position with a message only when the owner turned it on and the message
looks like a question about somewhere nearby; this module decides again, in code, and otherwise
drops it. The position is never stored (not in the message, not in memory, not in the record of
the turn) and never shown to the model: the planner only names what to look for ("farmácia"), and
the map address with the coordinates is built here. The address kept in the record of pages read
has the coordinates removed.
"""

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import quote

from core.memory.text import fold

MAX_ACCURACY_M = 3000  # coarser than this is a city, not "here"
MAX_AGE = timedelta(minutes=30)
ZOOM = 15
MAX_TERMS = 2

# "Perto do Natal", "daqui a pouco" and "perto de terminar" are not about a place.
_NEARBY = re.compile(
    r"\bperto (daqui|de mim|de onde (eu )?(estou|to))\b|\bperto\s*[?!.]*\s*$|\bmais perto\b|"
    r"\baqui perto\b|\bpertinho\b|\bpor aqui\b|\baqui (do lado|na rua|no bairro|na regiao)\b|"
    r"\bmais proxim[oa]s? (daqui|de mim)\b|\b(na|nessa|nesta) (minha )?regiao\b|"
    r"\bao (meu )?redor\b|\bnos arredores\b|\bonde (eu )?(estou|to) agora\b"
)


@dataclass(frozen=True)
class Here:
    lat: float
    lon: float
    accuracy_m: float | None = None


def parse(
    lat: float | None,
    lon: float | None,
    accuracy_m: float | None = None,
    at: datetime | None = None,
    now: datetime | None = None,
) -> Here | None:
    """A usable position, or None: out of range, too coarse or too old."""
    if lat is None or lon is None or not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    if accuracy_m is not None and not (0 <= accuracy_m <= MAX_ACCURACY_M):
        return None
    if at is not None:
        when = at if at.tzinfo else at.replace(tzinfo=UTC)
        if (now or datetime.now(UTC)) - when > MAX_AGE:
            return None
    return Here(lat=float(lat), lon=float(lon), accuracy_m=accuracy_m)


def asks_nearby(text: str) -> bool:
    """The message is about somewhere near the owner right now."""
    return len(text) <= 1000 and bool(_NEARBY.search(fold(text)))


def maps_url(term: str, here: Here) -> str:
    """Google Maps searching `term` around the owner (read live by the browser)."""
    term = " ".join(term.split())[:60]
    return (
        f"https://www.google.com/maps/search/{quote(term)}/"
        f"@{here.lat:.4f},{here.lon:.4f},{ZOOM}z?hl=pt-BR"
    )


_AT = re.compile(r"/@[^/?#]*")
_DATA = re.compile(r"/data=[^?#]*")
_PLACE = re.compile(r"!3d-?\d+(?:\.\d+)?!4d-?\d+(?:\.\d+)?")


def scrub(url: str) -> str:
    """The same address without the owner's coordinates, for what is kept."""
    if "google." not in url or "/maps" not in url:
        return url
    return _PLACE.sub("", _DATA.sub("", _AT.sub("/@local", url)))


def terms(plan: dict) -> list[str]:
    raw = plan.get("nearby")
    items = [raw] if isinstance(raw, str) else raw if isinstance(raw, list) else []
    clean = [" ".join(t.split())[:60] for t in items if isinstance(t, str) and t.strip()]
    return list(dict.fromkeys(clean))[:MAX_TERMS]


def accuracy_words(here: Here) -> str:
    if here.accuracy_m is None:
        return "precisão desconhecida"
    if here.accuracy_m <= 100:
        return "precisão boa (até 100 m)"
    if here.accuracy_m <= 1000:
        return f"precisão de uns {round(here.accuracy_m, -2):.0f} m"
    return "precisão baixa (mais de 1 km)"


def used_block(here: Here, opened: bool) -> str:
    if not opened:
        return (
            "Ela perguntou de um lugar perto dela e mandou a localização do celular, mas o mapa "
            "não abriu agora. Diga isso numa frase e ofereça tentar de novo; não invente lugares."
        )
    return (
        "Ela perguntou de um lugar perto dela e mandou a localização do celular "
        f"({accuracy_words(here)}). O Google Maps foi aberto agora no lugar onde ela está: use só "
        "os lugares lidos ali. Para cada um (até 3, os mais úteis primeiro): nome, endereço, se "
        "está aberto e até quando, e a nota se vier. Nunca diga coordenadas nem que você 'sabe "
        "onde ela está'; diga 'perto de você'."
    )


MISSING_BLOCK = (
    "Ela perguntou de um lugar perto dela, mas a mensagem não veio com a localização do "
    "celular. Peça o bairro ou a cidade numa frase curta, e diga que, se ela quiser, pode ligar "
    "'Usar minha localização' em Ajustes para você achar sozinho da próxima vez."
)
