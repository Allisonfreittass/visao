"""Static scan: no code, prompt or seed imposes a name or persona on the agent.

Heuristic by nature: it catches the obvious ways of imposing identity (calling the agent VISÃO,
assigning a literal name, prompting it to pick a name, declaring persona traits). New prompt
files must live under the scanned directories so this keeps covering them.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCANNED_DIRS = ("apps", "core", "integrations", "infrastructure", "migrations")
SCANNED_SUFFIXES = {".py", ".txt", ".md", ".yaml", ".yml", ".json", ".jinja", ".j2", ".toml"}

FORBIDDEN = {
    "project codename used as the agent's name": re.compile(
        r"(?i)(voc[eê]\s+(é|e|se\s+chama)|you\s+are|your\s+name\s+is|seu\s+nome\s+[eé]|"
        r"meu\s+nome\s+[eé]|eu\s+sou|i\s+am|call\s+yourself)\W+(o\s+|a\s+)?vis(ã|a)o\b|"
        r"\bvision\b\s+(assistant|agent)"
    ),
    "literal name assigned to chosen_name": re.compile(r"chosen_name\s*[:=]\s*['\"]"),
    "prompt pushing a name choice": re.compile(
        r"(?i)\b(escolha|escolher|choose|pick)\s+(um|a|o\s+seu|seu|your)\s+(novo\s+)?(nome|name)\b"
    ),
    "declared persona trait": re.compile(
        r"(?i)(voc[eê]\s+é|you\s+are)\s+(muito\s+|very\s+)?(curios[oa]|engraçad[oa]|sério|séria|"
        r"calm[oa]|sarcástic[oa]|carinhos[oa]|curious|funny|calm|sarcastic|friendly|caring)\b"
    ),
}


def _scanned_files() -> list[Path]:
    return [
        path
        for directory in SCANNED_DIRS
        for path in (ROOT / directory).rglob("*")
        if path.is_file() and path.suffix in SCANNED_SUFFIXES
    ]


def test_scan_covers_files() -> None:
    assert len(_scanned_files()) > 10


@pytest.mark.parametrize("rule", sorted(FORBIDDEN))
def test_no_imposed_identity(rule: str) -> None:
    pattern = FORBIDDEN[rule]
    hits = [
        f"{path.relative_to(ROOT)}:{lineno}: {line.strip()}"
        for path in _scanned_files()
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if pattern.search(line)
    ]
    assert hits == [], f"{rule}:\n" + "\n".join(hits)


@pytest.mark.parametrize(
    ("rule", "sample"),
    [
        ("project codename used as the agent's name", "Você é o VISÃO, um assistente"),
        ("project codename used as the agent's name", "You are Vision assistant"),
        ("literal name assigned to chosen_name", 'chosen_name = "Jarvis"'),
        ("prompt pushing a name choice", "Agora escolha um nome para você"),
        ("declared persona trait", "You are curious and witty"),
    ],
)
def test_patterns_detect_known_violations(rule: str, sample: str) -> None:
    assert FORBIDDEN[rule].search(sample)
