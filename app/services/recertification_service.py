"""Recertificação periódica de políticas (v2).

`policy.review_due_at` marca o prazo da próxima revisão obrigatória.
Recertificar = confirmar formalmente que a política vigente continua
válida (registrado em auditoria) e agendar o próximo ciclo. O relatório
responde: o que está vencido, o que vence em breve, o que nunca teve
prazo definido.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Policy, PolicyLifecycle, Role, User
from app.services import audit_service, authz
from app.services.errors import NotFound, ValidationFailed

DUE_SOON_DAYS = 60
DEFAULT_CYCLE_MONTHS = 12


def set_review_due(
    db: Session, actor: User, policy_id: str, due_at: datetime | None
) -> Policy:
    """Define (ou remove) o prazo de recertificação."""
    authz.ensure_role(actor, Role.AUTHOR, Role.APPROVER, Role.ADMIN)
    policy = db.get(Policy, policy_id)
    if policy is None:
        raise NotFound("política não encontrada")
    authz.ensure_area_scope(actor, policy.area_id, action="definir recertificação")
    before = policy.review_due_at.isoformat() if policy.review_due_at else None
    policy.review_due_at = due_at
    db.flush()
    audit_service.record(
        db, actor.id, "policy.review_due_set", "policy", policy.id,
        {"before": before, "after": due_at.isoformat() if due_at else None},
    )
    return policy


def recertify(
    db: Session, actor: User, policy_id: str, *, months: int = DEFAULT_CYCLE_MONTHS,
    note: str = "",
) -> Policy:
    """Confirma que a política continua válida e agenda o próximo ciclo."""
    authz.ensure_role(actor, Role.APPROVER, Role.ADMIN)
    if months < 1 or months > 60:
        raise ValidationFailed("ciclo de recertificação deve estar entre 1 e 60 meses")
    policy = db.get(Policy, policy_id)
    if policy is None:
        raise NotFound("política não encontrada")
    authz.ensure_area_scope(actor, policy.area_id, action="recertificar")
    if policy.current_version is None:
        raise ValidationFailed("apenas políticas com versão vigente podem ser recertificadas")
    previous_due = policy.review_due_at.isoformat() if policy.review_due_at else None
    policy.review_due_at = datetime.utcnow() + timedelta(days=months * 30)
    db.flush()
    audit_service.record(
        db, actor.id, "policy.recertified", "policy", policy.id,
        {
            "previous_due": previous_due,
            "next_due": policy.review_due_at.isoformat(),
            "cycle_months": months,
            "note": note.strip() or None,
        },
    )
    return policy


@dataclass
class RecertificationReport:
    overdue: list[Policy] = field(default_factory=list)  # prazo já passou
    due_soon: list[Policy] = field(default_factory=list)  # vence em <= DUE_SOON_DAYS
    scheduled: list[Policy] = field(default_factory=list)  # prazo futuro confortável
    unscheduled: list[Policy] = field(default_factory=list)  # vigente sem prazo definido


def report(db: Session) -> RecertificationReport:
    """Situação de recertificação das políticas ativas com versão vigente."""
    now = datetime.utcnow()
    soon = now + timedelta(days=DUE_SOON_DAYS)
    result = RecertificationReport()
    policies = db.scalars(
        select(Policy)
        .where(
            Policy.lifecycle_status == PolicyLifecycle.ACTIVE.value,
            Policy.current_version_id.is_not(None),
        )
        .order_by(Policy.review_due_at.is_(None), Policy.review_due_at, Policy.code)
    )
    for policy in policies:
        if policy.review_due_at is None:
            result.unscheduled.append(policy)
        elif policy.review_due_at <= now:
            result.overdue.append(policy)
        elif policy.review_due_at <= soon:
            result.due_soon.append(policy)
        else:
            result.scheduled.append(policy)
    return result
