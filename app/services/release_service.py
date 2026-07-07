"""Releases (v1): agrupamento nomeado de publicações feitas em conjunto.

Ex.: "Revisão trimestral Q3" contém Política A v7, B v12 e C v5. Permite
reconstruir o pacote que foi ao ar junto e comunicar mudanças à operação.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Publication, Release, Role, User
from app.services import audit_service, authz
from app.services.errors import NotFound, ValidationFailed


def create_release(
    db: Session, actor: User, *, name: str, description: str = ""
) -> Release:
    authz.ensure_role(actor, Role.APPROVER, Role.ADMIN)
    if not name.strip():
        raise ValidationFailed("nome da release é obrigatório")
    release = Release(name=name.strip(), description=description.strip() or None,
                      created_by=actor.id)
    db.add(release)
    db.flush()
    audit_service.record(
        db, actor.id, "release.created", "release", release.id, {"name": release.name}
    )
    return release


def get_release(db: Session, release_id: str) -> Release:
    release = db.get(Release, release_id)
    if release is None:
        raise NotFound("release não encontrada")
    return release


def list_releases(db: Session, viewer: User) -> list[Release]:
    authz.ensure_active(viewer)
    return list(db.scalars(select(Release).order_by(Release.created_at.desc())))


def publications_of(db: Session, release_id: str) -> list[Publication]:
    return list(
        db.scalars(
            select(Publication)
            .where(Publication.release_id == release_id)
            .order_by(Publication.published_at)
        )
    )


def open_releases(db: Session) -> list[Release]:
    """Releases disponíveis para receber novas publicações (todas — uma
    release permanece aberta; o agrupamento é semântico, não um lock)."""
    return list(db.scalars(select(Release).order_by(Release.created_at.desc())))
