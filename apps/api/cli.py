"""Administrative commands. Usage: python -m apps.api.cli <command> [options]"""

import argparse
import getpass
import json
import sys

from email_validator import EmailNotValidError, validate_email
from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.security import hash_password
from core.identity.genesis import get_genesis_record, get_identity, run_genesis
from infrastructure.database.audit import record_audit
from infrastructure.database.models import AgentIdentity, IdentityVersion, User
from infrastructure.database.session import get_sessionmaker

MIN_PASSWORD_LENGTH = 12


def create_user(session: Session, email: str, password: str) -> User:
    normalized = validate_email(email, check_deliverability=False).normalized.lower()
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f"senha precisa ter pelo menos {MIN_PASSWORD_LENGTH} caracteres")
    if session.scalar(select(User).where(User.email == normalized)) is not None:
        raise ValueError("já existe usuário com esse email")
    user = User(email=normalized, password_hash=hash_password(password))
    session.add(user)
    session.flush()
    record_audit(session, "user.create", "success", actor_user_id=user.id, details={"via": "cli"})
    session.commit()
    return user


def _describe(identity: AgentIdentity, record: IdentityVersion) -> str:
    return json.dumps(
        {
            "internal_id": str(identity.id),
            "chosen_name": identity.chosen_name,
            "genesis_version": record.genesis_version,
            "config_hash": record.config_hash,
            "components": record.components,
            "permissions": record.permissions,
            "created_at": record.created_at.isoformat(),
        },
        ensure_ascii=False,
        indent=2,
    )


def _voice_deliberation() -> int:
    from apps.api.llm import build_llm_provider, missing_llm_settings
    from apps.api.settings import get_settings
    from core.identity.voice import (
        DeliberationOutputError,
        deliberate_voice,
        resolve_voice,
    )
    from integrations.llm.base import LLMError
    from integrations.tts.catalog import approved_voices

    settings = get_settings()
    provider = build_llm_provider(settings)
    if provider is None:
        print("LLM não configurado. Faltam: " + ", ".join(missing_llm_settings(settings)))
        return 1
    approved = approved_voices(settings.tts_approved_voices)
    if not approved:
        print("Nenhuma voz aprovada (VISION_TTS_APPROVED_VOICES).")
        return 1
    with get_sessionmaker()() as session:
        identity = get_identity(session)
        if identity is None:
            print("Genesis ainda não executado.")
            return 1
        try:
            event = deliberate_voice(
                session,
                identity,
                approved,
                provider,
                max_output_tokens=settings.llm_curation_max_output_tokens,
            )
        except (LLMError, DeliberationOutputError, ValueError) as exc:
            print(f"Deliberação sem decisão registrada: {exc}")
            return 1
        resolved = resolve_voice(identity, approved)
        print(f"Decisão: {event.event_type} | voz: {event.new_voice or '-'}")
        print(f"Justificativa: {event.rationale_summary}")
        print(f"Modelo: {event.model_provider} / {event.model_version}")
        print(f"Voz em uso: {resolved.spec.id if resolved.spec else '-'} ({resolved.source})")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m apps.api.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create-user", help="cria um usuário (senha pedida no terminal)")
    create.add_argument("--email", required=True)
    genesis = sub.add_parser("genesis", help="cria a identidade mínima do agente, se não existir")
    genesis.add_argument("--status", action="store_true", help="só mostra o registro atual")
    sub.add_parser(
        "voice-deliberation",
        help="apresenta ao agente as vozes aprovadas; ele escolhe, adia ou recusa",
    )
    sub.add_parser(
        "webpush-keys",
        help="gera o par VAPID dos avisos push (cole no .env ou nos segredos da nuvem)",
    )
    args = parser.parse_args(argv)

    if args.command == "webpush-keys":
        from integrations.push.webpush import generate_vapid_keys

        public, private = generate_vapid_keys()
        print(f"VISION_WEBPUSH_PUBLIC_KEY={public}")
        print(f"VISION_WEBPUSH_PRIVATE_KEY={private}")
        print("VISION_WEBPUSH_SUBJECT=https://endereco-do-app (ou mailto:contato)")
        return 0

    if args.command == "voice-deliberation":
        return _voice_deliberation()

    if args.command == "genesis":
        with get_sessionmaker()() as session:
            if args.status:
                identity = get_identity(session)
                if identity is None:
                    print("Genesis ainda não executado.")
                    return 0
                print(_describe(identity, get_genesis_record(session, identity)))
                return 0
            result = run_genesis(session)
            if result.created:
                print("Genesis concluído.")
            else:
                print("Identidade já existe; nada foi alterado.")
            print(_describe(result.identity, result.genesis_record))
        return 0

    if args.command == "create-user":
        password = getpass.getpass("Senha: ")
        if password != getpass.getpass("Confirme: "):
            print("As senhas não conferem.", file=sys.stderr)
            return 1
        with get_sessionmaker()() as session:
            try:
                user = create_user(session, args.email, password)
            except (ValueError, EmailNotValidError) as exc:
                print(f"Erro: {exc}", file=sys.stderr)
                return 1
        print(f"Usuário criado: {user.id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
