"""Autenticação, bloqueio por força bruta, sessões e RBAC."""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from app.auth.sessions import create_session_token, read_session_token
from app.models import AuditLog, Role
from app.services import user_service
from app.services.authz import ensure_role
from app.services.errors import PermissionDenied, ValidationFailed
from app.services.user_service import AuthenticationFailed
from tests.conftest import login_as


def test_login_ok(db, author):
    user = user_service.authenticate(db, "autor", "senha-forte-123")
    assert user.id == author.id
    actions = [a.action for a in db.scalars(select(AuditLog))]
    assert "user.login" in actions


def test_login_by_email(db, author):
    user = user_service.authenticate(db, "autor@example.com", "senha-forte-123")
    assert user.id == author.id


def test_wrong_password_fails_and_audits(db, author):
    with pytest.raises(AuthenticationFailed):
        user_service.authenticate(db, "autor", "errada")
    actions = [a.action for a in db.scalars(select(AuditLog))]
    assert "user.login_failed" in actions


def test_lockout_after_5_failures(db, author):
    for _ in range(5):
        with pytest.raises(AuthenticationFailed):
            user_service.authenticate(db, "autor", "errada")
    db.refresh(author)
    assert author.locked_until is not None
    # mesmo a senha certa falha enquanto bloqueado
    with pytest.raises(AuthenticationFailed, match="bloqueada"):
        user_service.authenticate(db, "autor", "senha-forte-123")
    # após o período, volta a funcionar
    author.locked_until = datetime.utcnow() - timedelta(minutes=1)
    db.commit()
    assert user_service.authenticate(db, "autor", "senha-forte-123").id == author.id


def test_inactive_user_cannot_login(db, author):
    author.is_active = False
    db.commit()
    with pytest.raises(AuthenticationFailed):
        user_service.authenticate(db, "autor", "senha-forte-123")


def test_session_token_roundtrip(author):
    token = create_session_token(author.id)
    assert read_session_token(token) == author.id
    assert read_session_token("token-invalido") is None
    assert read_session_token(None) is None


def test_ensure_role_denies_wrong_role(reader, approver):
    with pytest.raises(PermissionDenied):
        ensure_role(reader, Role.APPROVER)
    ensure_role(approver, Role.APPROVER)  # não levanta


def test_admin_is_not_wildcard(admin):
    """Admin não participa do workflow: papel precisa estar explícito."""
    with pytest.raises(PermissionDenied):
        ensure_role(admin, Role.APPROVER)


def test_user_never_deleted_only_deactivated(db, admin, author):
    user_service.update_user(db, admin, author.id, is_active=False)
    db.commit()
    db.refresh(author)
    assert author.is_active is False  # linha continua existindo


def test_update_user_audits_before_after(db, admin, author):
    user_service.update_user(db, admin, author.id, display_name="Novo Nome")
    entries = [
        e for e in db.scalars(select(AuditLog)) if e.action == "user.updated"
    ]
    assert entries
    assert "Novo Nome" in (entries[-1].payload or "")
    assert "senha" not in (entries[-1].payload or "").lower()


def test_reset_password_forces_change(db, admin, author):
    temp = user_service.reset_password(db, admin, author.id)
    db.commit()
    user = user_service.authenticate(db, "autor", temp)
    assert user.must_change_password is True


def test_create_user_requires_admin(db, author):
    with pytest.raises(PermissionDenied):
        user_service.create_user(
            db, author,
            username="x", email="x@x.com", display_name="X",
            role="reader", password="12345678",
        )


def test_short_password_rejected(db, admin):
    with pytest.raises(ValidationFailed):
        user_service.create_user(
            db, admin,
            username="x", email="x@x.com", display_name="X",
            role="reader", password="curta",
        )


def test_web_login_flow(client, db, author):
    response = client.post(
        "/login", data={"username": "autor", "password": "senha-forte-123", "next": "/"}
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/"
    assert "creditops_session" in response.cookies


def test_web_protected_page_redirects_anonymous(client):
    response = client.get("/")
    assert response.status_code == 303
    assert "/login" in response.headers["location"]


def test_web_home_renders_for_logged_user(client, db, author):
    login_as(client, author)
    response = client.get("/")
    assert response.status_code == 200
    assert "Minha fila" in response.text
