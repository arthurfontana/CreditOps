"""Indicadores, hipótese estruturada e impacto observado (v1)."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.services import impact_service, indicator_service
from app.services.errors import ValidationFailed
from tests.helpers import approve_and_publish, draft_of, fill_and_submit, make_policy


@pytest.fixture()
def indicator(db):
    active = indicator_service.list_active(db)
    assert active, "seed do catálogo de indicadores deveria existir (migração 0002)"
    return active[0]


def test_catalog_is_seeded(db):
    codes = {i.code for i in indicator_service.list_active(db)}
    assert {"aprovacao", "fpd30", "fpd60", "over90"} <= codes


def test_hypothesis_declared_in_draft(db, author, area, indicator):
    policy = make_policy(db, author, area)
    draft = draft_of(policy)
    metrics = impact_service.set_hypothesis(
        db, author, draft.id,
        indicator_id=indicator.id, expected_change="+3 p.p. no PF", windows=[30, 90],
    )
    db.commit()
    assert [m.window_days for m in metrics] == [30, 90]
    assert all(m.expected_change == "+3 p.p. no PF" for m in metrics)


def test_hypothesis_frozen_after_submission(db, author, area, indicator):
    policy = make_policy(db, author, area)
    draft = draft_of(policy)
    fill_and_submit(db, author, draft)
    with pytest.raises(ValidationFailed):
        impact_service.set_hypothesis(
            db, author, draft.id, indicator_id=indicator.id, expected_change="tarde demais"
        )


def test_observed_recorded_once_after_effective(
    db, author, reviewer, approver, area, indicator
):
    policy = make_policy(db, author, area)
    draft = draft_of(policy)
    metrics = impact_service.set_hypothesis(
        db, author, draft.id, indicator_id=indicator.id, expected_change="-1 p.p.", windows=[30]
    )
    metric = metrics[0]

    # antes da vigência: não registra
    with pytest.raises(ValidationFailed):
        impact_service.record_observed(db, approver, metric.id, "-0,8 p.p.")

    approve_and_publish(db, author, reviewer, approver, draft)
    impact_service.record_observed(db, approver, metric.id, "-0,8 p.p.")
    db.commit()
    assert metric.observed_change == "-0,8 p.p."
    assert metric.recorded_by == approver.id

    # registro é evidência: não sobrescreve
    with pytest.raises(ValidationFailed):
        impact_service.record_observed(db, approver, metric.id, "-2 p.p.")


def test_pending_observations_after_window(
    db, author, reviewer, approver, area, indicator, monkeypatch
):
    policy = make_policy(db, author, area)
    draft = draft_of(policy)
    impact_service.set_hypothesis(
        db, author, draft.id, indicator_id=indicator.id, expected_change="+2 p.p.", windows=[30]
    )
    approve_and_publish(db, author, reviewer, approver, draft)

    assert impact_service.pending_observations(db) == []  # janela de 30d ainda não venceu

    real_date = date

    class FutureDate(date):
        @classmethod
        def today(cls):
            return real_date.today() + timedelta(days=31)

    monkeypatch.setattr("app.services.impact_service.date", FutureDate)
    pending = impact_service.pending_observations(db)
    assert len(pending) == 1
    assert pending[0].metric.window_days == 30
    assert pending[0].policy.id == policy.id


def test_narrative_impact_record(db, author, reviewer, approver, area):
    from sqlalchemy import select

    from app.models import Publication

    policy = make_policy(db, author, area)
    draft = draft_of(policy)
    approve_and_publish(db, author, reviewer, approver, draft)
    publication = db.scalars(
        select(Publication).where(Publication.version_id == draft.id)
    ).first()
    record = impact_service.record_impact(
        db, approver, publication.id, observed_impact="Aprovação subiu como esperado."
    )
    db.commit()
    assert record.recorded_by == approver.id
    assert impact_service.impact_records_for(db, publication.id) == [record]
