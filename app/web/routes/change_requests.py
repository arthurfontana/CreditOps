"""Demandas de mudança (v1): registro, acompanhamento e decisão."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import current_user, require_role
from app.db import get_db
from app.models import (
    Area,
    ChangeRequestPriority,
    ChangeRequestStatus,
    Policy,
    Role,
    User,
)
from app.services import change_request_service
from app.services.change_request_service import ChangeRequestFilters
from app.services.errors import DomainError
from app.web.csrf import csrf_protect
from app.web.templating import render

router = APIRouter()

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
            title=title, description_md=description_md,
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


@router.get("/change-requests/{change_request_id}")
def change_request_detail(
    request: Request,
    change_request_id: str,
    msg: str = "",
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    change_request = change_request_service.get(db, change_request_id)
    return render(
        request, "change_requests/detail.html", user,
        cr=change_request,
        lead_time=change_request_service.lead_time_days(change_request),
        priorities=PRIORITY_LABELS, cr_statuses=STATUS_LABELS, msg=msg,
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
