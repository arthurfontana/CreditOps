"""Cineminha: catálogo de variáveis, biblioteca versionada e instâncias em demanda.

Ciclo (espelha o fluxo combinado com a área de crédito):
1. o usuário mantém um catálogo de variáveis de decisão (domínios padrão);
2. cria entradas na biblioteca (Cinema) cruzando duas variáveis; a carga
   inicial (AS IS de produção) pode ser gravada manualmente como versão;
3. numa demanda, "puxa" um cineminha da biblioteca — vira CinemaInstance
   (cópia de trabalho); edita as caselas à vontade, a biblioteca fica intacta;
4. quando a versão de política vinculada à demanda entra em vigor,
   promote_for_change_request grava a instância como nova CinemaVersion
   (retroalimentação) — chamado por workflow_service.make_effective, na
   mesma transação da vigência, tudo auditado.

Caselas (`cells`): {"<linha>|<coluna>": valor}. eligibility: 0/1 (ausente=1);
offer: número >= 0 (ausente=0).
"""

from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    ChangeRequest,
    ChangeRequestStatus,
    Cinema,
    CinemaInstance,
    CinemaInstanceStatus,
    CinemaType,
    CinemaVersion,
    CinemaVersionOrigin,
    DecisionVariable,
    Role,
    User,
)
from app.services import audit_service, authz, events
from app.services.errors import NotFound, PermissionDenied, ValidationFailed

CELL_SEP = "|"
MAX_DOMAIN_VALUES = 60  # eixo maior que isso deixa a matriz inutilizável na tela


# ── Catálogo de variáveis ────────────────────────────────────────────────────


def _parse_domain(raw: str | list[str]) -> list[str]:
    """Normaliza o domínio: lista ordenada, sem vazios nem duplicados."""
    if isinstance(raw, str):
        values = [v.strip() for v in raw.replace("\n", ",").split(",")]
    else:
        values = [str(v).strip() for v in raw]
    seen: set[str] = set()
    domain: list[str] = []
    for v in values:
        if v and v not in seen:
            if CELL_SEP in v:
                raise ValidationFailed(f"valor de domínio não pode conter '{CELL_SEP}': {v}")
            seen.add(v)
            domain.append(v)
    if not domain:
        raise ValidationFailed("domínio da variável não pode ser vazio")
    if len(domain) > MAX_DOMAIN_VALUES:
        raise ValidationFailed(f"domínio excede o máximo de {MAX_DOMAIN_VALUES} valores")
    return domain


def create_variable(
    db: Session,
    actor: User,
    *,
    name: str,
    label: str,
    domain: str | list[str],
    is_ordinal: bool = True,
    description: str = "",
) -> DecisionVariable:
    authz.ensure_role(actor, Role.AUTHOR, Role.APPROVER, Role.ADMIN)
    name = name.strip().upper()
    if not name:
        raise ValidationFailed("nome da variável é obrigatório")
    if db.scalars(select(DecisionVariable).where(DecisionVariable.name == name)).first():
        raise ValidationFailed(f"variável já existe: {name}")
    variable = DecisionVariable(
        name=name,
        label=label.strip() or name,
        description=description.strip() or None,
        domain_json=json.dumps(_parse_domain(domain), ensure_ascii=False),
        is_ordinal=is_ordinal,
        created_by=actor.id,
    )
    db.add(variable)
    db.flush()
    audit_service.record(
        db, actor.id, "decision_variable.created", "decision_variable", variable.id,
        {"name": name, "domain": variable_domain(variable)},
    )
    return variable


def update_variable(
    db: Session,
    actor: User,
    variable_id: str,
    *,
    label: str,
    domain: str | list[str],
    is_ordinal: bool,
    description: str = "",
    is_active: bool = True,
) -> DecisionVariable:
    """Atualiza o catálogo — afeta apenas matrizes/instâncias criadas dali em diante."""
    authz.ensure_role(actor, Role.AUTHOR, Role.APPROVER, Role.ADMIN)
    variable = get_variable(db, variable_id)
    variable.label = label.strip() or variable.name
    variable.description = description.strip() or None
    variable.domain_json = json.dumps(_parse_domain(domain), ensure_ascii=False)
    variable.is_ordinal = is_ordinal
    variable.is_active = is_active
    db.flush()
    audit_service.record(
        db, actor.id, "decision_variable.updated", "decision_variable", variable.id,
        {"name": variable.name, "domain": variable_domain(variable), "is_active": is_active},
    )
    return variable


def get_variable(db: Session, variable_id: str) -> DecisionVariable:
    variable = db.get(DecisionVariable, variable_id)
    if variable is None:
        raise NotFound("variável não encontrada")
    return variable


def list_variables(db: Session, include_inactive: bool = False) -> list[DecisionVariable]:
    stmt = select(DecisionVariable).order_by(DecisionVariable.name)
    if not include_inactive:
        stmt = stmt.where(DecisionVariable.is_active)
    return list(db.scalars(stmt))


def variable_domain(variable: DecisionVariable) -> list[str]:
    return json.loads(variable.domain_json or "[]")


# ── Biblioteca (Cinema / CinemaVersion) ──────────────────────────────────────


def create_cinema(
    db: Session,
    actor: User,
    *,
    name: str,
    cinema_type: str,
    row_variable_id: str,
    col_variable_id: str,
    description: str = "",
) -> Cinema:
    authz.ensure_role(actor, Role.AUTHOR, Role.APPROVER, Role.ADMIN)
    name = name.strip()
    if not name:
        raise ValidationFailed("nome do cineminha é obrigatório")
    if cinema_type not in [t.value for t in CinemaType]:
        raise ValidationFailed(f"tipo de cineminha inválido: {cinema_type}")
    if db.scalars(select(Cinema).where(Cinema.name == name)).first():
        raise ValidationFailed(f"já existe cineminha com o nome: {name}")
    row_var = get_variable(db, row_variable_id)
    col_var = get_variable(db, col_variable_id)
    cinema = Cinema(
        name=name,
        description=description.strip() or None,
        cinema_type=cinema_type,
        row_variable_id=row_var.id,
        col_variable_id=col_var.id,
        created_by=actor.id,
    )
    db.add(cinema)
    db.flush()
    audit_service.record(
        db, actor.id, "cinema.created", "cinema", cinema.id,
        {"name": name, "type": cinema_type, "row": row_var.name, "col": col_var.name},
    )
    return cinema


def get_cinema(db: Session, cinema_id: str) -> Cinema:
    cinema = db.get(Cinema, cinema_id)
    if cinema is None:
        raise NotFound("cineminha não encontrado")
    return cinema


def list_cinemas(db: Session, include_inactive: bool = False) -> list[Cinema]:
    stmt = select(Cinema).order_by(Cinema.name)
    if not include_inactive:
        stmt = stmt.where(Cinema.is_active)
    return list(db.scalars(stmt))


def _validate_cells(cinema_type: str, cells: dict, row_domain: list[str], col_domain: list[str]):
    """Valida chaves e valores das caselas contra o domínio e o tipo."""
    if not isinstance(cells, dict):
        raise ValidationFailed("caselas inválidas: esperado objeto {chave: valor}")
    rows, cols = set(row_domain), set(col_domain)
    clean: dict[str, float | int] = {}
    for key, value in cells.items():
        parts = str(key).split(CELL_SEP)
        if len(parts) != 2 or parts[0] not in rows or parts[1] not in cols:
            raise ValidationFailed(f"casela fora do domínio: {key}")
        try:
            number = float(value)
        except (TypeError, ValueError):
            raise ValidationFailed(f"valor inválido na casela {key}: {value}") from None
        if cinema_type == CinemaType.ELIGIBILITY:
            if number not in (0, 1):
                raise ValidationFailed(f"casela de elegibilidade deve ser 0 ou 1: {key}")
            clean[key] = int(number)
        else:
            if number < 0:
                raise ValidationFailed(f"valor de oferta não pode ser negativo: {key}")
            clean[key] = int(number) if number.is_integer() else number
    return clean


def _next_version_number(db: Session, cinema_id: str) -> int:
    numbers = db.scalars(
        select(CinemaVersion.version_number).where(CinemaVersion.cinema_id == cinema_id)
    )
    return max(numbers, default=0) + 1


def create_manual_version(
    db: Session,
    actor: User,
    cinema_id: str,
    *,
    cells: dict,
    row_domain: list[str] | None = None,
    col_domain: list[str] | None = None,
) -> CinemaVersion:
    """Carga manual (baseline/AS IS de produção) direto na biblioteca — auditada.

    O caminho normal de evolução é a promoção via demanda; a carga manual
    existe para semear a biblioteca com o que já está em produção.
    """
    authz.ensure_role(actor, Role.AUTHOR, Role.APPROVER, Role.ADMIN)
    cinema = get_cinema(db, cinema_id)
    row_domain = row_domain or variable_domain(cinema.row_variable)
    col_domain = col_domain or variable_domain(cinema.col_variable)
    clean = _validate_cells(cinema.cinema_type, cells, row_domain, col_domain)
    version = CinemaVersion(
        cinema_id=cinema.id,
        version_number=_next_version_number(db, cinema.id),
        row_domain_json=json.dumps(row_domain, ensure_ascii=False),
        col_domain_json=json.dumps(col_domain, ensure_ascii=False),
        cells_json=json.dumps(clean, ensure_ascii=False),
        origin=CinemaVersionOrigin.MANUAL,
        created_by=actor.id,
    )
    db.add(version)
    db.flush()
    # atribui pela RELAÇÃO (não só o FK): a sessão usa expire_on_commit=False e
    # um current_version já carregado ficaria apontando para a versão antiga
    cinema.current_version = version
    db.flush()
    audit_service.record(
        db, actor.id, "cinema.version_created", "cinema", cinema.id,
        {"name": cinema.name, "version": version.version_number, "origin": "manual"},
    )
    return version


def version_history(db: Session, cinema_id: str) -> list[CinemaVersion]:
    """Trilha da biblioteca: versões da mais recente para a mais antiga."""
    return list(
        db.scalars(
            select(CinemaVersion)
            .where(CinemaVersion.cinema_id == cinema_id)
            .order_by(CinemaVersion.version_number.desc())
        )
    )


# ── Instâncias em demanda ────────────────────────────────────────────────────


def _ensure_can_edit_demand(db: Session, actor: User, change_request: ChangeRequest) -> None:
    """Solicitante, autores e admin mexem na demanda enquanto ela está aberta."""
    authz.ensure_active(actor)
    if change_request.status not in (
        ChangeRequestStatus.OPEN,
        ChangeRequestStatus.IN_PROGRESS,
    ):
        raise ValidationFailed("demanda encerrada não pode ser alterada")
    role = Role(actor.role)
    if role in (Role.ADMIN, Role.AUTHOR, Role.APPROVER):
        return
    if change_request.requested_by == actor.id:
        return
    raise PermissionDenied("apenas o solicitante ou autores podem alterar a demanda")


def get_instance(db: Session, instance_id: str) -> CinemaInstance:
    instance = db.get(CinemaInstance, instance_id)
    if instance is None:
        raise NotFound("cineminha da demanda não encontrado")
    return instance


def list_instances(db: Session, change_request_id: str) -> list[CinemaInstance]:
    return list(
        db.scalars(
            select(CinemaInstance)
            .where(CinemaInstance.change_request_id == change_request_id)
            .order_by(CinemaInstance.created_at)
        )
    )


def add_instance(
    db: Session, actor: User, change_request_id: str, cinema_id: str
) -> CinemaInstance:
    """"Puxa" um cineminha da biblioteca para a demanda (congela a origem)."""
    change_request = db.get(ChangeRequest, change_request_id)
    if change_request is None:
        raise NotFound("demanda não encontrada")
    _ensure_can_edit_demand(db, actor, change_request)
    cinema = get_cinema(db, cinema_id)
    if not cinema.is_active:
        raise ValidationFailed("cineminha inativo na biblioteca")

    source = cinema.current_version
    if source is not None:
        row_domain, col_domain = json.loads(source.row_domain_json), json.loads(
            source.col_domain_json
        )
        cells = source.cells_json
    else:
        row_domain = variable_domain(cinema.row_variable)
        col_domain = variable_domain(cinema.col_variable)
        cells = "{}"

    instance = CinemaInstance(
        change_request_id=change_request.id,
        cinema_id=cinema.id,
        source_version_id=source.id if source else None,
        row_domain_json=json.dumps(row_domain, ensure_ascii=False),
        col_domain_json=json.dumps(col_domain, ensure_ascii=False),
        cells_json=cells,
        created_by=actor.id,
    )
    db.add(instance)
    db.flush()
    audit_service.record(
        db, actor.id, "cinema_instance.created", "cinema_instance", instance.id,
        {
            "change_request": change_request.code,
            "cinema": cinema.name,
            "source_version": source.version_number if source else None,
        },
    )
    return instance


def update_instance_cells(
    db: Session, actor: User, instance_id: str, cells: dict, notes: str = ""
) -> CinemaInstance:
    instance = get_instance(db, instance_id)
    _ensure_can_edit_demand(db, actor, instance.change_request)
    if instance.status != CinemaInstanceStatus.DRAFT:
        raise ValidationFailed("instância já promovida à biblioteca é imutável")
    clean = _validate_cells(
        instance.cinema.cinema_type,
        cells,
        json.loads(instance.row_domain_json),
        json.loads(instance.col_domain_json),
    )
    instance.cells_json = json.dumps(clean, ensure_ascii=False)
    instance.notes = notes.strip() or None
    db.flush()
    audit_service.record(
        db, actor.id, "cinema_instance.updated", "cinema_instance", instance.id,
        {
            "change_request": instance.change_request.code,
            "cinema": instance.cinema.name,
            "changed_cells": len(diff_cells(instance)),
        },
    )
    return instance


def remove_instance(db: Session, actor: User, instance_id: str) -> None:
    instance = get_instance(db, instance_id)
    _ensure_can_edit_demand(db, actor, instance.change_request)
    if instance.status != CinemaInstanceStatus.DRAFT:
        raise ValidationFailed("instância já promovida à biblioteca não pode ser removida")
    audit_service.record(
        db, actor.id, "cinema_instance.removed", "cinema_instance", instance.id,
        {"change_request": instance.change_request.code, "cinema": instance.cinema.name},
    )
    db.delete(instance)
    db.flush()


# ── Leitura das matrizes (render/diff/export) ────────────────────────────────


def cell_value(cinema_type: str, cells: dict, row: str, col: str):
    """Valor efetivo de uma casela, aplicando o default do tipo."""
    raw = cells.get(f"{row}{CELL_SEP}{col}")
    if raw is None:
        return 1 if cinema_type == CinemaType.ELIGIBILITY else 0
    return raw


def matrix_view(
    *,
    cinema_type: str,
    row_domain_json: str,
    col_domain_json: str,
    cells_json: str,
    baseline_cells_json: str | None = None,
) -> dict:
    """Estrutura pronta para o template/JS: domínios, grade de valores e diff.

    `changed` marca as caselas cujo valor difere do baseline (origem na
    biblioteca) — é o que o aprovador precisa enxergar de imediato.
    """
    row_domain = json.loads(row_domain_json or "[]")
    col_domain = json.loads(col_domain_json or "[]")
    cells = json.loads(cells_json or "{}")
    baseline = json.loads(baseline_cells_json) if baseline_cells_json is not None else None

    grid: list[list] = []
    changed: list[list[bool]] = []
    max_value = 0.0
    for row in row_domain:
        grid_row: list = []
        changed_row: list[bool] = []
        for col in col_domain:
            value = cell_value(cinema_type, cells, row, col)
            grid_row.append(value)
            max_value = max(max_value, float(value))
            if baseline is None:
                changed_row.append(False)
            else:
                changed_row.append(value != cell_value(cinema_type, baseline, row, col))
        grid.append(grid_row)
        changed.append(changed_row)

    return {
        "cinema_type": cinema_type,
        "row_domain": row_domain,
        "col_domain": col_domain,
        "cells": cells,
        "grid": grid,
        "changed": changed,
        "max_value": max_value,
        "changed_count": sum(sum(1 for c in r if c) for r in changed),
    }


def instance_view(instance: CinemaInstance) -> dict:
    """matrix_view da instância com diff contra a versão de origem."""
    baseline = instance.source_version.cells_json if instance.source_version else None
    return matrix_view(
        cinema_type=instance.cinema.cinema_type,
        row_domain_json=instance.row_domain_json,
        col_domain_json=instance.col_domain_json,
        cells_json=instance.cells_json,
        baseline_cells_json=baseline,
    )


def diff_cells(instance: CinemaInstance) -> list[dict]:
    """Lista de caselas alteradas vs. a origem: [{row, col, before, after}]."""
    view = instance_view(instance)
    baseline = json.loads(instance.source_version.cells_json) if instance.source_version else {}
    ctype = instance.cinema.cinema_type
    out: list[dict] = []
    for i, row in enumerate(view["row_domain"]):
        for j, col in enumerate(view["col_domain"]):
            if view["changed"][i][j]:
                out.append(
                    {
                        "row": row,
                        "col": col,
                        "before": cell_value(ctype, baseline, row, col),
                        "after": view["grid"][i][j],
                    }
                )
    return out


def is_stale(instance: CinemaInstance) -> bool:
    """Base defasada: a biblioteca já tem versão vigente mais nova que a origem."""
    current_id = instance.cinema.current_version_id
    return (
        instance.status == CinemaInstanceStatus.DRAFT
        and current_id is not None
        and current_id != instance.source_version_id
    )


def rebase_instance(db: Session, actor: User, instance_id: str) -> CinemaInstance:
    """Re-baseia a instância na versão vigente atual, preservando as edições.

    As caselas editadas (diferentes da origem antiga) são reaplicadas sobre a
    versão vigente; o restante passa a refletir a biblioteca atual.
    """
    instance = get_instance(db, instance_id)
    _ensure_can_edit_demand(db, actor, instance.change_request)
    if instance.status != CinemaInstanceStatus.DRAFT:
        raise ValidationFailed("instância já promovida não pode ser re-baseada")
    current = instance.cinema.current_version
    if current is None or current.id == instance.source_version_id:
        raise ValidationFailed("instância já está na versão vigente da biblioteca")

    edits = diff_cells(instance)  # antes de trocar a base
    instance.source_version = current  # relação, não só FK (expire_on_commit=False)
    instance.row_domain_json = current.row_domain_json
    instance.col_domain_json = current.col_domain_json
    cells = json.loads(current.cells_json)
    row_domain = json.loads(current.row_domain_json)
    col_domain = json.loads(current.col_domain_json)
    reapplied = 0
    for edit in edits:
        if edit["row"] in row_domain and edit["col"] in col_domain:
            cells[f"{edit['row']}{CELL_SEP}{edit['col']}"] = edit["after"]
            reapplied += 1
    instance.cells_json = json.dumps(cells, ensure_ascii=False)
    db.flush()
    audit_service.record(
        db, actor.id, "cinema_instance.rebased", "cinema_instance", instance.id,
        {
            "cinema": instance.cinema.name,
            "new_source_version": current.version_number,
            "reapplied_edits": reapplied,
        },
    )
    return instance


# ── Retroalimentação da biblioteca (chamada pela vigência) ───────────────────


def promote_for_change_request(db: Session, change_request_id: str, policy_version_id: str) -> int:
    """Promove as instâncias em rascunho da demanda a novas versões da biblioteca.

    Ação de SISTEMA (actor_id=None), chamada por workflow_service.make_effective
    na MESMA transação da vigência — a política entra em vigor e a biblioteca é
    retroalimentada atomicamente. Retorna o número de instâncias promovidas.
    """
    promoted = 0
    for instance in list_instances(db, change_request_id):
        if instance.status != CinemaInstanceStatus.DRAFT:
            continue
        cinema = instance.cinema
        version = CinemaVersion(
            cinema_id=cinema.id,
            version_number=_next_version_number(db, cinema.id),
            row_domain_json=instance.row_domain_json,
            col_domain_json=instance.col_domain_json,
            cells_json=instance.cells_json,
            origin=CinemaVersionOrigin.PROMOTION,
            change_request_id=change_request_id,
            policy_version_id=policy_version_id,
            created_by=None,
        )
        db.add(version)
        db.flush()
        # relações, não só FKs (expire_on_commit=False — ver create_manual_version)
        cinema.current_version = version
        instance.status = CinemaInstanceStatus.PROMOTED
        instance.promoted_version = version
        db.flush()
        audit_service.record(
            db, None, "cinema.version_promoted", "cinema", cinema.id,
            {
                "name": cinema.name,
                "version": version.version_number,
                "change_request_id": change_request_id,
                "policy_version_id": policy_version_id,
                "changed_cells": len(diff_cells(instance)),
            },
        )
        events.emit(
            db,
            "cinema.promoted",
            {
                "cinema_id": cinema.id,
                "cinema_name": cinema.name,
                "version": version.version_number,
                "change_request_id": change_request_id,
            },
        )
        promoted += 1
    return promoted
