"""Ações do workflow: submeter, revisar, aprovar, rejeitar, publicar."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.auth.deps import current_user, require_role
from app.db import get_db
from app.models import Role, User
from app.services import (
    comment_service,
    delegation_service,
    diff_service,
    impact_service,
    policy_service,
    release_service,
    search_service,
    version_service,
    workflow_service,
)
from app.services.errors import DomainError
from app.web.csrf import csrf_protect
from app.web.templating import render

router = APIRouter()


def _back(version_id: str, msg: str) -> RedirectResponse:
    return RedirectResponse(f"/versions/{version_id}?msg={msg}", status_code=303)


@router.post("/versions/{version_id}/submit")
def submit(
    request: Request,
    version_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
    _csrf: None = Depends(csrf_protect),
):
    try:
        workflow_service.submit_for_review(db, user, version_id)
    except DomainError as exc:
        return _back(version_id, str(exc))
    db.commit()
    return _back(version_id, "Enviada para revisão")


@router.post("/versions/{version_id}/request-changes")
def request_changes(
    request: Request,
    version_id: str,
    reason: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
    _csrf: None = Depends(csrf_protect),
):
    try:
        workflow_service.request_changes(db, user, version_id, reason)
    except DomainError as exc:
        return _back(version_id, str(exc))
    db.commit()
    return _back(version_id, "Devolvida para ajustes")


@router.post("/versions/{version_id}/send-to-approval")
def send_to_approval(
    request: Request,
    version_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
    _csrf: None = Depends(csrf_protect),
):
    try:
        workflow_service.send_to_approval(db, user, version_id)
    except DomainError as exc:
        return _back(version_id, str(exc))
    db.commit()
    return _back(version_id, "Enviada para aprovação")


@router.get("/versions/{version_id}/review")
def review_screen(
    request: Request,
    version_id: str,
    msg: str = "",
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """Tela do aprovador: diff contra a vigente + justificativa + impacto +
    comentários — tudo em uma página, decisão em 2 minutos."""
    version = version_service.get_version(db, version_id)
    policy = policy_service.get_policy(db, user, version.policy_id)
    current = policy.current_version
    rows = diff_service.side_by_side(current, version) if current else None
    stats = diff_service.stats(current, version) if current else None
    field_changes = diff_service.field_diff(current, version) if current else []
    comments = comment_service.list_for_version(db, version.id)
    approved_levels, required_levels = workflow_service.approval_progress(db, version)
    delegations = delegation_service.active_delegations_to(db, user.id)
    releases = release_service.open_releases(db)
    metrics = impact_service.metrics_for_version(db, version.id)
    return render(
        request, "version/review.html", user,
        version=version, policy=policy, current=current,
        rows=rows, stats=stats, field_changes=field_changes,
        comments=comments, msg=msg, today=date.today(),
        approved_levels=approved_levels, required_levels=required_levels,
        delegations=delegations, releases=releases, metrics=metrics,
    )


@router.post("/versions/{version_id}/approve")
def approve(
    request: Request,
    version_id: str,
    justification: str = Form(""),
    on_behalf_of: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_role(Role.APPROVER)),
    _csrf: None = Depends(csrf_protect),
):
    try:
        version = workflow_service.approve(
            db, user, version_id, justification, on_behalf_of=on_behalf_of or None
        )
    except DomainError as exc:
        return _back(version_id, str(exc))
    db.commit()
    done, required = workflow_service.approval_progress(db, version)
    if version.status == "in_approval":
        return _back(
            version_id,
            f"N%C3%ADvel+{done}+de+{required}+aprovado+—+aguardando+pr%C3%B3ximo+n%C3%ADvel",
        )
    return _back(version_id, "Vers%C3%A3o+aprovada")


@router.post("/versions/{version_id}/reject")
def reject(
    request: Request,
    version_id: str,
    justification: str = Form(""),
    on_behalf_of: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_role(Role.APPROVER)),
    _csrf: None = Depends(csrf_protect),
):
    try:
        workflow_service.reject(
            db, user, version_id, justification, on_behalf_of=on_behalf_of or None
        )
    except DomainError as exc:
        return _back(version_id, str(exc))
    db.commit()
    return _back(version_id, "Vers%C3%A3o+rejeitada+—+devolvida+ao+autor")


@router.post("/versions/{version_id}/publish")
def publish(
    request: Request,
    version_id: str,
    effective_from: str = Form(...),
    release_id: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_role(Role.APPROVER)),
    _csrf: None = Depends(csrf_protect),
):
    try:
        effective = date.fromisoformat(effective_from)
    except ValueError:
        return _back(version_id, "Data+de+vig%C3%AAncia+inv%C3%A1lida")
    try:
        version = workflow_service.publish(
            db, user, version_id, effective, release_id=release_id or None
        )
    except DomainError as exc:
        return _back(version_id, str(exc))
    search_service.reindex_policy(db, version.policy_id)
    db.commit()
    return _back(version_id, "Vers%C3%A3o+publicada")
