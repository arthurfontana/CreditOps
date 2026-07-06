"""Importador de legado assistido (v1).

Upload em lote de documentos existentes → cada arquivo vira uma política
com rascunho v1 e o documento original anexado (com hash). Arquivos de
texto/Markdown entram como corpo; binários (PDF, DOCX) ficam anexados e o
corpo nasce do template do tipo, para reescrita assistida.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from app.models import Role, User
from app.services import attachment_service, audit_service, authz, policy_service
from app.services.errors import DomainError, ValidationFailed

TEXT_EXTENSIONS = {"md", "txt"}


@dataclass
class ImportResult:
    filename: str
    ok: bool
    policy_code: str | None = None
    policy_id: str | None = None
    error: str | None = None


def _title_from_filename(filename: str) -> str:
    stem = Path(filename).stem.replace("_", " ").replace("-", " ").strip()
    return stem[:1].upper() + stem[1:] if stem else filename


def import_batch(
    db: Session,
    actor: User,
    *,
    files: list[tuple[str, bytes]],
    area_id: str,
    policy_type: str,
    owner_id: str | None = None,
) -> list[ImportResult]:
    """Importa um lote. Cada arquivo é atômico: falha em um não derruba os demais."""
    authz.ensure_role(actor, Role.AUTHOR, Role.ADMIN)
    authz.ensure_area_scope(actor, area_id, action="importar políticas")
    if not files:
        raise ValidationFailed("nenhum arquivo enviado")

    results: list[ImportResult] = []
    for filename, content in files:
        savepoint = db.begin_nested()
        try:
            policy = policy_service.create_policy(
                db,
                actor,
                title=_title_from_filename(filename),
                policy_type=policy_type,
                area_id=area_id,
                owner_id=owner_id or actor.id,
            )
            draft = policy.versions[-1] if policy.versions else None
            if draft is None:  # criação sempre gera v1; guarda defensiva
                raise ValidationFailed("rascunho inicial não encontrado")
            ext = Path(filename).suffix.lower().lstrip(".")
            if ext in TEXT_EXTENSIONS:
                draft.body_md = content.decode("utf-8", errors="replace")
            attachment_service.upload(
                db, actor, draft.id, filename=filename, content=content
            )
            audit_service.record(
                db, actor.id, "policy.imported", "policy", policy.id,
                {"filename": filename, "code": policy.code},
            )
            savepoint.commit()
            results.append(ImportResult(filename, True, policy.code, policy.id))
        except DomainError as exc:
            savepoint.rollback()
            results.append(ImportResult(filename, False, error=str(exc)))
    db.flush()
    return results
