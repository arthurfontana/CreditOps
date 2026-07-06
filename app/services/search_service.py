"""Busca full-text sobre a versão vigente (SQLite FTS5).

Indexa código, título e corpo da versão EM VIGOR — rascunhos nunca
aparecem na busca (leitor não os vê nem por acidente).
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.models import Policy, PolicyLifecycle, User
from app.services import authz


def reindex_policy(db: Session, policy_id: str) -> None:
    """(Re)indexa a política: corpo da versão vigente; remove se arquivada/sem vigente."""
    db.execute(
        text("DELETE FROM policy_search WHERE policy_id = :pid"), {"pid": policy_id}
    )
    policy = db.get(Policy, policy_id)
    if (
        policy is None
        or policy.lifecycle_status == PolicyLifecycle.ARCHIVED
        or policy.current_version is None
    ):
        return
    db.execute(
        text(
            "INSERT INTO policy_search (policy_id, code, title, body) "
            "VALUES (:pid, :code, :title, :body)"
        ),
        {
            "pid": policy.id,
            "code": policy.code,
            "title": policy.title,
            "body": policy.current_version.body_md,
        },
    )


def reindex_all(db: Session) -> int:
    db.execute(text("DELETE FROM policy_search"))
    count = 0
    for policy in db.scalars(select(Policy)):
        reindex_policy(db, policy.id)
        count += 1
    return count


@dataclass
class SearchHit:
    policy_id: str
    code: str
    title: str
    snippet: str


def _fts_escape(query: str) -> str:
    """Trata a consulta como termos literais (prefix match no último termo)."""
    terms = [t.replace('"', '""') for t in query.split() if t.strip()]
    if not terms:
        return ""
    quoted = [f'"{t}"' for t in terms[:-1]]
    quoted.append(f'"{terms[-1]}"*')
    return " ".join(quoted)


def search(db: Session, query: str, viewer: User, limit: int = 20) -> list[SearchHit]:
    authz.ensure_active(viewer)
    match = _fts_escape(query)
    if not match:
        return []
    rows = db.execute(
        text(
            "SELECT policy_id, code, title, "
            "snippet(policy_search, 3, '<mark>', '</mark>', ' … ', 12) AS snip "
            "FROM policy_search WHERE policy_search MATCH :match "
            "ORDER BY rank LIMIT :limit"
        ),
        {"match": match, "limit": limit},
    ).all()
    return [SearchHit(policy_id=r[0], code=r[1], title=r[2], snippet=r[3]) for r in rows]
