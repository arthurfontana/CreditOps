"""Catálogo: geração de código, filtros, visibilidade de rascunho."""

import pytest
from sqlalchemy import select

from app.models import Area, AuditLog, VersionStatus
from app.services import policy_service
from app.services.errors import PermissionDenied, ValidationFailed
from app.services.policy_service import PolicyFilters
from tests.helpers import draft_of, make_policy


def test_sequential_code_per_area(db, author, area):
    p1 = make_policy(db, author, area, "Primeira")
    p2 = make_policy(db, author, area, "Segunda")
    assert p1.code == "POL-CRD-001"
    assert p2.code == "POL-CRD-002"
    other = Area(name="Cobrança", code="COB")
    db.add(other)
    db.commit()
    p3 = policy_service.create_policy(
        db, author, title="Outra área", policy_type="cobranca",
        area_id=other.id, owner_id=author.id,
    )
    assert p3.code == "POL-COB-001"


def test_reader_cannot_create_policy(db, reader, area):
    with pytest.raises(PermissionDenied):
        policy_service.create_policy(
            db, reader, title="X", policy_type="limite",
            area_id=area.id, owner_id=reader.id,
        )


def test_invalid_type_rejected(db, author, area):
    with pytest.raises(ValidationFailed):
        policy_service.create_policy(
            db, author, title="X", policy_type="inexistente",
            area_id=area.id, owner_id=author.id,
        )


def test_body_from_template(db, author, area):
    policy = make_policy(db, author, area)
    body = draft_of(policy).body_md
    assert "## Objetivo" in body
    assert "## Regras" in body


def test_filters_by_area_type_and_text(db, author, area):
    make_policy(db, author, area, "Limite PJ especial")
    make_policy(db, author, area, "Outra política")
    hits = policy_service.list_policies(
        db, author, PolicyFilters(text="especial")
    )
    assert len(hits) == 1
    hits = policy_service.list_policies(db, author, PolicyFilters(policy_type="limite"))
    assert len(hits) == 2
    hits = policy_service.list_policies(db, author, PolicyFilters(policy_type="score"))
    assert hits == []


def test_reader_does_not_see_draft_versions(db, author, reader, area):
    policy = make_policy(db, author, area)
    assert policy_service.visible_versions(db, reader, policy) == []
    assert len(policy_service.visible_versions(db, author, policy)) == 1


def test_metadata_update_audited_with_before_after(db, author, area):
    policy = make_policy(db, author, area)
    policy_service.update_policy_metadata(db, author, policy.id, title="Título Novo")
    entries = [
        e for e in db.scalars(select(AuditLog)) if e.action == "policy.updated"
    ]
    assert entries
    assert "Título Novo" in entries[-1].payload
    assert "before" in entries[-1].payload


def test_archive_policy_requires_approver_and_reason(db, author, approver, area):
    policy = make_policy(db, author, area)
    with pytest.raises(PermissionDenied):
        policy_service.archive_policy(db, author, policy.id, "motivo")
    with pytest.raises(ValidationFailed):
        policy_service.archive_policy(db, approver, policy.id, " ")
    policy_service.archive_policy(db, approver, policy.id, "descontinuada")
    assert policy.lifecycle_status == "archived"


def test_new_policy_first_version_is_draft(db, author, area):
    policy = make_policy(db, author, area)
    assert draft_of(policy).status == VersionStatus.DRAFT
