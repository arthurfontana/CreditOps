"""Usuários: autenticação com bloqueio por força bruta e administração.

Usuários nunca são deletados fisicamente (integridade do histórico) —
apenas desativados logicamente.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.passwords import hash_password, verify_password
from app.config import get_settings
from app.models import Role, User
from app.services import audit_service, authz
from app.services.errors import NotFound, ValidationFailed


class AuthenticationFailed(Exception):
    """Credencial inválida, usuário inativo ou bloqueado. Mensagem única
    para o usuário final (não revelar qual campo falhou)."""


def _credential_ok(user: User, password: str) -> bool:
    """Valida a credencial: SSO (plugin) para usuário sem senha local;
    argon2 local caso contrário (fallback se o diretório cair — wiki 04).

    Import lazy do registry (mesma convenção do notification_service):
    o service não depende do plugin para operar.
    """
    if user.password_hash is None:  # usuário SSO (v2): password_hash nulo
        from app.plugins import registry

        sso = registry.get_plugin("auth")
        if sso is None:
            return False  # sem plugin de SSO, usuário SSO não autentica
        return bool(sso.authenticate(user.username, password))
    return verify_password(user.password_hash, password)


def authenticate(db: Session, username: str, password: str) -> User:
    settings = get_settings()
    user = db.scalars(
        select(User).where((User.username == username) | (User.email == username))
    ).first()
    if user is None:
        audit_service.record(
            db, None, "user.login_failed", "user", None, {"username": username}
        )
        raise AuthenticationFailed("credenciais inválidas")

    now = datetime.utcnow()
    if user.locked_until and user.locked_until > now:
        audit_service.record(
            db, None, "user.login_failed", "user", user.id, {"reason": "locked"}
        )
        raise AuthenticationFailed("conta bloqueada temporariamente; tente mais tarde")
    if not user.is_active:
        audit_service.record(
            db, None, "user.login_failed", "user", user.id, {"reason": "inactive"}
        )
        raise AuthenticationFailed("credenciais inválidas")

    if not _credential_ok(user, password):
        user.failed_login_count += 1
        payload: dict = {"failures": user.failed_login_count}
        if user.failed_login_count >= settings.login_max_failures:
            user.locked_until = now + timedelta(minutes=settings.login_lockout_minutes)
            user.failed_login_count = 0
            payload["locked_until"] = user.locked_until.isoformat()
        db.flush()
        audit_service.record(db, None, "user.login_failed", "user", user.id, payload)
        raise AuthenticationFailed("credenciais inválidas")

    user.failed_login_count = 0
    user.locked_until = None
    db.flush()
    audit_service.record(db, user.id, "user.login", "user", user.id, None)
    return user


def record_logout(db: Session, user: User) -> None:
    audit_service.record(db, user.id, "user.logout", "user", user.id, None)


def create_user(
    db: Session,
    actor: User | None,
    *,
    username: str,
    email: str,
    display_name: str,
    role: str,
    password: str | None,
    area_id: str | None = None,
    is_auditor: bool = False,
    must_change_password: bool = True,
) -> User:
    """actor=None apenas para o bootstrap via CLI create-admin.

    password=None cria usuário SSO (v2): sem senha local (password_hash
    nulo), autentica exclusivamente no diretório via plugin `auth`.
    """
    if actor is not None:
        authz.ensure_role(actor, Role.ADMIN)
    if role not in [r.value for r in Role]:
        raise ValidationFailed(f"papel inválido: {role}")
    if not username.strip() or not email.strip():
        raise ValidationFailed("username e e-mail são obrigatórios")
    if password is not None and len(password) < 8:
        raise ValidationFailed("senha deve ter no mínimo 8 caracteres")
    existing = db.scalars(
        select(User).where((User.username == username) | (User.email == email))
    ).first()
    if existing is not None:
        raise ValidationFailed("já existe usuário com este username ou e-mail")

    user = User(
        username=username.strip(),
        email=email.strip(),
        display_name=display_name.strip() or username.strip(),
        role=role,
        password_hash=hash_password(password) if password is not None else None,
        area_id=area_id,
        is_auditor=is_auditor,
        must_change_password=must_change_password if password is not None else False,
    )
    db.add(user)
    db.flush()
    audit_service.record(
        db,
        actor.id if actor else None,
        "user.created",
        "user",
        user.id,
        {"username": user.username, "role": user.role, "sso": password is None},
    )
    return user


def update_user(
    db: Session,
    actor: User,
    user_id: str,
    *,
    display_name: str | None = None,
    email: str | None = None,
    role: str | None = None,
    area_id: str | None = None,
    is_active: bool | None = None,
    is_auditor: bool | None = None,
) -> User:
    authz.ensure_role(actor, Role.ADMIN)
    user = db.get(User, user_id)
    if user is None:
        raise NotFound("usuário não encontrado")
    fields = {
        "display_name": display_name,
        "email": email,
        "role": role,
        "area_id": area_id,
        "is_active": is_active,
        "is_auditor": is_auditor,
    }
    if role is not None and role not in [r.value for r in Role]:
        raise ValidationFailed(f"papel inválido: {role}")
    changes: dict = {}
    for field, value in fields.items():
        if value is not None and getattr(user, field) != value:
            changes[field] = {"before": getattr(user, field), "after": value}
            setattr(user, field, value)
    db.flush()
    if changes:
        audit_service.record(db, actor.id, "user.updated", "user", user.id, changes)
    return user


def reset_password(db: Session, actor: User, user_id: str) -> str:
    """Gera senha temporária; usuário deve trocá-la no próximo login."""
    authz.ensure_role(actor, Role.ADMIN)
    user = db.get(User, user_id)
    if user is None:
        raise NotFound("usuário não encontrado")
    temp_password = secrets.token_urlsafe(12)
    user.password_hash = hash_password(temp_password)
    user.must_change_password = True
    user.failed_login_count = 0
    user.locked_until = None
    db.flush()
    audit_service.record(db, actor.id, "user.password_reset", "user", user.id, None)
    return temp_password


def change_password(db: Session, user: User, current: str, new: str) -> None:
    if not user.password_hash or not verify_password(user.password_hash, current):
        raise ValidationFailed("senha atual incorreta")
    if len(new) < 8:
        raise ValidationFailed("senha deve ter no mínimo 8 caracteres")
    user.password_hash = hash_password(new)
    user.must_change_password = False
    db.flush()
    audit_service.record(db, user.id, "user.password_changed", "user", user.id, None)
