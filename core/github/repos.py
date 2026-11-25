"""Reading a GitHub question in code: which repository, which period, what is asked.

No model call: "quantos commits teve hoje no visao?" is answered from words, so the turn never
stops to ask "qual repositório?". The owner's nicknames for this project ("o do visao", "visão",
"meu assistente") all mean DEFAULT_REPO, and a message that names no repository means it too.
"""

import re
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from core.memory.text import fold

OWNER = "Allisonfreittass"
DEFAULT_REPO = f"{OWNER}/visao"

# Matched on fold()ed text (no accents, lower case). The project's own names and the ways the
# owner refers to it, including talking to it ("o seu código", "você").
_ALIASES = re.compile(
    r"(?<![\w/-])(?:o do visao|do visao|no visao|visao|meu assistente|o assistente|"
    r"seu (?:repo|repositorio|codigo|projeto)|teu (?:repo|repositorio|codigo|projeto)|"
    r"(?:em|de|no|do) voce)(?![\w-])"
)
_EXPLICIT = re.compile(r"(?<![\w.-])([A-Za-z0-9-]{1,39})/([A-Za-z0-9_.-]{1,100})(?![\w/-])")
_COMMITS = re.compile(r"\bcommits?\b")
_PULLS = re.compile(r"\bprs?\b|\bpull ?requests?\b|\bpulls?\b")
_ISSUES = re.compile(r"\bissues?\b")
_REPOS = re.compile(
    r"\b(?:meus|minhas|quais|todos os|lista\w*|mostra\w*) (?:\w+ ){0,2}(?:repos|repositorios)\b"
    r"|\bmeus repos\b|\bmeus repositorios\b"
)
# Changing something on GitHub is not a read: it goes to the apps or the Mac, with a tap.
_WRITE = re.compile(
    r"\b(?:fa[cz]a?|fazer|cri[ae]r?|abr[ae]r?|commit(?:a|e|ar)|commita|merg(?:e|ea|ear)|"
    r"fech[ae]r?|apag[ae]r?|coment[ae]r?|push(?:a|ar)?|sob[ea]|subir)\b"
)
_LAST_N = re.compile(r"\bult\w* (\d{1,3}) (dias?|horas?|semanas?)\b")

COMMITS, PULLS, ISSUES, REPOS = "commits", "pulls", "issues", "repos"


@dataclass(frozen=True)
class Period:
    since: datetime
    until: datetime
    words: str  # "hoje", "nos últimos 7 dias"


@dataclass(frozen=True)
class Ask:
    kinds: tuple[str, ...]
    repo: str
    period: Period | None  # only for commits


def kinds(text: str) -> tuple[str, ...]:
    """What the message asks to read on GitHub, in a fixed order; () when nothing or a change."""
    folded = fold(text)
    if _WRITE.search(folded) and not re.search(r"\b(?:quant|quais|qual|lista|mostr)", folded):
        return ()
    found = []
    if _COMMITS.search(folded):
        found.append(COMMITS)
    if _PULLS.search(folded):
        found.append(PULLS)
    if _ISSUES.search(folded):
        found.append(ISSUES)
    if _REPOS.search(folded):
        found.append(REPOS)
    return tuple(found)


def explicit(text: str) -> str | None:
    """An "owner/name" written in the message."""
    for owner, name in _EXPLICIT.findall(text):
        if not re.fullmatch(r"\d+", owner):  # "25/11" is a date, not a repository
            return f"{owner}/{name.removesuffix('.git')}"
    return None


def aliased(text: str) -> bool:
    """The message calls this project by one of its nicknames."""
    return bool(_ALIASES.search(fold(text)))


def resolve(text: str, known: list[str] | tuple[str, ...] = ()) -> str:
    """The repository the message is about, as "owner/name". Never asks: an explicit
    "owner/name" wins, then a nickname of this project, then one of the owner's repositories
    named by its short name, and otherwise DEFAULT_REPO."""
    named = explicit(text)
    if named:
        return named
    if aliased(text):
        return DEFAULT_REPO
    folded = fold(text)
    for full in known:
        short = fold(full.split("/")[-1])
        if short and re.search(rf"(?<![\w-]){re.escape(short)}(?![\w-])", folded):
            return full
    return DEFAULT_REPO


def period(text: str, now: datetime, timezone: str) -> Period:
    """The window a commit question means, on the owner's clock. Without one: the last 7 days."""
    try:
        zone = ZoneInfo(timezone)
    except Exception:
        zone = ZoneInfo("UTC")
    here = now.astimezone(zone)
    midnight = datetime.combine(here.date(), time(0), tzinfo=zone)
    folded = fold(text)
    if re.search(r"\bontem\b", folded):
        return Period(midnight - timedelta(days=1), midnight, "ontem")
    if re.search(r"\bhoje\b", folded):
        return Period(midnight, here, "hoje")
    if re.search(r"\bsemana passada\b", folded):
        monday = midnight - timedelta(days=here.weekday())
        return Period(monday - timedelta(days=7), monday, "na semana passada")
    if re.search(r"\b(?:esta|essa|nesta|nessa) semana\b", folded):
        return Period(midnight - timedelta(days=here.weekday()), here, "nesta semana")
    if re.search(r"\bmes passado\b", folded):
        first = midnight.replace(day=1)
        previous = (first - timedelta(days=1)).replace(day=1)
        return Period(previous, first, "no mês passado")
    if re.search(r"\b(?:este|esse|neste|nesse) mes\b", folded):
        return Period(midnight.replace(day=1), here, "neste mês")
    last = _LAST_N.search(folded)
    if last:
        n, unit = int(last.group(1)), last.group(2)
        if unit.startswith("hora"):
            delta, words = timedelta(hours=n), f"nas últimas {n} horas"
        elif unit.startswith("semana"):
            delta, words = timedelta(weeks=n), f"nas últimas {n} semanas"
        else:
            delta, words = timedelta(days=n), f"nos últimos {n} dias"
        return Period(here - delta, here, words)
    if re.search(r"\bultima hora\b", folded):
        return Period(here - timedelta(hours=1), here, "na última hora")
    return Period(here - timedelta(days=7), here, "nos últimos 7 dias")


def read(text: str, now: datetime, timezone: str, known: tuple[str, ...] = ()) -> Ask | None:
    asked = kinds(text)
    if not asked:
        return None
    return Ask(
        kinds=asked,
        repo=resolve(text, known),
        period=period(text, now, timezone) if COMMITS in asked else None,
    )
