"""Rotas de sugestão de IA (v2) — fragmentos HTMX.

Toda rota devolve SUGESTÃO para o humano revisar e aplicar manualmente;
nada aqui grava conteúdo em versão. Falha de IA vira mensagem amigável
("sugestão indisponível"), nunca erro de sistema (fail-soft, wiki 08).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.auth.deps import require_role
from app.db import get_db
from app.models import Role, User
from app.plugins.ai.service import AIUnavailable
from app.services import version_service
from app.web.csrf import csrf_protect
from app.web.templating import render

router = APIRouter(prefix="/ai")


def _get_ai():
    from app.plugins import registry

    return registry.get_plugin("ai")


def _unavailable(message: str) -> HTMLResponse:
    return HTMLResponse(f"<div class='flash'>Sugestão indisponível: {message}</div>")


@router.post("/versions/{version_id}/summarize-diff")
def summarize_diff(
    request: Request,
    version_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(Role.AUTHOR, Role.ADMIN)),
    _csrf: None = Depends(csrf_protect),
):
    from app.plugins.ai import tasks

    ai = _get_ai()
    if ai is None:
        return _unavailable("IA não configurada")
    version = version_service.get_version(db, version_id)
    try:
        suggestion = tasks.summarize_diff(db, ai, user, version)
    except AIUnavailable as exc:
        return _unavailable(str(exc))
    db.commit()
    return render(
        request, "platform/_ai_suggestion.html", user,
        title="Resumo sugerido pela IA (revise e cole no campo de justificativa)",
        suggestion=suggestion,
    )


@router.post("/versions/{version_id}/suggest-tags")
def suggest_tags(
    request: Request,
    version_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(Role.AUTHOR, Role.ADMIN)),
    _csrf: None = Depends(csrf_protect),
):
    from app.plugins.ai import tasks

    ai = _get_ai()
    if ai is None:
        return _unavailable("IA não configurada")
    version = version_service.get_version(db, version_id)
    try:
        tags = tasks.suggest_tags(db, ai, user, version)
    except AIUnavailable as exc:
        return _unavailable(str(exc))
    db.commit()
    if not tags:
        return _unavailable("nenhuma tag do catálogo se aplica")
    return render(
        request, "platform/_ai_suggestion.html", user,
        title="Tags sugeridas pela IA (selecione-as em Editar metadados)",
        suggestion=", ".join(tags),
    )


@router.get("/draft")
def draft_form(
    request: Request,
    user: User = Depends(require_role(Role.AUTHOR, Role.ADMIN)),
):
    ai = _get_ai()
    enabled = ai is not None and ai.feature_enabled("draft_from_document")
    return render(request, "platform/ai_draft.html", user, enabled=enabled, suggestion=None)


@router.post("/draft")
def draft_from_document(
    request: Request,
    raw_text: str = Form(...),
    policy_type: str = Form("outro"),
    db: Session = Depends(get_db),
    user: User = Depends(require_role(Role.AUTHOR, Role.ADMIN)),
    _csrf: None = Depends(csrf_protect),
):
    from app.plugins.ai import tasks

    ai = _get_ai()
    if ai is None:
        return render(
            request, "platform/ai_draft.html", user, enabled=False, suggestion=None,
            msg="IA não configurada",
        )
    try:
        suggestion = tasks.draft_from_document(db, ai, user, raw_text, policy_type)
    except AIUnavailable as exc:
        return render(
            request, "platform/ai_draft.html", user, enabled=True, suggestion=None,
            msg=f"Sugestão indisponível: {exc}",
        )
    db.commit()
    return render(
        request, "platform/ai_draft.html", user, enabled=True, suggestion=suggestion,
    )
