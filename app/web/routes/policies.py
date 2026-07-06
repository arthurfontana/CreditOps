"""Catálogo, detalhe, histórico, time travel, comparação e ações da política."""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import current_user, require_role
from app.db import get_db
from app.models import (
    Area,
    PolicyType,
    PolicyVersion,
    Product,
    Publication,
    Role,
    Segment,
    Tag,
    User,
)
from app.services import (
    diff_service,
    policy_service,
    search_service,
    version_service,
    workflow_service,
)
from app.services.errors import DomainError, NotFound, ValidationFailed
from app.services.policy_service import PolicyFilters
from app.web.csrf import csrf_protect
from app.web.templating import render

router = APIRouter()


def _catalog_context(db: Session) -> dict:
    return {
        "areas": list(db.scalars(select(Area).where(Area.is_active).order_by(Area.name))),
        "products": list(
            db.scalars(select(Product).where(Product.is_active).order_by(Product.name))
        ),
        "segments": list(
            db.scalars(select(Segment).where(Segment.is_active).order_by(Segment.name))
        ),
        "tags": list(db.scalars(select(Tag).order_by(Tag.name))),
        "policy_types": [t.value for t in PolicyType],
    }


def _publication_of(db: Session, version: PolicyVersion | None) -> Publication | None:
    if version is None:
        return None
    return db.scalars(select(Publication).where(Publication.version_id == version.id)).first()


@router.get("/policies")
def list_policies(
    request: Request,
    area_id: str = "",
    product_id: str = "",
    segment_id: str = "",
    policy_type: str = "",
    tag_id: str = "",
    text: str = "",
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    filters = PolicyFilters(
        area_id=area_id or None,
        product_id=product_id or None,
        segment_id=segment_id or None,
        policy_type=policy_type or None,
        tag_id=tag_id or None,
        text=text or None,
    )
    policies = policy_service.list_policies(db, user, filters)
    publications = {
        p.id: _publication_of(db, p.current_version) for p in policies
    }
    template = (
        "policy/_table.html" if request.headers.get("HX-Request") else "policy/list.html"
    )
    return render(
        request, template, user,
        policies=policies, publications=publications,
        filters=filters, **_catalog_context(db),
    )


@router.get("/policies/new")
def new_policy_form(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(Role.AUTHOR, Role.ADMIN)),
):
    authors = list(db.scalars(select(User).where(User.is_active).order_by(User.display_name)))
    return render(request, "policy/new.html", user, owners=authors, **_catalog_context(db))


@router.post("/policies")
def create_policy(
    request: Request,
    title: str = Form(...),
    policy_type: str = Form(...),
    area_id: str = Form(...),
    owner_id: str = Form(...),
    product_ids: list[str] = Form([]),
    segment_ids: list[str] = Form([]),
    tag_ids: list[str] = Form([]),
    db: Session = Depends(get_db),
    user: User = Depends(require_role(Role.AUTHOR, Role.ADMIN)),
    _csrf: None = Depends(csrf_protect),
):
    try:
        policy = policy_service.create_policy(
            db, user,
            title=title, policy_type=policy_type, area_id=area_id, owner_id=owner_id,
            product_ids=product_ids, segment_ids=segment_ids, tag_ids=tag_ids,
        )
    except DomainError as exc:
        authors = list(db.scalars(select(User).where(User.is_active)))
        return render(
            request, "policy/new.html", user, owners=authors, msg=str(exc),
            **_catalog_context(db),
        )
    db.commit()
    return RedirectResponse(f"/policies/{policy.id}?msg=Pol%C3%ADtica+criada", status_code=303)


@router.get("/policies/{policy_id}")
def policy_detail(
    request: Request,
    policy_id: str,
    msg: str = "",
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    # verificação lazy de vigência ao carregar a política
    if workflow_service.apply_due_publications(db):
        db.commit()
    policy = policy_service.get_policy(db, user, policy_id)
    versions = policy_service.visible_versions(db, user, policy)
    open_version = version_service.open_version(db, policy.id)
    publication = _publication_of(db, policy.current_version)
    return render(
        request, "policy/detail.html", user,
        policy=policy, versions=versions, open_version=open_version,
        publication=publication, msg=msg,
    )


@router.get("/policies/{policy_id}/history")
def policy_history(
    request: Request,
    policy_id: str,
    at: str = "",
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    policy = policy_service.get_policy(db, user, policy_id)
    versions = policy_service.visible_versions(db, user, policy)
    publications = {
        v.id: _publication_of(db, v) for v in versions
    }
    at_version = None
    at_date = None
    if at:
        try:
            at_date = date.fromisoformat(at)
        except ValueError as exc:
            raise ValidationFailed("data inválida (use AAAA-MM-DD)") from exc
        at_version = version_service.version_at(db, policy.id, at_date)
    return render(
        request, "policy/history.html", user,
        policy=policy, versions=versions, publications=publications,
        at_date=at_date, at_version=at_version,
    )


@router.get("/policies/{policy_id}/compare")
def policy_compare(
    request: Request,
    policy_id: str,
    from_version: int = 0,
    to_version: int = 0,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    policy = policy_service.get_policy(db, user, policy_id)
    versions = policy_service.visible_versions(db, user, policy)
    by_number = {v.version_number: v for v in versions}
    a = by_number.get(from_version)
    b = by_number.get(to_version)
    rows = unified = stats = None
    if a is not None and b is not None:
        rows = diff_service.side_by_side(a, b)
        unified = diff_service.unified(a, b)
        stats = diff_service.stats(a, b)
    return render(
        request, "policy/compare.html", user,
        policy=policy, versions=versions,
        from_version=a, to_version=b, rows=rows, unified=unified, stats=stats,
    )


@router.get("/policies/{policy_id}/edit")
def edit_policy_form(
    request: Request,
    policy_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(Role.AUTHOR, Role.ADMIN)),
):
    policy = policy_service.get_policy(db, user, policy_id)
    owners = list(db.scalars(select(User).where(User.is_active).order_by(User.display_name)))
    return render(
        request, "policy/edit.html", user, policy=policy, owners=owners,
        **_catalog_context(db),
    )


@router.post("/policies/{policy_id}/edit")
def edit_policy(
    request: Request,
    policy_id: str,
    title: str = Form(...),
    owner_id: str = Form(...),
    product_ids: list[str] = Form([]),
    segment_ids: list[str] = Form([]),
    tag_ids: list[str] = Form([]),
    db: Session = Depends(get_db),
    user: User = Depends(require_role(Role.AUTHOR, Role.ADMIN)),
    _csrf: None = Depends(csrf_protect),
):
    policy_service.update_policy_metadata(
        db, user, policy_id,
        title=title, owner_id=owner_id,
        product_ids=product_ids, segment_ids=segment_ids, tag_ids=tag_ids,
    )
    search_service.reindex_policy(db, policy_id)
    db.commit()
    return RedirectResponse(f"/policies/{policy_id}?msg=Metadados+atualizados", status_code=303)


@router.post("/policies/{policy_id}/revisions")
def create_revision(
    request: Request,
    policy_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(Role.AUTHOR, Role.ADMIN)),
    _csrf: None = Depends(csrf_protect),
):
    try:
        version = version_service.create_revision(db, user, policy_id)
    except DomainError as exc:
        return RedirectResponse(f"/policies/{policy_id}?msg={exc}", status_code=303)
    db.commit()
    return RedirectResponse(f"/versions/{version.id}/edit", status_code=303)


@router.post("/policies/{policy_id}/rollback")
def rollback(
    request: Request,
    policy_id: str,
    target_version_id: str = Form(...),
    reason: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_role(Role.APPROVER)),
    _csrf: None = Depends(csrf_protect),
):
    try:
        version = workflow_service.rollback(db, user, policy_id, target_version_id, reason)
    except DomainError as exc:
        return RedirectResponse(f"/policies/{policy_id}/history?msg={exc}", status_code=303)
    db.commit()
    return RedirectResponse(
        f"/versions/{version.id}/review?msg=Rollback+criado+—+aguardando+aprova%C3%A7%C3%A3o",
        status_code=303,
    )


@router.post("/policies/{policy_id}/archive")
def archive_policy(
    request: Request,
    policy_id: str,
    reason: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_role(Role.APPROVER)),
    _csrf: None = Depends(csrf_protect),
):
    try:
        policy_service.archive_policy(db, user, policy_id, reason)
    except DomainError as exc:
        return RedirectResponse(f"/policies/{policy_id}?msg={exc}", status_code=303)
    search_service.reindex_policy(db, policy_id)
    db.commit()
    return RedirectResponse(f"/policies/{policy_id}?msg=Pol%C3%ADtica+arquivada", status_code=303)


@router.get("/versions/{version_id}/at-view")
def version_at_view(
    request: Request,
    version_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    version = version_service.get_version(db, version_id)
    policy = policy_service.get_policy(db, user, version.policy_id)
    if version not in policy_service.visible_versions(db, user, policy):
        raise NotFound("versão não encontrada")
    publication = _publication_of(db, version)
    return render(
        request, "version/view.html", user,
        version=version, policy=policy, publication=publication,
        historical=True, comments=[], attachments=[],
    )
