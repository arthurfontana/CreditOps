"""Rotas web da v2: recertificação, trilha de leitura, comparação entre
políticas, grafo de referências/análise de impacto e perguntas (RAG)."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.deps import current_user, require_role
from app.db import get_db
from app.models import Policy, PolicyLifecycle, ReferenceRelation, Role, User
from app.services import (
    diff_service,
    policy_service,
    read_receipt_service,
    recertification_service,
    reference_service,
    search_service,
)
from app.services.errors import DomainError
from app.web.csrf import csrf_protect
from app.web.templating import render

router = APIRouter()

RELATION_LABELS = {
    ReferenceRelation.USA.value: "usa",
    ReferenceRelation.DEPENDE_DE.value: "depende de",
    ReferenceRelation.SUBSTITUI.value: "substitui",
}


# ─── recertificação periódica ────────────────────────────────────────────────


@router.get("/recertification")
def recertification_report(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    report = recertification_service.report(db)
    return render(request, "platform/recertification.html", user, r=report, now=datetime.utcnow())


@router.post("/policies/{policy_id}/review-due")
def set_review_due(
    request: Request,
    policy_id: str,
    review_due: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_role(Role.AUTHOR, Role.APPROVER, Role.ADMIN)),
    _csrf: None = Depends(csrf_protect),
):
    due = None
    if review_due:
        try:
            due = datetime.fromisoformat(review_due)
        except ValueError:
            return RedirectResponse(
                f"/policies/{policy_id}?msg=Data+inv%C3%A1lida", status_code=303
            )
    try:
        recertification_service.set_review_due(db, user, policy_id, due)
    except DomainError as exc:
        return RedirectResponse(f"/policies/{policy_id}?msg={exc}", status_code=303)
    db.commit()
    return RedirectResponse(
        f"/policies/{policy_id}?msg=Prazo+de+recertifica%C3%A7%C3%A3o+atualizado",
        status_code=303,
    )


@router.post("/policies/{policy_id}/recertify")
def recertify(
    request: Request,
    policy_id: str,
    months: int = Form(recertification_service.DEFAULT_CYCLE_MONTHS),
    note: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_role(Role.APPROVER, Role.ADMIN)),
    _csrf: None = Depends(csrf_protect),
):
    try:
        recertification_service.recertify(db, user, policy_id, months=months, note=note)
    except DomainError as exc:
        return RedirectResponse(f"/policies/{policy_id}?msg={exc}", status_code=303)
    db.commit()
    return RedirectResponse(
        f"/policies/{policy_id}?msg=Pol%C3%ADtica+recertificada", status_code=303
    )


# ─── trilha de leitura ("ciência da operação") ───────────────────────────────


@router.post("/policies/{policy_id}/acknowledge")
def acknowledge(
    request: Request,
    policy_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
    _csrf: None = Depends(csrf_protect),
):
    try:
        read_receipt_service.acknowledge(db, user, policy_id)
    except DomainError as exc:
        return RedirectResponse(f"/policies/{policy_id}?msg={exc}", status_code=303)
    db.commit()
    return RedirectResponse(
        f"/policies/{policy_id}?msg=Ci%C3%AAncia+registrada", status_code=303
    )


@router.get("/policies/{policy_id}/readers")
def readers_report(
    request: Request,
    policy_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    policy = policy_service.get_policy(db, user, policy_id)
    report = read_receipt_service.policy_report(db, policy.id)
    return render(request, "platform/readers.html", user, policy=policy, report=report)


@router.get("/reading")
def my_pending_readings(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    pending = read_receipt_service.pending_for_user(db, user)
    return render(request, "platform/reading.html", user, pending=pending)


# ─── comparação entre políticas ──────────────────────────────────────────────


@router.get("/compare-policies")
def compare_policies(
    request: Request,
    policy_a: str = "",
    policy_b: str = "",
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    candidates = list(
        db.scalars(
            select(Policy)
            .where(Policy.current_version_id.is_not(None))
            .order_by(Policy.code)
        )
    )
    a = db.get(Policy, policy_a) if policy_a else None
    b = db.get(Policy, policy_b) if policy_b else None
    rows = stats = None
    if (
        a is not None and b is not None and a.id != b.id
        and a.current_version is not None and b.current_version is not None
    ):
        rows = diff_service.side_by_side(a.current_version, b.current_version)
        stats = diff_service.stats(a.current_version, b.current_version)
    return render(
        request, "platform/compare_policies.html", user,
        candidates=candidates, a=a, b=b, rows=rows, stats=stats,
    )


# ─── grafo de referências + análise de impacto ───────────────────────────────


@router.post("/policies/{policy_id}/references")
def add_reference(
    request: Request,
    policy_id: str,
    relation: str = Form(...),
    to_policy_id: str = Form(""),
    artifact_name: str = Form(""),
    note: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(require_role(Role.AUTHOR, Role.ADMIN)),
    _csrf: None = Depends(csrf_protect),
):
    try:
        reference_service.add_reference(
            db, user, policy_id,
            relation=relation,
            to_policy_id=to_policy_id or None,
            artifact_name=artifact_name or None,
            note=note,
        )
    except DomainError as exc:
        return RedirectResponse(f"/policies/{policy_id}?msg={exc}", status_code=303)
    db.commit()
    return RedirectResponse(
        f"/policies/{policy_id}?msg=Refer%C3%AAncia+adicionada", status_code=303
    )


@router.post("/policies/{policy_id}/references/{reference_id}/delete")
def remove_reference(
    request: Request,
    policy_id: str,
    reference_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require_role(Role.AUTHOR, Role.ADMIN)),
    _csrf: None = Depends(csrf_protect),
):
    try:
        reference_service.remove_reference(db, user, reference_id)
    except DomainError as exc:
        return RedirectResponse(f"/policies/{policy_id}?msg={exc}", status_code=303)
    db.commit()
    return RedirectResponse(
        f"/policies/{policy_id}?msg=Refer%C3%AAncia+removida", status_code=303
    )


@router.get("/impact")
def impact_analysis(
    request: Request,
    policy_id: str = "",
    artifact: str = "",
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """'Se eu mudar X, quais políticas são afetadas?' — X = política ou artefato."""
    candidates = list(
        db.scalars(
            select(Policy)
            .where(Policy.lifecycle_status == PolicyLifecycle.ACTIVE.value)
            .order_by(Policy.code)
        )
    )
    artifacts = reference_service.artifact_names(db)
    target_policy = db.get(Policy, policy_id) if policy_id else None
    hits = None
    target_label = None
    try:
        if target_policy is not None:
            hits = reference_service.impact_analysis(db, policy_id=target_policy.id)
            target_label = f"{target_policy.code} — {target_policy.title}"
        elif artifact.strip():
            hits = reference_service.impact_analysis(db, artifact_name=artifact)
            target_label = artifact.strip()
    except DomainError:
        hits = None
    return render(
        request, "platform/impact.html", user,
        candidates=candidates, artifacts=artifacts,
        selected_policy=target_policy, artifact=artifact,
        hits=hits, target_label=target_label,
    )


# ─── perguntas sobre políticas (RAG local, fail-soft) ────────────────────────


@router.get("/ask")
def ask(
    request: Request,
    q: str = "",
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    """RAG local: FTS5 recupera; provider (se houver) responde citando fontes.

    Sem IA configurada a página continua útil: vira busca melhorada
    (wiki 08 — retrieval sozinho).
    """
    answer = None
    sources = []
    ai_enabled = False
    if q.strip():
        from app.plugins import registry
        from app.plugins.ai import tasks as ai_tasks

        hits = search_service.search(db, q, user)
        ai = registry.get_plugin("ai")
        if ai is not None and ai.feature_enabled("qa_search"):
            ai_enabled = True
            result = ai_tasks.qa_answer(db, ai, user, q, hits)
            db.commit()  # persiste a auditoria da sugestão
            answer, sources = result.answer, result.sources
        else:
            result = ai_tasks.qa_answer(
                db, _DisabledAI(), user, q, hits
            )
            sources = result.sources
    return render(
        request, "platform/ask.html", user,
        q=q, answer=answer, sources=sources, ai_enabled=ai_enabled,
    )


class _DisabledAI:
    """Stub para reutilizar o retrieval do qa_answer sem provider ativo."""

    def feature_enabled(self, feature: str) -> bool:
        return False
