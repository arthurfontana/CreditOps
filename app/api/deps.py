"""Autenticação da API de consumo: Authorization: Bearer <token de serviço>."""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import ServiceToken
from app.services import service_token_service


def require_service_token(request: Request, db: Session = Depends(get_db)) -> ServiceToken:
    header = request.headers.get("Authorization", "")
    scheme, _, credential = header.partition(" ")
    if scheme.lower() != "bearer" or not credential.strip():
        raise HTTPException(
            status_code=401,
            detail="token de serviço ausente (use Authorization: Bearer <token>)",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = service_token_service.verify_token(db, credential.strip())
    if token is None:
        raise HTTPException(
            status_code=401,
            detail="token de serviço inválido ou revogado",
            headers={"WWW-Authenticate": "Bearer"},
        )
    db.commit()  # persiste last_used_at
    return token
