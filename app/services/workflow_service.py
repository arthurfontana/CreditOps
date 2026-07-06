"""Máquina de estados do workflow de aprovação.

A whitelist TRANSITIONS é a especificação executável da wiki (cap. 06):
qualquer transição fora dela é rejeitada pelo core — não existe força
bruta nem edição direta de status.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Approval,
    ApprovalDecision,
    Policy,
    PolicyVersion,
    Publication,
    Role,
    StatusTransition,
    User,
    VersionStatus,
)
from app.services import audit_service, authz, events, version_service
from app.services.errors import (
    InvalidTransition,
    PermissionDenied,
    ValidationFailed,
)


@dataclass(frozen=True)
class TransitionRule:
    roles: tuple[Role, ...]  # vazio = ação exclusiva do sistema
    reason_required: bool = False
    actor_must_be_author: bool = False  # ações do autor sobre a própria versão
    actor_must_not_be_author: bool = False  # segregação de funções
    rollback_only: bool = False  # fluxo expresso de rollback


D = VersionStatus  # atalho de leitura

TRANSITIONS: dict[tuple[VersionStatus, VersionStatus], TransitionRule] = {
    # autor submete para revisão (exige justificativa + impacto — validado em submit)
    (D.DRAFT, D.IN_REVIEW): TransitionRule(roles=(Role.AUTHOR,), actor_must_be_author=True),
    # revisor (ou o próprio autor) devolve para ajustes
    (D.IN_REVIEW, D.DRAFT): TransitionRule(roles=(Role.REVIEWER, Role.AUTHOR)),
    # revisor conclui a revisão e envia para aprovação (congela conteúdo)
    (D.IN_REVIEW, D.IN_APPROVAL): TransitionRule(roles=(Role.REVIEWER,)),
    # fluxo expresso de rollback: direto para aprovação
    (D.DRAFT, D.IN_APPROVAL): TransitionRule(
        roles=(Role.APPROVER,), rollback_only=True, reason_required=True
    ),
    # aprovador decide (nunca o próprio autor)
    (D.IN_APPROVAL, D.APPROVED): TransitionRule(
        roles=(Role.APPROVER,), actor_must_not_be_author=True
    ),
    # rejeição: volta a rascunho com justificativa obrigatória
    (D.IN_APPROVAL, D.DRAFT): TransitionRule(roles=(Role.APPROVER,), reason_required=True),
    # publicação (no MVP o aprovador também publica)
    (D.APPROVED, D.PUBLISHED): TransitionRule(roles=(Role.APPROVER,)),
    # vigência e substituição: exclusivas do sistema
    (D.PUBLISHED, D.EFFECTIVE): TransitionRule(roles=()),
    (D.EFFECTIVE, D.SUPERSEDED): TransitionRule(roles=()),
    # arquivamento
    (D.EFFECTIVE, D.ARCHIVED): TransitionRule(roles=(Role.APPROVER,), reason_required=True),
    (D.SUPERSEDED, D.ARCHIVED): TransitionRule(roles=(Role.APPROVER,), reason_required=True),
    (D.DRAFT, D.ARCHIVED): TransitionRule(roles=(Role.AUTHOR,), actor_must_be_author=True),
}


def _transition(
    db: Session,
    actor: User | None,
    version: PolicyVersion,
    to_status: VersionStatus,
    *,
    reason: str | None = None,
) -> None:
    """Valida a whitelist + papel, muda o status e grava a evidência."""
    from_status = VersionStatus(version.status)
    rule = TRANSITIONS.get((from_status, to_status))
    if rule is None:
        raise InvalidTransition(f"transição não permitida: {from_status} → {to_status}")

    if not rule.roles:  # ação do sistema
        if actor is not None:
            raise InvalidTransition(
                f"transição {from_status} → {to_status} é exclusiva do sistema"
            )
    else:
        if actor is None:
            raise PermissionDenied("ação requer usuário autenticado")
        authz.ensure_role(actor, *rule.roles)
        if rule.actor_must_be_author and version.created_by != actor.id:
            raise PermissionDenied("apenas o autor da versão pode executar esta ação")
        # segregação autor≠aprovador; rollback é exceção deliberada (fluxo
        # expresso da wiki 06: conteúdo já aprovado no passado, decisão única
        # do gerente, com justificativa obrigatória e tudo auditado)
        if (
            rule.actor_must_not_be_author
            and version.created_by == actor.id
            and not version.is_rollback
        ):
            raise PermissionDenied("segregação de funções: autor não decide a própria versão")
    if rule.rollback_only and not version.is_rollback:
        raise InvalidTransition("fluxo expresso é exclusivo de rollback")
    if rule.reason_required and not (reason and reason.strip()):
        raise ValidationFailed("justificativa é obrigatória para esta ação")

    version.status = to_status
    db.add(
        StatusTransition(
            version_id=version.id,
            from_status=from_status,
            to_status=to_status,
            actor_id=actor.id if actor else None,
            reason=reason,
        )
    )
    db.flush()
    audit_service.record(
        db,
        actor.id if actor else None,
        "version.status_changed",
        "policy_version",
        version.id,
        {"from": from_status.value, "to": to_status.value, "reason": reason},
    )


# ─── ações do fluxo ──────────────────────────────────────────────────────────


def submit_for_review(db: Session, actor: User, version_id: str) -> PolicyVersion:
    version = version_service.get_version(db, version_id)
    if not (version.change_summary and version.change_summary.strip()):
        raise ValidationFailed("justificativa da alteração (change_summary) é obrigatória")
    if not (version.expected_impact and version.expected_impact.strip()):
        raise ValidationFailed("impacto esperado (expected_impact) é obrigatório")
    _transition(db, actor, version, VersionStatus.IN_REVIEW)
    version.submitted_at = datetime.utcnow()
    db.flush()
    audit_service.record(db, actor.id, "version.submitted", "policy_version", version.id, None)
    events.emit(db, "version.submitted", {"version_id": version.id})
    return version


def request_changes(db: Session, actor: User, version_id: str, reason: str) -> PolicyVersion:
    version = version_service.get_version(db, version_id)
    _transition(db, actor, version, VersionStatus.DRAFT, reason=reason or None)
    return version


def send_to_approval(db: Session, actor: User, version_id: str) -> PolicyVersion:
    version = version_service.get_version(db, version_id)
    _transition(db, actor, version, VersionStatus.IN_APPROVAL)
    version_service.freeze(version)  # conteúdo congela: hash calculado
    db.flush()
    return version


def approve(db: Session, actor: User, version_id: str, justification: str = "") -> PolicyVersion:
    version = version_service.get_version(db, version_id)
    _transition(db, actor, version, VersionStatus.APPROVED)
    db.add(
        Approval(
            version_id=version.id,
            approver_id=actor.id,
            decision=ApprovalDecision.APPROVED,
            justification=justification or None,
        )
    )
    db.flush()
    audit_service.record(
        db, actor.id, "version.approved", "policy_version", version.id,
        {"justification": justification or None},
    )
    events.emit(db, "version.approved", {"version_id": version.id})
    return version


def reject(db: Session, actor: User, version_id: str, justification: str) -> PolicyVersion:
    version = version_service.get_version(db, version_id)
    if version.created_by == actor.id and not version.is_rollback:
        raise PermissionDenied("segregação de funções: autor não decide a própria versão")
    _transition(db, actor, version, VersionStatus.DRAFT, reason=justification)
    db.add(
        Approval(
            version_id=version.id,
            approver_id=actor.id,
            decision=ApprovalDecision.REJECTED,
            justification=justification,
        )
    )
    db.flush()
    audit_service.record(
        db, actor.id, "version.rejected", "policy_version", version.id,
        {"justification": justification},
    )
    events.emit(db, "version.rejected", {"version_id": version.id})
    return version


def publish(
    db: Session, actor: User, version_id: str, effective_from: date
) -> PolicyVersion:
    """Publica versão aprovada com data de vigência (hoje = imediata; futura = agendada).

    Vigência retroativa não existe: effective_from >= hoje.
    """
    version = version_service.get_version(db, version_id)
    today = date.today()
    if effective_from < today:
        raise ValidationFailed("vigência retroativa não é permitida (effective_from >= hoje)")
    _transition(db, actor, version, VersionStatus.PUBLISHED)
    db.add(
        Publication(
            version_id=version.id,
            published_by=actor.id,
            effective_from=effective_from,
        )
    )
    db.flush()
    audit_service.record(
        db, actor.id, "version.published", "policy_version", version.id,
        {"effective_from": effective_from.isoformat()},
    )
    events.emit(db, "version.published", {"version_id": version.id})
    if effective_from <= today:
        make_effective(db, version.id)
    return version


def make_effective(db: Session, version_id: str) -> PolicyVersion:
    """Ação de SISTEMA: ativa a vigência em uma única transação.

    1. versão anterior vigente → superseded, com effective_until preenchido;
    2. nova versão → effective;
    3. policy.current_version_id atualizado;
    4. tudo auditado com actor_id=None.
    """
    version = version_service.get_version(db, version_id)
    policy = db.get(Policy, version.policy_id)
    publication = db.scalars(
        select(Publication).where(Publication.version_id == version.id)
    ).first()
    if publication is None:
        raise ValidationFailed("versão não tem publicação registrada")

    previous = db.scalars(
        select(PolicyVersion).where(
            PolicyVersion.policy_id == policy.id,
            PolicyVersion.status == VersionStatus.EFFECTIVE.value,
        )
    ).first()
    if previous is not None:
        _transition(db, None, previous, VersionStatus.SUPERSEDED)
        prev_publication = db.scalars(
            select(Publication).where(Publication.version_id == previous.id)
        ).first()
        if prev_publication is not None:
            prev_publication.effective_until = publication.effective_from
        db.flush()

    _transition(db, None, version, VersionStatus.EFFECTIVE)
    policy.current_version_id = version.id
    db.flush()
    audit_service.record(
        db, None, "version.effective", "policy_version", version.id,
        {
            "policy_code": policy.code,
            "version": version.version_number,
            "effective_from": publication.effective_from.isoformat(),
            "superseded_version": previous.version_number if previous else None,
        },
    )
    events.emit(
        db, "version.effective", {"version_id": version.id, "policy_id": policy.id}
    )
    return version


def apply_due_publications(db: Session) -> int:
    """Ativa vigências agendadas cuja data chegou. Retorna quantas ativou.

    Chamado por: tarefa periódica no lifespan + verificação lazy na leitura.
    """
    today = date.today()
    due = db.scalars(
        select(Publication)
        .join(PolicyVersion, PolicyVersion.id == Publication.version_id)
        .where(
            Publication.effective_from <= today,
            PolicyVersion.status == VersionStatus.PUBLISHED.value,
        )
    ).all()
    for publication in due:
        make_effective(db, publication.version_id)
    return len(due)


def rollback(
    db: Session, actor: User, policy_id: str, target_version_id: str, reason: str
) -> PolicyVersion:
    """Rollback = roll-forward: nova versão com conteúdo copiado da versão-alvo.

    Nada é apagado; histórico linear preservado. Fluxo expresso: a nova
    versão vai direto para aprovação (o conteúdo já foi aprovado no passado).
    """
    authz.ensure_role(actor, Role.APPROVER)
    if not reason.strip():
        raise ValidationFailed("justificativa é obrigatória para rollback")
    policy = db.get(Policy, policy_id)
    if policy is None:
        raise ValidationFailed("política não encontrada")
    target = version_service.get_version(db, target_version_id)
    if target.policy_id != policy_id:
        raise ValidationFailed("versão-alvo não pertence a esta política")
    if VersionStatus(target.status) not in (VersionStatus.SUPERSEDED, VersionStatus.EFFECTIVE):
        raise ValidationFailed("rollback só é possível para versões que já estiveram em vigor")
    existing = version_service.open_version(db, policy_id)
    if existing is not None:
        raise ValidationFailed(
            f"já existe a versão v{existing.version_number} aberta para esta política"
        )

    version = PolicyVersion(
        policy_id=policy.id,
        version_number=version_service.max_version_number(db, policy.id) + 1,
        status=VersionStatus.DRAFT,
        body_md=target.body_md,
        structured_fields=target.structured_fields,
        based_on_version_id=target.id,
        is_rollback=True,
        change_summary=f"Rollback para v{target.version_number}: {reason}",
        expected_impact=f"Restauração do comportamento da v{target.version_number}",
        created_by=actor.id,
    )
    db.add(version)
    db.flush()
    audit_service.record(
        db, actor.id, "version.rollback_created", "policy_version", version.id,
        {"target_version": target.version_number, "reason": reason},
    )
    _transition(db, actor, version, VersionStatus.IN_APPROVAL, reason=reason)
    version_service.freeze(version)
    db.flush()
    return version


def archive_version(db: Session, actor: User, version_id: str, reason: str = "") -> PolicyVersion:
    version = version_service.get_version(db, version_id)
    _transition(db, actor, version, VersionStatus.ARCHIVED, reason=reason or None)
    return version
