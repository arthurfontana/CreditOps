"""Biblioteca de cineminhas e catálogo de variáveis de decisão."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.auth.deps import current_user, require_role
from app.db import get_db
from app.models import Role, User
from app.services import cinema_service
from app.services.errors import DomainError
from app.web.csrf import csrf_protect
from app.web.templating import render

router = APIRouter()


def _with_domain(variables):
    for v in variables:
        v.domain_list = cinema_service.variable_domain(v)
    return variables


def _grid_config(
    *,
    cinema,
    row_domain: list[str],
    col_domain: list[str],
    cells: dict,
    baseline: dict | None,
) -> str:
    """JSON consumido por static/js/cinema-grid.js."""
    return json.dumps(
        {
            "cinemaType": cinema.cinema_type,
            "rowDomain": row_domain,
            "colDomain": col_domain,
            "cells": cells,
            "baseline": baseline,
            "rowLabel": cinema.row_variable.label,
            "colLabel": cinema.col_variable.label,
        },
        ensure_ascii=False,
    )


# ── Biblioteca ───────────────────────────────────────────────────────────────


@router.get("/cinemas")
def list_cinemas(
    request: Request,
    msg: str = "",
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    return render(
        request, "cinemas/list.html", user,
        cinemas=cinema_service.list_cinemas(db, include_inactive=True), msg=msg,
    )


@router.get("/cinemas/new")
def new_cinema_form(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(Role.AUTHOR, Role.APPROVER, Role.ADMIN)),
):
    return render(
        request, "cinemas/new.html", user, variables=cinema_service.list_variables(db),
    )


@router.post("/cinemas")
def create_cinema(
    request: Request,
    name: str = Form(...),
    description: str = Form(""),
    cinema_type: str = Form(...),
    row_variable_id: str = Form(...),
    col_variable_id: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_role(Role.AUTHOR, Role.APPROVER, Role.ADMIN)),
    _csrf: None = Depends(csrf_protect),
):
    try:
        cinema = cinema_service.create_cinema(
            db, user,
            name=name, description=description, cinema_type=cinema_type,
            row_variable_id=row_variable_id, col_variable_id=col_variable_id,
        )
    except DomainError as exc:
        return render(
            request, "cinemas/new.html", user,
            variables=cinema_service.list_variables(db), msg=str(exc),
        )
    db.commit()
    return RedirectResponse(f"/cinemas/{cinema.id}?msg=Cineminha+criado", status_code=303)


@router.get("/cinemas/{cinema_id}")
def cinema_detail(
    request: Request,
    cinema_id: str,
    msg: str = "",
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    cinema = cinema_service.get_cinema(db, cinema_id)
    current = cinema.current_version
    current_view = None
    if current is not None:
        current_view = cinema_service.matrix_view(
            cinema_type=cinema.cinema_type,
            row_domain_json=current.row_domain_json,
            col_domain_json=current.col_domain_json,
            cells_json=current.cells_json,
        )
    return render(
        request, "cinemas/detail.html", user,
        cinema=cinema, current_view=current_view,
        history=cinema_service.version_history(db, cinema_id), msg=msg,
    )


@router.get("/cinemas/{cinema_id}/baseline")
def baseline_form(
    request: Request,
    cinema_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(Role.AUTHOR, Role.APPROVER, Role.ADMIN)),
):
    cinema = cinema_service.get_cinema(db, cinema_id)
    current = cinema.current_version
    if current is not None:
        row_domain = json.loads(current.row_domain_json)
        col_domain = json.loads(current.col_domain_json)
        cells = json.loads(current.cells_json)
    else:
        row_domain = cinema_service.variable_domain(cinema.row_variable)
        col_domain = cinema_service.variable_domain(cinema.col_variable)
        cells = {}
    return render(
        request, "cinemas/baseline.html", user,
        cinema=cinema,
        grid_config=_grid_config(
            cinema=cinema, row_domain=row_domain, col_domain=col_domain,
            cells=cells, baseline=None,
        ),
    )


@router.post("/cinemas/{cinema_id}/baseline")
def save_baseline(
    request: Request,
    cinema_id: str,
    cells_json: str = Form("{}"),
    db: Session = Depends(get_db),
    user: User = Depends(require_role(Role.AUTHOR, Role.APPROVER, Role.ADMIN)),
    _csrf: None = Depends(csrf_protect),
):
    try:
        cells = json.loads(cells_json or "{}")
    except json.JSONDecodeError:
        return RedirectResponse(
            f"/cinemas/{cinema_id}?msg=Caselas+inv%C3%A1lidas", status_code=303
        )
    try:
        version = cinema_service.create_manual_version(db, user, cinema_id, cells=cells)
    except DomainError as exc:
        return RedirectResponse(f"/cinemas/{cinema_id}?msg={exc}", status_code=303)
    db.commit()
    return RedirectResponse(
        f"/cinemas/{cinema_id}?msg=Vers%C3%A3o+v{version.version_number}+gravada",
        status_code=303,
    )


# ── Catálogo de variáveis ────────────────────────────────────────────────────


@router.get("/variables")
def list_variables(
    request: Request,
    msg: str = "",
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    return render(
        request, "cinemas/variables.html", user,
        variables=_with_domain(cinema_service.list_variables(db, include_inactive=True)),
        msg=msg,
    )


@router.post("/variables")
def create_variable(
    request: Request,
    name: str = Form(...),
    label: str = Form(""),
    domain: str = Form(...),
    is_ordinal: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_role(Role.AUTHOR, Role.APPROVER, Role.ADMIN)),
    _csrf: None = Depends(csrf_protect),
):
    try:
        cinema_service.create_variable(
            db, user, name=name, label=label, domain=domain, is_ordinal=bool(is_ordinal),
        )
    except DomainError as exc:
        return RedirectResponse(f"/variables?msg={exc}", status_code=303)
    db.commit()
    return RedirectResponse("/variables?msg=Vari%C3%A1vel+criada", status_code=303)


@router.get("/variables/{variable_id}/edit")
def edit_variable_form(
    request: Request,
    variable_id: str,
    msg: str = "",
    db: Session = Depends(get_db),
    user: User = Depends(require_role(Role.AUTHOR, Role.APPROVER, Role.ADMIN)),
):
    variable = cinema_service.get_variable(db, variable_id)
    variable.domain_list = cinema_service.variable_domain(variable)
    return render(request, "cinemas/variable_edit.html", user, variable=variable, msg=msg)


@router.post("/variables/{variable_id}/edit")
def edit_variable(
    request: Request,
    variable_id: str,
    label: str = Form(""),
    description: str = Form(""),
    domain: str = Form(...),
    is_ordinal: str = Form(""),
    is_active: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_role(Role.AUTHOR, Role.APPROVER, Role.ADMIN)),
    _csrf: None = Depends(csrf_protect),
):
    try:
        cinema_service.update_variable(
            db, user, variable_id,
            label=label, description=description, domain=domain,
            is_ordinal=bool(is_ordinal), is_active=bool(is_active),
        )
    except DomainError as exc:
        return RedirectResponse(f"/variables/{variable_id}/edit?msg={exc}", status_code=303)
    db.commit()
    return RedirectResponse("/variables?msg=Vari%C3%A1vel+atualizada", status_code=303)
