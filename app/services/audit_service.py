"""Trilha de auditoria append-only com hash encadeado (v1).

Só INSERT — UPDATE/DELETE são bloqueados por trigger no banco.
Cada linha carrega `row_hash = sha256(prev_hash + dados canônicos)`:
adulteração de qualquer linha quebra a cadeia e é detectável por
`verify_chain` (usado por scripts/verify_audit.py).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditLog

GENESIS_HASH = ""  # prev_hash da primeira linha encadeada


def _canonical(
    actor_id: str | None,
    action: str,
    entity_type: str,
    entity_id: str | None,
    payload: str | None,
    created_at: datetime,
) -> str:
    return json.dumps(
        {
            "actor_id": actor_id,
            "action": action,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "payload": payload,
            "created_at": created_at.isoformat(),
        },
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _row_hash(prev_hash: str, canonical: str) -> str:
    return hashlib.sha256((prev_hash + canonical).encode("utf-8")).hexdigest()


def _last_row_hash(db: Session) -> str:
    last = db.scalars(select(AuditLog).order_by(AuditLog.id.desc()).limit(1)).first()
    if last is None:
        return GENESIS_HASH
    # linhas anteriores à v1 não têm hash: a cadeia (re)começa do genesis
    return last.row_hash or GENESIS_HASH


def record(
    db: Session,
    actor_id: str | None,
    action: str,
    entity_type: str,
    entity_id: str | None,
    payload: dict[str, Any] | None = None,
) -> AuditLog:
    """Registra um evento. actor_id=None indica ação do sistema (ex.: vigência)."""
    payload_json = (
        json.dumps(payload, ensure_ascii=False, default=str) if payload else None
    )
    created_at = datetime.utcnow()
    prev_hash = _last_row_hash(db)
    entry = AuditLog(
        actor_id=actor_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        payload=payload_json,
        prev_hash=prev_hash,
        row_hash=_row_hash(
            prev_hash,
            _canonical(actor_id, action, entity_type, entity_id, payload_json, created_at),
        ),
        created_at=created_at,
    )
    db.add(entry)
    db.flush()
    return entry


@dataclass
class ChainReport:
    total: int = 0
    chained: int = 0
    legacy: int = 0  # linhas do MVP, sem hash (anteriores à v1)
    broken: list[dict[str, Any]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.broken


def verify_chain(db: Session) -> ChainReport:
    """Percorre a trilha em ordem total e recalcula a cadeia de hashes.

    Linhas legadas (row_hash nulo) são toleradas apenas ANTES do início da
    cadeia; qualquer linha sem hash depois disso, hash divergente ou elo
    quebrado entra no relatório como violação.
    """
    report = ChainReport()
    prev_hash = GENESIS_HASH
    chain_started = False
    for entry in db.scalars(select(AuditLog).order_by(AuditLog.id)):
        report.total += 1
        if entry.row_hash is None:
            if chain_started:
                report.broken.append(
                    {"id": entry.id, "error": "linha sem hash no meio da cadeia"}
                )
            else:
                report.legacy += 1
            continue
        if not chain_started:
            chain_started = True
        if (entry.prev_hash or GENESIS_HASH) != prev_hash:
            report.broken.append(
                {"id": entry.id, "error": "prev_hash não corresponde à linha anterior"}
            )
        expected = _row_hash(
            entry.prev_hash or GENESIS_HASH,
            _canonical(
                entry.actor_id,
                entry.action,
                entry.entity_type,
                entry.entity_id,
                entry.payload,
                entry.created_at,
            ),
        )
        if entry.row_hash != expected:
            report.broken.append({"id": entry.id, "error": "row_hash divergente (adulteração?)"})
        else:
            report.chained += 1
        prev_hash = entry.row_hash
    return report


def query(
    db: Session,
    *,
    action: str | None = None,
    actor_id: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[AuditLog]:
    stmt = select(AuditLog).order_by(AuditLog.id.desc())
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if actor_id:
        stmt = stmt.where(AuditLog.actor_id == actor_id)
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    if entity_id:
        stmt = stmt.where(AuditLog.entity_id == entity_id)
    if date_from:
        stmt = stmt.where(AuditLog.created_at >= date_from)
    if date_to:
        stmt = stmt.where(AuditLog.created_at <= date_to)
    return list(db.scalars(stmt.limit(limit).offset(offset)))
