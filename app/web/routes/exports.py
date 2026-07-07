"""Exportação de políticas: Markdown, JSON e dossiê de auditoria."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Request
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session

from app.auth.deps import current_user
from app.db import get_db
from app.models import User
from app.services import audit_service, export_service, policy_service
from app.services.errors import ValidationFailed

router = APIRouter()


@router.get("/policies/{policy_id}/export.md")
def export_md(
    request: Request,
    policy_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    policy = policy_service.get_policy(db, user, policy_id)
    if policy.current_version is None:
        raise ValidationFailed("política ainda não tem versão vigente")
    content = export_service.export_version_md(db, policy.current_version)
    audit_service.record(
        db, user.id, "export.generated", "policy", policy.id, {"kind": "md"}
    )
    db.commit()
    return Response(
        content=content,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{policy.code}.md"'},
    )


@router.get("/policies/{policy_id}/export.json")
def export_json(
    request: Request,
    policy_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    policy = policy_service.get_policy(db, user, policy_id)
    payload = export_service.export_policy_json(db, policy)
    audit_service.record(
        db, user.id, "export.generated", "policy", policy.id, {"kind": "json"}
    )
    db.commit()
    return Response(
        content=json.dumps(payload, ensure_ascii=False, indent=2),
        media_type="application/json; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{policy.code}.json"'},
    )


@router.get("/policies/{policy_id}/export.pdf")
def export_pdf(
    request: Request,
    policy_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    from app.plugins import registry

    exporter = registry.get_plugin("export_pdf")
    if exporter is None:
        raise ValidationFailed("exportação PDF não está habilitada (plugin export_pdf)")
    policy = policy_service.get_policy(db, user, policy_id)
    if policy.current_version is None:
        raise ValidationFailed("política ainda não tem versão vigente")
    content = export_service.export_version_md(db, policy.current_version)
    pdf = exporter.render(f"{policy.code} — {policy.title}", content.splitlines())
    audit_service.record(
        db, user.id, "export.generated", "policy", policy.id, {"kind": "pdf"}
    )
    db.commit()
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{policy.code}.pdf"'},
    )


@router.get("/policies/{policy_id}/dossier")
def export_dossier(
    request: Request,
    policy_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    policy = policy_service.get_policy(db, user, policy_id)
    path = export_service.export_dossier(db, user, policy)
    db.commit()
    return FileResponse(
        path, media_type="application/zip", filename=path.name
    )
