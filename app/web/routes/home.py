"""Home por perfil: a fila de trabalho de cada papel."""

from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import current_user
from app.db import get_db
from app.models import (
    PolicyVersion,
    Publication,
    Role,
    User,
    VersionStatus,
)
from app.services import search_service, workflow_service
from app.web.templating import render

router = APIRouter()


@router.get("/")
def home(
    request: Request,
    msg: str = "",
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    # verificação lazy de vigências agendadas (além da tarefa periódica)
    if workflow_service.apply_due_publications(db):
        db.commit()

    role = Role(user.role)
    context: dict = {"msg": msg}

    if role in (Role.AUTHOR, Role.ADMIN):
        context["my_drafts"] = list(
            db.scalars(
                select(PolicyVersion)
                .where(
                    PolicyVersion.created_by == user.id,
                    PolicyVersion.status == VersionStatus.DRAFT.value,
                )
                .order_by(PolicyVersion.created_at.desc())
            )
        )
    if role in (Role.REVIEWER, Role.ADMIN):
        context["to_review"] = list(
            db.scalars(
                select(PolicyVersion)
                .where(PolicyVersion.status == VersionStatus.IN_REVIEW.value)
                .order_by(PolicyVersion.submitted_at)
            )
        )
    if role in (Role.APPROVER, Role.ADMIN):
        context["to_approve"] = list(
            db.scalars(
                select(PolicyVersion)
                .where(PolicyVersion.status == VersionStatus.IN_APPROVAL.value)
                .order_by(PolicyVersion.submitted_at)
            )
        )
        context["to_publish"] = list(
            db.scalars(
                select(PolicyVersion)
                .where(PolicyVersion.status == VersionStatus.APPROVED.value)
                .order_by(PolicyVersion.created_at)
            )
        )

    cutoff = date.today() - timedelta(days=30)
    context["recently_effective"] = list(
        db.scalars(
            select(PolicyVersion)
            .join(Publication, Publication.version_id == PolicyVersion.id)
            .where(
                PolicyVersion.status == VersionStatus.EFFECTIVE.value,
                Publication.effective_from >= cutoff,
            )
            .order_by(Publication.effective_from.desc())
            .limit(10)
        )
    )
    return render(request, "home.html", user, **context)


@router.get("/search")
def search(
    request: Request,
    q: str = "",
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    hits = search_service.search(db, q, user) if q.strip() else []
    return render(request, "search.html", user, q=q, hits=hits)
