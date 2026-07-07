"""Hipótese e impacto observado por indicador (v1).

Na submissão a mudança declara hipóteses estruturadas (indicador + mudança
esperada, por janela de 30/60/90 dias). Após a vigência, o responsável
registra o observado — o sistema COBRA e REGISTRA; não calcula (não é BI).
O par esperado × observado transforma o histórico em aprendizado.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    IMPACT_WINDOWS,
    ImpactMetric,
    ImpactRecord,
    Indicator,
    Policy,
    PolicyVersion,
    Publication,
    Role,
    User,
    VersionStatus,
)
from app.services import audit_service, authz
from app.services.errors import NotFound, PermissionDenied, ValidationFailed

OBSERVER_ROLES = (Role.AUTHOR, Role.REVIEWER, Role.APPROVER, Role.ADMIN)


# ── hipóteses (declaradas em rascunho, congeladas com a versão) ──────────────


def set_hypothesis(
    db: Session,
    actor: User,
    version_id: str,
    *,
    indicator_id: str,
    expected_change: str,
    windows: list[int] | None = None,
) -> list[ImpactMetric]:
    """Declara (ou substitui) a hipótese de um indicador para a versão."""
    from app.services import version_service

    version = version_service.get_version(db, version_id)
    authz.ensure_role(actor, Role.AUTHOR, Role.ADMIN)
    if Role(actor.role) != Role.ADMIN and version.created_by != actor.id:
        raise PermissionDenied("apenas o autor da versão declara hipóteses")
    if version.status != VersionStatus.DRAFT:
        raise ValidationFailed("hipóteses só podem mudar em rascunho")
    if not expected_change.strip():
        raise ValidationFailed("mudança esperada é obrigatória (ex.: '+3 p.p. no segmento PF')")
    indicator = db.get(Indicator, indicator_id)
    if indicator is None or not indicator.is_active:
        raise ValidationFailed("indicador inválido")
    windows = windows or list(IMPACT_WINDOWS)
    for window in windows:
        if window not in IMPACT_WINDOWS:
            raise ValidationFailed(f"janela inválida: {window} (use {IMPACT_WINDOWS})")

    # substitui a hipótese anterior deste indicador (ainda em rascunho)
    for existing in db.scalars(
        select(ImpactMetric).where(
            ImpactMetric.version_id == version.id,
            ImpactMetric.indicator_id == indicator_id,
        )
    ):
        db.delete(existing)
    db.flush()

    metrics = []
    for window in sorted(set(windows)):
        metric = ImpactMetric(
            version_id=version.id,
            indicator_id=indicator_id,
            expected_change=expected_change.strip(),
            window_days=window,
        )
        db.add(metric)
        metrics.append(metric)
    db.flush()
    audit_service.record(
        db, actor.id, "impact.hypothesis_set", "policy_version", version.id,
        {
            "indicator": indicator.code,
            "expected_change": expected_change.strip(),
            "windows": sorted(set(windows)),
        },
    )
    return metrics


def remove_hypothesis(db: Session, actor: User, version_id: str, indicator_id: str) -> None:
    from app.services import version_service

    version = version_service.get_version(db, version_id)
    authz.ensure_role(actor, Role.AUTHOR, Role.ADMIN)
    if Role(actor.role) != Role.ADMIN and version.created_by != actor.id:
        raise PermissionDenied("apenas o autor da versão altera hipóteses")
    if version.status != VersionStatus.DRAFT:
        raise ValidationFailed("hipóteses só podem mudar em rascunho")
    for metric in db.scalars(
        select(ImpactMetric).where(
            ImpactMetric.version_id == version_id,
            ImpactMetric.indicator_id == indicator_id,
        )
    ):
        db.delete(metric)
    db.flush()
    audit_service.record(
        db, actor.id, "impact.hypothesis_removed", "policy_version", version_id,
        {"indicator_id": indicator_id},
    )


def metrics_for_version(db: Session, version_id: str) -> list[ImpactMetric]:
    return list(
        db.scalars(
            select(ImpactMetric)
            .join(Indicator, Indicator.id == ImpactMetric.indicator_id)
            .where(ImpactMetric.version_id == version_id)
            .order_by(Indicator.code, ImpactMetric.window_days)
        )
    )


# ── observado (pós-vigência) ─────────────────────────────────────────────────


def record_observed(
    db: Session, actor: User, metric_id: str, observed_change: str
) -> ImpactMetric:
    """Registra o observado de uma janela. Registro único — evidência, não flag."""
    metric = db.get(ImpactMetric, metric_id)
    if metric is None:
        raise NotFound("hipótese não encontrada")
    authz.ensure_role(actor, *OBSERVER_ROLES)
    version = metric.version
    authz.ensure_area_scope(actor, version.policy.area_id, action="registrar impacto")
    if VersionStatus(version.status) not in (VersionStatus.EFFECTIVE, VersionStatus.SUPERSEDED):
        raise ValidationFailed("o observado só é registrado após a vigência")
    if metric.observed_change:
        raise ValidationFailed(
            "observado já registrado (registro é evidência; complemente no impacto narrativo)"
        )
    if not observed_change.strip():
        raise ValidationFailed("valor observado é obrigatório")
    metric.observed_change = observed_change.strip()
    metric.recorded_by = actor.id
    metric.recorded_at = datetime.utcnow()
    db.flush()
    audit_service.record(
        db, actor.id, "impact.observed_recorded", "impact_metric", metric.id,
        {
            "version_id": version.id,
            "indicator": metric.indicator.code,
            "window_days": metric.window_days,
            "observed_change": metric.observed_change,
        },
    )
    return metric


@dataclass
class PendingObservation:
    metric: ImpactMetric
    version: PolicyVersion
    policy: Policy
    due_since: date


def pending_observations(
    db: Session, *, area_id: str | None = None, limit: int = 100
) -> list[PendingObservation]:
    """Cobrança pendente: janelas vencidas sem observado registrado."""
    today = date.today()
    stmt = (
        select(ImpactMetric, PolicyVersion, Publication)
        .join(PolicyVersion, PolicyVersion.id == ImpactMetric.version_id)
        .join(Publication, Publication.version_id == PolicyVersion.id)
        .where(
            ImpactMetric.observed_change.is_(None),
            PolicyVersion.status.in_(
                [VersionStatus.EFFECTIVE.value, VersionStatus.SUPERSEDED.value]
            ),
        )
        .order_by(Publication.effective_from)
        .limit(limit * 3)  # filtro fino de janela é feito em Python
    )
    pending: list[PendingObservation] = []
    for metric, version, publication in db.execute(stmt):
        due = publication.effective_from + timedelta(days=metric.window_days)
        if due > today:
            continue
        policy = version.policy
        if area_id and policy.area_id != area_id:
            continue
        pending.append(PendingObservation(metric, version, policy, due))
        if len(pending) >= limit:
            break
    return pending


# ── impacto narrativo (fecha o ciclo qualitativamente) ───────────────────────


def record_impact(
    db: Session,
    actor: User,
    publication_id: str,
    *,
    observed_impact: str,
    metrics_json: str | None = None,
) -> ImpactRecord:
    publication = db.get(Publication, publication_id)
    if publication is None:
        raise NotFound("publicação não encontrada")
    authz.ensure_role(actor, *OBSERVER_ROLES)
    version = publication.version
    authz.ensure_area_scope(actor, version.policy.area_id, action="registrar impacto")
    if not observed_impact.strip():
        raise ValidationFailed("descrição do impacto observado é obrigatória")
    record = ImpactRecord(
        publication_id=publication.id,
        observed_impact=observed_impact.strip(),
        metrics=metrics_json,
        recorded_by=actor.id,
    )
    db.add(record)
    db.flush()
    audit_service.record(
        db, actor.id, "impact.recorded", "publication", publication.id,
        {"version_id": version.id},
    )
    return record


def impact_records_for(db: Session, publication_id: str) -> list[ImpactRecord]:
    return list(
        db.scalars(
            select(ImpactRecord)
            .where(ImpactRecord.publication_id == publication_id)
            .order_by(ImpactRecord.recorded_at)
        )
    )
