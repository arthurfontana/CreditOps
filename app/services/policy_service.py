"""Catálogo de políticas: criação, metadados, listagem com filtros."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.config import BASE_DIR
from app.models import (
    Area,
    Policy,
    PolicyLifecycle,
    PolicyType,
    PolicyVersion,
    Product,
    Role,
    Segment,
    Tag,
    User,
    VersionStatus,
)
from app.services import audit_service, authz
from app.services.errors import NotFound, ValidationFailed

TEMPLATES_DIR = BASE_DIR / "docs" / "templates"

DEFAULT_BODY = """## Objetivo

## Escopo

## Regras

## Exceções

## Alçadas

## Referências
"""


def _template_body(policy_type: str) -> str:
    path: Path = TEMPLATES_DIR / f"{policy_type}.md"
    if not path.exists():
        path = TEMPLATES_DIR / "generico.md"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return DEFAULT_BODY


def _next_code(db: Session, area: Area) -> str:
    """Gera POL-<AREA_CODE>-NNN sequencial por área.

    Corrida entre dois autores é resolvida pelo unique de policy.code:
    a rota faz retry (escritas SQLite são serializadas, colisão é rara).
    """
    prefix = f"POL-{area.code}-"
    max_n = 0
    codes = db.scalars(select(Policy.code).where(Policy.code.like(f"{prefix}%")))
    for code in codes:
        m = re.match(rf"^{re.escape(prefix)}(\d+)$", code)
        if m:
            max_n = max(max_n, int(m.group(1)))
    return f"{prefix}{max_n + 1:03d}"


def create_policy(
    db: Session,
    actor: User,
    *,
    title: str,
    policy_type: str,
    area_id: str,
    owner_id: str,
    product_ids: list[str] | None = None,
    segment_ids: list[str] | None = None,
    tag_ids: list[str] | None = None,
) -> Policy:
    """Cria a política e sua versão 1 em rascunho, com corpo do template do tipo."""
    authz.ensure_role(actor, Role.AUTHOR, Role.ADMIN)
    if not title.strip():
        raise ValidationFailed("título é obrigatório")
    if policy_type not in [t.value for t in PolicyType]:
        raise ValidationFailed(f"tipo de política inválido: {policy_type}")
    area = db.get(Area, area_id)
    if area is None or not area.is_active:
        raise ValidationFailed("área inválida")
    owner = db.get(User, owner_id)
    if owner is None or not owner.is_active:
        raise ValidationFailed("responsável inválido")

    policy = Policy(
        code=_next_code(db, area),
        title=title.strip(),
        policy_type=policy_type,
        area_id=area_id,
        owner_id=owner_id,
    )
    if product_ids:
        policy.products = list(db.scalars(select(Product).where(Product.id.in_(product_ids))))
    if segment_ids:
        policy.segments = list(db.scalars(select(Segment).where(Segment.id.in_(segment_ids))))
    if tag_ids:
        policy.tags = list(db.scalars(select(Tag).where(Tag.id.in_(tag_ids))))
    db.add(policy)
    db.flush()

    version = PolicyVersion(
        policy_id=policy.id,
        version_number=1,
        status=VersionStatus.DRAFT,
        body_md=_template_body(policy_type),
        created_by=actor.id,
    )
    db.add(version)
    db.flush()

    audit_service.record(
        db,
        actor.id,
        "policy.created",
        "policy",
        policy.id,
        {"code": policy.code, "title": policy.title, "type": policy.policy_type},
    )
    return policy


def update_policy_metadata(
    db: Session,
    actor: User,
    policy_id: str,
    *,
    title: str | None = None,
    owner_id: str | None = None,
    product_ids: list[str] | None = None,
    segment_ids: list[str] | None = None,
    tag_ids: list[str] | None = None,
) -> Policy:
    """Atualiza metadados do contêiner (nunca toca em versões). Audita before/after."""
    authz.ensure_role(actor, Role.AUTHOR, Role.ADMIN)
    policy = db.get(Policy, policy_id)
    if policy is None:
        raise NotFound("política não encontrada")

    before = {
        "title": policy.title,
        "owner_id": policy.owner_id,
        "products": sorted(p.id for p in policy.products),
        "segments": sorted(s.id for s in policy.segments),
        "tags": sorted(t.id for t in policy.tags),
    }
    if title is not None:
        if not title.strip():
            raise ValidationFailed("título é obrigatório")
        policy.title = title.strip()
    if owner_id is not None:
        owner = db.get(User, owner_id)
        if owner is None or not owner.is_active:
            raise ValidationFailed("responsável inválido")
        policy.owner_id = owner_id
    if product_ids is not None:
        policy.products = list(db.scalars(select(Product).where(Product.id.in_(product_ids))))
    if segment_ids is not None:
        policy.segments = list(db.scalars(select(Segment).where(Segment.id.in_(segment_ids))))
    if tag_ids is not None:
        policy.tags = list(db.scalars(select(Tag).where(Tag.id.in_(tag_ids))))
    db.flush()

    after = {
        "title": policy.title,
        "owner_id": policy.owner_id,
        "products": sorted(p.id for p in policy.products),
        "segments": sorted(s.id for s in policy.segments),
        "tags": sorted(t.id for t in policy.tags),
    }
    changed = {k: {"before": before[k], "after": after[k]} for k in before if before[k] != after[k]}
    if changed:
        audit_service.record(db, actor.id, "policy.updated", "policy", policy.id, changed)
    return policy


@dataclass
class PolicyFilters:
    area_id: str | None = None
    product_id: str | None = None
    segment_id: str | None = None
    policy_type: str | None = None
    tag_id: str | None = None
    text: str | None = None
    lifecycle: str | None = None
    only_effective: bool = False
    _: dict = field(default_factory=dict, repr=False)


def list_policies(db: Session, viewer: User, filters: PolicyFilters | None = None) -> list[Policy]:
    """Catálogo com filtros. Todos os papéis autenticados veem o catálogo;
    o que muda é a visibilidade de versões em fluxo (rascunhos)."""
    authz.ensure_active(viewer)
    f = filters or PolicyFilters()
    stmt = select(Policy).order_by(Policy.code)
    if f.area_id:
        stmt = stmt.where(Policy.area_id == f.area_id)
    if f.policy_type:
        stmt = stmt.where(Policy.policy_type == f.policy_type)
    if f.lifecycle:
        stmt = stmt.where(Policy.lifecycle_status == f.lifecycle)
    if f.product_id:
        stmt = stmt.where(Policy.products.any(Product.id == f.product_id))
    if f.segment_id:
        stmt = stmt.where(Policy.segments.any(Segment.id == f.segment_id))
    if f.tag_id:
        stmt = stmt.where(Policy.tags.any(Tag.id == f.tag_id))
    if f.text:
        like = f"%{f.text.strip()}%"
        stmt = stmt.where(or_(Policy.title.ilike(like), Policy.code.ilike(like)))
    if f.only_effective:
        stmt = stmt.where(Policy.current_version_id.is_not(None))
    return list(db.scalars(stmt))


def get_policy(db: Session, viewer: User, policy_id: str) -> Policy:
    authz.ensure_active(viewer)
    policy = db.get(Policy, policy_id)
    if policy is None:
        raise NotFound("política não encontrada")
    return policy


def visible_versions(db: Session, viewer: User, policy: Policy) -> list[PolicyVersion]:
    """Leitor não vê versões em fluxo (rascunho/revisão/aprovação)."""
    versions = sorted(policy.versions, key=lambda v: v.version_number, reverse=True)
    if authz.can_see_drafts(viewer):
        return versions
    public = {
        VersionStatus.PUBLISHED,
        VersionStatus.EFFECTIVE,
        VersionStatus.SUPERSEDED,
        VersionStatus.ARCHIVED,
    }
    return [v for v in versions if VersionStatus(v.status) in public]


def archive_policy(db: Session, actor: User, policy_id: str, reason: str) -> Policy:
    """Arquiva a política inteira (descontinuada). Papel: aprovador."""
    authz.ensure_role(actor, Role.APPROVER)
    if not reason.strip():
        raise ValidationFailed("justificativa é obrigatória para arquivar")
    policy = db.get(Policy, policy_id)
    if policy is None:
        raise NotFound("política não encontrada")
    if policy.lifecycle_status == PolicyLifecycle.ARCHIVED:
        raise ValidationFailed("política já está arquivada")
    policy.lifecycle_status = PolicyLifecycle.ARCHIVED
    db.flush()
    audit_service.record(
        db, actor.id, "policy.archived", "policy", policy.id, {"reason": reason}
    )
    return policy


def count_by_status(db: Session) -> dict[str, int]:
    rows = db.execute(
        select(PolicyVersion.status, func.count()).group_by(PolicyVersion.status)
    ).all()
    return {status: n for status, n in rows}
