"""Ambiente Jinja2 compartilhado pelas rotas web."""

from __future__ import annotations

from pathlib import Path

from fastapi import Request
from fastapi.templating import Jinja2Templates

from app.config import get_settings
from app.models import Role, User, VersionStatus
from app.web.csrf import make_csrf_token
from app.web.markdown import render_markdown

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

STATUS_LABELS = {
    VersionStatus.DRAFT: "Rascunho",
    VersionStatus.IN_REVIEW: "Em revisão",
    VersionStatus.IN_APPROVAL: "Em aprovação",
    VersionStatus.APPROVED: "Aprovada",
    VersionStatus.PUBLISHED: "Publicada",
    VersionStatus.EFFECTIVE: "Em vigor",
    VersionStatus.SUPERSEDED: "Substituída",
    VersionStatus.ARCHIVED: "Arquivada",
    VersionStatus.REJECTED: "Rejeitada",
}

ROLE_LABELS = {
    Role.ADMIN: "Administrador",
    Role.AUTHOR: "Autor",
    Role.REVIEWER: "Revisor",
    Role.APPROVER: "Aprovador",
    Role.READER: "Leitor",
}

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
templates.env.filters["markdown"] = render_markdown
templates.env.globals["app_name"] = get_settings().app_name
templates.env.globals["status_label"] = lambda s: STATUS_LABELS.get(VersionStatus(s), s)
templates.env.globals["role_label"] = lambda r: ROLE_LABELS.get(Role(r), r)


def render(request: Request, name: str, user: User | None = None, **context):
    ctx = {"request": request, "user": user, **context}
    if user is not None:
        ctx.setdefault("csrf_token", make_csrf_token(user.id))
    return templates.TemplateResponse(request, name, ctx)
