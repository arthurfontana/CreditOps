"""Comentários por versão — a conversa da revisão fica registrada."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Comment, Role, User
from app.services import audit_service, authz, version_service
from app.services.errors import NotFound, ValidationFailed


def add(
    db: Session, actor: User, version_id: str, body_md: str, anchor: str | None = None
) -> Comment:
    authz.ensure_role(actor, Role.AUTHOR, Role.REVIEWER, Role.APPROVER, Role.ADMIN)
    version = version_service.get_version(db, version_id)
    if not body_md.strip():
        raise ValidationFailed("comentário vazio")
    comment = Comment(
        version_id=version.id, author_id=actor.id, body_md=body_md.strip(), anchor=anchor
    )
    db.add(comment)
    db.flush()
    audit_service.record(
        db, actor.id, "comment.created", "comment", comment.id,
        {"version_id": version.id, "anchor": anchor},
    )
    return comment


def resolve(db: Session, actor: User, comment_id: str) -> Comment:
    authz.ensure_role(actor, Role.AUTHOR, Role.REVIEWER, Role.APPROVER, Role.ADMIN)
    comment = db.get(Comment, comment_id)
    if comment is None:
        raise NotFound("comentário não encontrado")
    if comment.resolved_at is None:
        comment.resolved_at = datetime.utcnow()
        db.flush()
        audit_service.record(db, actor.id, "comment.resolved", "comment", comment.id, None)
    return comment


def list_for_version(db: Session, version_id: str) -> list[Comment]:
    return list(
        db.scalars(
            select(Comment)
            .where(Comment.version_id == version_id)
            .order_by(Comment.created_at)
        )
    )
