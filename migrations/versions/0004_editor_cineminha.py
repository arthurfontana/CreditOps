"""v3 "Editor e Cineminha": WYSIWYG, anexos em demanda e biblioteca de cineminhas.

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-07

Novas tabelas: decision_variable, cinema, cinema_version, cinema_instance.
Colunas novas: change_request.description_html, policy_version.body_html,
attachment.change_request_id (+ attachment.version_id passa a aceitar nulo —
anexo pertence a UMA das âncoras: versão OU demanda).

Reinstala os guards (schema_guards.install): o trigger de imutabilidade de
policy_version passa a cobrir também body_html.

Idempotente como a 0002/0003: em bancos novos a 0001 cria o esquema completo
a partir do metadata dos models; aqui só se adiciona o que faltar.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app import schema_guards
from app.models import Base

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

V3_TABLES = [
    "decision_variable",
    "cinema",
    "cinema_version",
    "cinema_instance",
]


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = set(inspector.get_table_names())

    for name in V3_TABLES:
        if name not in existing:
            Base.metadata.tables[name].create(bind=bind)

    cr_columns = {c["name"] for c in inspector.get_columns("change_request")}
    if "description_html" not in cr_columns:
        op.add_column(
            "change_request",
            sa.Column("description_html", sa.Text(), nullable=False, server_default=""),
        )

    pv_columns = {c["name"] for c in inspector.get_columns("policy_version")}
    if "body_html" not in pv_columns:
        op.add_column(
            "policy_version",
            sa.Column("body_html", sa.Text(), nullable=False, server_default=""),
        )

    att_columns = {c["name"] for c in inspector.get_columns("attachment")}
    if "change_request_id" not in att_columns:
        op.add_column(
            "attachment",
            sa.Column(
                "change_request_id",
                sa.String(36),
                sa.ForeignKey("change_request.id"),
                nullable=True,
            ),
        )
    version_id_col = next(c for c in inspector.get_columns("attachment") if c["name"] == "version_id")
    if not version_id_col["nullable"]:
        with op.batch_alter_table("attachment") as batch:
            batch.alter_column("version_id", existing_type=sa.String(36), nullable=True)

    # triggers atualizados (imutabilidade cobre body_html) — install é idempotente
    schema_guards.install(bind)


def downgrade() -> None:
    bind = op.get_bind()
    for name in reversed(V3_TABLES):
        op.drop_table(name)
    op.drop_column("change_request", "description_html")
    op.drop_column("policy_version", "body_html")
    op.drop_column("attachment", "change_request_id")
    schema_guards.install(bind)
