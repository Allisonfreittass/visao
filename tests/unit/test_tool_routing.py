"""Each tool says where it runs. A Mac that is off blocks only the "mac" tools; the owner's own
data comes from a tool or the reply says what is missing, never from a web search."""

import pytest

from core.tools import registry as tools
from core.tools.registry import CLOUD, MAC, MacState

OFF = MacState(paired=True, online=False)
ON = MacState(paired=True, online=True)
NONE = MacState(paired=False, online=False)


def test_every_tool_declares_cloud_or_mac():
    assert {t.runs_on for t in tools.TOOLS.values()} == {CLOUD, MAC}
    assert tools.runs_on("github") == CLOUD
    assert tools.runs_on("google") == CLOUD
    assert tools.runs_on("mac_task") == MAC


@pytest.mark.parametrize("name", [n for n, t in tools.TOOLS.items() if t.runs_on == CLOUD])
def test_a_mac_that_is_off_or_missing_never_blocks_a_cloud_tool(name):
    for mac in (OFF, ON, NONE):
        assert tools.blocked(name, mac) is None


@pytest.mark.parametrize("name", [n for n, t in tools.TOOLS.items() if t.runs_on == MAC])
def test_a_mac_tool_runs_only_with_the_mac_on(name):
    assert tools.blocked(name, ON) is None
    assert tools.blocked(name, OFF) == tools.MAC_OFF
    assert tools.blocked(name, NONE) == tools.MAC_UNPAIRED


def test_the_mac_off_message_is_short_and_says_how_to_unblock():
    assert len(tools.MAC_OFF) < 120 and "desligado" in tools.MAC_OFF and "liga" in tools.MAC_OFF


def test_owner_data_is_read_in_the_owners_words():
    assert tools.owner_data("tem algo novo nos meus e-mails?") == ["email"]
    assert tools.owner_data("o que tem na minha agenda amanhã") == ["calendar"]
    assert tools.owner_data("lista meus repositórios") == ["repos"]
    assert tools.owner_data("acha o PDF nos meus arquivos") == ["files"]
    assert tools.owner_data("o que é um e-mail?") == []


def test_without_a_tool_it_says_exactly_what_is_missing():
    said = tools.missing_access("o que tem no meu gmail?", available={"github"}, mac=ON)
    assert said == "Não tenho acesso ao seu e-mail; precisa conectar o Google em Ajustes."
    assert tools.missing_access("o que tem no meu gmail?", available={"google"}, mac=ON) is None
    said = tools.missing_access("lista meus repositórios", available=set(), mac=ON)
    assert "VISION_GITHUB_TOKEN" in said
    # Files live on the Mac: off, it says so; on, the Mac step handles it.
    assert "desligado" in tools.missing_access("meus arquivos", available=set(), mac=OFF)
    assert tools.missing_access("meus arquivos", available=set(), mac=ON) is None
    assert "parear" in tools.missing_access("meus arquivos", available=set(), mac=NONE)
    block = tools.block("Não tenho acesso ao seu e-mail; precisa conectar o Google em Ajustes.")
    assert "Não pesquise na web" in block
