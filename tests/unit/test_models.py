"""Invariantes garantidos pelo BANCO (triggers e constraints)."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.models import AuditLog, PolicyVersion, VersionStatus
from tests.helpers import draft_of, make_policy


def test_policy_born_with_draft_v1(db, author, area):
    policy = make_policy(db, author, area)
    assert len(policy.versions) == 1
    v1 = policy.versions[0]
    assert v1.version_number == 1
    assert v1.status == VersionStatus.DRAFT


def test_frozen_version_body_update_blocked_by_trigger(db, author, area):
    policy = make_policy(db, author, area)
    version = draft_of(policy)
    db.execute(
        text("UPDATE policy_version SET status = 'approved' WHERE id = :id"),
        {"id": version.id},
    )
    db.commit()
    with pytest.raises(IntegrityError, match="immutable version"):
        db.execute(
            text("UPDATE policy_version SET body_md = 'adulterado' WHERE id = :id"),
            {"id": version.id},
        )
        db.commit()
    db.rollback()


def test_frozen_version_delete_blocked_by_trigger(db, author, area):
    policy = make_policy(db, author, area)
    version = draft_of(policy)
    db.execute(
        text("UPDATE policy_version SET status = 'effective' WHERE id = :id"),
        {"id": version.id},
    )
    db.commit()
    with pytest.raises(IntegrityError, match="immutable version"):
        db.execute(text("DELETE FROM policy_version WHERE id = :id"), {"id": version.id})
        db.commit()
    db.rollback()


def test_audit_log_update_and_delete_blocked(db, author, area):
    make_policy(db, author, area)  # gera eventos de auditoria
    entry = db.query(AuditLog).first()
    assert entry is not None
    with pytest.raises(IntegrityError, match="append-only"):
        db.execute(
            text("UPDATE audit_log SET action = 'forjado' WHERE id = :id"), {"id": entry.id}
        )
        db.commit()
    db.rollback()
    with pytest.raises(IntegrityError, match="append-only"):
        db.execute(text("DELETE FROM audit_log WHERE id = :id"), {"id": entry.id})
        db.commit()
    db.rollback()


def test_only_one_effective_version_per_policy(db, author, area):
    policy = make_policy(db, author, area)
    v1 = draft_of(policy)
    db.execute(
        text("UPDATE policy_version SET status = 'effective' WHERE id = :id"), {"id": v1.id}
    )
    db.commit()
    v2 = PolicyVersion(
        policy_id=policy.id, version_number=2, status="effective",
        body_md="x", created_by=author.id,
    )
    db.add(v2)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_duplicate_version_number_fails(db, author, area):
    policy = make_policy(db, author, area)
    dup = PolicyVersion(
        policy_id=policy.id, version_number=1, status="draft",
        body_md="x", created_by=author.id,
    )
    db.add(dup)
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
