"""Deterministic gate over the model's memory proposals.

The model decides what is worth proposing; these rules decide what is allowed. They never call a
model, so the same input always gets the same verdict under the same POLICY_VERSION.
"""

import re
from dataclasses import dataclass, field

from core.memory.text import jaccard, tokens

POLICY_VERSION = "2026-10-31.1"

ALLOWED_TYPES = frozenset({"relational", "episodic", "semantic"})
MAX_CONTENT_CHARS = 500
MIN_CONFIDENCE = 0.6
DUPLICATE_THRESHOLD = 0.8

STORED = "STORED"
DISCARDED = "DISCARDED"
REJECTED = "REJECTED_BY_POLICY"

# Human-readable meaning of each reason code (pt-BR, shown in the audit API).
REASONS = {
    "accepted": "Aceito pela política.",
    "model_discard": "O modelo considerou e descartou.",
    "invalid_type": "Tipo de memória não permitido nesta versão.",
    "invalid_content": "Conteúdo vazio ou longo demais.",
    "no_evidence": "Sem mensagens de evidência válidas na conversa.",
    "not_user_stated": "Fato sobre o interlocutor sem evidência numa fala dele.",
    "sensitive": "Dado sensível (saúde, religião, política, finanças etc.).",
    "secret_detected": "Parece conter senha, chave, documento ou cartão.",
    "third_party": "Informação sobre outra pessoa que não o interlocutor.",
    "low_confidence": "Confiança abaixo do mínimo.",
    "duplicate": "Já existe memória equivalente.",
    "instruction_like": "Parece instrução dirigida ao sistema, não informação.",
}

_SECRETS = [
    re.compile(r"\bsk-[A-Za-z0-9_\-]{12,}"),
    # Any mention of credentials is refused outright; false positives are the safe side.
    re.compile(r"(?i)\b(senha|password|api[_ ]?key|chave de api|token de acesso)\b"),
    re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b"),  # CPF
    re.compile(r"\b(?:\d[ -]?){13,19}\b"),  # card-like digit runs
]
_INSTRUCTION_LIKE = re.compile(
    r"(?i)\b(ignore|ignorar|desconsidere|a partir de agora|from now on|you must|"
    r"voc[eê] deve|sempre responda|nunca responda|system prompt|prompt de sistema)\b"
)


@dataclass(frozen=True)
class ProposedMemory:
    memory_type: str
    content: str
    evidence_refs: list[str]
    decision: str
    confidence: float
    sensitive: bool
    third_party: bool


@dataclass(frozen=True)
class EvidenceMessage:
    role: str
    content: str


@dataclass(frozen=True)
class Verdict:
    decision: str
    reason_code: str


@dataclass
class PolicyContext:
    """Evidence available for this batch and memories that already exist for the owner."""

    evidence: dict[str, EvidenceMessage]
    existing_contents: list[str] = field(default_factory=list)
    _accepted_tokens: list[set[str]] = field(default_factory=list)

    def is_duplicate(self, content: str) -> bool:
        candidate = tokens(content)
        known = [tokens(c) for c in self.existing_contents] + self._accepted_tokens
        return any(jaccard(candidate, other) >= DUPLICATE_THRESHOLD for other in known)

    def remember_accepted(self, content: str) -> None:
        self._accepted_tokens.append(tokens(content))


def evaluate(proposal: ProposedMemory, context: PolicyContext) -> Verdict:
    def reject(code: str) -> Verdict:
        return Verdict(REJECTED, code)

    if proposal.decision != "store":
        return Verdict(DISCARDED, "model_discard")
    if proposal.memory_type not in ALLOWED_TYPES:
        return reject("invalid_type")
    content = proposal.content.strip()
    if not content or len(content) > MAX_CONTENT_CHARS:
        return reject("invalid_content")

    evidence = [context.evidence[ref] for ref in proposal.evidence_refs if ref in context.evidence]
    if not evidence or len(evidence) != len(proposal.evidence_refs):
        return reject("no_evidence")
    if proposal.memory_type == "relational" and not any(e.role == "user" for e in evidence):
        return reject("not_user_stated")

    if proposal.sensitive:
        return reject("sensitive")
    if any(p.search(content) for p in _SECRETS):
        return reject("secret_detected")
    if proposal.third_party:
        return reject("third_party")
    if _INSTRUCTION_LIKE.search(content):
        return reject("instruction_like")
    if proposal.confidence < MIN_CONFIDENCE:
        return reject("low_confidence")
    if context.is_duplicate(content):
        return reject("duplicate")

    context.remember_accepted(content)
    return Verdict(STORED, "accepted")
