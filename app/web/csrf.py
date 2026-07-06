"""Proteção CSRF: token assinado por usuário, exigido em todo POST de formulário."""

from __future__ import annotations

from fastapi import Depends, Form
from itsdangerous import BadSignature, URLSafeTimedSerializer

from app.auth.deps import current_user
from app.config import get_settings
from app.models import User

MAX_AGE_SECONDS = 12 * 3600


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(get_settings().secret_key, salt="creditops.csrf")


def make_csrf_token(user_id: str) -> str:
    return _serializer().dumps({"uid": user_id})


def validate_csrf_token(token: str | None, user_id: str) -> bool:
    if not token:
        return False
    try:
        payload = _serializer().loads(token, max_age=MAX_AGE_SECONDS)
    except BadSignature:
        return False
    return payload.get("uid") == user_id


class CSRFError(Exception):
    pass


def csrf_protect(
    csrf_token: str = Form(""), user: User = Depends(current_user)
) -> None:
    """Dependência para rotas POST autenticadas: valida token contra o usuário."""
    if not validate_csrf_token(csrf_token, user.id):
        raise CSRFError("token CSRF inválido ou ausente")
