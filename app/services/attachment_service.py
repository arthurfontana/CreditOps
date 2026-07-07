"""Anexos: filesystem com hash SHA-256, deduplicação e download auditado."""

from __future__ import annotations

import hashlib
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Attachment, Role, User, VersionStatus
from app.services import audit_service, authz, version_service
from app.services.errors import NotFound, PermissionDenied, ValidationFailed


def _attachments_dir() -> Path:
    return get_settings().data_path / "attachments"


def _validate_and_store(filename: str, content: bytes) -> tuple[str, Path]:
    """Validações comuns (extensão, tamanho) + gravação deduplicada por hash."""
    settings = get_settings()
    ext = Path(filename).suffix.lower().lstrip(".")
    if ext not in settings.allowed_extensions:
        raise ValidationFailed(f"extensão não permitida: .{ext}")
    if len(content) == 0:
        raise ValidationFailed("arquivo vazio")
    if len(content) > settings.attachment_max_bytes:
        raise ValidationFailed(
            f"arquivo excede o tamanho máximo de {settings.attachment_max_bytes // (1024 * 1024)}MB"
        )
    sha = hashlib.sha256(content).hexdigest()
    rel_path = Path(sha[:2]) / sha[2:4] / f"{sha}.{ext}"
    stored = _attachments_dir() / rel_path
    if not stored.exists():  # deduplicação por hash
        stored.parent.mkdir(parents=True, exist_ok=True)
        stored.write_bytes(content)
    return sha, rel_path


def upload(
    db: Session,
    actor: User,
    version_id: str,
    *,
    filename: str,
    content: bytes,
    content_type: str | None = None,
) -> Attachment:
    """Upload só em rascunho; extensão em lista permitida; tamanho máximo; hash."""
    version = version_service.get_version(db, version_id)
    authz.ensure_role(actor, Role.AUTHOR, Role.ADMIN)
    if Role(actor.role) != Role.ADMIN and version.created_by != actor.id:
        raise PermissionDenied("apenas o autor da versão pode anexar arquivos")
    if version.status != VersionStatus.DRAFT:
        raise ValidationFailed("anexos só podem ser adicionados em rascunho")

    sha, rel_path = _validate_and_store(filename, content)

    attachment = Attachment(
        version_id=version.id,
        filename=filename,
        stored_path=str(rel_path),
        sha256=sha,
        size_bytes=len(content),
        content_type=content_type,
        uploaded_by=actor.id,
    )
    db.add(attachment)
    db.flush()
    audit_service.record(
        db, actor.id, "attachment.uploaded", "attachment", attachment.id,
        {"filename": filename, "sha256": sha, "size": len(content)},
    )
    return attachment


def upload_for_change_request(
    db: Session,
    actor: User,
    change_request_id: str,
    *,
    filename: str,
    content: bytes,
    content_type: str | None = None,
) -> Attachment:
    """Anexo de demanda: enquanto ela está aberta, pelo solicitante ou autores."""
    from app.models import ChangeRequest, ChangeRequestStatus
    from app.services import change_request_service

    change_request: ChangeRequest = change_request_service.get(db, change_request_id)
    authz.ensure_active(actor)
    role = Role(actor.role)
    if role not in (Role.ADMIN, Role.AUTHOR, Role.APPROVER) and (
        change_request.requested_by != actor.id
    ):
        raise PermissionDenied("apenas o solicitante ou autores podem anexar arquivos à demanda")
    if change_request.status not in (
        ChangeRequestStatus.OPEN,
        ChangeRequestStatus.IN_PROGRESS,
    ):
        raise ValidationFailed("anexos só podem ser adicionados com a demanda aberta")

    sha, rel_path = _validate_and_store(filename, content)

    attachment = Attachment(
        change_request_id=change_request.id,
        filename=filename,
        stored_path=str(rel_path),
        sha256=sha,
        size_bytes=len(content),
        content_type=content_type,
        uploaded_by=actor.id,
    )
    db.add(attachment)
    db.flush()
    audit_service.record(
        db, actor.id, "attachment.uploaded", "attachment", attachment.id,
        {
            "filename": filename,
            "sha256": sha,
            "size": len(content),
            "change_request": change_request.code,
        },
    )
    return attachment


def get_content(db: Session, actor: User, attachment_id: str) -> tuple[Attachment, bytes]:
    authz.ensure_active(actor)
    attachment = db.get(Attachment, attachment_id)
    if attachment is None:
        raise NotFound("anexo não encontrado")
    path = _attachments_dir() / attachment.stored_path
    if not path.exists():
        raise NotFound("arquivo do anexo não encontrado no filesystem")
    content = path.read_bytes()
    if hashlib.sha256(content).hexdigest() != attachment.sha256:
        raise ValidationFailed("integridade do anexo violada (hash não confere)")
    audit_service.record(
        db, actor.id, "attachment.downloaded", "attachment", attachment.id,
        {"filename": attachment.filename},
    )
    return attachment, content
