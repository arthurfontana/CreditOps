"""Máquina de estados — a parte mais importante do sistema."""

from datetime import date, timedelta

import pytest
from sqlalchemy import select, text

from app.models import (
    Approval,
    AuditLog,
    Publication,
    StatusTransition,
    VersionStatus,
)
from app.services import workflow_service
from app.services.errors import (
    InvalidTransition,
    PermissionDenied,
    ValidationFailed,
)
from app.services.workflow_service import TRANSITIONS
from tests.helpers import (
    approve_and_publish,
    draft_of,
    fill_and_submit,
    make_policy,
    to_approval,
)

ALL_STATUSES = list(VersionStatus)


def _force_status(db, version, status: str) -> None:
    db.execute(
        text("UPDATE policy_version SET status = :s WHERE id = :id"),
        {"s": status, "id": version.id},
    )
    db.commit()
    db.refresh(version)


def test_submit_requires_summary_and_impact(db, author, area):
    policy = make_policy(db, author, area)
    version = draft_of(policy)
    with pytest.raises(ValidationFailed):
        workflow_service.submit_for_review(db, author, version.id)


def test_full_happy_path(db, author, reviewer, approver, area):
    policy = make_policy(db, author, area)
    version = draft_of(policy)
    approve_and_publish(db, author, reviewer, approver, version)
    db.refresh(version)
    db.refresh(policy)
    assert version.status == VersionStatus.EFFECTIVE
    assert policy.current_version_id == version.id
    publication = db.scalars(
        select(Publication).where(Publication.version_id == version.id)
    ).one()
    assert publication.effective_from == date.today()
    assert publication.effective_until is None


@pytest.mark.parametrize(
    "from_status,to_status",
    [
        (a, b)
        for a in ALL_STATUSES
        for b in ALL_STATUSES
        if (a, b) not in TRANSITIONS and a != b
    ],
)
def test_transitions_outside_whitelist_rejected(
    db, author, reviewer, approver, admin, area, from_status, to_status
):
    """Produto cartesiano estados×estados: tudo fora da whitelist falha."""
    policy = make_policy(db, author, area)
    version = draft_of(policy)
    _force_status(db, version, from_status.value)
    for actor in (author, reviewer, approver, admin, None):
        with pytest.raises((InvalidTransition, PermissionDenied, ValidationFailed)):
            workflow_service._transition(db, actor, version, to_status)
        db.rollback()


def test_wrong_role_rejected_for_each_transition(db, author, reviewer, approver, reader, area):
    policy = make_policy(db, author, area)
    version = draft_of(policy)
    role_map = {"author": author, "reviewer": reviewer, "approver": approver}
    for (from_status, to_status), rule in TRANSITIONS.items():
        if not rule.roles:
            continue  # transições do sistema testadas separadamente
        _force_status(db, version, from_status.value)
        allowed = {r.value for r in rule.roles}
        # leitor nunca pode; papéis fora da regra também não
        wrong_actors = [reader] + [u for r, u in role_map.items() if r not in allowed]
        for actor in wrong_actors:
            with pytest.raises((PermissionDenied, InvalidTransition, ValidationFailed)):
                workflow_service._transition(
                    db, actor, version, to_status, reason="justificativa x"
                )
            db.rollback()
            db.refresh(version)


def test_system_transitions_refuse_human_actor(db, author, reviewer, approver, area):
    policy = make_policy(db, author, area)
    version = draft_of(policy)
    _force_status(db, version, VersionStatus.PUBLISHED.value)
    with pytest.raises(InvalidTransition):
        workflow_service._transition(db, approver, version, VersionStatus.EFFECTIVE)


def test_author_cannot_approve_own_version(db, author, reviewer, approver, area):
    """Segregação de funções — mesmo se o autor tivesse papel de aprovador."""
    policy = make_policy(db, author, area)
    version = draft_of(policy)
    to_approval(db, author, reviewer, version)
    author.role = "approver"  # simula acúmulo de papéis
    db.commit()
    with pytest.raises(PermissionDenied, match="segregação"):
        workflow_service.approve(db, author, version.id)
    db.rollback()
    with pytest.raises(PermissionDenied, match="segregação"):
        workflow_service.reject(db, author, version.id, "não gostei")


def test_admin_cannot_participate_in_workflow(db, author, admin, reviewer, area):
    policy = make_policy(db, author, area)
    version = draft_of(policy)
    to_approval(db, author, reviewer, version)
    with pytest.raises(PermissionDenied):
        workflow_service.approve(db, admin, version.id)


def test_reject_requires_justification(db, author, reviewer, approver, area):
    policy = make_policy(db, author, area)
    version = draft_of(policy)
    to_approval(db, author, reviewer, version)
    with pytest.raises(ValidationFailed):
        workflow_service.reject(db, approver, version.id, "   ")


def test_reject_returns_to_draft_and_records_evidence(db, author, reviewer, approver, area):
    from app.services import comment_service

    policy = make_policy(db, author, area)
    version = draft_of(policy)
    fill_and_submit(db, author, version)
    comment_service.add(db, reviewer, version.id, "atenção na seção de alçadas")
    db.commit()
    workflow_service.send_to_approval(db, reviewer, version.id)
    workflow_service.reject(db, approver, version.id, "limite acima da alçada permitida")
    db.commit()
    db.refresh(version)
    assert version.status == VersionStatus.DRAFT
    # evidência permanente da tentativa
    approval = db.scalars(select(Approval).where(Approval.version_id == version.id)).one()
    assert approval.decision == "rejected"
    assert approval.justification == "limite acima da alçada permitida"
    # comentários preservados
    assert len(comment_service.list_for_version(db, version.id)) == 1


def test_publish_with_past_date_fails(db, author, reviewer, approver, area):
    policy = make_policy(db, author, area)
    version = draft_of(policy)
    to_approval(db, author, reviewer, version)
    workflow_service.approve(db, approver, version.id)
    with pytest.raises(ValidationFailed, match="retroativa"):
        workflow_service.publish(
            db, approver, version.id, date.today() - timedelta(days=1)
        )


def test_future_effectiveness_waits_and_activates(
    db, author, reviewer, approver, area, monkeypatch
):
    policy = make_policy(db, author, area)
    version = draft_of(policy)
    to_approval(db, author, reviewer, version)
    workflow_service.approve(db, approver, version.id)
    future = date.today() + timedelta(days=10)
    workflow_service.publish(db, approver, version.id, future)
    db.commit()
    db.refresh(version)
    assert version.status == VersionStatus.PUBLISHED  # ainda não vigente
    assert policy.current_version_id is None

    # nada a ativar hoje
    assert workflow_service.apply_due_publications(db) == 0

    # simula a chegada da data (avança o relógio do serviço)
    class FakeDate(date):
        @classmethod
        def today(cls):
            return future

    monkeypatch.setattr(workflow_service, "date", FakeDate)
    assert workflow_service.apply_due_publications(db) == 1
    db.commit()
    db.refresh(version)
    db.refresh(policy)
    assert version.status == VersionStatus.EFFECTIVE
    assert policy.current_version_id == version.id


def test_supersede_fills_effective_until_and_updates_pointer(
    db, author, reviewer, approver, area
):
    from app.services import version_service

    policy = make_policy(db, author, area)
    v1 = draft_of(policy)
    approve_and_publish(db, author, reviewer, approver, v1)

    v2 = version_service.create_revision(db, author, policy.id)
    version_service.update_draft(db, author, v2.id, body_md="conteúdo novo v2")
    approve_and_publish(db, author, reviewer, approver, v2)

    db.refresh(v1)
    db.refresh(v2)
    db.refresh(policy)
    assert v1.status == VersionStatus.SUPERSEDED
    assert v2.status == VersionStatus.EFFECTIVE
    assert policy.current_version_id == v2.id
    pub1 = db.scalars(select(Publication).where(Publication.version_id == v1.id)).one()
    pub2 = db.scalars(select(Publication).where(Publication.version_id == v2.id)).one()
    assert pub1.effective_until == pub2.effective_from


def test_rollback_creates_new_version_with_target_content(
    db, author, reviewer, approver, area
):
    from app.services import version_service

    policy = make_policy(db, author, area)
    v1 = draft_of(policy)
    version_service.update_draft(db, author, v1.id, body_md="regra original")
    approve_and_publish(db, author, reviewer, approver, v1)

    v2 = version_service.create_revision(db, author, policy.id)
    version_service.update_draft(db, author, v2.id, body_md="regra com problema")
    approve_and_publish(db, author, reviewer, approver, v2)

    v3 = workflow_service.rollback(
        db, approver, policy.id, v1.id, "regra nova causou aumento de inadimplência"
    )
    db.commit()
    assert v3.version_number == 3
    assert v3.is_rollback is True
    assert v3.body_md == "regra original"
    assert v3.based_on_version_id == v1.id
    assert v3.status == VersionStatus.IN_APPROVAL  # fluxo expresso
    assert v3.content_hash  # congelada

    # aprovação e publicação seguem o fluxo normal
    workflow_service.approve(db, approver, v3.id)
    workflow_service.publish(db, approver, v3.id, date.today())
    db.commit()
    db.refresh(v2)
    db.refresh(policy)
    assert v2.status == VersionStatus.SUPERSEDED
    assert policy.current_version.version_number == 3
    # histórico linear: v1, v2, v3 todas presentes
    assert [v.version_number for v in policy.versions] == [1, 2, 3]


def test_rollback_requires_reason_and_approver(db, author, reviewer, approver, area):
    from app.services import version_service

    policy = make_policy(db, author, area)
    v1 = draft_of(policy)
    approve_and_publish(db, author, reviewer, approver, v1)
    v2 = version_service.create_revision(db, author, policy.id)
    approve_and_publish(db, author, reviewer, approver, v2)

    with pytest.raises(ValidationFailed):
        workflow_service.rollback(db, approver, policy.id, v1.id, "  ")
    with pytest.raises(PermissionDenied):
        workflow_service.rollback(db, author, policy.id, v1.id, "motivo")


def test_every_transition_generates_transition_and_audit_rows(
    db, author, reviewer, approver, area
):
    policy = make_policy(db, author, area)
    version = draft_of(policy)
    approve_and_publish(db, author, reviewer, approver, version)
    transitions = db.scalars(
        select(StatusTransition).where(StatusTransition.version_id == version.id)
    ).all()
    kinds = [(t.from_status, t.to_status) for t in transitions]
    assert ("draft", "in_review") in kinds
    assert ("in_review", "in_approval") in kinds
    assert ("in_approval", "approved") in kinds
    assert ("approved", "published") in kinds
    assert ("published", "effective") in kinds
    # sistema como ator da vigência
    eff = next(t for t in transitions if t.to_status == "effective")
    assert eff.actor_id is None
    audit_actions = {
        a.action
        for a in db.scalars(
            select(AuditLog).where(AuditLog.entity_id == version.id)
        )
    }
    assert {"version.submitted", "version.approved", "version.published",
            "version.effective"} <= audit_actions


def test_content_frozen_on_approval_entry(db, author, reviewer, area):
    from app.services import version_service
    from app.services.errors import ValidationFailed as VF

    policy = make_policy(db, author, area)
    version = draft_of(policy)
    fill_and_submit(db, author, version)
    workflow_service.send_to_approval(db, reviewer, version.id)
    db.commit()
    db.refresh(version)
    assert version.content_hash is not None
    with pytest.raises(VF):
        version_service.update_draft(db, author, version.id, body_md="mudança tardia")
