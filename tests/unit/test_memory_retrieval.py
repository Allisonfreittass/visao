import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from core.identity.genesis import run_genesis
from core.memory.retrieval import retrieve
from core.memory.text import tokens
from infrastructure.database.models import Conversation, MemoryCandidate, MemoryRecord, User


def _user(db: Session, email: str) -> User:
    user = User(email=email, password_hash="!")
    db.add(user)
    db.flush()
    return user


def _memory(
    db: Session,
    owner: User,
    content: str,
    memory_type: str = "semantic",
    confidence: float = 0.9,
    created_at: datetime | None = None,
    valid_until: datetime | None = None,
) -> MemoryRecord:
    identity = run_genesis(db).identity
    conversation = Conversation(user_id=owner.id, identity_id=identity.id)
    db.add(conversation)
    db.flush()
    candidate = MemoryCandidate(
        owner_user_id=owner.id,
        conversation_id=conversation.id,
        memory_type=memory_type,
        content=content,
        evidence_message_ids=[],
        proposed_decision="store",
        scores={},
        flags={},
        rationale="",
    )
    db.add(candidate)
    db.flush()
    record = MemoryRecord(
        owner_user_id=owner.id,
        candidate_id=candidate.id,
        memory_type=memory_type,
        content=content,
        confidence=confidence,
        created_at=created_at or datetime.now(UTC),
        valid_until=valid_until,
    )
    db.add(record)
    db.commit()
    return record


def test_tokens_fold_accents_and_drop_stopwords() -> None:
    # "está" folds to "esta", which is a stopword (demonstrative); accents never split tokens.
    assert tokens("Você está usando PostgreSQL? Não, é Postgres.") == {
        "usando",
        "postgresql",
        "postgres",
    }


def test_lexical_match_ranks_first(db: Session) -> None:
    owner = _user(db, "a@exemplo.com")
    _memory(db, owner, "O projeto usa PostgreSQL como banco de dados.")
    _memory(db, owner, "O interlocutor gosta de café.", memory_type="semantic")

    result = retrieve(db, owner.id, "qual banco de dados o projeto usa?")

    assert [m.record.content for m in result] == ["O projeto usa PostgreSQL como banco de dados."]


def test_relational_memories_are_eligible_without_overlap(db: Session) -> None:
    owner = _user(db, "a@exemplo.com")
    _memory(db, owner, "O interlocutor se chama Ana.", memory_type="relational")

    result = retrieve(db, owner.id, "você lembra de mim?")

    assert [m.record.content for m in result] == ["O interlocutor se chama Ana."]


def test_retrieval_never_crosses_owners(db: Session) -> None:
    owner = _user(db, "a@exemplo.com")
    other = _user(db, "b@exemplo.com")
    _memory(db, other, "O interlocutor se chama Bia.", memory_type="relational")

    assert retrieve(db, owner.id, "Bia se chama interlocutor") == []


def test_expired_memories_are_skipped(db: Session) -> None:
    owner = _user(db, "a@exemplo.com")
    _memory(
        db,
        owner,
        "A reunião sobre orçamento é amanhã.",
        valid_until=datetime.now(UTC) - timedelta(days=1),
    )
    assert retrieve(db, owner.id, "reunião orçamento") == []


def test_recency_breaks_ties(db: Session) -> None:
    owner = _user(db, "a@exemplo.com")
    _memory(
        db, owner, "Projeto alfa usa Python.", created_at=datetime.now(UTC) - timedelta(days=90)
    )
    _memory(db, owner, "Projeto beta usa Python.")

    result = retrieve(db, owner.id, "Python")

    assert result[0].record.content == "Projeto beta usa Python."


def test_limit_and_char_budget(db: Session) -> None:
    owner = _user(db, "a@exemplo.com")
    for i in range(8):
        _memory(db, owner, f"Fato numero {i} sobre Python {'x' * 300}")

    assert len(retrieve(db, owner.id, "Python", limit=5)) == 5
    assert len(retrieve(db, owner.id, "Python", max_chars=700)) == 2


def test_unknown_owner_gets_nothing(db: Session) -> None:
    assert retrieve(db, uuid.uuid4(), "qualquer coisa") == []


def test_explicit_recall_can_retrieve_recent_curated_episode_without_shared_words(db):
    owner = _user(db, "a@exemplo.com")
    _memory(db, owner, "No exercício fictício, Maré tinha livros móveis.", memory_type="episodic")
    _memory(
        db,
        owner,
        "Uma hipótese antiga.",
        memory_type="episodic",
        created_at=datetime.now(UTC) - timedelta(days=8),
    )
    result = retrieve(db, owner.id, "Você lembra da conversa anterior?")
    assert [item.record.content for item in result] == [
        "No exercício fictício, Maré tinha livros móveis."
    ]
    assert retrieve(db, owner.id, "Qual a previsão do tempo?") == []
