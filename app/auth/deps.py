"""Dependências FastAPI de autenticação/autorização das rotas web."""

from __future__ import annotations

from fastapi import Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.auth.sessions import COOKIE_NAME, read_session_token
from app.db import get_db
from app.models import Role, User


class AuthRedirect(Exception):
    """Sinaliza redirecionamento para /login (tratado por exception handler)."""

    def __init__(self, next_url: str = "/") -> None:
        self.next_url = next_url


class Forbidden(Exception):
    def __init__(self, detail: str = "") -> None:
        self.detail = detail


def optional_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    user_id = read_session_token(request.cookies.get(COOKIE_NAME))
    if user_id is None:
        return None
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        return None
    return user


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    user = optional_user(request, db)
    if user is None:
        raise AuthRedirect(next_url=str(request.url.path))
    return user


def require_role(*roles: Role):
    def dependency(user: User = Depends(current_user)) -> User:
        if Role(user.role) not in roles:
            allowed = ", ".join(r.value for r in roles)
            raise Forbidden(f"esta área requer papel: {allowed}")
        return user

    return dependency


def login_redirect(exc: AuthRedirect) -> RedirectResponse:
    return RedirectResponse(f"/login?next={exc.next_url}", status_code=303)
