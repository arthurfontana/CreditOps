"""CLI de operação: python -m app.cli <comando>.

Comandos: create-admin, reindex-all, apply-effectiveness,
create-token, list-tokens, revoke-token (API de consumo, v2).
"""

from __future__ import annotations

import argparse
import getpass
import sys

from app.db import SessionLocal
from app.models import Role
from app.services import (
    search_service,
    service_token_service,
    user_service,
    workflow_service,
)


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


def cmd_create_token(args: argparse.Namespace) -> int:
    db = SessionLocal()
    try:
        token, plaintext = service_token_service.create_token(db, None, args.name)
        db.commit()
        print(f"Token de serviço criado: {token.name}")
        print(f"  {plaintext}")
        print("Guarde agora — o token não pode ser recuperado (o banco só tem o hash).")
        return 0
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        print(f"Erro: {exc}", file=sys.stderr)
        return 1
    finally:
        db.close()


def cmd_list_tokens(args: argparse.Namespace) -> int:
    db = SessionLocal()
    try:
        tokens = service_token_service.list_tokens(db)
        if not tokens:
            print("Nenhum token de serviço cadastrado.")
            return 0
        for t in tokens:
            status = "REVOGADO" if t.revoked_at else "ativo"
            last = t.last_used_at.isoformat() if t.last_used_at else "nunca usado"
            print(f"{t.id}  {t.name:30s}  {status:8s}  último uso: {last}")
        return 0
    finally:
        db.close()


def cmd_revoke_token(args: argparse.Namespace) -> int:
    db = SessionLocal()
    try:
        token = service_token_service.revoke_token(db, None, args.token_id)
        db.commit()
        print(f"Token revogado: {token.name}")
        return 0
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        print(f"Erro: {exc}", file=sys.stderr)
        return 1
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

    p_token = sub.add_parser("create-token", help="cria token de serviço da API de consumo")
    p_token.add_argument("--name", required=True, help="nome do sistema consumidor")
    p_token.set_defaults(func=cmd_create_token)

    p_tokens = sub.add_parser("list-tokens", help="lista tokens de serviço")
    p_tokens.set_defaults(func=cmd_list_tokens)

    p_revoke = sub.add_parser("revoke-token", help="revoga um token de serviço")
    p_revoke.add_argument("token_id", help="id do token (ver list-tokens)")
    p_revoke.set_defaults(func=cmd_revoke_token)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
