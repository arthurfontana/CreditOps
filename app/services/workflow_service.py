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
    ChangeRequest,
    ChangeRequestStatus,
    Policy,
    PolicyVersion,
    Publication,
    Release,
    Role,
    RolloutScope,
    StatusTransition,
    User,
    VersionStatus,
)
from app.services import (
    approval_rules,
    audit_service,
    authz,
    delegation_service,
    events,
    version_service,
)
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
    scope_user: User | None = None,
) -> None:
    """Valida a whitelist + papel + escopo de área, muda o status e grava a evidência.

    `scope_user`: usuário cujo escopo de área vale para esta ação — o próprio
    ator por padrão; o delegante quando a decisão é tomada sob delegação.
    """
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
        authz.ensure_area_scope(scope_user or actor, version.policy.area_id)
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
    events.emit(db, "version.sent_to_approval", {"version_id": version.id})
    return version


# ─── aprovação multinível + delegação (v1) ───────────────────────────────────


def _current_round_approvals(db: Session, version: PolicyVersion) -> list[Approval]:
    """Aprovações da rodada atual (após a última entrada em `in_approval`).

    Rodadas anteriores (rejeitadas e reenviadas) não contam para os níveis.
    """
    last_entry = db.scalars(
        select(StatusTransition)
        .where(
            StatusTransition.version_id == version.id,
            StatusTransition.to_status == VersionStatus.IN_APPROVAL.value,
        )
        .order_by(StatusTransition.created_at.desc(), StatusTransition.id.desc())
        .limit(1)
    ).first()
    stmt = select(Approval).where(
        Approval.version_id == version.id,
        Approval.decision == ApprovalDecision.APPROVED.value,
    )
    if last_entry is not None:
        stmt = stmt.where(Approval.decided_at >= last_entry.created_at)
    return list(db.scalars(stmt.order_by(Approval.level)))


def approval_progress(db: Session, version: PolicyVersion) -> tuple[int, int]:
    """(níveis aprovados na rodada atual, níveis exigidos pelo tipo)."""
    required = approval_rules.required_levels(db, version.policy.policy_type)
    done = len(_current_round_approvals(db, version))
    return done, required


def _resolve_decision_actor(
    db: Session, actor: User, version: PolicyVersion, on_behalf_of: str | None
) -> User | None:
    """Valida papel/escopo/segregação do decisor e resolve a delegação.

    Retorna o delegante (para registrar `delegated_from_id`) ou None quando
    o aprovador decide em nome próprio.
    """
    authz.ensure_role(actor, Role.APPROVER)
    if version.created_by == actor.id and not version.is_rollback:
        raise PermissionDenied("segregação de funções: autor não decide a própria versão")

    area_id = version.policy.area_id
    delegator: User | None = None
    if on_behalf_of:
        candidates = {
            d.delegator_id for d in delegation_service.active_delegations_to(db, actor.id)
        }
        if on_behalf_of not in candidates:
            raise PermissionDenied("não há delegação ativa deste aprovador para você")
        delegator = db.get(User, on_behalf_of)
    elif not authz.in_area_scope(actor, area_id):
        # fora da própria área: só decide se alguém da área delegou
        delegator = delegation_service.resolve_delegator(db, actor, area_id=area_id)
        if delegator is None:
            raise PermissionDenied(
                "permissão por área: você não pode decidir políticas de outra área"
            )
    if delegator is not None:
        if delegator.id == version.created_by and not version.is_rollback:
            raise PermissionDenied(
                "segregação de funções: delegação do autor não permite decidir a própria versão"
            )
        authz.ensure_area_scope(delegator, area_id)
    return delegator


def approve(
    db: Session,
    actor: User,
    version_id: str,
    justification: str = "",
    *,
    on_behalf_of: str | None = None,
) -> PolicyVersion:
    """Aprova o nível corrente. A versão só avança para `approved` quando o
    último nível exigido pelo tipo é atingido; qualquer rejeição devolve tudo."""
    version = version_service.get_version(db, version_id)
    if VersionStatus(version.status) != VersionStatus.IN_APPROVAL:
        raise InvalidTransition(
            f"transição não permitida: {version.status} → {VersionStatus.APPROVED}"
        )
    delegator = _resolve_decision_actor(db, actor, version, on_behalf_of)
    done, required = approval_progress(db, version)
    round_approvals = _current_round_approvals(db, version)
    deciders = {a.approver_id for a in round_approvals} | {
        a.delegated_from_id for a in round_approvals if a.delegated_from_id
    }
    if actor.id in deciders or (delegator and delegator.id in deciders):
        raise ValidationFailed("cada nível de aprovação exige um aprovador diferente")

    level = done + 1
    db.add(
        Approval(
            version_id=version.id,
            approver_id=actor.id,
            decision=ApprovalDecision.APPROVED,
            level=level,
            justification=justification or None,
            delegated_from_id=delegator.id if delegator else None,
        )
    )
    db.flush()
    audit_service.record(
        db, actor.id, "version.approved", "policy_version", version.id,
        {
            "level": level,
            "required_levels": required,
            "justification": justification or None,
            "delegated_from": delegator.id if delegator else None,
        },
    )
    if level >= required:
        _transition(db, actor, version, VersionStatus.APPROVED, scope_user=delegator or actor)
        events.emit(db, "version.approved", {"version_id": version.id})
    else:
        events.emit(
            db, "version.approval_level",
            {"version_id": version.id, "level": level, "required": required},
        )
    return version


def reject(
    db: Session,
    actor: User,
    version_id: str,
    justification: str,
    *,
    on_behalf_of: str | None = None,
) -> PolicyVersion:
    version = version_service.get_version(db, version_id)
    if VersionStatus(version.status) != VersionStatus.IN_APPROVAL:
        raise InvalidTransition(
            f"transição não permitida: {version.status} → {VersionStatus.DRAFT}"
        )
    delegator = _resolve_decision_actor(db, actor, version, on_behalf_of)
    _transition(
        db, actor, version, VersionStatus.DRAFT,
        reason=justification, scope_user=delegator or actor,
    )
    db.add(
        Approval(
            version_id=version.id,
            approver_id=actor.id,
            decision=ApprovalDecision.REJECTED,
            justification=justification,
            delegated_from_id=delegator.id if delegator else None,
        )
    )
    db.flush()
    audit_service.record(
        db, actor.id, "version.rejected", "policy_version", version.id,
        {
            "justification": justification,
            "delegated_from": delegator.id if delegator else None,
        },
    )
    events.emit(db, "version.rejected", {"version_id": version.id})
    return version


def publish(
    db: Session,
    actor: User,
    version_id: str,
    effective_from: date,
    *,
    release_id: str | None = None,
    rollout_scope: str = RolloutScope.FULL.value,
    pilot_description: str | None = None,
    pilot_ends_at: date | None = None,
) -> PolicyVersion:
    """Publica versão aprovada com data de vigência (hoje = imediata; futura = agendada).

    Vigência retroativa não existe: effective_from >= hoje.
    `release_id` (v1) agrupa publicações feitas em conjunto.
    Publicação-experimento (v2): rollout_scope="pilot" exige escopo declarado
    (pilot_description) e prazo (pilot_ends_at) — o motor executa o teste,
    o CreditOps o documenta e governa; promoção/encerramento seguem o fluxo
    normal de aprovação.
    """
    version = version_service.get_version(db, version_id)
    today = date.today()
    if effective_from < today:
        raise ValidationFailed("vigência retroativa não é permitida (effective_from >= hoje)")
    if rollout_scope not in [s.value for s in RolloutScope]:
        raise ValidationFailed(f"escopo de publicação inválido: {rollout_scope}")
    if rollout_scope == RolloutScope.PILOT.value:
        if not (pilot_description and pilot_description.strip()):
            raise ValidationFailed(
                "piloto exige escopo declarado (segmento, região, % da esteira e "
                "critério de sucesso)"
            )
        if pilot_ends_at is None:
            raise ValidationFailed("piloto exige prazo (pilot_ends_at)")
        if pilot_ends_at <= effective_from:
            raise ValidationFailed("prazo do piloto deve ser posterior à vigência")
    else:
        pilot_description = None
        pilot_ends_at = None
    release = None
    if release_id:
        release = db.get(Release, release_id)
        if release is None:
            raise ValidationFailed("release não encontrada")
    _transition(db, actor, version, VersionStatus.PUBLISHED)
    db.add(
        Publication(
            version_id=version.id,
            published_by=actor.id,
            effective_from=effective_from,
            release_id=release_id or None,
            rollout_scope=rollout_scope,
            pilot_description=pilot_description.strip() if pilot_description else None,
            pilot_ends_at=pilot_ends_at,
        )
    )
    if release is not None:
        release.published_at = datetime.utcnow()
    db.flush()
    audit_service.record(
        db, actor.id, "version.published", "policy_version", version.id,
        {
            "effective_from": effective_from.isoformat(),
            "release": release.name if release else None,
            "rollout_scope": rollout_scope,
            "pilot_ends_at": pilot_ends_at.isoformat() if pilot_ends_at else None,
        },
    )
    events.emit(
        db, "version.published",
        {"version_id": version.id, "rollout_scope": rollout_scope},
    )
    if effective_from <= today:
        make_effective(db, version.id)
    return version


def active_pilots(db: Session) -> list[Publication]:
    """Publicações-experimento cuja versão está em vigor (v2).

    Piloto com prazo vencido continua na lista — é exatamente o que
    precisa de decisão (promover, ajustar ou encerrar pelo fluxo normal).
    """
    return list(
        db.scalars(
            select(Publication)
            .join(PolicyVersion, PolicyVersion.id == Publication.version_id)
            .where(
                Publication.rollout_scope == RolloutScope.PILOT.value,
                PolicyVersion.status == VersionStatus.EFFECTIVE.value,
            )
            .order_by(Publication.pilot_ends_at)
        )
    )


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

    # fecha a demanda vinculada: lead time demanda → vigência (v1)
    if version.change_request_id:
        change_request = db.get(ChangeRequest, version.change_request_id)
        if change_request is not None and change_request.status in (
            ChangeRequestStatus.OPEN,
            ChangeRequestStatus.IN_PROGRESS,
        ):
            change_request.status = ChangeRequestStatus.DONE
            change_request.closed_at = datetime.utcnow()
            change_request.resolution = (
                f"Concluída pela vigência de {policy.code} v{version.version_number}"
            )
            db.flush()
            audit_service.record(
                db, None, "change_request.done", "change_request", change_request.id,
                {"code": change_request.code, "version_id": version.id},
            )
        # retroalimenta a biblioteca de cineminhas na mesma transação da vigência
        from app.services import cinema_service

        cinema_service.promote_for_change_request(db, version.change_request_id, version.id)

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
    authz.ensure_area_scope(actor, policy.area_id, action="fazer rollback")
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
