"""Dashboard de governança (v1).

Agregados sobre os dados que o MVP já grava: políticas por status, tempo
de ciclo, políticas paradas, mudanças por período e esperado × observado
por indicador. Só leitura — nenhuma escrita acontece aqui.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import (
    ChangeRequest,
    ChangeRequestStatus,
    ImpactMetric,
    Indicator,
    Policy,
    PolicyLifecycle,
    PolicyVersion,
    Publication,
    User,
    VersionStatus,
)
from app.services import authz, impact_service


@dataclass
class StalePolicy:
    policy: Policy
    effective_since: date
    months: int


@dataclass
class IndicatorOutcome:
    policy_code: str
    version_number: int
    version_id: str
    indicator_code: str
    indicator_name: str
    window_days: int
    expected: str
    observed: str | None


@dataclass
class Overview:
    versions_by_status: dict[str, int] = field(default_factory=dict)
    avg_cycle_days: float | None = None  # submissão → vigência (últimos 90d)
    cycle_sample: int = 0
    avg_lead_time_days: float | None = None  # demanda → vigência
    lead_time_sample: int = 0
    open_change_requests: int = 0
    publications_by_month: list[tuple[str, int]] = field(default_factory=list)
    stale_policies: list[StalePolicy] = field(default_factory=list)
    pending_observations: int = 0
    outcomes: list[IndicatorOutcome] = field(default_factory=list)


def _versions_by_status(db: Session) -> dict[str, int]:
    rows = db.execute(
        select(PolicyVersion.status, func.count()).group_by(PolicyVersion.status)
    ).all()
    return dict(rows)


def _avg_cycle_days(db: Session, days: int = 90) -> tuple[float | None, int]:
    """Média de submissão → vigência das versões que entraram em vigor no período."""
    cutoff = date.today() - timedelta(days=days)
    rows = db.execute(
        select(PolicyVersion.submitted_at, Publication.effective_from)
        .join(Publication, Publication.version_id == PolicyVersion.id)
        .where(
            Publication.effective_from >= cutoff,
            PolicyVersion.submitted_at.is_not(None),
            PolicyVersion.status.in_(
                [VersionStatus.EFFECTIVE.value, VersionStatus.SUPERSEDED.value]
            ),
        )
    ).all()
    durations = [
        (effective - submitted.date()).days
        for submitted, effective in rows
        if effective >= submitted.date()
    ]
    if not durations:
        return None, 0
    return round(sum(durations) / len(durations), 1), len(durations)


def _avg_lead_time_days(db: Session) -> tuple[float | None, int]:
    rows = db.execute(
        select(ChangeRequest.created_at, ChangeRequest.closed_at).where(
            ChangeRequest.status == ChangeRequestStatus.DONE.value,
            ChangeRequest.closed_at.is_not(None),
        )
    ).all()
    durations = [(closed - created).days for created, closed in rows]
    if not durations:
        return None, 0
    return round(sum(durations) / len(durations), 1), len(durations)


def _publications_by_month(db: Session, months: int = 12) -> list[tuple[str, int]]:
    start = (date.today().replace(day=1) - timedelta(days=months * 31)).replace(day=1)
    start_dt = datetime.combine(start, datetime.min.time())
    rows = db.execute(
        select(Publication.published_at).where(Publication.published_at >= start_dt)
    ).all()
    counts: dict[str, int] = {}
    for (published_at,) in rows:
        key = published_at.strftime("%Y-%m")
        counts[key] = counts.get(key, 0) + 1
    return sorted(counts.items())


def _stale_policies(db: Session, months: int) -> list[StalePolicy]:
    """Políticas ativas cuja versão vigente entrou em vigor há mais de N meses."""
    threshold = date.today() - timedelta(days=months * 30)
    rows = db.execute(
        select(Policy, Publication.effective_from)
        .join(PolicyVersion, PolicyVersion.id == Policy.current_version_id)
        .join(Publication, Publication.version_id == PolicyVersion.id)
        .where(
            Policy.lifecycle_status == PolicyLifecycle.ACTIVE.value,
            Publication.effective_from <= threshold,
        )
        .order_by(Publication.effective_from)
    ).all()
    return [
        StalePolicy(policy, effective_from, (date.today() - effective_from).days // 30)
        for policy, effective_from in rows
    ]


def _outcomes(db: Session, limit: int = 50) -> list[IndicatorOutcome]:
    rows = db.execute(
        select(ImpactMetric, Indicator, PolicyVersion, Policy)
        .join(Indicator, Indicator.id == ImpactMetric.indicator_id)
        .join(PolicyVersion, PolicyVersion.id == ImpactMetric.version_id)
        .join(Policy, Policy.id == PolicyVersion.policy_id)
        .where(
            PolicyVersion.status.in_(
                [VersionStatus.EFFECTIVE.value, VersionStatus.SUPERSEDED.value]
            )
        )
        .order_by(Policy.code, PolicyVersion.version_number, Indicator.code,
                  ImpactMetric.window_days)
        .limit(limit)
    ).all()
    return [
        IndicatorOutcome(
            policy_code=policy.code,
            version_number=version.version_number,
            version_id=version.id,
            indicator_code=indicator.code,
            indicator_name=indicator.name,
            window_days=metric.window_days,
            expected=metric.expected_change,
            observed=metric.observed_change,
        )
        for metric, indicator, version, policy in rows
    ]


def overview(db: Session, viewer: User) -> Overview:
    authz.ensure_active(viewer)
    settings = get_settings()
    avg_cycle, cycle_sample = _avg_cycle_days(db)
    avg_lead, lead_sample = _avg_lead_time_days(db)
    open_requests = db.scalar(
        select(func.count()).select_from(ChangeRequest).where(
            ChangeRequest.status.in_(
                [ChangeRequestStatus.OPEN.value, ChangeRequestStatus.IN_PROGRESS.value]
            )
        )
    )
    return Overview(
        versions_by_status=_versions_by_status(db),
        avg_cycle_days=avg_cycle,
        cycle_sample=cycle_sample,
        avg_lead_time_days=avg_lead,
        lead_time_sample=lead_sample,
        open_change_requests=int(open_requests or 0),
        publications_by_month=_publications_by_month(db),
        stale_policies=_stale_policies(db, settings.stale_policy_months),
        pending_observations=len(impact_service.pending_observations(db)),
        outcomes=_outcomes(db),
    )
