"""Trilha de leitura obrigatória — "ciência da operação" (v2).

Registro datado de que um usuário leu a versão VIGENTE de uma política.
O registro é por (versão, usuário): quando uma nova versão entra em
vigor, a ciência anterior deixa de valer e a leitura volta a ser
pendente — exatamente o comportamento esperado de compliance.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Policy, PolicyLifecycle, ReadReceipt, User
from app.services import audit_service, authz
from app.services.errors import NotFound, ValidationFailed


def acknowledge(db: Session, actor: User, policy_id: str) -> ReadReceipt:
    """Registra a ciência do usuário sobre a versão vigente. Idempotente."""
    authz.ensure_active(actor)
    policy = db.get(Policy, policy_id)
    if policy is None:
        raise NotFound("política não encontrada")
    version = policy.current_version
    if version is None:
        raise ValidationFailed("a política não tem versão vigente para declarar ciência")
    existing = db.scalars(
        select(ReadReceipt).where(
            ReadReceipt.version_id == version.id, ReadReceipt.user_id == actor.id
        )
    ).first()
    if existing is not None:
        return existing
    receipt = ReadReceipt(policy_id=policy.id, version_id=version.id, user_id=actor.id)
    db.add(receipt)
    db.flush()
    audit_service.record(
        db, actor.id, "version.acknowledged", "policy_version", version.id,
        {"policy_code": policy.code, "version": version.version_number},
    )
    return receipt


def receipt_of(db: Session, user: User, version_id: str) -> ReadReceipt | None:
    return db.scalars(
        select(ReadReceipt).where(
            ReadReceipt.version_id == version_id, ReadReceipt.user_id == user.id
        )
    ).first()


@dataclass
class PolicyReadReport:
    policy: Policy
    receipts: list[ReadReceipt]
    pending_users: list[User]  # usuários ativos sem ciência da versão vigente


def policy_report(db: Session, policy_id: str) -> PolicyReadReport:
    """Quem leu (e quem ainda não leu) a versão vigente da política."""
    policy = db.get(Policy, policy_id)
    if policy is None:
        raise NotFound("política não encontrada")
    receipts: list[ReadReceipt] = []
    read_user_ids: set[str] = set()
    if policy.current_version is not None:
        receipts = list(
            db.scalars(
                select(ReadReceipt)
                .where(ReadReceipt.version_id == policy.current_version.id)
                .order_by(ReadReceipt.acknowledged_at)
            )
        )
        read_user_ids = {r.user_id for r in receipts}
    pending = [
        u
        for u in db.scalars(select(User).where(User.is_active).order_by(User.display_name))
        if u.id not in read_user_ids
    ]
    return PolicyReadReport(policy=policy, receipts=receipts, pending_users=pending)


def pending_for_user(db: Session, user: User, limit: int = 50) -> list[Policy]:
    """Políticas vigentes cuja versão atual o usuário ainda não leu."""
    read_version_ids = {
        r.version_id
        for r in db.scalars(select(ReadReceipt).where(ReadReceipt.user_id == user.id))
    }
    policies = db.scalars(
        select(Policy)
        .where(
            Policy.lifecycle_status == PolicyLifecycle.ACTIVE.value,
            Policy.current_version_id.is_not(None),
        )
        .order_by(Policy.code)
    )
    return [p for p in policies if p.current_version_id not in read_version_ids][:limit]
