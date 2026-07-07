"""Casos de uso de IA — implementados ACIMA do provider (wiki 08).

Prompts são artefatos versionados em prompts/runtime/*.md; trocar de
modelo = reavaliar prompts, não reescrever features. Toda sugestão é
auditada (`ai.suggestion_generated`) — a IA também é auditada.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from difflib import unified_diff
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import BASE_DIR
from app.models import Policy, PolicyVersion, Tag, User
from app.plugins.ai.service import AIService, AIUnavailable
from app.plugins.base import AIResult
from app.services import audit_service

RUNTIME_PROMPTS_DIR = BASE_DIR / "prompts" / "runtime"

# limites defensivos de contexto (caracteres) — política gigante não estoura o provider
MAX_DIFF_CHARS = 12_000
MAX_BODY_CHARS = 12_000
MAX_EXCERPT_CHARS = 1_500
QA_TOP_HITS = 5


def load_runtime_prompt(name: str) -> tuple[str, str]:
    """Lê prompts/runtime/<name>.md e devolve (system, user_template)."""
    path: Path = RUNTIME_PROMPTS_DIR / f"{name}.md"
    text = path.read_text(encoding="utf-8")
    system_match = re.search(r"^## System\s*$(.*?)^## User\s*$", text, re.M | re.S)
    user_match = re.search(r"^## User\s*$(.*)", text, re.M | re.S)
    if not system_match or not user_match:
        raise AIUnavailable(f"prompt de runtime malformado: {path.name}")
    return system_match.group(1).strip(), user_match.group(1).strip()


def _fill(template: str, values: dict[str, str]) -> str:
    # replace simples (não str.format): o conteúdo dos prompts contém chaves JSON
    for key, value in values.items():
        template = template.replace("{" + key + "}", value)
    return template


def _audit_suggestion(
    db: Session, actor: User, feature: str, result: AIResult, suggestion: str,
    entity_type: str = "policy_version", entity_id: str | None = None,
) -> None:
    audit_service.record(
        db, actor.id, "ai.suggestion_generated", entity_type, entity_id,
        {
            "feature": feature,
            "provider": result.provider,
            "model": result.model,
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
            "latency_ms": result.latency_ms,
            "suggestion_sha256": hashlib.sha256(suggestion.encode("utf-8")).hexdigest(),
            "suggestion_excerpt": suggestion[:500],
        },
    )


def _require_feature(ai: AIService, feature: str) -> None:
    if not ai.feature_enabled(feature):
        raise AIUnavailable(f"feature de IA desligada: {feature}")


def summarize_diff(db: Session, ai: AIService, actor: User, version: PolicyVersion) -> str:
    """Rascunho do resumo de mudança a partir do diff — o autor edita/confirma."""
    _require_feature(ai, "summarize_diff")
    policy = version.policy
    base = policy.current_version or version.based_on
    if base is None or base.id == version.id:
        raise AIUnavailable("primeira versão da política — não há diff para resumir")
    diff = "".join(
        unified_diff(
            base.body_md.splitlines(keepends=True),
            version.body_md.splitlines(keepends=True),
            fromfile=f"v{base.version_number}",
            tofile=f"v{version.version_number}",
        )
    )
    if not diff.strip():
        raise AIUnavailable("não há diferenças entre as versões")
    system, template = load_runtime_prompt("summarize_diff")
    prompt = _fill(
        template,
        {"diff": diff[:MAX_DIFF_CHARS], "policy_title": f"{policy.code} — {policy.title}"},
    )
    result = ai.complete(prompt, system=system)
    suggestion = result.text.strip()
    _audit_suggestion(db, actor, "summarize_diff", result, suggestion, entity_id=version.id)
    return suggestion


def suggest_tags(db: Session, ai: AIService, actor: User, version: PolicyVersion) -> list[str]:
    """Sugere tags do catálogo existente com base no conteúdo — humano confirma."""
    _require_feature(ai, "suggest_tags")
    existing = [t.name for t in db.scalars(select(Tag).order_by(Tag.name))]
    if not existing:
        raise AIUnavailable("não há tags cadastradas para sugerir")
    system, template = load_runtime_prompt("suggest_tags")
    prompt = _fill(
        template,
        {"body": version.body_md[:MAX_BODY_CHARS], "existing_tags": ", ".join(existing)},
    )
    result = ai.complete(prompt, system=system)
    try:
        raw = result.text.strip()
        match = re.search(r"\{.*\}", raw, re.S)
        tags = json.loads(match.group(0) if match else raw).get("tags", [])
    except (json.JSONDecodeError, AttributeError) as exc:
        raise AIUnavailable("resposta do provedor não é JSON válido") from exc
    valid = {t.lower(): t for t in existing}
    suggestion = [valid[t.lower()] for t in tags if isinstance(t, str) and t.lower() in valid]
    _audit_suggestion(
        db, actor, "suggest_tags", result, ", ".join(suggestion), entity_id=version.id
    )
    return suggestion[:5]


def draft_from_document(
    db: Session, ai: AIService, actor: User, raw_text: str, policy_type: str
) -> str:
    """Converte documento legado em Markdown no template do tipo — autor revisa."""
    _require_feature(ai, "draft_from_document")
    if not raw_text.strip():
        raise AIUnavailable("documento vazio")
    from app.services.policy_service import _template_body

    system, template = load_runtime_prompt("draft_from_document")
    prompt = _fill(
        template,
        {"raw_text": raw_text[:MAX_BODY_CHARS], "template": _template_body(policy_type)},
    )
    result = ai.complete(prompt, system=system, max_tokens=4096)
    suggestion = result.text.strip()
    _audit_suggestion(db, actor, "draft_from_document", result, suggestion, "policy", None)
    return suggestion


@dataclass
class QAAnswer:
    """Resposta do RAG local: texto (se houver provider) + fontes citáveis."""

    answer: str | None
    sources: list[dict]  # code, title, version_number, policy_id, snippet


def _excerpts(db: Session, hits) -> list[dict]:
    sources: list[dict] = []
    for hit in hits[:QA_TOP_HITS]:
        policy = db.get(Policy, hit.policy_id)
        if policy is None or policy.current_version is None:
            continue
        version = policy.current_version
        sources.append(
            {
                "policy_id": policy.id,
                "code": policy.code,
                "title": policy.title,
                "version_number": version.version_number,
                "snippet": hit.snippet,
                "body": version.body_md[:MAX_EXCERPT_CHARS],
            }
        )
    return sources


def qa_answer(db: Session, ai: AIService, actor: User, question: str, hits) -> QAAnswer:
    """RAG local: FTS5 seleciona trechos → IA responde citando política e versão.

    Sem provider (ou com a feature desligada) o retrieval sozinho vira
    "busca melhorada" — a rota exibe apenas as fontes (wiki 08).
    """
    sources = _excerpts(db, hits)
    if not ai.feature_enabled("qa_search") or not sources:
        return QAAnswer(answer=None, sources=sources)
    excerpts_text = "\n\n".join(
        f"[{s['code']} v{s['version_number']}] {s['title']}\n{s['body']}" for s in sources
    )
    system, template = load_runtime_prompt("qa_answer")
    prompt = _fill(template, {"question": question, "excerpts": excerpts_text})
    try:
        result = ai.complete(prompt, system=system, max_tokens=2048)
    except AIUnavailable:
        return QAAnswer(answer=None, sources=sources)  # fail-soft: vira busca melhorada
    answer = result.text.strip()
    _audit_suggestion(db, actor, "qa_search", result, answer, "policy", None)
    return QAAnswer(answer=answer, sources=sources)
