"""Delegação de aprovação (v1) — férias/ausência, com registro em auditoria.

O aprovador ausente delega a um par (outro aprovador ativo) por uma janela
datada. Enquanto a delegação está ativa, as decisões do delegado registram
`delegated_from_id` — a evidência mostra em nome de quem se decidiu.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ApprovalDelegation, Role, User
from app.services import audit_service, authz
from app.services.errors import NotFound, PermissionDenied, ValidationFailed


def create_delegation(
    db: Session,
    actor: User,
    *,
    delegate_id: str,
    starts_at: date,
    ends_at: date,
    reason: str = "",
) -> ApprovalDelegation:
    authz.ensure_role(actor, Role.APPROVER)
    if delegate_id == actor.id:
        raise ValidationFailed("não é possível delegar para si mesmo")
    delegate = db.get(User, delegate_id)
    if delegate is None or not delegate.is_active:
        raise ValidationFailed("delegado inválido")
    if Role(delegate.role) != Role.APPROVER:
        raise ValidationFailed("a delegação deve ser para outro aprovador (um par)")
    if ends_at < starts_at:
        raise ValidationFailed("período de delegação inválido (fim antes do início)")
    if ends_at < date.today():
        raise ValidationFailed("período de delegação já encerrado")

    delegation = ApprovalDelegation(
        delegator_id=actor.id,
        delegate_id=delegate_id,
        starts_at=starts_at,
        ends_at=ends_at,
        reason=reason.strip() or None,
    )
    db.add(delegation)
    db.flush()
    audit_service.record(
        db, actor.id, "delegation.created", "approval_delegation", delegation.id,
        {
            "delegate_id": delegate_id,
            "starts_at": starts_at.isoformat(),
            "ends_at": ends_at.isoformat(),
            "reason": reason or None,
        },
    )
    return delegation


def revoke_delegation(db: Session, actor: User, delegation_id: str) -> ApprovalDelegation:
    delegation = db.get(ApprovalDelegation, delegation_id)
    if delegation is None:
        raise NotFound("delegação não encontrada")
    if delegation.delegator_id != actor.id and Role(actor.role) != Role.ADMIN:
        raise PermissionDenied("apenas quem delegou (ou admin) pode revogar")
    if delegation.revoked_at is not None:
        raise ValidationFailed("delegação já revogada")
    delegation.revoked_at = datetime.utcnow()
    db.flush()
    audit_service.record(
        db, actor.id, "delegation.revoked", "approval_delegation", delegation.id,
        {"delegator_id": delegation.delegator_id, "delegate_id": delegation.delegate_id},
    )
    return delegation


def active_delegations_to(
    db: Session, user_id: str, on: date | None = None
) -> list[ApprovalDelegation]:
    """Delegações ativas em que `user_id` é o delegado."""
    on = on or date.today()
    stmt = select(ApprovalDelegation).where(
        ApprovalDelegation.delegate_id == user_id,
        ApprovalDelegation.starts_at <= on,
        ApprovalDelegation.ends_at >= on,
        ApprovalDelegation.revoked_at.is_(None),
    )
    return list(db.scalars(stmt))


def resolve_delegator(
    db: Session, actor: User, *, area_id: str | None, exclude_user_ids: set[str] | None = None
) -> User | None:
    """Delegante em cujo nome o ator pode decidir nesta política.

    Prioriza delegante com escopo na área da política (permite que o delegado
    decida fora da própria área, herdando o escopo de quem delegou).
    """
    exclude = exclude_user_ids or set()
    candidates = [
        db.get(User, d.delegator_id)
        for d in active_delegations_to(db, actor.id)
        if d.delegator_id not in exclude
    ]
    candidates = [u for u in candidates if u is not None and u.is_active]
    for user in candidates:
        if authz.in_area_scope(user, area_id):
            return user
    return None


def list_delegations(db: Session, viewer: User) -> list[ApprovalDelegation]:
    authz.ensure_active(viewer)
    stmt = select(ApprovalDelegation).order_by(ApprovalDelegation.created_at.desc())
    if Role(viewer.role) != Role.ADMIN:
        stmt = stmt.where(
            (ApprovalDelegation.delegator_id == viewer.id)
            | (ApprovalDelegation.delegate_id == viewer.id)
        )
    return list(db.scalars(stmt))
