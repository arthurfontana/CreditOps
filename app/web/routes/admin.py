"""Administração: usuários e cadastros de apoio (área, produto, segmento, tag)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import require_role
from app.db import get_db
from app.models import Area, Product, Role, Segment, Tag, User
from app.services import audit_service, user_service
from app.services.errors import DomainError, NotFound
from app.web.csrf import csrf_protect
from app.web.templating import render

router = APIRouter(prefix="/admin")

admin_only = require_role(Role.ADMIN)

CATALOGS = {
    "areas": (Area, "Áreas"),
    "products": (Product, "Produtos"),
    "segments": (Segment, "Segmentos"),
}


# ── usuários ────────────────────────────────────────────────────────────────


@router.get("/users")
def list_users(
    request: Request,
    msg: str = "",
    db: Session = Depends(get_db),
    user: User = Depends(admin_only),
):
    users = list(db.scalars(select(User).order_by(User.display_name)))
    return render(request, "admin/users.html", user, users=users, msg=msg)


@router.get("/users/new")
def new_user_form(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(admin_only),
):
    areas = list(db.scalars(select(Area).where(Area.is_active).order_by(Area.name)))
    return render(request, "admin/user_form.html", user, target=None, areas=areas, msg="")


@router.post("/users")
def create_user(
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
    display_name: str = Form(...),
    role: str = Form(...),
    password: str = Form(...),
    area_id: str = Form(""),
    is_auditor: bool = Form(False),
    db: Session = Depends(get_db),
    user: User = Depends(admin_only),
    _csrf: None = Depends(csrf_protect),
):
    try:
        user_service.create_user(
            db, user,
            username=username, email=email, display_name=display_name,
            role=role, password=password, area_id=area_id or None,
            is_auditor=is_auditor,
        )
    except DomainError as exc:
        areas = list(db.scalars(select(Area).where(Area.is_active)))
        return render(
            request, "admin/user_form.html", user, target=None, areas=areas, msg=str(exc)
        )
    db.commit()
    return RedirectResponse("/admin/users?msg=Usu%C3%A1rio+criado", status_code=303)


@router.get("/users/{user_id}/edit")
def edit_user_form(
    request: Request,
    user_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(admin_only),
):
    target = db.get(User, user_id)
    if target is None:
        raise NotFound("usuário não encontrado")
    areas = list(db.scalars(select(Area).where(Area.is_active).order_by(Area.name)))
    return render(request, "admin/user_form.html", user, target=target, areas=areas, msg="")


@router.post("/users/{user_id}/edit")
def edit_user(
    request: Request,
    user_id: str,
    email: str = Form(...),
    display_name: str = Form(...),
    role: str = Form(...),
    area_id: str = Form(""),
    is_active: bool = Form(False),
    is_auditor: bool = Form(False),
    db: Session = Depends(get_db),
    user: User = Depends(admin_only),
    _csrf: None = Depends(csrf_protect),
):
    try:
        user_service.update_user(
            db, user, user_id,
            email=email, display_name=display_name, role=role,
            area_id=area_id or None, is_active=is_active, is_auditor=is_auditor,
        )
    except DomainError as exc:
        return RedirectResponse(f"/admin/users?msg={exc}", status_code=303)
    db.commit()
    return RedirectResponse("/admin/users?msg=Usu%C3%A1rio+atualizado", status_code=303)


@router.post("/users/{user_id}/reset-password")
def reset_password(
    request: Request,
    user_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(admin_only),
    _csrf: None = Depends(csrf_protect),
):
    try:
        temp = user_service.reset_password(db, user, user_id)
    except DomainError as exc:
        return RedirectResponse(f"/admin/users?msg={exc}", status_code=303)
    db.commit()
    return RedirectResponse(
        f"/admin/users?msg=Senha+tempor%C3%A1ria:+{temp}", status_code=303
    )


# ── cadastros (área / produto / segmento) ───────────────────────────────────


@router.get("/catalogs/{kind}")
def list_catalog(
    request: Request,
    kind: str,
    msg: str = "",
    db: Session = Depends(get_db),
    user: User = Depends(admin_only),
):
    if kind not in CATALOGS:
        raise NotFound("cadastro não encontrado")
    model, label = CATALOGS[kind]
    items = list(db.scalars(select(model).order_by(model.name)))
    return render(
        request, "admin/catalog.html", user, kind=kind, label=label, items=items, msg=msg
    )


@router.post("/catalogs/{kind}")
def create_catalog_item(
    request: Request,
    kind: str,
    name: str = Form(...),
    code: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(admin_only),
    _csrf: None = Depends(csrf_protect),
):
    if kind not in CATALOGS:
        raise NotFound("cadastro não encontrado")
    model, _ = CATALOGS[kind]
    code = code.strip().upper()
    if not name.strip() or not code:
        return RedirectResponse(
            f"/admin/catalogs/{kind}?msg=Nome+e+c%C3%B3digo+obrigat%C3%B3rios", status_code=303
        )
    if db.scalars(select(model).where(model.code == code)).first():
        return RedirectResponse(
            f"/admin/catalogs/{kind}?msg=C%C3%B3digo+j%C3%A1+existe", status_code=303
        )
    item = model(name=name.strip(), code=code)
    db.add(item)
    db.flush()
    audit_service.record(
        db, user.id, f"{model.__tablename__}.created", model.__tablename__, item.id,
        {"name": item.name, "code": item.code},
    )
    db.commit()
    return RedirectResponse(f"/admin/catalogs/{kind}?msg=Criado", status_code=303)


@router.post("/catalogs/{kind}/{item_id}/toggle")
def toggle_catalog_item(
    request: Request,
    kind: str,
    item_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(admin_only),
    _csrf: None = Depends(csrf_protect),
):
    if kind not in CATALOGS:
        raise NotFound("cadastro não encontrado")
    model, _ = CATALOGS[kind]
    item = db.get(model, item_id)
    if item is None:
        raise NotFound("item não encontrado")
    item.is_active = not item.is_active
    db.flush()
    audit_service.record(
        db, user.id, f"{model.__tablename__}.updated", model.__tablename__, item.id,
        {"is_active": {"before": not item.is_active, "after": item.is_active}},
    )
    db.commit()
    return RedirectResponse(f"/admin/catalogs/{kind}", status_code=303)


# ── tags ────────────────────────────────────────────────────────────────────


@router.get("/tags")
def list_tags(
    request: Request,
    msg: str = "",
    db: Session = Depends(get_db),
    user: User = Depends(admin_only),
):
    tags = list(db.scalars(select(Tag).order_by(Tag.name)))
    return render(request, "admin/tags.html", user, tags=tags, msg=msg)


@router.post("/tags")
def create_tag(
    request: Request,
    name: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(admin_only),
    _csrf: None = Depends(csrf_protect),
):
    name = name.strip().lower()
    if not name:
        return RedirectResponse("/admin/tags?msg=Nome+obrigat%C3%B3rio", status_code=303)
    if db.scalars(select(Tag).where(Tag.name == name)).first():
        return RedirectResponse("/admin/tags?msg=Tag+j%C3%A1+existe", status_code=303)
    tag = Tag(name=name)
    db.add(tag)
    db.flush()
    audit_service.record(db, user.id, "tag.created", "tag", tag.id, {"name": name})
    db.commit()
    return RedirectResponse("/admin/tags?msg=Tag+criada", status_code=303)
