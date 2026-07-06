"""Auxiliares de teste: fábricas e avanço de workflow."""

from __future__ import annotations

from datetime import date

from sqlalchemy.orm import Session

from app.models import Area, Policy, PolicyVersion, User
from app.services import policy_service, version_service, workflow_service


def make_policy(db: Session, author: User, area: Area, title: str = "Política de Teste") -> Policy:
    policy = policy_service.create_policy(
        db, author, title=title, policy_type="limite", area_id=area.id, owner_id=author.id
    )
    db.commit()
    return policy


def draft_of(policy: Policy) -> PolicyVersion:
    return max(policy.versions, key=lambda v: v.version_number)


def fill_and_submit(db: Session, author: User, version: PolicyVersion) -> PolicyVersion:
    version_service.update_submission_fields(
        db, author, version.id,
        change_summary="Ajuste de regra de teste",
        expected_impact="Nenhum impacto relevante",
    )
    workflow_service.submit_for_review(db, author, version.id)
    db.commit()
    return version


def to_approval(
    db: Session, author: User, reviewer: User, version: PolicyVersion
) -> PolicyVersion:
    fill_and_submit(db, author, version)
    workflow_service.send_to_approval(db, reviewer, version.id)
    db.commit()
    return version


def approve_and_publish(
    db: Session,
    author: User,
    reviewer: User,
    approver: User,
    version: PolicyVersion,
    effective_from: date | None = None,
) -> PolicyVersion:
    to_approval(db, author, reviewer, version)
    workflow_service.approve(db, approver, version.id)
    workflow_service.publish(db, approver, version.id, effective_from or date.today())
    db.commit()
    return version
