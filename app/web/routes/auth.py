"""Login, logout e troca de senha."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.auth.deps import current_user
from app.auth.sessions import clear_session_cookie, set_session_cookie
from app.db import get_db
from app.models import User
from app.services import user_service
from app.services.errors import ValidationFailed
from app.services.user_service import AuthenticationFailed
from app.web.csrf import csrf_protect
from app.web.templating import render

router = APIRouter()


def _safe_next(next_url: str) -> str:
    # apenas caminhos internos — evita open redirect
    if not next_url.startswith("/") or next_url.startswith("//"):
        return "/"
    return next_url


@router.get("/login")
def login_form(request: Request, next: str = "/", msg: str = ""):
    return render(request, "auth/login.html", None, next=_safe_next(next), msg=msg)


@router.post("/login")
def login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    next: str = Form("/"),
    db: Session = Depends(get_db),
):
    try:
        user = user_service.authenticate(db, username, password)
    except AuthenticationFailed as exc:
        db.commit()  # persiste contadores de falha e auditoria
        return render(
            request, "auth/login.html", None, next=_safe_next(next), msg=str(exc)
        )
    db.commit()
    target = "/change-password" if user.must_change_password else _safe_next(next)
    response = RedirectResponse(target, status_code=303)
    set_session_cookie(response, user.id)
    return response


@router.post("/logout")
def logout(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
    _csrf: None = Depends(csrf_protect),
):
    user_service.record_logout(db, user)
    db.commit()
    response = RedirectResponse("/login", status_code=303)
    clear_session_cookie(response)
    return response


@router.get("/change-password")
def change_password_form(request: Request, user: User = Depends(current_user), msg: str = ""):
    return render(request, "auth/change_password.html", user, msg=msg)


@router.post("/change-password")
def change_password(
    request: Request,
    current_password: str = Form(...),
    new_password: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
    _csrf: None = Depends(csrf_protect),
):
    try:
        user_service.change_password(db, user, current_password, new_password)
    except ValidationFailed as exc:
        return render(request, "auth/change_password.html", user, msg=str(exc))
    db.commit()
    return RedirectResponse("/?msg=Senha+alterada", status_code=303)
