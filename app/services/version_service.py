"""Versões: edição de rascunho, nova revisão, congelamento e time travel.

Imutabilidade: fora de `draft` o conteúdo nunca muda — validado aqui e
garantido por trigger no banco (defesa em profundidade).
"""

from __future__ import annotations

import hashlib
import json
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    OPEN_STATUSES,
    Policy,
    PolicyVersion,
    Publication,
    Role,
    User,
    VersionStatus,
)
from app.services import audit_service, authz
from app.services.errors import NotFound, PermissionDenied, ValidationFailed


def get_version(db: Session, version_id: str) -> PolicyVersion:
    version = db.get(PolicyVersion, version_id)
    if version is None:
        raise NotFound("versão não encontrada")
    return version


def content_hash(body_md: str, structured_fields: str | None, body_html: str = "") -> str:
    normalized = body_md + "\n" + json.dumps(
        json.loads(structured_fields) if structured_fields else None,
        sort_keys=True,
        ensure_ascii=False,
    )
    # corpo WYSIWYG entra no hash quando presente (sem alterar hashes históricos)
    if body_html:
        normalized += "\n" + body_html
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def update_draft(
    db: Session,
    actor: User,
    version_id: str,
    *,
    body_md: str,
    structured_fields: str | None = None,
    body_html: str | None = None,
) -> PolicyVersion:
    """Edita o conteúdo — só autor da versão (ou admin) e só em rascunho."""
    from app.services import richtext

    version = get_version(db, version_id)
    authz.ensure_role(actor, Role.AUTHOR, Role.ADMIN)
    authz.ensure_area_scope(actor, version.policy.area_id, action="editar")
    if Role(actor.role) != Role.ADMIN and version.created_by != actor.id:
        raise PermissionDenied("apenas o autor da versão pode editá-la")
    if version.status != VersionStatus.DRAFT:
        raise ValidationFailed("apenas rascunhos podem ser editados (versões são imutáveis)")
    version.body_md = body_md
    version.structured_fields = structured_fields
    if body_html is not None:
        version.body_html = richtext.sanitize_html(body_html)
    db.flush()
    # auditoria sem o corpo inteiro: grava apenas o hash do novo conteúdo
    audit_service.record(
        db,
        actor.id,
        "version.updated",
        "policy_version",
        version.id,
        {"content_sha256": content_hash(body_md, structured_fields, version.body_html)},
    )
    return version


def update_submission_fields(
    db: Session,
    actor: User,
    version_id: str,
    *,
    change_summary: str,
    expected_impact: str,
) -> PolicyVersion:
    """Justificativa e impacto esperado — editáveis apenas em rascunho."""
    version = get_version(db, version_id)
    authz.ensure_role(actor, Role.AUTHOR, Role.ADMIN)
    authz.ensure_area_scope(actor, version.policy.area_id, action="editar")
    if Role(actor.role) != Role.ADMIN and version.created_by != actor.id:
        raise PermissionDenied("apenas o autor da versão pode editá-la")
    if version.status != VersionStatus.DRAFT:
        raise ValidationFailed("apenas rascunhos podem ser editados")
    version.change_summary = change_summary
    version.expected_impact = expected_impact
    db.flush()
    return version


def max_version_number(db: Session, policy_id: str) -> int:
    return int(
        db.scalar(
            select(func.max(PolicyVersion.version_number)).where(
                PolicyVersion.policy_id == policy_id
            )
        )
        or 0
    )


def open_version(db: Session, policy_id: str) -> PolicyVersion | None:
    """Versão 'aberta' (não terminal) da política, se houver."""
    stmt = select(PolicyVersion).where(
        PolicyVersion.policy_id == policy_id,
        PolicyVersion.status.in_([s.value for s in OPEN_STATUSES]),
    )
    return db.scalars(stmt).first()


def create_revision(db: Session, actor: User, policy_id: str) -> PolicyVersion:
    """'Nova revisão': rascunho copiado da versão vigente.

    Só um rascunho aberto por política (história linear, sem forks).
    """
    authz.ensure_role(actor, Role.AUTHOR, Role.ADMIN)
    policy = db.get(Policy, policy_id)
    if policy is None:
        raise NotFound("política não encontrada")
    authz.ensure_area_scope(actor, policy.area_id, action="criar revisões")
    existing = open_version(db, policy_id)
    if existing is not None:
        raise ValidationFailed(
            f"já existe a versão v{existing.version_number} aberta "
            f"({existing.status}) para esta política"
        )
    base = policy.current_version
    if base is None:
        raise ValidationFailed("política ainda não tem versão vigente para revisar")
    version = PolicyVersion(
        policy_id=policy.id,
        version_number=max_version_number(db, policy.id) + 1,
        status=VersionStatus.DRAFT,
        body_md=base.body_md,
        body_html=base.body_html or "",
        structured_fields=base.structured_fields,
        based_on_version_id=base.id,
        created_by=actor.id,
    )
    db.add(version)
    db.flush()
    audit_service.record(
        db,
        actor.id,
        "version.revision_created",
        "policy_version",
        version.id,
        {
            "policy_code": policy.code,
            "version": version.version_number,
            "based_on": base.version_number,
        },
    )
    return version


def freeze(version: PolicyVersion) -> None:
    """Congela o conteúdo: calcula o hash. Chamado pelo workflow ao entrar em aprovação."""
    version.content_hash = content_hash(
        version.body_md, version.structured_fields, version.body_html or ""
    )


def version_at(db: Session, policy_id: str, d: date) -> PolicyVersion | None:
    """Time travel: a versão vigente na data D.

    Regra: effective_from <= D < effective_until (ou effective_until nulo).
    """
    stmt = (
        select(PolicyVersion)
        .join(Publication, Publication.version_id == PolicyVersion.id)
        .where(
            PolicyVersion.policy_id == policy_id,
            Publication.effective_from <= d,
            (Publication.effective_until.is_(None)) | (Publication.effective_until > d),
            PolicyVersion.status.in_(
                [VersionStatus.EFFECTIVE.value, VersionStatus.SUPERSEDED.value]
            ),
        )
        .order_by(Publication.effective_from.desc())
    )
    return db.scalars(stmt).first()
