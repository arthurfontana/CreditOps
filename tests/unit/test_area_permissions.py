"""Permissões por área (v1): autor/aprovador atuam apenas na própria área."""

from __future__ import annotations

import pytest

from app.models import Area, Role
from app.services import policy_service, user_service, version_service, workflow_service
from app.services.errors import PermissionDenied
from tests.helpers import draft_of, make_policy, to_approval


@pytest.fixture()
def area_b(db) -> Area:
    other = Area(name="Cobrança", code="COB")
    db.add(other)
    db.commit()
    return other


def _scoped_user(db, role: Role, name: str, area_id: str):
    user = user_service.create_user(
        db, None,
        username=name, email=f"{name}@example.com", display_name=name,
        role=role.value, password="senha-forte-123",
        area_id=area_id, must_change_password=False,
    )
    db.commit()
    return user


def test_author_cannot_create_policy_in_other_area(db, area, area_b):
    author_b = _scoped_user(db, Role.AUTHOR, "autor-cob", area_b.id)
    with pytest.raises(PermissionDenied):
        policy_service.create_policy(
            db, author_b,
            title="Fora da área", policy_type="limite",
            area_id=area.id, owner_id=author_b.id,
        )


def test_author_cannot_edit_draft_of_other_area(db, area, area_b, author):
    # autor corporativo (sem área) cria na área CRD
    policy = make_policy(db, author, area)
    draft = draft_of(policy)
    author_b = _scoped_user(db, Role.AUTHOR, "autor-cob2", area_b.id)
    with pytest.raises(PermissionDenied):
        version_service.update_draft(db, author_b, draft.id, body_md="invasão")


def test_corporate_user_without_area_has_full_scope(db, area, author):
    policy = make_policy(db, author, area)
    assert policy.area_id == area.id  # autor sem área (escopo corporativo) cria em qualquer área


def test_approver_of_other_area_cannot_decide(db, area, area_b, author, reviewer):
    policy = make_policy(db, author, area)
    version = to_approval(db, author, reviewer, draft_of(policy))
    approver_b = _scoped_user(db, Role.APPROVER, "aprovador-cob", area_b.id)
    with pytest.raises(PermissionDenied):
        workflow_service.approve(db, approver_b, version.id)


def test_approver_of_same_area_can_decide(db, area, author, reviewer):
    policy = make_policy(db, author, area)
    version = to_approval(db, author, reviewer, draft_of(policy))
    approver_a = _scoped_user(db, Role.APPROVER, "aprovador-crd", area.id)
    workflow_service.approve(db, approver_a, version.id)
    db.commit()
    assert version.status == "approved"
