"""Where each tool of the turn runs: on the server ("cloud", the Lightsail) or on the Mac ("mac").

The backend lives on the server; the Mac is an optional node for local work. A Mac that is off
blocks only the "mac" tools, with one short sentence; every "cloud" tool runs as usual. Before
this, a paired Mac made a GitHub question wait for it (25/11/2026).

Also the rule for the owner's own data (repositories, email, calendar, files): it comes from a
tool or not at all. Without a tool for it, the reply says in one sentence what is missing and how
to set it up; a web search is never a stand-in for the owner's data.
"""

import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from core.arm import service as arm
from core.memory.text import fold
from infrastructure.database.models import ArmDevice

RunsOn = Literal["cloud", "mac"]
CLOUD: RunsOn = "cloud"
MAC: RunsOn = "mac"


@dataclass(frozen=True)
class Tool:
    name: str
    runs_on: RunsOn
    what: str  # in the owner's words, for the sentence that says what is missing


TOOLS: dict[str, Tool] = {
    t.name: t
    for t in (
        Tool("github", CLOUD, "seus repositórios no GitHub"),
        Tool("google", CLOUD, "seu e-mail e sua agenda"),
        Tool("apps", CLOUD, "seus outros apps"),
        Tool("browser", CLOUD, "sites ao vivo"),
        Tool("research", CLOUD, "pesquisa de fatos públicos"),
        Tool("panels", CLOUD, "painéis de preço"),
        Tool("mac_task", MAC, "trabalho num projeto do Mac"),
        Tool("mac_screen", MAC, "a tela do Mac"),
        Tool("mac_pc", MAC, "mouse e teclado do Mac"),
        Tool("mac_files", MAC, "seus arquivos no Mac"),
    )
}

MAC_OFF = (
    "Seu Mac está desligado agora, então isso não dá para fazer; liga ele com o braço aberto e "
    "me pede de novo."
)
MAC_UNPAIRED = "Não tenho acesso ao seu Mac; precisa parear o braço na página Mac."


@dataclass(frozen=True)
class MacState:
    paired: bool
    online: bool


def mac_state(session: Session, owner_id: uuid.UUID, now: datetime | None = None) -> MacState:
    devices = session.scalars(select(ArmDevice).where(ArmDevice.owner_user_id == owner_id)).all()
    return MacState(paired=bool(devices), online=any(arm.online(d, now) for d in devices))


def runs_on(name: str) -> RunsOn:
    return TOOLS[name].runs_on


def blocked(name: str, mac: MacState) -> str | None:
    """The sentence that says why this tool cannot run now, or None when it can. A "cloud" tool
    is never blocked by the Mac."""
    if runs_on(name) == CLOUD:
        return None
    if not mac.paired:
        return MAC_UNPAIRED
    if not mac.online:
        return MAC_OFF
    return None


# The owner's own data, asked in their words (matched on fold()ed text). Possessive on purpose:
# "o que é um e-mail" is not about the owner's inbox.
_OWNER_DATA: dict[str, re.Pattern[str]] = {
    "email": re.compile(
        r"\b(?:meus? e-?mails?|minha caixa(?: de entrada)?|meu gmail|no gmail|meu inbox)\b"
    ),
    "calendar": re.compile(
        r"\b(?:minha agenda|meu calendario|meus compromissos|minhas reunioes|na agenda|"
        r"google agenda)\b"
    ),
    "files": re.compile(
        r"\b(?:meus arquivos|minhas pastas|meus documentos|minha pasta|no meu (?:mac|computador|"
        r"desktop|notebook))\b"
    ),
    "repos": re.compile(r"\b(?:meus? repos?|meus? repositorios?|meu github|no github)\b"),
}
_FIX = {
    "email": ("google", "Não tenho acesso ao seu e-mail; precisa conectar o Google em Ajustes."),
    "calendar": (
        "google",
        "Não tenho acesso à sua agenda; precisa conectar o Google em Ajustes.",
    ),
    "repos": (
        "github",
        "Não tenho acesso ao seu GitHub; precisa configurar VISION_GITHUB_TOKEN no servidor.",
    ),
    "files": ("mac_files", ""),
}


def owner_data(text: str) -> list[str]:
    """Which of the owner's own data the message asks about ("email", "calendar", "files",
    "repos")."""
    folded = fold(text)
    return [kind for kind, pattern in _OWNER_DATA.items() if pattern.search(folded)]


def missing_access(text: str, *, available: set[str], mac: MacState) -> str | None:
    """One sentence saying what is missing for the owner's data this message asks about, or
    None when a tool covers it (or it asks for none). `available`: the cloud tools on now."""
    for kind in owner_data(text):
        tool, sentence = _FIX[kind]
        if runs_on(tool) == MAC:
            why = blocked(tool, mac)
            if why:
                return why.replace("isso não dá para fazer", "não alcanço seus arquivos")
            continue
        if tool not in available:
            return sentence
    return None


def block(sentence: str) -> str:
    return (
        "A mensagem pede dados da própria pessoa que nenhuma ferramenta sua alcança agora. Diga "
        f"exatamente isto numa frase, com suas palavras: «{sentence}» Não pesquise na web, não "
        "adivinhe e não improvise outro caminho."
    )
