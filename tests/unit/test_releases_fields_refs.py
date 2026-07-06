"""Releases, campos estruturados (+diff) e referência de implementação (v1)."""

from __future__ import annotations

import json
from datetime import date

import pytest

from app.services import (
    diff_service,
    implementation_service,
    release_service,
    structured_fields,
    version_service,
    workflow_service,
)
from app.services.errors import ValidationFailed
from tests.helpers import (
    approve_and_publish,
    draft_of,
    fill_and_submit,
    make_policy,
    to_approval,
)

# ── releases ─────────────────────────────────────────────────────────────────


def test_publish_into_release(db, author, reviewer, approver, area):
    release = release_service.create_release(db, approver, name="Revisão Q3/2026")
    policy = make_policy(db, author, area)
    version = to_approval(db, author, reviewer, draft_of(policy))
    workflow_service.approve(db, approver, version.id)
    workflow_service.publish(db, approver, version.id, date.today(), release_id=release.id)
    db.commit()

    publications = release_service.publications_of(db, release.id)
    assert [p.version_id for p in publications] == [version.id]
    assert release.published_at is not None


def test_publish_with_unknown_release_fails(db, author, reviewer, approver, area):
    policy = make_policy(db, author, area)
    version = to_approval(db, author, reviewer, draft_of(policy))
    workflow_service.approve(db, approver, version.id)
    with pytest.raises(ValidationFailed):
        workflow_service.publish(
            db, approver, version.id, date.today(), release_id="inexistente"
        )


# ── campos estruturados ──────────────────────────────────────────────────────


def test_parse_form_types_and_errors():
    parsed = structured_fields.parse_form(
        "limite", {"score_minimo": "620", "comprometimento_max": "35,5"}
    )
    assert json.loads(parsed) == {"score_minimo": 620, "comprometimento_max": 35.5}

    with pytest.raises(ValidationFailed):
        structured_fields.parse_form("limite", {"score_minimo": "abc"})

    assert structured_fields.parse_form("limite", {"score_minimo": ""}) is None


def test_field_diff_between_versions(db, author, reviewer, approver, area):
    policy = make_policy(db, author, area)
    draft = draft_of(policy)
    version_service.update_draft(
        db, author, draft.id,
        body_md=draft.body_md,
        structured_fields=json.dumps({"score_minimo": 600, "comprometimento_max": 30}),
    )
    approve_and_publish(db, author, reviewer, approver, draft)

    revision = version_service.create_revision(db, author, policy.id)
    version_service.update_draft(
        db, author, revision.id,
        body_md=revision.body_md,
        structured_fields=json.dumps({"score_minimo": 640, "renda_minima": 2500}),
    )
    db.commit()

    changes = {c.label: c for c in diff_service.field_diff(draft, revision)}
    assert changes["Score mínimo"].before == 600
    assert changes["Score mínimo"].after == 640
    assert changes["Comprometimento máximo de renda (%)"].kind == "removed"
    assert changes["Renda mínima (R$)"].kind == "added"


def test_structured_fields_enter_content_hash(db, author, reviewer, area):
    policy = make_policy(db, author, area)
    draft = draft_of(policy)
    version_service.update_draft(
        db, author, draft.id,
        body_md=draft.body_md,
        structured_fields=json.dumps({"score_minimo": 620}),
    )
    fill_and_submit(db, author, draft)
    workflow_service.send_to_approval(db, reviewer, draft.id)
    db.commit()
    assert draft.content_hash == version_service.content_hash(
        draft.body_md, draft.structured_fields
    )


# ── referência de implementação ──────────────────────────────────────────────


def test_implementation_ref_only_after_publication(db, author, reviewer, approver, area):
    policy = make_policy(db, author, area)
    draft = draft_of(policy)
    with pytest.raises(ValidationFailed):
        implementation_service.register(
            db, author, draft.id,
            system="PowerCurve", artifact="strategy-pf", artifact_version="v12",
        )

    approve_and_publish(db, author, reviewer, approver, draft)
    ref = implementation_service.register(
        db, author, draft.id,
        system="PowerCurve", artifact="strategy-pf", artifact_version="v12",
        node_path="no-07-corte",
    )
    db.commit()
    assert implementation_service.refs_for_version(db, draft.id) == [ref]
