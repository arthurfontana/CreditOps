"""Demanda de mudança (v1): código, vínculo, fechamento automático e lead time."""

from __future__ import annotations

from datetime import date

import pytest

from app.services import change_request_service, workflow_service
from app.services.errors import ValidationFailed
from tests.helpers import draft_of, make_policy, to_approval


def _open_request(db, user, area, policy=None):
    change_request = change_request_service.create(
        db, user,
        title="Rever score mínimo", description_md="FPD60 deteriorou",
        area_id=area.id, policy_id=policy.id if policy else None,
    )
    db.commit()
    return change_request


def test_code_is_sequential_per_year(db, author, area):
    first = _open_request(db, author, area)
    second = _open_request(db, author, area)
    year = date.today().year
    assert first.code == f"DEM-{year}-001"
    assert second.code == f"DEM-{year}-002"


def test_reject_requires_justification(db, author, approver, area):
    change_request = _open_request(db, author, area)
    with pytest.raises(ValidationFailed):
        change_request_service.reject(db, approver, change_request.id, "  ")
    change_request_service.reject(db, approver, change_request.id, "sem aderência à estratégia")
    db.commit()
    assert change_request.status == "rejected"
    assert change_request.closed_at is not None


def test_linked_version_effective_closes_request(db, author, reviewer, approver, area):
    policy = make_policy(db, author, area)
    change_request = _open_request(db, author, area, policy)
    draft = draft_of(policy)
    change_request_service.link_version(db, author, draft.id, change_request.id)
    db.commit()
    assert change_request.status == "in_progress"  # vínculo tira do estado 'aberta'

    to_approval(db, author, reviewer, draft)
    workflow_service.approve(db, approver, draft.id)
    workflow_service.publish(db, approver, draft.id, date.today())
    db.commit()

    db.refresh(change_request)
    assert change_request.status == "done"
    assert change_request.closed_at is not None
    assert change_request_service.lead_time_days(change_request) is not None


def test_cannot_link_closed_request(db, author, approver, area):
    policy = make_policy(db, author, area)
    change_request = _open_request(db, author, area)
    change_request_service.reject(db, approver, change_request.id, "duplicada")
    db.commit()
    with pytest.raises(ValidationFailed):
        change_request_service.link_version(
            db, author, draft_of(policy).id, change_request.id
        )
