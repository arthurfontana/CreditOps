"""Versões: edição, nova revisão, congelamento, time travel."""

from datetime import date, timedelta

import pytest

from app.services import version_service, workflow_service
from app.services.errors import PermissionDenied, ValidationFailed
from tests.helpers import approve_and_publish, draft_of, make_policy


def test_update_draft_only_by_author(db, author, author2, area):
    policy = make_policy(db, author, area)
    version = draft_of(policy)
    with pytest.raises(PermissionDenied):
        version_service.update_draft(db, author2, version.id, body_md="x")
    version_service.update_draft(db, author, version.id, body_md="novo corpo")
    assert version.body_md == "novo corpo"


def test_update_blocked_outside_draft(db, author, reviewer, approver, area):
    policy = make_policy(db, author, area)
    version = draft_of(policy)
    approve_and_publish(db, author, reviewer, approver, version)
    with pytest.raises(ValidationFailed):
        version_service.update_draft(db, author, version.id, body_md="tarde demais")


def test_create_revision_copies_content_and_links_base(db, author, reviewer, approver, area):
    policy = make_policy(db, author, area)
    v1 = draft_of(policy)
    version_service.update_draft(db, author, v1.id, body_md="conteúdo v1")
    approve_and_publish(db, author, reviewer, approver, v1)
    v2 = version_service.create_revision(db, author, policy.id)
    assert v2.version_number == 2
    assert v2.body_md == "conteúdo v1"
    assert v2.based_on_version_id == v1.id
    assert v2.status == "draft"


def test_create_revision_fails_with_open_version(db, author, reviewer, approver, area):
    policy = make_policy(db, author, area)
    v1 = draft_of(policy)
    approve_and_publish(db, author, reviewer, approver, v1)
    version_service.create_revision(db, author, policy.id)
    db.commit()
    with pytest.raises(ValidationFailed, match="aberta"):
        version_service.create_revision(db, author, policy.id)


def test_create_revision_fails_without_effective_version(db, author, area):
    policy = make_policy(db, author, area)  # v1 ainda em draft
    with pytest.raises(ValidationFailed):
        version_service.create_revision(db, author, policy.id)


def test_freeze_hash_is_deterministic(db, author, area):
    policy = make_policy(db, author, area)
    version = draft_of(policy)
    version_service.freeze(version)
    h1 = version.content_hash
    version_service.freeze(version)
    assert version.content_hash == h1
    assert len(h1) == 64


def test_version_at_boundaries(db, author, reviewer, approver, area, monkeypatch):
    """Time travel com 3 vigências e fronteiras exatas."""
    policy = make_policy(db, author, area)
    v1 = draft_of(policy)
    approve_and_publish(db, author, reviewer, approver, v1)

    d0 = date.today()

    # v2 entra em vigor "amanhã" (relógio avançado)
    class Day1(date):
        @classmethod
        def today(cls):
            return d0 + timedelta(days=10)

    v2 = version_service.create_revision(db, author, policy.id)
    monkeypatch.setattr(workflow_service, "date", Day1)
    approve_and_publish(
        db, author, reviewer, approver, v2, effective_from=d0 + timedelta(days=10)
    )

    class Day2(date):
        @classmethod
        def today(cls):
            return d0 + timedelta(days=20)

    v3 = version_service.create_revision(db, author, policy.id)
    monkeypatch.setattr(workflow_service, "date", Day2)
    approve_and_publish(
        db, author, reviewer, approver, v3, effective_from=d0 + timedelta(days=20)
    )

    def at(days: int):
        result = version_service.version_at(db, policy.id, d0 + timedelta(days=days))
        return result.version_number if result else None

    assert at(-1) is None            # antes da primeira vigência
    assert at(0) == 1                # dia da primeira vigência
    assert at(9) == 1                # véspera da troca
    assert at(10) == 2               # dia exato da troca → nova versão
    assert at(15) == 2
    assert at(20) == 3               # segunda troca
    assert at(365) == 3              # vigente atual, sem effective_until
