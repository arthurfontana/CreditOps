"""Exportação: Markdown com front matter, JSON e dossiê de auditoria (ZIP)."""

from __future__ import annotations

import json
import zipfile
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import (
    Approval,
    AuditLog,
    Policy,
    PolicyVersion,
    Publication,
    StatusTransition,
    User,
)
from app.services import audit_service


def _versions(db: Session, policy: Policy) -> list[PolicyVersion]:
    return list(
        db.scalars(
            select(PolicyVersion)
            .where(PolicyVersion.policy_id == policy.id)
            .order_by(PolicyVersion.version_number)
        )
    )


def _user_label(db: Session, user_id: str | None) -> str | None:
    if user_id is None:
        return None
    user = db.get(User, user_id)
    return user.display_name if user else user_id


def export_version_md(db: Session, version: PolicyVersion) -> str:
    policy = version.policy
    publication = db.scalars(
        select(Publication).where(Publication.version_id == version.id)
    ).first()
    approvals = db.scalars(
        select(Approval).where(Approval.version_id == version.id)
    ).all()
    lines = [
        "---",
        f"codigo: {policy.code}",
        f"titulo: {policy.title}",
        f"tipo: {policy.policy_type}",
        f"versao: {version.version_number}",
        f"status: {version.status}",
        f"autor: {_user_label(db, version.created_by)}",
        f"criada_em: {version.created_at.isoformat()}",
    ]
    if version.change_summary:
        lines.append(f"justificativa: {json.dumps(version.change_summary, ensure_ascii=False)}")
    if version.content_hash:
        lines.append(f"content_hash: {version.content_hash}")
    for approval in approvals:
        lines.append(
            f"aprovacao: {approval.decision} por {_user_label(db, approval.approver_id)} "
            f"em {approval.decided_at.isoformat()}"
        )
    if publication:
        lines.append(f"publicada_em: {publication.published_at.isoformat()}")
        lines.append(f"vigente_de: {publication.effective_from.isoformat()}")
        if publication.effective_until:
            lines.append(f"vigente_ate: {publication.effective_until.isoformat()}")
    lines += ["---", "", version.body_md]
    return "\n".join(lines)


def export_policy_json(db: Session, policy: Policy) -> dict:
    def version_dict(v: PolicyVersion) -> dict:
        publication = db.scalars(
            select(Publication).where(Publication.version_id == v.id)
        ).first()
        approvals = db.scalars(select(Approval).where(Approval.version_id == v.id)).all()
        transitions = db.scalars(
            select(StatusTransition)
            .where(StatusTransition.version_id == v.id)
            .order_by(StatusTransition.created_at)
        ).all()
        return {
            "version_number": v.version_number,
            "status": v.status,
            "author": _user_label(db, v.created_by),
            "created_at": v.created_at.isoformat(),
            "change_summary": v.change_summary,
            "expected_impact": v.expected_impact,
            "is_rollback": v.is_rollback,
            "content_hash": v.content_hash,
            "body_md": v.body_md,
            "approvals": [
                {
                    "decision": a.decision,
                    "approver": _user_label(db, a.approver_id),
                    "justification": a.justification,
                    "decided_at": a.decided_at.isoformat(),
                }
                for a in approvals
            ],
            "publication": (
                {
                    "published_by": _user_label(db, publication.published_by),
                    "published_at": publication.published_at.isoformat(),
                    "effective_from": publication.effective_from.isoformat(),
                    "effective_until": (
                        publication.effective_until.isoformat()
                        if publication.effective_until
                        else None
                    ),
                }
                if publication
                else None
            ),
            "transitions": [
                {
                    "from": t.from_status,
                    "to": t.to_status,
                    "actor": _user_label(db, t.actor_id) or "sistema",
                    "reason": t.reason,
                    "at": t.created_at.isoformat(),
                }
                for t in transitions
            ],
        }

    return {
        "code": policy.code,
        "title": policy.title,
        "type": policy.policy_type,
        "area": policy.area.name if policy.area else None,
        "owner": _user_label(db, policy.owner_id),
        "lifecycle_status": policy.lifecycle_status,
        "current_version": (
            policy.current_version.version_number if policy.current_version else None
        ),
        "products": [p.name for p in policy.products],
        "segments": [s.name for s in policy.segments],
        "tags": [t.name for t in policy.tags],
        "created_at": policy.created_at.isoformat(),
        "versions": [version_dict(v) for v in _versions(db, policy)],
    }


def _policy_audit_trail(db: Session, policy: Policy) -> list[dict]:
    version_ids = [v.id for v in _versions(db, policy)]
    entries = db.scalars(
        select(AuditLog)
        .where(
            ((AuditLog.entity_type == "policy") & (AuditLog.entity_id == policy.id))
            | (
                (AuditLog.entity_type == "policy_version")
                & (AuditLog.entity_id.in_(version_ids))
            )
        )
        .order_by(AuditLog.id)
    ).all()
    return [
        {
            "seq": e.id,
            "actor": _user_label(db, e.actor_id) or "sistema",
            "action": e.action,
            "entity_type": e.entity_type,
            "entity_id": e.entity_id,
            "payload": json.loads(e.payload) if e.payload else None,
            "at": e.created_at.isoformat(),
        }
        for e in entries
    ]


def export_dossier(db: Session, actor: User, policy: Policy) -> Path:
    """Gera o dossiê de auditoria: ZIP com política vigente, histórico
    completo, metadados e trilha. O entregável de auditoria."""
    exports_dir = get_settings().data_path / "exports"
    exports_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    path = exports_dir / f"dossie-{policy.code}-{stamp}.zip"

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        if policy.current_version:
            zf.writestr("politica.md", export_version_md(db, policy.current_version))
        for version in _versions(db, policy):
            zf.writestr(
                f"historico/v{version.version_number}.md",
                export_version_md(db, version),
            )
        zf.writestr(
            "metadados.json",
            json.dumps(export_policy_json(db, policy), ensure_ascii=False, indent=2),
        )
        zf.writestr(
            "trilha_auditoria.json",
            json.dumps(_policy_audit_trail(db, policy), ensure_ascii=False, indent=2),
        )

    audit_service.record(
        db, actor.id, "export.generated", "policy", policy.id,
        {"kind": "dossier", "file": path.name},
    )
    return path
