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
    change_request_service,
    comment_service,
    impact_service,
    implementation_service,
    indicator_service,
    policy_service,
    structured_fields,
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
        field_values=structured_fields.load(version.structured_fields),
        field_defs=structured_fields.defs_for(policy.policy_type),
        metrics=impact_service.metrics_for_version(db, version.id),
        impact_records=(
            impact_service.impact_records_for(db, publication.id) if publication else []
        ),
        implementation_refs=implementation_service.refs_for_version(db, version.id),
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
        field_values=structured_fields.load(version.structured_fields),
        field_defs=structured_fields.defs_for(policy.policy_type),
        indicators=indicator_service.list_active(db),
        metrics=impact_service.metrics_for_version(db, version.id),
        open_change_requests=change_request_service.open_requests(db, policy.area_id),
    )


@router.post("/versions/{version_id}/edit")
async def save_version(
    request: Request,
    version_id: str,
    body_md: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_role(Role.AUTHOR, Role.ADMIN)),
    _csrf: None = Depends(csrf_protect),
):
    try:
        version = version_service.get_version(db, version_id)
        form = await request.form()
        fields_json = structured_fields.parse_form(
            version.policy.policy_type,
            {key[3:]: value for key, value in form.items() if key.startswith("sf_")},
        )
        version_service.update_draft(
            db, user, version_id, body_md=body_md, structured_fields=fields_json
        )
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


# ── v1: demanda, hipóteses, impacto e implementação ─────────────────────────


@router.post("/versions/{version_id}/change-request")
def link_change_request(
    request: Request,
    version_id: str,
    change_request_id: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_role(Role.AUTHOR, Role.ADMIN)),
    _csrf: None = Depends(csrf_protect),
):
    try:
        change_request_service.link_version(db, user, version_id, change_request_id or None)
    except DomainError as exc:
        return RedirectResponse(f"/versions/{version_id}/edit?msg={exc}", status_code=303)
    db.commit()
    return RedirectResponse(
        f"/versions/{version_id}/edit?msg=V%C3%ADnculo+com+demanda+atualizado", status_code=303
    )


@router.post("/versions/{version_id}/hypotheses")
def add_hypothesis(
    request: Request,
    version_id: str,
    indicator_id: str = Form(...),
    expected_change: str = Form(...),
    windows: list[int] = Form([]),
    db: Session = Depends(get_db),
    user: User = Depends(require_role(Role.AUTHOR, Role.ADMIN)),
    _csrf: None = Depends(csrf_protect),
):
    try:
        impact_service.set_hypothesis(
            db, user, version_id,
            indicator_id=indicator_id,
            expected_change=expected_change,
            windows=windows or None,
        )
    except DomainError as exc:
        return RedirectResponse(f"/versions/{version_id}/edit?msg={exc}", status_code=303)
    db.commit()
    return RedirectResponse(
        f"/versions/{version_id}/edit?msg=Hip%C3%B3tese+registrada", status_code=303
    )


@router.post("/versions/{version_id}/hypotheses/{indicator_id}/remove")
def remove_hypothesis(
    request: Request,
    version_id: str,
    indicator_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(Role.AUTHOR, Role.ADMIN)),
    _csrf: None = Depends(csrf_protect),
):
    try:
        impact_service.remove_hypothesis(db, user, version_id, indicator_id)
    except DomainError as exc:
        return RedirectResponse(f"/versions/{version_id}/edit?msg={exc}", status_code=303)
    db.commit()
    return RedirectResponse(
        f"/versions/{version_id}/edit?msg=Hip%C3%B3tese+removida", status_code=303
    )


@router.post("/impact-metrics/{metric_id}/observed")
def record_observed(
    request: Request,
    metric_id: str,
    version_id: str = Form(...),
    observed_change: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
    _csrf: None = Depends(csrf_protect),
):
    try:
        impact_service.record_observed(db, user, metric_id, observed_change)
    except DomainError as exc:
        return RedirectResponse(f"/versions/{version_id}?msg={exc}", status_code=303)
    db.commit()
    return RedirectResponse(
        f"/versions/{version_id}?msg=Observado+registrado", status_code=303
    )


@router.post("/publications/{publication_id}/impact")
def record_impact(
    request: Request,
    publication_id: str,
    version_id: str = Form(...),
    observed_impact: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
    _csrf: None = Depends(csrf_protect),
):
    try:
        impact_service.record_impact(db, user, publication_id, observed_impact=observed_impact)
    except DomainError as exc:
        return RedirectResponse(f"/versions/{version_id}?msg={exc}", status_code=303)
    db.commit()
    return RedirectResponse(
        f"/versions/{version_id}?msg=Impacto+registrado", status_code=303
    )


@router.post("/versions/{version_id}/implementation-refs")
def add_implementation_ref(
    request: Request,
    version_id: str,
    system: str = Form(...),
    artifact: str = Form(...),
    artifact_version: str = Form(...),
    node_path: str = Form(""),
    url: str = Form(""),
    deployed_at: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
    _csrf: None = Depends(csrf_protect),
):
    from datetime import date as date_cls

    deployed = None
    if deployed_at:
        try:
            deployed = date_cls.fromisoformat(deployed_at)
        except ValueError:
            return RedirectResponse(
                f"/versions/{version_id}?msg=Data+de+implanta%C3%A7%C3%A3o+inv%C3%A1lida",
                status_code=303,
            )
    try:
        implementation_service.register(
            db, user, version_id,
            system=system, artifact=artifact, artifact_version=artifact_version,
            node_path=node_path, url=url, deployed_at=deployed,
        )
    except DomainError as exc:
        return RedirectResponse(f"/versions/{version_id}?msg={exc}", status_code=303)
    db.commit()
    return RedirectResponse(
        f"/versions/{version_id}?msg=Implementa%C3%A7%C3%A3o+registrada", status_code=303
    )


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
