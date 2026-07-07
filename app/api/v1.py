"""API de consumo v1 (v2 do roadmap) — SOMENTE leitura.

Sistemas (motores de decisão, data lake) buscam a versão vigente de uma
política de forma programática. Nenhum endpoint de escrita existe aqui
por construção: mudanças passam apenas pelo workflow da aplicação web.

Só conteúdo público é servido: versões vigentes, substituídas e
arquivadas — rascunhos e versões em fluxo nunca aparecem.
"""

from __future__ import annotations

import json
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_service_token
from app.db import get_db
from app.models import (
    Policy,
    PolicyLifecycle,
    PolicyVersion,
    Publication,
    ServiceToken,
    VersionStatus,
)
from app.services import version_service, workflow_service

router = APIRouter(prefix="/api/v1", tags=["consumo"])

# versões visíveis para consumidores externos (mesma regra do leitor na web)
PUBLIC_STATUSES = (
    VersionStatus.EFFECTIVE.value,
    VersionStatus.SUPERSEDED.value,
    VersionStatus.ARCHIVED.value,
)


def _apply_due(db: Session) -> None:
    """Verificação lazy de vigência — a API sempre serve a vigência correta."""
    if workflow_service.apply_due_publications(db):
        db.commit()


def _policy_by_code(db: Session, code: str) -> Policy:
    policy = db.scalars(select(Policy).where(Policy.code == code)).first()
    if policy is None:
        raise HTTPException(status_code=404, detail=f"política não encontrada: {code}")
    return policy


def _publication_of(db: Session, version: PolicyVersion) -> Publication | None:
    return db.scalars(
        select(Publication).where(Publication.version_id == version.id)
    ).first()


def _policy_summary(policy: Policy) -> dict:
    return {
        "code": policy.code,
        "title": policy.title,
        "type": policy.policy_type,
        "area": policy.area.code if policy.area else None,
        "lifecycle_status": policy.lifecycle_status,
        "effective_version": (
            policy.current_version.version_number if policy.current_version else None
        ),
        "review_due_at": (
            policy.review_due_at.date().isoformat() if policy.review_due_at else None
        ),
    }


def _version_payload(db: Session, policy: Policy, version: PolicyVersion) -> dict:
    publication = _publication_of(db, version)
    return {
        "policy": _policy_summary(policy),
        "version": {
            "number": version.version_number,
            "status": version.status,
            "body_md": version.body_md,
            "structured_fields": (
                json.loads(version.structured_fields) if version.structured_fields else None
            ),
            "change_summary": version.change_summary,
            "content_hash": version.content_hash,
            "created_at": version.created_at.isoformat(),
        },
        "publication": {
            "published_at": publication.published_at.isoformat(),
            "effective_from": publication.effective_from.isoformat(),
            "effective_until": (
                publication.effective_until.isoformat() if publication.effective_until else None
            ),
            "rollout_scope": publication.rollout_scope,
            "pilot_description": publication.pilot_description,
            "pilot_ends_at": (
                publication.pilot_ends_at.isoformat() if publication.pilot_ends_at else None
            ),
        }
        if publication
        else None,
    }


@router.get("/policies")
def list_policies(
    area: str = "",
    policy_type: str = "",
    q: str = "",
    db: Session = Depends(get_db),
    token: ServiceToken = Depends(require_service_token),
) -> dict:
    """Catálogo (políticas ativas com versão vigente)."""
    _apply_due(db)
    stmt = (
        select(Policy)
        .where(
            Policy.lifecycle_status == PolicyLifecycle.ACTIVE.value,
            Policy.current_version_id.is_not(None),
        )
        .order_by(Policy.code)
    )
    if policy_type:
        stmt = stmt.where(Policy.policy_type == policy_type)
    policies = list(db.scalars(stmt))
    if area:
        policies = [p for p in policies if p.area and p.area.code == area]
    if q:
        needle = q.lower()
        policies = [
            p for p in policies if needle in p.title.lower() or needle in p.code.lower()
        ]
    return {"count": len(policies), "policies": [_policy_summary(p) for p in policies]}


@router.get("/policies/{code}")
def get_effective_policy(
    code: str,
    db: Session = Depends(get_db),
    token: ServiceToken = Depends(require_service_token),
) -> dict:
    """A versão EM VIGOR da política — o endpoint principal de consumo."""
    _apply_due(db)
    policy = _policy_by_code(db, code)
    if policy.current_version is None:
        raise HTTPException(status_code=404, detail=f"política sem versão vigente: {code}")
    return _version_payload(db, policy, policy.current_version)


@router.get("/policies/{code}/versions")
def list_versions(
    code: str,
    db: Session = Depends(get_db),
    token: ServiceToken = Depends(require_service_token),
) -> dict:
    """Histórico público (vigente, substituídas, arquivadas) — sem corpo."""
    _apply_due(db)
    policy = _policy_by_code(db, code)
    versions = [
        v
        for v in sorted(policy.versions, key=lambda v: v.version_number, reverse=True)
        if v.status in PUBLIC_STATUSES
    ]
    items = []
    for version in versions:
        publication = _publication_of(db, version)
        items.append(
            {
                "number": version.version_number,
                "status": version.status,
                "content_hash": version.content_hash,
                "effective_from": (
                    publication.effective_from.isoformat() if publication else None
                ),
                "effective_until": (
                    publication.effective_until.isoformat()
                    if publication and publication.effective_until
                    else None
                ),
            }
        )
    return {"policy": _policy_summary(policy), "count": len(items), "versions": items}


@router.get("/policies/{code}/versions/{number}")
def get_version(
    code: str,
    number: int,
    db: Session = Depends(get_db),
    token: ServiceToken = Depends(require_service_token),
) -> dict:
    """Uma versão pública específica, com conteúdo."""
    _apply_due(db)
    policy = _policy_by_code(db, code)
    version = next(
        (
            v
            for v in policy.versions
            if v.version_number == number and v.status in PUBLIC_STATUSES
        ),
        None,
    )
    if version is None:
        raise HTTPException(status_code=404, detail=f"versão pública não encontrada: v{number}")
    return _version_payload(db, policy, version)


@router.get("/policies/{code}/effective")
def get_effective_at(
    code: str,
    at: str,
    db: Session = Depends(get_db),
    token: ServiceToken = Depends(require_service_token),
) -> dict:
    """Time travel: a versão que vigorava na data `at` (AAAA-MM-DD)."""
    _apply_due(db)
    policy = _policy_by_code(db, code)
    try:
        target = date.fromisoformat(at)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="data inválida (use AAAA-MM-DD)") from exc
    version = version_service.version_at(db, policy.id, target)
    if version is None:
        raise HTTPException(
            status_code=404, detail=f"nenhuma versão vigente em {target.isoformat()}"
        )
    return _version_payload(db, policy, version)
