"""Catálogo administrável de indicadores (v1).

O catálogo existe para que hipóteses e resultados sejam comparáveis entre
mudanças — texto livre não agrega. Seed padrão na migração 0002.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Indicator, IndicatorDirection, Role, User
from app.services import audit_service, authz
from app.services.errors import NotFound, ValidationFailed


def list_all(db: Session) -> list[Indicator]:
    return list(db.scalars(select(Indicator).order_by(Indicator.code)))


def list_active(db: Session) -> list[Indicator]:
    return list(
        db.scalars(select(Indicator).where(Indicator.is_active).order_by(Indicator.code))
    )


def create(
    db: Session,
    actor: User,
    *,
    code: str,
    name: str,
    unit: str = "",
    desired_direction: str = IndicatorDirection.CONTEXTUAL,
) -> Indicator:
    authz.ensure_role(actor, Role.ADMIN)
    code = code.strip().lower().replace(" ", "_")
    if not code or not name.strip():
        raise ValidationFailed("código e nome do indicador são obrigatórios")
    if desired_direction not in [d.value for d in IndicatorDirection]:
        raise ValidationFailed(f"direção inválida: {desired_direction}")
    if db.scalars(select(Indicator).where(Indicator.code == code)).first():
        raise ValidationFailed(f"indicador '{code}' já existe")
    indicator = Indicator(
        code=code,
        name=name.strip(),
        unit=unit.strip() or None,
        desired_direction=desired_direction,
    )
    db.add(indicator)
    db.flush()
    audit_service.record(
        db, actor.id, "indicator.created", "indicator", indicator.id,
        {"code": code, "name": indicator.name},
    )
    return indicator


def toggle(db: Session, actor: User, indicator_id: str) -> Indicator:
    authz.ensure_role(actor, Role.ADMIN)
    indicator = db.get(Indicator, indicator_id)
    if indicator is None:
        raise NotFound("indicador não encontrado")
    indicator.is_active = not indicator.is_active
    db.flush()
    audit_service.record(
        db, actor.id, "indicator.updated", "indicator", indicator.id,
        {"is_active": {"before": not indicator.is_active, "after": indicator.is_active}},
    )
    return indicator
