"""Delegação de aprovação (v1)."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import current_user, require_role
from app.db import get_db
from app.models import Role, User
from app.services import delegation_service
from app.services.errors import DomainError
from app.web.csrf import csrf_protect
from app.web.templating import render

router = APIRouter()


@router.get("/delegations")
def list_delegations(
    request: Request,
    msg: str = "",
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    delegations = delegation_service.list_delegations(db, user)
    approvers = list(
        db.scalars(
            select(User)
            .where(User.role == Role.APPROVER.value, User.is_active, User.id != user.id)
            .order_by(User.display_name)
        )
    )
    return render(
        request, "delegations/list.html", user,
        delegations=delegations, approvers=approvers, msg=msg, today=date.today(),
    )


@router.post("/delegations")
def create_delegation(
    request: Request,
    delegate_id: str = Form(...),
    starts_at: str = Form(...),
    ends_at: str = Form(...),
    reason: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_role(Role.APPROVER)),
    _csrf: None = Depends(csrf_protect),
):
    try:
        delegation_service.create_delegation(
            db, user,
            delegate_id=delegate_id,
            starts_at=date.fromisoformat(starts_at),
            ends_at=date.fromisoformat(ends_at),
            reason=reason,
        )
    except ValueError:
        return RedirectResponse("/delegations?msg=Datas+inv%C3%A1lidas", status_code=303)
    except DomainError as exc:
        return RedirectResponse(f"/delegations?msg={exc}", status_code=303)
    db.commit()
    return RedirectResponse("/delegations?msg=Delega%C3%A7%C3%A3o+criada", status_code=303)


@router.post("/delegations/{delegation_id}/revoke")
def revoke_delegation(
    request: Request,
    delegation_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
    _csrf: None = Depends(csrf_protect),
):
    try:
        delegation_service.revoke_delegation(db, user, delegation_id)
    except DomainError as exc:
        return RedirectResponse(f"/delegations?msg={exc}", status_code=303)
    db.commit()
    return RedirectResponse("/delegations?msg=Delega%C3%A7%C3%A3o+revogada", status_code=303)
