"""Administrative commands. Usage: python -m apps.api.cli <command> [options]"""

import argparse
import getpass
import sys

from email_validator import EmailNotValidError, validate_email
from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.security import hash_password
from infrastructure.database.audit import record_audit
from infrastructure.database.models import User
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m apps.api.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create-user", help="cria um usuário (senha pedida no terminal)")
    create.add_argument("--email", required=True)
    args = parser.parse_args(argv)

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
