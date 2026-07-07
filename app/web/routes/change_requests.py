"""Demandas de mudança: registro, edição rica, cineminhas, anexos e export."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Form, Request, UploadFile
from fastapi.responses import RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import current_user, require_role
from app.db import get_db
from app.models import (
    Area,
    Attachment,
    ChangeRequestPriority,
    ChangeRequestStatus,
    Policy,
    Role,
    User,
)
from app.services import attachment_service, change_request_service, cinema_service
from app.services.change_request_service import ChangeRequestFilters
from app.services.errors import DomainError, PermissionDenied, ValidationFailed
from app.web.csrf import csrf_protect
from app.web.markdown import render_markdown
from app.web.templating import render

router = APIRouter()

AUDIT_ACTION_LABELS = {
    "change_request.created": "Demanda registrada",
    "change_request.updated": "Demanda editada",
    "change_request.started": "Marcada em andamento",
    "change_request.done": "Concluída pela vigência",
    "change_request.rejected": "Rejeitada",
    "cinema_instance.created": "Cineminha adicionado",
    "cinema_instance.updated": "Caselas do cineminha alteradas",
    "cinema_instance.removed": "Cineminha removido",
    "cinema_instance.rebased": "Cineminha re-baseado na versão vigente",
    "attachment.uploaded": "Anexo enviado",
}

PRIORITY_LABELS = {
    ChangeRequestPriority.LOW: "Baixa",
    ChangeRequestPriority.MEDIUM: "Média",
    ChangeRequestPriority.HIGH: "Alta",
    ChangeRequestPriority.REGULATORY: "Regulatória",
}

STATUS_LABELS = {
    ChangeRequestStatus.OPEN: "Aberta",
    ChangeRequestStatus.IN_PROGRESS: "Em andamento",
    ChangeRequestStatus.DONE: "Concluída",
    ChangeRequestStatus.REJECTED: "Rejeitada",
}


def _form_context(db: Session) -> dict:
    return {
        "areas": list(db.scalars(select(Area).where(Area.is_active).order_by(Area.name))),
        "policies": list(db.scalars(select(Policy).order_by(Policy.code))),
        "priorities": PRIORITY_LABELS,
        "cr_statuses": STATUS_LABELS,
    }


@router.get("/change-requests")
def list_change_requests(
    request: Request,
    status: str = "",
    area_id: str = "",
    priority: str = "",
    msg: str = "",
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    filters = ChangeRequestFilters(
        status=status or None, area_id=area_id or None, priority=priority or None
    )
    requests_ = change_request_service.list_requests(db, user, filters)
    return render(
        request, "change_requests/list.html", user,
        change_requests=requests_, filters=filters, msg=msg, **_form_context(db),
    )


@router.get("/change-requests/new")
def new_change_request_form(
    request: Request,
    policy_id: str = "",
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    return render(
        request, "change_requests/new.html", user,
        selected_policy_id=policy_id, **_form_context(db),
    )


@router.post("/change-requests")
def create_change_request(
    request: Request,
    title: str = Form(...),
    description_md: str = Form(""),
    description_html: str = Form(""),
    area_id: str = Form(...),
    policy_id: str = Form(""),
    priority: str = Form("medium"),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
    _csrf: None = Depends(csrf_protect),
):
    try:
        change_request = change_request_service.create(
            db, user,
            title=title, description_md=description_md, description_html=description_html,
            area_id=area_id, policy_id=policy_id or None, priority=priority,
        )
    except DomainError as exc:
        return render(
            request, "change_requests/new.html", user,
            selected_policy_id=policy_id, msg=str(exc), **_form_context(db),
        )
    db.commit()
    return RedirectResponse(
        f"/change-requests/{change_request.id}?msg=Demanda+registrada", status_code=303
    )


def _instances_context(db: Session, change_request_id: str) -> list[dict]:
    """Instâncias da demanda com matriz renderizável, diff e aviso de defasagem."""
    return [
        {
            "instance": instance,
            "view": cinema_service.instance_view(instance),
            "stale": cinema_service.is_stale(instance),
        }
        for instance in cinema_service.list_instances(db, change_request_id)
    ]


def _can_edit(db: Session, user: User, change_request) -> bool:
    try:
        change_request_service.ensure_can_edit(db, user, change_request)
        return True
    except (PermissionDenied, ValidationFailed):
        return False


@router.get("/change-requests/{change_request_id}")
def change_request_detail(
    request: Request,
    change_request_id: str,
    msg: str = "",
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    change_request = change_request_service.get(db, change_request_id)
    attachments = list(
        db.scalars(
            select(Attachment)
            .where(Attachment.change_request_id == change_request.id)
            .order_by(Attachment.created_at)
        )
    )
    return render(
        request, "change_requests/detail.html", user,
        cr=change_request,
        lead_time=change_request_service.lead_time_days(change_request),
        priorities=PRIORITY_LABELS, cr_statuses=STATUS_LABELS, msg=msg,
        can_edit=_can_edit(db, user, change_request),
        instances=_instances_context(db, change_request.id),
        library=cinema_service.list_cinemas(db),
        attachments=attachments,
        history=change_request_service.update_history(db, change_request.id),
        audit_labels=AUDIT_ACTION_LABELS,
    )


@router.get("/change-requests/{change_request_id}/edit")
def edit_change_request_form(
    request: Request,
    change_request_id: str,
    msg: str = "",
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    change_request = change_request_service.get(db, change_request_id)
    change_request_service.ensure_can_edit(db, user, change_request)
    # demandas antigas (Markdown) entram no editor já convertidas para HTML
    initial_html = change_request.description_html or render_markdown(
        change_request.description_md
    )
    return render(
        request, "change_requests/edit.html", user,
        cr=change_request, initial_html=initial_html,
        priorities=PRIORITY_LABELS, msg=msg,
    )


@router.post("/change-requests/{change_request_id}/edit")
def save_change_request(
    request: Request,
    change_request_id: str,
    title: str = Form(...),
    description_html: str = Form(""),
    priority: str = Form("medium"),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
    _csrf: None = Depends(csrf_protect),
):
    try:
        change_request_service.update(
            db, user, change_request_id,
            title=title, description_html=description_html, priority=priority,
        )
    except DomainError as exc:
        return RedirectResponse(
            f"/change-requests/{change_request_id}/edit?msg={exc}", status_code=303
        )
    db.commit()
    return RedirectResponse(
        f"/change-requests/{change_request_id}?msg=Demanda+atualizada", status_code=303
    )


@router.post("/change-requests/{change_request_id}/attachments")
async def upload_change_request_attachment(
    request: Request,
    change_request_id: str,
    file: UploadFile,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
    _csrf: None = Depends(csrf_protect),
):
    try:
        content = await file.read()
        attachment_service.upload_for_change_request(
            db, user, change_request_id,
            filename=file.filename or "arquivo",
            content=content,
            content_type=file.content_type,
        )
    except DomainError as exc:
        return RedirectResponse(f"/change-requests/{change_request_id}?msg={exc}", status_code=303)
    db.commit()
    return RedirectResponse(
        f"/change-requests/{change_request_id}?msg=Anexo+enviado", status_code=303
    )


@router.get("/change-requests/{change_request_id}/print")
def print_change_request(
    request: Request,
    change_request_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    change_request = change_request_service.get(db, change_request_id)
    return render(
        request, "change_requests/print.html", user,
        cr=change_request,
        priorities=PRIORITY_LABELS, cr_statuses=STATUS_LABELS,
        instances=_instances_context(db, change_request.id),
        history=change_request_service.update_history(db, change_request.id),
        audit_labels=AUDIT_ACTION_LABELS,
    )


@router.get("/change-requests/{change_request_id}/export.docx")
def export_change_request_docx(
    request: Request,
    change_request_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    from app.services import docx_service

    change_request = change_request_service.get(db, change_request_id)
    content = docx_service.export_change_request_docx(db, change_request)
    db.commit()
    filename = f"{change_request.code}.docx"
    return Response(
        content=content,
        media_type=(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── Cineminhas da demanda ────────────────────────────────────────────────────


@router.post("/change-requests/{change_request_id}/cinemas")
def add_cinema_instance(
    request: Request,
    change_request_id: str,
    cinema_id: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
    _csrf: None = Depends(csrf_protect),
):
    try:
        instance = cinema_service.add_instance(db, user, change_request_id, cinema_id)
    except DomainError as exc:
        return RedirectResponse(f"/change-requests/{change_request_id}?msg={exc}", status_code=303)
    db.commit()
    return RedirectResponse(f"/cinema-instances/{instance.id}", status_code=303)


@router.get("/cinema-instances/{instance_id}")
def edit_cinema_instance_form(
    request: Request,
    instance_id: str,
    msg: str = "",
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    instance = cinema_service.get_instance(db, instance_id)
    baseline = (
        json.loads(instance.source_version.cells_json) if instance.source_version else None
    )
    grid_config = json.dumps(
        {
            "cinemaType": instance.cinema.cinema_type,
            "rowDomain": json.loads(instance.row_domain_json),
            "colDomain": json.loads(instance.col_domain_json),
            "cells": json.loads(instance.cells_json),
            "baseline": baseline,
            "rowLabel": instance.cinema.row_variable.label,
            "colLabel": instance.cinema.col_variable.label,
        },
        ensure_ascii=False,
    )
    return render(
        request, "change_requests/instance_edit.html", user,
        instance=instance, cr=instance.change_request,
        grid_config=grid_config, stale=cinema_service.is_stale(instance), msg=msg,
    )


@router.post("/cinema-instances/{instance_id}")
def save_cinema_instance(
    request: Request,
    instance_id: str,
    cells_json: str = Form("{}"),
    notes: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
    _csrf: None = Depends(csrf_protect),
):
    instance = cinema_service.get_instance(db, instance_id)
    try:
        cells = json.loads(cells_json or "{}")
    except json.JSONDecodeError:
        return RedirectResponse(
            f"/cinema-instances/{instance_id}?msg=Caselas+inv%C3%A1lidas", status_code=303
        )
    try:
        cinema_service.update_instance_cells(db, user, instance_id, cells, notes=notes)
    except DomainError as exc:
        return RedirectResponse(f"/cinema-instances/{instance_id}?msg={exc}", status_code=303)
    db.commit()
    return RedirectResponse(
        f"/change-requests/{instance.change_request_id}?msg=Caselas+salvas", status_code=303
    )


@router.post("/cinema-instances/{instance_id}/remove")
def remove_cinema_instance(
    request: Request,
    instance_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
    _csrf: None = Depends(csrf_protect),
):
    instance = cinema_service.get_instance(db, instance_id)
    change_request_id = instance.change_request_id
    try:
        cinema_service.remove_instance(db, user, instance_id)
    except DomainError as exc:
        return RedirectResponse(f"/change-requests/{change_request_id}?msg={exc}", status_code=303)
    db.commit()
    return RedirectResponse(
        f"/change-requests/{change_request_id}?msg=Cineminha+removido", status_code=303
    )


@router.post("/cinema-instances/{instance_id}/rebase")
def rebase_cinema_instance(
    request: Request,
    instance_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
    _csrf: None = Depends(csrf_protect),
):
    try:
        cinema_service.rebase_instance(db, user, instance_id)
    except DomainError as exc:
        return RedirectResponse(f"/cinema-instances/{instance_id}?msg={exc}", status_code=303)
    db.commit()
    return RedirectResponse(
        f"/cinema-instances/{instance_id}?msg=Re-baseado+na+vers%C3%A3o+vigente", status_code=303
    )


@router.post("/change-requests/{change_request_id}/start")
def start_change_request(
    request: Request,
    change_request_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(Role.AUTHOR, Role.APPROVER, Role.ADMIN)),
    _csrf: None = Depends(csrf_protect),
):
    try:
        change_request_service.start_progress(db, user, change_request_id)
    except DomainError as exc:
        return RedirectResponse(f"/change-requests/{change_request_id}?msg={exc}", status_code=303)
    db.commit()
    return RedirectResponse(
        f"/change-requests/{change_request_id}?msg=Demanda+em+andamento", status_code=303
    )


@router.post("/change-requests/{change_request_id}/reject")
def reject_change_request(
    request: Request,
    change_request_id: str,
    justification: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_role(Role.APPROVER, Role.ADMIN)),
    _csrf: None = Depends(csrf_protect),
):
    try:
        change_request_service.reject(db, user, change_request_id, justification)
    except DomainError as exc:
        return RedirectResponse(f"/change-requests/{change_request_id}?msg={exc}", status_code=303)
    db.commit()
    return RedirectResponse(
        f"/change-requests/{change_request_id}?msg=Demanda+rejeitada", status_code=303
    )
