"""Triggers de integridade e tabela FTS5.

Usado pela migração Alembic e pelas fixtures de teste — a mesma fonte
garante que produção e testes rodam com as mesmas proteções.

Garantias no nível do BANCO (defesa em profundidade além do service layer):
- `policy_version` fora de `draft` é imutável (conteúdo) e indeletável;
- `audit_log`, `approval`, `status_transition` são append-only;
- `publication` só permite UPDATE de `effective_until` (substituição).
"""

from __future__ import annotations

TRIGGERS: list[str] = [
    # versão fora de rascunho: conteúdo imutável
    """
    CREATE TRIGGER trg_policy_version_immutable_update
    BEFORE UPDATE OF body_md, body_html, structured_fields, change_summary, expected_impact
    ON policy_version
    WHEN OLD.status != 'draft'
    BEGIN
        SELECT RAISE(ABORT, 'immutable version');
    END
    """,
    """
    CREATE TRIGGER trg_policy_version_no_delete
    BEFORE DELETE ON policy_version
    WHEN OLD.status != 'draft'
    BEGIN
        SELECT RAISE(ABORT, 'immutable version');
    END
    """,
    # trilha de auditoria: append-only
    """
    CREATE TRIGGER trg_audit_log_no_update
    BEFORE UPDATE ON audit_log
    BEGIN
        SELECT RAISE(ABORT, 'audit log is append-only');
    END
    """,
    """
    CREATE TRIGGER trg_audit_log_no_delete
    BEFORE DELETE ON audit_log
    BEGIN
        SELECT RAISE(ABORT, 'audit log is append-only');
    END
    """,
    # aprovações são evidência permanente
    """
    CREATE TRIGGER trg_approval_no_update
    BEFORE UPDATE ON approval
    BEGIN
        SELECT RAISE(ABORT, 'approval records are immutable');
    END
    """,
    """
    CREATE TRIGGER trg_approval_no_delete
    BEFORE DELETE ON approval
    BEGIN
        SELECT RAISE(ABORT, 'approval records are immutable');
    END
    """,
    # transições de status são histórico permanente
    """
    CREATE TRIGGER trg_status_transition_no_update
    BEFORE UPDATE ON status_transition
    BEGIN
        SELECT RAISE(ABORT, 'status transitions are immutable');
    END
    """,
    """
    CREATE TRIGGER trg_status_transition_no_delete
    BEFORE DELETE ON status_transition
    BEGIN
        SELECT RAISE(ABORT, 'status transitions are immutable');
    END
    """,
    # publicação: imutável, exceto effective_until (preenchido na substituição)
    """
    CREATE TRIGGER trg_publication_immutable_update
    BEFORE UPDATE OF version_id, published_by, published_at, effective_from,
                     release_id, rollout_scope, pilot_description, pilot_ends_at
    ON publication
    BEGIN
        SELECT RAISE(ABORT, 'publication records are immutable');
    END
    """,
    """
    CREATE TRIGGER trg_publication_no_delete
    BEFORE DELETE ON publication
    BEGIN
        SELECT RAISE(ABORT, 'publication records are immutable');
    END
    """,
]

TRIGGER_NAMES: list[str] = [
    "trg_policy_version_immutable_update",
    "trg_policy_version_no_delete",
    "trg_audit_log_no_update",
    "trg_audit_log_no_delete",
    "trg_approval_no_update",
    "trg_approval_no_delete",
    "trg_status_transition_no_update",
    "trg_status_transition_no_delete",
    "trg_publication_immutable_update",
    "trg_publication_no_delete",
]

FTS_CREATE = """
CREATE VIRTUAL TABLE IF NOT EXISTS policy_search USING fts5(
    policy_id UNINDEXED,
    code,
    title,
    body,
    tokenize = 'unicode61 remove_diacritics 2'
)
"""

FTS_DROP = "DROP TABLE IF EXISTS policy_search"


def install(connection) -> None:  # noqa: ANN001 - conexão DBAPI/SQLAlchemy
    """Instala triggers e a tabela FTS5 (idempotente)."""
    from sqlalchemy import text as sa_text

    for name in TRIGGER_NAMES:
        connection.execute(sa_text(f"DROP TRIGGER IF EXISTS {name}"))
    for ddl in TRIGGERS:
        connection.execute(sa_text(ddl))
    connection.execute(sa_text(FTS_CREATE))


def uninstall(connection) -> None:  # noqa: ANN001
    from sqlalchemy import text as sa_text

    for name in TRIGGER_NAMES:
        connection.execute(sa_text(f"DROP TRIGGER IF EXISTS {name}"))
    connection.execute(sa_text(FTS_DROP))
