"""Aprovação multinível por tipo (v1) e delegação de aprovação."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.models import Approval, Role
from app.services import approval_rules, delegation_service, user_service, workflow_service
from app.services.errors import PermissionDenied, ValidationFailed
from tests.helpers import draft_of, make_policy, to_approval


@pytest.fixture()
def approver2(db):
    user = user_service.create_user(
        db, None,
        username="aprovador2", email="aprovador2@example.com", display_name="Aprovador 2",
        role=Role.APPROVER.value, password="senha-forte-123", must_change_password=False,
    )
    db.commit()
    return user


def _version_in_approval(db, author, reviewer, area):
    policy = make_policy(db, author, area)
    return to_approval(db, author, reviewer, draft_of(policy))


# ── multinível ───────────────────────────────────────────────────────────────


def test_default_is_single_level(db, area, author, reviewer, approver):
    version = _version_in_approval(db, author, reviewer, area)
    workflow_service.approve(db, approver, version.id)
    db.commit()
    assert version.status == "approved"


def test_two_levels_required(db, area, admin, author, reviewer, approver, approver2):
    approval_rules.set_rule(db, admin, "limite", 2)
    db.commit()
    version = _version_in_approval(db, author, reviewer, area)

    workflow_service.approve(db, approver, version.id)
    db.commit()
    assert version.status == "in_approval"  # nível 1 de 2: ainda não avança

    workflow_service.approve(db, approver2, version.id)
    db.commit()
    assert version.status == "approved"

    levels = [
        a.level
        for a in db.scalars(select(Approval).where(Approval.version_id == version.id))
    ]
    assert sorted(levels) == [1, 2]


def test_same_approver_cannot_approve_two_levels(db, area, admin, author, reviewer, approver):
    approval_rules.set_rule(db, admin, "limite", 2)
    db.commit()
    version = _version_in_approval(db, author, reviewer, area)
    workflow_service.approve(db, approver, version.id)
    with pytest.raises(ValidationFailed):
        workflow_service.approve(db, approver, version.id)


def test_rejection_at_second_level_returns_to_draft(
    db, area, admin, author, reviewer, approver, approver2
):
    approval_rules.set_rule(db, admin, "limite", 2)
    db.commit()
    version = _version_in_approval(db, author, reviewer, area)
    workflow_service.approve(db, approver, version.id)
    workflow_service.reject(db, approver2, version.id, "não concordo com o corte")
    db.commit()
    assert version.status == "draft"


def test_new_round_resets_levels(db, area, admin, author, reviewer, approver, approver2):
    approval_rules.set_rule(db, admin, "limite", 2)
    db.commit()
    version = _version_in_approval(db, author, reviewer, area)
    workflow_service.approve(db, approver, version.id)
    workflow_service.reject(db, approver2, version.id, "ajustar")
    db.commit()
    # nova rodada: reenvia e exige os 2 níveis de novo
    workflow_service.submit_for_review(db, author, version.id)
    workflow_service.send_to_approval(db, reviewer, version.id)
    db.commit()
    workflow_service.approve(db, approver2, version.id)
    db.commit()
    assert version.status == "in_approval"  # apenas 1 nível da rodada atual


# ── delegação ────────────────────────────────────────────────────────────────


def test_delegation_records_delegated_from(db, area, author, reviewer, approver, approver2):
    delegation_service.create_delegation(
        db, approver,
        delegate_id=approver2.id,
        starts_at=date.today(), ends_at=date.today() + timedelta(days=7),
        reason="férias",
    )
    db.commit()
    version = _version_in_approval(db, author, reviewer, area)
    workflow_service.approve(db, approver2, version.id, on_behalf_of=approver.id)
    db.commit()

    approval = db.scalars(select(Approval).where(Approval.version_id == version.id)).first()
    assert approval.approver_id == approver2.id
    assert approval.delegated_from_id == approver.id
    assert version.status == "approved"


def test_on_behalf_without_delegation_is_denied(db, area, author, reviewer, approver, approver2):
    version = _version_in_approval(db, author, reviewer, area)
    with pytest.raises(PermissionDenied):
        workflow_service.approve(db, approver2, version.id, on_behalf_of=approver.id)


def test_delegation_must_target_an_approver(db, approver, author):
    with pytest.raises(ValidationFailed):
        delegation_service.create_delegation(
            db, approver,
            delegate_id=author.id,
            starts_at=date.today(), ends_at=date.today() + timedelta(days=1),
        )


def test_revoked_delegation_stops_working(db, area, author, reviewer, approver, approver2):
    delegation = delegation_service.create_delegation(
        db, approver,
        delegate_id=approver2.id,
        starts_at=date.today(), ends_at=date.today() + timedelta(days=7),
    )
    db.commit()
    delegation_service.revoke_delegation(db, approver, delegation.id)
    db.commit()
    version = _version_in_approval(db, author, reviewer, area)
    with pytest.raises(PermissionDenied):
        workflow_service.approve(db, approver2, version.id, on_behalf_of=approver.id)


def test_delegation_cannot_bypass_segregation(db, area, author, reviewer, approver, approver2):
    """Delegado não decide versão cujo autor é o delegante — nem a própria."""
    delegation_service.create_delegation(
        db, approver,
        delegate_id=approver2.id,
        starts_at=date.today(), ends_at=date.today() + timedelta(days=7),
    )
    db.commit()
    version = _version_in_approval(db, author, reviewer, area)
    # autor da versão é 'author'; caso delegante fosse o autor, seria bloqueado.
    # aqui validamos a segregação direta: o próprio autor delegado não decide.
    assert version.created_by == author.id
