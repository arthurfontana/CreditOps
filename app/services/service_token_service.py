"""Tokens de serviço da API de consumo (v2).

O token em claro (`cok_...`) é exibido UMA única vez na criação; o banco
guarda apenas o SHA-256 — vazamento do banco não vaza credenciais.
Revogação é lógica e auditada.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Role, ServiceToken, User
from app.services import audit_service, authz
from app.services.errors import NotFound, ValidationFailed

TOKEN_PREFIX = "cok_"  # identificável em varreduras de segredo


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_token(db: Session, actor: User | None, name: str) -> tuple[ServiceToken, str]:
    """Cria o token e devolve (registro, token em claro — mostrar uma vez).

    actor=None apenas para o bootstrap via CLI (mesma convenção do create-admin).
    """
    if actor is not None:
        authz.ensure_role(actor, Role.ADMIN)
    if not name.strip():
        raise ValidationFailed("nome do token é obrigatório (ex.: sistema consumidor)")
    existing = db.scalars(select(ServiceToken).where(ServiceToken.name == name.strip())).first()
    if existing is not None:
        raise ValidationFailed("já existe token com este nome")
    plaintext = TOKEN_PREFIX + secrets.token_urlsafe(32)
    token = ServiceToken(
        name=name.strip(),
        token_hash=_hash(plaintext),
        created_by=actor.id if actor else None,
    )
    db.add(token)
    db.flush()
    audit_service.record(
        db, actor.id if actor else None, "api.token_created", "service_token", token.id,
        {"name": token.name},
    )
    return token, plaintext


def revoke_token(db: Session, actor: User | None, token_id: str) -> ServiceToken:
    if actor is not None:
        authz.ensure_role(actor, Role.ADMIN)
    token = db.get(ServiceToken, token_id)
    if token is None:
        raise NotFound("token não encontrado")
    if token.revoked_at is not None:
        raise ValidationFailed("token já está revogado")
    token.revoked_at = datetime.utcnow()
    db.flush()
    audit_service.record(
        db, actor.id if actor else None, "api.token_revoked", "service_token", token.id,
        {"name": token.name},
    )
    return token


def list_tokens(db: Session) -> list[ServiceToken]:
    return list(db.scalars(select(ServiceToken).order_by(ServiceToken.created_at)))


def verify_token(db: Session, plaintext: str) -> ServiceToken | None:
    """Valida o token apresentado. Atualiza last_used_at em caso de sucesso."""
    if not plaintext or not plaintext.startswith(TOKEN_PREFIX):
        return None
    token = db.scalars(
        select(ServiceToken).where(ServiceToken.token_hash == _hash(plaintext))
    ).first()
    if token is None or token.revoked_at is not None:
        return None
    token.last_used_at = datetime.utcnow()
    db.flush()
    return token
