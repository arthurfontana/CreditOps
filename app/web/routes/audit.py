"""Consulta e exportação da trilha de auditoria (admin ou auditor)."""

from __future__ import annotations

import csv
import io
from datetime import datetime

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import Forbidden, current_user
from app.db import get_db
from app.models import Role, User
from app.services import audit_service
from app.web.templating import render

router = APIRouter()

PAGE_SIZE = 50


def require_auditor(user: User = Depends(current_user)) -> User:
    if Role(user.role) != Role.ADMIN and not user.is_auditor:
        raise Forbidden("esta área requer papel admin ou acesso de auditor")
    return user


def _parse_date(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _filters(
    action: str = "",
    actor_id: str = "",
    entity_type: str = "",
    entity_id: str = "",
    date_from: str = "",
    date_to: str = "",
    page: int = 1,
) -> dict:
    return {
        "action": action or None,
        "actor_id": actor_id or None,
        "entity_type": entity_type or None,
        "entity_id": entity_id or None,
        "date_from": _parse_date(date_from),
        "date_to": _parse_date(date_to),
        "page": max(page, 1),
    }


@router.get("/audit")
def audit_list(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_auditor),
    filters: dict = Depends(_filters),
):
    page = filters.pop("page")
    entries = audit_service.query(
        db, **filters, limit=PAGE_SIZE + 1, offset=(page - 1) * PAGE_SIZE
    )
    has_next = len(entries) > PAGE_SIZE
    actors = list(db.scalars(select(User).order_by(User.display_name)))
    return render(
        request, "audit/list.html", user,
        entries=entries[:PAGE_SIZE], page=page, has_next=has_next,
        actors=actors, query=dict(request.query_params),
    )


@router.get("/audit/export.csv")
def audit_export_csv(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_auditor),
    filters: dict = Depends(_filters),
):
    filters.pop("page")
    entries = audit_service.query(db, **filters, limit=100_000)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["seq", "data_hora", "ator", "acao", "entidade", "entidade_id", "payload"])
    for e in entries:
        writer.writerow(
            [
                e.id,
                e.created_at.isoformat(),
                e.actor.display_name if e.actor else "sistema",
                e.action,
                e.entity_type,
                e.entity_id or "",
                e.payload or "",
            ]
        )
    audit_service.record(
        db, user.id, "export.generated", "audit_log", None, {"kind": "csv"}
    )
    db.commit()
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="trilha_auditoria.csv"'},
    )
