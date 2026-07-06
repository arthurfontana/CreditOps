"""Releases (v1): pacotes de publicação."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.auth.deps import current_user, require_role
from app.db import get_db
from app.models import Role, User
from app.services import release_service
from app.services.errors import DomainError
from app.web.csrf import csrf_protect
from app.web.templating import render

router = APIRouter()


@router.get("/releases")
def list_releases(
    request: Request,
    msg: str = "",
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    releases = release_service.list_releases(db, user)
    counts = {r.id: len(release_service.publications_of(db, r.id)) for r in releases}
    return render(request, "releases/list.html", user, releases=releases, counts=counts, msg=msg)


@router.post("/releases")
def create_release(
    request: Request,
    name: str = Form(...),
    description: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_role(Role.APPROVER, Role.ADMIN)),
    _csrf: None = Depends(csrf_protect),
):
    try:
        release = release_service.create_release(db, user, name=name, description=description)
    except DomainError as exc:
        return RedirectResponse(f"/releases?msg={exc}", status_code=303)
    db.commit()
    return RedirectResponse(f"/releases/{release.id}?msg=Release+criada", status_code=303)


@router.get("/releases/{release_id}")
def release_detail(
    request: Request,
    release_id: str,
    msg: str = "",
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    release = release_service.get_release(db, release_id)
    publications = release_service.publications_of(db, release_id)
    return render(
        request, "releases/detail.html", user,
        release=release, publications=publications, msg=msg,
    )
