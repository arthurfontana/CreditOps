"""Demanda de mudança (v1): o pedido que antecede o rascunho.

Qualquer usuário ativo registra a necessidade (novo produto, apontamento
de auditoria, deterioração de indicador…). A demanda pode gerar N versões
(inclusive em políticas diferentes) ou ser rejeitada — também é decisão,
também fica registrada. Lead time = demanda aberta → versão em vigor
(fechamento automático em workflow_service.make_effective).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Area,
    ChangeRequest,
    ChangeRequestPriority,
    ChangeRequestStatus,
    Policy,
    Role,
    User,
)
from app.services import audit_service, authz
from app.services.errors import NotFound, PermissionDenied, ValidationFailed


def _next_code(db: Session) -> str:
    """DEM-YYYY-NNN sequencial por ano."""
    year = datetime.utcnow().year
    prefix = f"DEM-{year}-"
    max_n = 0
    for code in db.scalars(select(ChangeRequest.code).where(ChangeRequest.code.like(f"{prefix}%"))):
        m = re.match(rf"^{re.escape(prefix)}(\d+)$", code)
        if m:
            max_n = max(max_n, int(m.group(1)))
    return f"{prefix}{max_n + 1:03d}"


def create(
    db: Session,
    actor: User,
    *,
    title: str,
    description_md: str,
    area_id: str,
    policy_id: str | None = None,
    priority: str = ChangeRequestPriority.MEDIUM,
) -> ChangeRequest:
    authz.ensure_active(actor)
    if not title.strip():
        raise ValidationFailed("título da demanda é obrigatório")
    if priority not in [p.value for p in ChangeRequestPriority]:
        raise ValidationFailed(f"prioridade inválida: {priority}")
    area = db.get(Area, area_id)
    if area is None or not area.is_active:
        raise ValidationFailed("área inválida")
    if policy_id:
        policy = db.get(Policy, policy_id)
        if policy is None:
            raise ValidationFailed("política não encontrada")

    change_request = ChangeRequest(
        code=_next_code(db),
        title=title.strip(),
        description_md=description_md,
        requested_by=actor.id,
        area_id=area_id,
        policy_id=policy_id or None,
        priority=priority,
    )
    db.add(change_request)
    db.flush()
    audit_service.record(
        db, actor.id, "change_request.created", "change_request", change_request.id,
        {"code": change_request.code, "title": change_request.title, "priority": priority},
    )
    return change_request


def get(db: Session, change_request_id: str) -> ChangeRequest:
    change_request = db.get(ChangeRequest, change_request_id)
    if change_request is None:
        raise NotFound("demanda não encontrada")
    return change_request


@dataclass
class ChangeRequestFilters:
    status: str | None = None
    area_id: str | None = None
    priority: str | None = None


def list_requests(
    db: Session, viewer: User, filters: ChangeRequestFilters | None = None
) -> list[ChangeRequest]:
    authz.ensure_active(viewer)
    f = filters or ChangeRequestFilters()
    stmt = select(ChangeRequest).order_by(ChangeRequest.created_at.desc())
    if f.status:
        stmt = stmt.where(ChangeRequest.status == f.status)
    if f.area_id:
        stmt = stmt.where(ChangeRequest.area_id == f.area_id)
    if f.priority:
        stmt = stmt.where(ChangeRequest.priority == f.priority)
    return list(db.scalars(stmt))


def open_requests(db: Session, area_id: str | None = None) -> list[ChangeRequest]:
    """Demandas abertas/em andamento — candidatas a vincular a um rascunho."""
    stmt = (
        select(ChangeRequest)
        .where(
            ChangeRequest.status.in_(
                [ChangeRequestStatus.OPEN.value, ChangeRequestStatus.IN_PROGRESS.value]
            )
        )
        .order_by(ChangeRequest.created_at)
    )
    if area_id:
        stmt = stmt.where(ChangeRequest.area_id == area_id)
    return list(db.scalars(stmt))


def start_progress(db: Session, actor: User, change_request_id: str) -> ChangeRequest:
    """Marca a demanda como em andamento (normalmente ao abrir o rascunho)."""
    authz.ensure_role(actor, Role.AUTHOR, Role.APPROVER, Role.ADMIN)
    change_request = get(db, change_request_id)
    if change_request.status != ChangeRequestStatus.OPEN:
        raise ValidationFailed("apenas demandas abertas podem entrar em andamento")
    change_request.status = ChangeRequestStatus.IN_PROGRESS
    db.flush()
    audit_service.record(
        db, actor.id, "change_request.started", "change_request", change_request.id,
        {"code": change_request.code},
    )
    return change_request


def reject(db: Session, actor: User, change_request_id: str, justification: str) -> ChangeRequest:
    """Rejeita a demanda sem gerar mudança — decisão registrada."""
    authz.ensure_role(actor, Role.APPROVER, Role.ADMIN)
    if not justification.strip():
        raise ValidationFailed("justificativa é obrigatória para rejeitar a demanda")
    change_request = get(db, change_request_id)
    if change_request.status in (ChangeRequestStatus.DONE, ChangeRequestStatus.REJECTED):
        raise ValidationFailed("demanda já encerrada")
    authz.ensure_area_scope(actor, change_request.area_id, action="decidir demandas")
    change_request.status = ChangeRequestStatus.REJECTED
    change_request.resolution = justification.strip()
    change_request.closed_at = datetime.utcnow()
    db.flush()
    audit_service.record(
        db, actor.id, "change_request.rejected", "change_request", change_request.id,
        {"code": change_request.code, "justification": justification},
    )
    return change_request


def link_version(db: Session, actor: User, version_id: str, change_request_id: str | None):
    """Vincula (ou desvincula) o rascunho à demanda que o originou."""
    from app.models import VersionStatus
    from app.services import version_service

    version = version_service.get_version(db, version_id)
    authz.ensure_role(actor, Role.AUTHOR, Role.ADMIN)
    if Role(actor.role) != Role.ADMIN and version.created_by != actor.id:
        raise PermissionDenied("apenas o autor da versão pode vinculá-la a uma demanda")
    if version.status != VersionStatus.DRAFT:
        raise ValidationFailed("vínculo com demanda só pode mudar em rascunho")
    if change_request_id:
        change_request = get(db, change_request_id)
        if change_request.status in (ChangeRequestStatus.DONE, ChangeRequestStatus.REJECTED):
            raise ValidationFailed("demanda já encerrada não pode receber novas mudanças")
        if change_request.status == ChangeRequestStatus.OPEN:
            change_request.status = ChangeRequestStatus.IN_PROGRESS
    version.change_request_id = change_request_id or None
    db.flush()
    audit_service.record(
        db, actor.id, "version.change_request_linked", "policy_version", version.id,
        {"change_request_id": change_request_id},
    )
    return version


def lead_time_days(change_request: ChangeRequest) -> int | None:
    """Lead time ponta a ponta: demanda aberta → encerramento (vigência)."""
    if change_request.closed_at is None:
        return None
    return (change_request.closed_at - change_request.created_at).days
