"""CLI de operação: python -m app.cli <comando>.

Comandos: create-admin, reindex-all, apply-effectiveness.
"""

from __future__ import annotations

import argparse
import getpass
import sys

from app.db import SessionLocal
from app.models import Role
from app.services import search_service, user_service, workflow_service


def cmd_create_admin(args: argparse.Namespace) -> int:
    password = getpass.getpass("Senha do admin (mín. 8 caracteres): ")
    confirm = getpass.getpass("Confirme a senha: ")
    if password != confirm:
        print("Senhas não conferem.", file=sys.stderr)
        return 1
    db = SessionLocal()
    try:
        user = user_service.create_user(
            db,
            None,  # bootstrap: sem ator
            username=args.email,
            email=args.email,
            display_name=args.name,
            role=Role.ADMIN.value,
            password=password,
            must_change_password=False,
        )
        db.commit()
        print(f"Admin criado: {user.display_name} <{user.email}>")
        return 0
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        print(f"Erro: {exc}", file=sys.stderr)
        return 1
    finally:
        db.close()


def cmd_reindex_all(args: argparse.Namespace) -> int:
    db = SessionLocal()
    try:
        count = search_service.reindex_all(db)
        db.commit()
        print(f"Reindexadas {count} políticas.")
        return 0
    finally:
        db.close()


def cmd_apply_effectiveness(args: argparse.Namespace) -> int:
    db = SessionLocal()
    try:
        activated = workflow_service.apply_due_publications(db)
        db.commit()
        print(f"Vigências ativadas: {activated}")
        return 0
    finally:
        db.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="creditops", description="CLI do CreditOps")
    sub = parser.add_subparsers(dest="command", required=True)

    p_admin = sub.add_parser("create-admin", help="cria o primeiro usuário administrador")
    p_admin.add_argument("--email", required=True)
    p_admin.add_argument("--name", required=True)
    p_admin.set_defaults(func=cmd_create_admin)

    p_reindex = sub.add_parser("reindex-all", help="reconstrói o índice de busca FTS5")
    p_reindex.set_defaults(func=cmd_reindex_all)

    p_apply = sub.add_parser(
        "apply-effectiveness", help="ativa vigências agendadas cuja data chegou"
    )
    p_apply.set_defaults(func=cmd_apply_effectiveness)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
