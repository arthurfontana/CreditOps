"""Referência de implementação (v1): documentação → motor de decisão.

Registro manual do vínculo entre a versão publicada e o artefato que a
implementa (sistema, strategy/ruleset/arquivo, versão, nó). Responde em
auditoria: "esta regra aprovada está implementada onde, em qual versão?".
Conferência automática é evolução enterprise.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ImplementationRef, Role, User, VersionStatus
from app.services import audit_service, authz, version_service
from app.services.errors import ValidationFailed

PUBLISHED_STATUSES = (
    VersionStatus.PUBLISHED,
    VersionStatus.EFFECTIVE,
    VersionStatus.SUPERSEDED,
)


def register(
    db: Session,
    actor: User,
    version_id: str,
    *,
    system: str,
    artifact: str,
    artifact_version: str,
    node_path: str = "",
    url: str = "",
    deployed_at: date | None = None,
) -> ImplementationRef:
    version = version_service.get_version(db, version_id)
    authz.ensure_role(actor, Role.AUTHOR, Role.APPROVER, Role.ADMIN)
    authz.ensure_area_scope(actor, version.policy.area_id, action="registrar implementação")
    if VersionStatus(version.status) not in PUBLISHED_STATUSES:
        raise ValidationFailed(
            "referência de implementação só se aplica a versões publicadas"
        )
    if not (system.strip() and artifact.strip() and artifact_version.strip()):
        raise ValidationFailed("sistema, artefato e versão do artefato são obrigatórios")

    ref = ImplementationRef(
        version_id=version.id,
        system=system.strip(),
        artifact=artifact.strip(),
        artifact_version=artifact_version.strip(),
        node_path=node_path.strip() or None,
        url=url.strip() or None,
        deployed_at=deployed_at,
        registered_by=actor.id,
    )
    db.add(ref)
    db.flush()
    audit_service.record(
        db, actor.id, "implementation.registered", "policy_version", version.id,
        {
            "system": ref.system,
            "artifact": ref.artifact,
            "artifact_version": ref.artifact_version,
            "node_path": ref.node_path,
        },
    )
    return ref


def refs_for_version(db: Session, version_id: str) -> list[ImplementationRef]:
    return list(
        db.scalars(
            select(ImplementationRef)
            .where(ImplementationRef.version_id == version_id)
            .order_by(ImplementationRef.created_at)
        )
    )
