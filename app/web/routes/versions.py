"""Visualização e edição de versões, comentários e anexos."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import current_user, require_role
from app.db import get_db
from app.models import Attachment, Publication, Role, User
from app.services import (
    attachment_service,
    comment_service,
    policy_service,
    version_service,
)
from app.services.errors import DomainError, NotFound
from app.web.csrf import csrf_protect
from app.web.markdown import render_markdown
from app.web.templating import render

router = APIRouter()


def _load(db: Session, user: User, version_id: str):
    version = version_service.get_version(db, version_id)
    policy = policy_service.get_policy(db, user, version.policy_id)
    if version not in policy_service.visible_versions(db, user, policy):
        raise NotFound("versão não encontrada")
    return version, policy


@router.get("/versions/{version_id}")
def view_version(
    request: Request,
    version_id: str,
    msg: str = "",
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    version, policy = _load(db, user, version_id)
    publication = db.scalars(
        select(Publication).where(Publication.version_id == version.id)
    ).first()
    comments = comment_service.list_for_version(db, version.id)
    attachments = list(
        db.scalars(select(Attachment).where(Attachment.version_id == version.id))
    )
    return render(
        request, "version/view.html", user,
        version=version, policy=policy, publication=publication,
        comments=comments, attachments=attachments, msg=msg, historical=False,
    )


@router.get("/versions/{version_id}/edit")
def edit_version_form(
    request: Request,
    version_id: str,
    msg: str = "",
    db: Session = Depends(get_db),
    user: User = Depends(require_role(Role.AUTHOR, Role.ADMIN)),
):
    version, policy = _load(db, user, version_id)
    attachments = list(
        db.scalars(select(Attachment).where(Attachment.version_id == version.id))
    )
    return render(
        request, "version/edit.html", user,
        version=version, policy=policy, attachments=attachments, msg=msg,
    )


@router.post("/versions/{version_id}/edit")
def save_version(
    request: Request,
    version_id: str,
    body_md: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_role(Role.AUTHOR, Role.ADMIN)),
    _csrf: None = Depends(csrf_protect),
):
    try:
        version_service.update_draft(db, user, version_id, body_md=body_md)
    except DomainError as exc:
        if request.headers.get("HX-Request"):
            return HTMLResponse(f"<span class='save-status error'>{exc}</span>", status_code=400)
        return RedirectResponse(f"/versions/{version_id}/edit?msg={exc}", status_code=303)
    db.commit()
    if request.headers.get("HX-Request"):
        return HTMLResponse(
            f"<span class='save-status'>salvo às {datetime.now().strftime('%H:%M')}</span>"
        )
    return RedirectResponse(f"/versions/{version_id}/edit?msg=Salvo", status_code=303)


@router.post("/versions/{version_id}/preview")
def preview(
    request: Request,
    version_id: str,
    body_md: str = Form(""),
    user: User = Depends(current_user),
):
    return HTMLResponse(f"<div class='md-body'>{render_markdown(body_md)}</div>")


@router.post("/versions/{version_id}/fields")
def save_submission_fields(
    request: Request,
    version_id: str,
    change_summary: str = Form(""),
    expected_impact: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_role(Role.AUTHOR, Role.ADMIN)),
    _csrf: None = Depends(csrf_protect),
):
    try:
        version_service.update_submission_fields(
            db, user, version_id,
            change_summary=change_summary, expected_impact=expected_impact,
        )
    except DomainError as exc:
        return RedirectResponse(f"/versions/{version_id}?msg={exc}", status_code=303)
    db.commit()
    return RedirectResponse(
        f"/versions/{version_id}?msg=Justificativa+e+impacto+salvos", status_code=303
    )


@router.post("/versions/{version_id}/comments")
def add_comment(
    request: Request,
    version_id: str,
    body_md: str = Form(...),
    anchor: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
    _csrf: None = Depends(csrf_protect),
):
    try:
        comment_service.add(db, user, version_id, body_md, anchor or None)
    except DomainError as exc:
        return RedirectResponse(f"/versions/{version_id}?msg={exc}", status_code=303)
    db.commit()
    return RedirectResponse(
        f"/versions/{version_id}?msg=Coment%C3%A1rio+adicionado", status_code=303
    )


@router.post("/comments/{comment_id}/resolve")
def resolve_comment(
    request: Request,
    comment_id: str,
    version_id: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
    _csrf: None = Depends(csrf_protect),
):
    try:
        comment_service.resolve(db, user, comment_id)
    except DomainError as exc:
        return RedirectResponse(f"/versions/{version_id}?msg={exc}", status_code=303)
    db.commit()
    return RedirectResponse(f"/versions/{version_id}", status_code=303)


@router.post("/versions/{version_id}/attachments")
async def upload_attachment(
    request: Request,
    version_id: str,
    file: UploadFile,
    csrf_token: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_role(Role.AUTHOR, Role.ADMIN)),
):
    from app.web.csrf import validate_csrf_token

    if not validate_csrf_token(csrf_token, user.id):
        return RedirectResponse(
            f"/versions/{version_id}/edit?msg=Sess%C3%A3o+inv%C3%A1lida", status_code=303
        )
    content = await file.read()
    try:
        attachment_service.upload(
            db, user, version_id,
            filename=file.filename or "arquivo",
            content=content,
            content_type=file.content_type,
        )
    except DomainError as exc:
        return RedirectResponse(f"/versions/{version_id}/edit?msg={exc}", status_code=303)
    db.commit()
    return RedirectResponse(f"/versions/{version_id}/edit?msg=Anexo+enviado", status_code=303)


@router.get("/attachments/{attachment_id}")
def download_attachment(
    request: Request,
    attachment_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    attachment, content = attachment_service.get_content(db, user, attachment_id)
    db.commit()  # auditoria do download
    return Response(
        content=content,
        media_type=attachment.content_type or "application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{attachment.filename}"'
        },
    )
