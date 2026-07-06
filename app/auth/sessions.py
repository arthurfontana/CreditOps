"""Sessões via cookie assinado (itsdangerous).

Payload: {user_id, issued_at}. Expiração por inatividade (max_age na
verificação); cookie HttpOnly + SameSite=Lax + Secure configurável.
"""

from __future__ import annotations

from itsdangerous import BadSignature, URLSafeTimedSerializer
from starlette.responses import Response

from app.config import get_settings

COOKIE_NAME = "creditops_session"


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(get_settings().secret_key, salt="creditops.session")


def create_session_token(user_id: str) -> str:
    return _serializer().dumps({"user_id": user_id})


def read_session_token(token: str | None) -> str | None:
    """Retorna user_id ou None (token ausente, inválido ou expirado)."""
    if not token:
        return None
    try:
        payload = _serializer().loads(
            token, max_age=get_settings().session_max_age_seconds
        )
    except BadSignature:
        return None
    return payload.get("user_id")


def set_session_cookie(response: Response, user_id: str) -> None:
    settings = get_settings()
    response.set_cookie(
        COOKIE_NAME,
        create_session_token(user_id),
        max_age=settings.session_max_age_seconds,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME)
