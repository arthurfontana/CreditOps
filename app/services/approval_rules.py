"""Regras de aprovação multinível por tipo de política (v1).

Sem regra cadastrada, todo tipo exige 1 nível (comportamento do MVP).
Ex.: mudanças de limite exigem gerente + superintendente → 2 níveis.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ApprovalRule, PolicyType, Role, User
from app.services import audit_service, authz
from app.services.errors import ValidationFailed

MAX_LEVELS = 5


def required_levels(db: Session, policy_type: str) -> int:
    rule = db.scalars(
        select(ApprovalRule).where(ApprovalRule.policy_type == policy_type)
    ).first()
    return rule.required_levels if rule else 1


def set_rule(db: Session, actor: User, policy_type: str, levels: int) -> ApprovalRule:
    authz.ensure_role(actor, Role.ADMIN)
    if policy_type not in [t.value for t in PolicyType]:
        raise ValidationFailed(f"tipo de política inválido: {policy_type}")
    if not 1 <= levels <= MAX_LEVELS:
        raise ValidationFailed(f"níveis de aprovação devem estar entre 1 e {MAX_LEVELS}")
    rule = db.scalars(
        select(ApprovalRule).where(ApprovalRule.policy_type == policy_type)
    ).first()
    before = rule.required_levels if rule else 1
    if rule is None:
        rule = ApprovalRule(policy_type=policy_type, required_levels=levels)
        db.add(rule)
    else:
        rule.required_levels = levels
    db.flush()
    audit_service.record(
        db, actor.id, "approval_rule.updated", "approval_rule", rule.id,
        {"policy_type": policy_type, "levels": {"before": before, "after": levels}},
    )
    return rule


def list_rules(db: Session) -> dict[str, int]:
    """Níveis exigidos por tipo (todos os tipos, com default 1)."""
    rules = {r.policy_type: r.required_levels for r in db.scalars(select(ApprovalRule))}
    return {t.value: rules.get(t.value, 1) for t in PolicyType}
