"""Cenários que provam as promessas do produto (backlog épico 7.3)."""

from datetime import date, timedelta

import pytest
from sqlalchemy import select, text

from app.models import AuditLog, StatusTransition, VersionStatus
from app.services import (
    comment_service,
    version_service,
    workflow_service,
)
from app.services.errors import PermissionDenied, ValidationFailed
from tests.helpers import approve_and_publish, draft_of, fill_and_submit, make_policy


def test_complete_lifecycle_with_four_users(db, author, reviewer, approver, reader, area):
    """criar → submeter → devolver → re-submeter → aprovar → publicar futuro →
    ativar vigência → nova revisão → publicar → anterior substituída."""
    policy = make_policy(db, author, area, "Ciclo Completo")
    v1 = draft_of(policy)
    version_service.update_draft(db, author, v1.id, body_md="regra inicial")

    # submete e revisor devolve
    fill_and_submit(db, author, v1)
    workflow_service.request_changes(db, reviewer, v1.id, "detalhar alçadas")
    db.commit()
    assert v1.status == VersionStatus.DRAFT

    # re-submete e avança
    version_service.update_draft(db, author, v1.id, body_md="regra inicial + alçadas")
    workflow_service.submit_for_review(db, author, v1.id)
    workflow_service.send_to_approval(db, reviewer, v1.id)
    workflow_service.approve(db, approver, v1.id)
    db.commit()
    assert v1.status == VersionStatus.APPROVED
    assert v1.content_hash is not None

    # publica com vigência futura
    future = date.today() + timedelta(days=5)
    workflow_service.publish(db, approver, v1.id, future)
    db.commit()
    assert v1.status == VersionStatus.PUBLISHED
    assert policy.current_version_id is None

    # sistema ativa a vigência na data
    class FakeDate(date):
        @classmethod
        def today(cls):
            return future

    import unittest.mock

    with unittest.mock.patch.object(workflow_service, "date", FakeDate):
        assert workflow_service.apply_due_publications(db) == 1
    db.commit()
    db.refresh(v1)
    db.refresh(policy)
    assert v1.status == VersionStatus.EFFECTIVE
    assert policy.current_version_id == v1.id

    # nova revisão substitui a anterior
    v2 = version_service.create_revision(db, author, policy.id)
    version_service.update_draft(db, author, v2.id, body_md="regra revisada")
    approve_and_publish(db, author, reviewer, approver, v2)
    db.refresh(v1)
    db.refresh(policy)
    assert v1.status == VersionStatus.SUPERSEDED
    assert policy.current_version_id == v2.id

    # trilha: cada passo gerou transição e auditoria
    transitions = db.scalars(
        select(StatusTransition).where(StatusTransition.version_id.in_([v1.id, v2.id]))
    ).all()
    assert len(transitions) >= 10
    audit_count = db.scalar(
        select(AuditLog.id).order_by(AuditLog.id.desc()).limit(1)
    )
    assert audit_count and audit_count > 15


def test_immutability_end_to_end(db, author, reviewer, approver, area):
    """Versão publicada não muda por NENHUM caminho (service e SQL direto)."""
    policy = make_policy(db, author, area)
    version = draft_of(policy)
    version_service.update_draft(db, author, version.id, body_md="conteúdo oficial")
    approve_and_publish(db, author, reviewer, approver, version)

    # via service
    with pytest.raises(ValidationFailed):
        version_service.update_draft(db, author, version.id, body_md="hack")
    with pytest.raises(ValidationFailed):
        version_service.update_submission_fields(
            db, author, version.id, change_summary="x", expected_impact="y"
        )
    # via SQL direto — trigger do banco
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError):
        db.execute(
            text("UPDATE policy_version SET body_md = 'hack' WHERE id = :id"),
            {"id": version.id},
        )
        db.commit()
    db.rollback()
    with pytest.raises(IntegrityError):
        db.execute(text("DELETE FROM policy_version WHERE id = :id"), {"id": version.id})
        db.commit()
    db.rollback()
    db.refresh(version)
    assert version.body_md == "conteúdo oficial"


def test_segregation_of_duties(db, author, reviewer, approver, admin, reader, area):
    policy = make_policy(db, author, area)
    version = draft_of(policy)
    fill_and_submit(db, author, version)
    workflow_service.send_to_approval(db, reviewer, version.id)
    db.commit()

    # autor (com papel acumulado de aprovador) não aprova a própria versão
    author.role = "approver"
    db.commit()
    with pytest.raises(PermissionDenied):
        workflow_service.approve(db, author, version.id)
    author.role = "author"
    db.commit()

    # leitor não edita nem aprova
    with pytest.raises(PermissionDenied):
        version_service.update_draft(db, reader, version.id, body_md="x")
    with pytest.raises(PermissionDenied):
        workflow_service.approve(db, reader, version.id)

    # admin administra mas não participa do fluxo
    with pytest.raises(PermissionDenied):
        workflow_service.approve(db, admin, version.id)


def test_rejection_preserves_comments_and_audits(db, author, reviewer, approver, area):
    policy = make_policy(db, author, area)
    version = draft_of(policy)
    fill_and_submit(db, author, version)
    comment_service.add(db, reviewer, version.id, "cuidado com o teto")
    workflow_service.send_to_approval(db, reviewer, version.id)
    db.commit()

    with pytest.raises(ValidationFailed):
        workflow_service.reject(db, approver, version.id, "")
    workflow_service.reject(db, approver, version.id, "teto acima da alçada")
    db.commit()
    db.refresh(version)
    assert version.status == VersionStatus.DRAFT
    assert len(comment_service.list_for_version(db, version.id)) == 1
    actions = [a.action for a in db.scalars(select(AuditLog))]
    assert "version.rejected" in actions


def test_rollback_scenario(db, author, reviewer, approver, area):
    """v3 com problema → rollback para v2 → v4 vigente com conteúdo de v2."""
    policy = make_policy(db, author, area)
    v1 = draft_of(policy)
    version_service.update_draft(db, author, v1.id, body_md="v1")
    approve_and_publish(db, author, reviewer, approver, v1)

    v2 = version_service.create_revision(db, author, policy.id)
    version_service.update_draft(db, author, v2.id, body_md="v2 boa")
    approve_and_publish(db, author, reviewer, approver, v2)

    v3 = version_service.create_revision(db, author, policy.id)
    version_service.update_draft(db, author, v3.id, body_md="v3 problemática")
    approve_and_publish(db, author, reviewer, approver, v3)

    v4 = workflow_service.rollback(db, approver, policy.id, v2.id, "v3 elevou FPD30")
    workflow_service.approve(db, approver, v4.id)
    workflow_service.publish(db, approver, v4.id, date.today())
    db.commit()

    db.refresh(policy)
    db.refresh(v3)
    assert policy.current_version.version_number == 4
    assert policy.current_version.body_md == "v2 boa"
    assert policy.current_version.is_rollback
    assert v3.status == VersionStatus.SUPERSEDED
    # histórico íntegro: nada apagado
    numbers = sorted(v.version_number for v in policy.versions)
    assert numbers == [1, 2, 3, 4]


def test_time_travel_five_dates(db, author, reviewer, approver, area, monkeypatch):
    policy = make_policy(db, author, area)
    d0 = date.today()

    v1 = draft_of(policy)
    version_service.update_draft(db, author, v1.id, body_md="época 1")
    approve_and_publish(db, author, reviewer, approver, v1)

    for offset, body in ((30, "época 2"), (60, "época 3")):
        v = version_service.create_revision(db, author, policy.id)
        version_service.update_draft(db, author, v.id, body_md=body)

        class Clock(date):
            _now = d0 + timedelta(days=offset)

            @classmethod
            def today(cls):
                return cls._now

        monkeypatch.setattr(workflow_service, "date", Clock)
        approve_and_publish(
            db, author, reviewer, approver, v, effective_from=d0 + timedelta(days=offset)
        )

    cases = {
        -1: None,      # antes de tudo
        0: "época 1",  # fronteira: primeiro dia da v1
        29: "época 1",  # véspera da troca
        30: "época 2",  # dia exato da troca
        60: "época 3",  # segunda troca
        90: "época 3",  # vigente atual
    }
    for offset, expected in cases.items():
        found = version_service.version_at(db, policy.id, d0 + timedelta(days=offset))
        if expected is None:
            assert found is None, f"dia {offset}"
        else:
            assert found is not None and found.body_md == expected, f"dia {offset}"


def test_audit_trail_reconstructs_workflow(db, author, reviewer, approver, area):
    """A pergunta de auditoria: quem aprovou, quando e por quê."""
    policy = make_policy(db, author, area)
    version = draft_of(policy)
    approve_and_publish(db, author, reviewer, approver, version)

    from app.services import export_service

    data = export_service.export_policy_json(db, policy)
    v = data["versions"][0]
    assert v["approvals"][0]["approver"] == "Aprovador"
    assert v["change_summary"] == "Ajuste de regra de teste"
    assert v["publication"]["published_by"] == "Aprovador"
    chain = [(t["from"], t["to"], t["actor"]) for t in v["transitions"]]
    assert ("in_approval", "approved", "Aprovador") in chain
    assert ("published", "effective", "sistema") in chain
