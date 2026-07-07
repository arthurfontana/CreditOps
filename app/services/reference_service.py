"""Grafo de referências entre políticas e artefatos (v2).

Arestas `usa` / `depende_de` / `substitui` de política → política ou
política → artefato (ex.: "Score Serasa"). Habilita a análise de
impacto: "se eu mudar X, quais políticas são afetadas?" — percorrendo
as arestas no sentido inverso (quem referencia o alvo, transitivo).
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import (
    Policy,
    PolicyReference,
    ReferenceRelation,
    ReferenceTargetType,
    Role,
    User,
)
from app.services import audit_service, authz
from app.services.errors import NotFound, ValidationFailed

MAX_DEPTH = 10  # grafos de política são rasos; limite defensivo contra ciclos longos


def add_reference(
    db: Session,
    actor: User,
    from_policy_id: str,
    *,
    relation: str,
    to_policy_id: str | None = None,
    artifact_name: str | None = None,
    note: str = "",
) -> PolicyReference:
    authz.ensure_role(actor, Role.AUTHOR, Role.ADMIN)
    policy = db.get(Policy, from_policy_id)
    if policy is None:
        raise NotFound("política não encontrada")
    authz.ensure_area_scope(actor, policy.area_id, action="editar referências")
    if relation not in [r.value for r in ReferenceRelation]:
        raise ValidationFailed(f"relação inválida: {relation}")

    artifact_name = (artifact_name or "").strip()
    if bool(to_policy_id) == bool(artifact_name):
        raise ValidationFailed("informe a política-alvo OU o nome do artefato (exatamente um)")

    if to_policy_id:
        if to_policy_id == from_policy_id:
            raise ValidationFailed("uma política não pode referenciar a si mesma")
        target = db.get(Policy, to_policy_id)
        if target is None:
            raise ValidationFailed("política-alvo não encontrada")
        to_type = ReferenceTargetType.POLICY.value
        target_label = target.code
    else:
        to_type = ReferenceTargetType.ARTIFACT.value
        target_label = artifact_name

    duplicate = db.scalars(
        select(PolicyReference).where(
            PolicyReference.from_policy_id == from_policy_id,
            PolicyReference.relation == relation,
            PolicyReference.to_policy_id == (to_policy_id or None),
            PolicyReference.artifact_name == (artifact_name or None),
        )
    ).first()
    if duplicate is not None:
        raise ValidationFailed("esta referência já existe")

    reference = PolicyReference(
        from_policy_id=from_policy_id,
        to_type=to_type,
        to_policy_id=to_policy_id or None,
        artifact_name=artifact_name or None,
        relation=relation,
        note=note.strip() or None,
        created_by=actor.id,
    )
    db.add(reference)
    db.flush()
    audit_service.record(
        db, actor.id, "policy.reference_added", "policy", from_policy_id,
        {"relation": relation, "to": target_label, "to_type": to_type},
    )
    return reference


def remove_reference(db: Session, actor: User, reference_id: str) -> None:
    authz.ensure_role(actor, Role.AUTHOR, Role.ADMIN)
    reference = db.get(PolicyReference, reference_id)
    if reference is None:
        raise NotFound("referência não encontrada")
    authz.ensure_area_scope(
        actor, reference.from_policy.area_id, action="editar referências"
    )
    target = (
        reference.to_policy.code if reference.to_policy else reference.artifact_name
    )
    audit_service.record(
        db, actor.id, "policy.reference_removed", "policy", reference.from_policy_id,
        {"relation": reference.relation, "to": target},
    )
    db.delete(reference)
    db.flush()


def outgoing(db: Session, policy_id: str) -> list[PolicyReference]:
    """Referências que esta política declara (o que ela usa/depende/substitui)."""
    return list(
        db.scalars(
            select(PolicyReference)
            .where(PolicyReference.from_policy_id == policy_id)
            .order_by(PolicyReference.relation, PolicyReference.created_at)
        )
    )


def incoming(db: Session, policy_id: str) -> list[PolicyReference]:
    """Referências que apontam para esta política (quem depende dela)."""
    return list(
        db.scalars(
            select(PolicyReference)
            .where(PolicyReference.to_policy_id == policy_id)
            .order_by(PolicyReference.relation, PolicyReference.created_at)
        )
    )


def artifact_names(db: Session) -> list[str]:
    """Artefatos já referenciados — para autocomplete e análise por artefato."""
    rows = db.execute(
        select(PolicyReference.artifact_name)
        .where(PolicyReference.artifact_name.is_not(None))
        .group_by(PolicyReference.artifact_name)
        .order_by(func.lower(PolicyReference.artifact_name))
    ).all()
    return [r[0] for r in rows]


@dataclass
class ImpactHit:
    """Política afetada pela mudança no alvo, com profundidade e caminho."""

    policy: Policy
    depth: int  # 1 = referencia o alvo diretamente
    via: str  # cadeia legível, ex.: "POL-CRD-002 → Score Serasa"


def impact_analysis(
    db: Session, *, policy_id: str | None = None, artifact_name: str | None = None
) -> list[ImpactHit]:
    """Quem é afetado se o alvo mudar: BFS nas arestas em sentido inverso.

    Nível 1 = políticas que referenciam o alvo; níveis seguintes =
    políticas que referenciam as afetadas (propagação transitiva).
    """
    if bool(policy_id) == bool(artifact_name is not None and artifact_name.strip()):
        raise ValidationFailed("informe a política OU o artefato (exatamente um)")

    if policy_id:
        target = db.get(Policy, policy_id)
        if target is None:
            raise NotFound("política não encontrada")
        target_label = target.code
        stmt = select(PolicyReference).where(PolicyReference.to_policy_id == policy_id)
    else:
        target_label = artifact_name.strip()
        stmt = select(PolicyReference).where(
            func.lower(PolicyReference.artifact_name) == target_label.lower()
        )

    hits: list[ImpactHit] = []
    seen: set[str] = {policy_id} if policy_id else set()
    frontier: list[tuple[str, str]] = []  # (policy_id, rótulo do caminho até aqui)

    for ref in db.scalars(stmt):
        if ref.from_policy_id in seen:
            continue
        seen.add(ref.from_policy_id)
        hits.append(ImpactHit(policy=ref.from_policy, depth=1, via=target_label))
        frontier.append((ref.from_policy_id, ref.from_policy.code))

    depth = 1
    while frontier and depth < MAX_DEPTH:
        depth += 1
        next_frontier: list[tuple[str, str]] = []
        for pid, path in frontier:
            for ref in db.scalars(
                select(PolicyReference).where(PolicyReference.to_policy_id == pid)
            ):
                if ref.from_policy_id in seen:
                    continue
                seen.add(ref.from_policy_id)
                hits.append(
                    ImpactHit(policy=ref.from_policy, depth=depth, via=f"{path} → {target_label}")
                )
                next_frontier.append((ref.from_policy_id, ref.from_policy.code))
        frontier = next_frontier
    return hits
