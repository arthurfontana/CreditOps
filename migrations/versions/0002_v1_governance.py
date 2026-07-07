"""v1 "Governança para valer": ciclo de mudança, multinível, delegação e indicadores.

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-06

Novas tabelas: change_request, indicator, impact_metric, implementation_ref,
approval_rule, approval_delegation. Nova coluna: policy_version.change_request_id.
Seed do catálogo padrão de indicadores (wiki 16 — Domínio do Produto).

A migração é idempotente: em bancos novos a 0001 já cria o esquema completo
a partir do metadata dos models; aqui só se adiciona o que faltar (bancos
que rodaram o MVP).
"""
from __future__ import annotations

import uuid

import sqlalchemy as sa
from alembic import op

from app.models import Base

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

V1_TABLES = [
    "change_request",
    "indicator",
    "impact_metric",
    "implementation_ref",
    "approval_rule",
    "approval_delegation",
]

DEFAULT_INDICATORS = [
    ("aprovacao", "Taxa de aprovação", "p.p.", "contextual"),
    ("conversao", "Conversão de propostas", "p.p.", "up"),
    ("fpd30", "First Payment Default 30", "p.p.", "down"),
    ("fpd60", "First Payment Default 60", "p.p.", "down"),
    ("over90", "Atraso > 90 dias", "p.p.", "down"),
    ("perda", "Perda esperada/realizada", "R$", "down"),
    ("receita", "Receita da carteira", "R$", "up"),
    ("churn", "Cancelamento/atrito", "p.p.", "down"),
]


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = set(inspector.get_table_names())

    for name in V1_TABLES:
        if name not in existing:
            Base.metadata.tables[name].create(bind=bind)

    release_columns = {c["name"] for c in inspector.get_columns("release")}
    if "created_at" not in release_columns:
        op.add_column("release", sa.Column("created_at", sa.DateTime(), nullable=True))
        bind.execute(
            sa.text(
                "UPDATE release SET created_at = COALESCE(published_at, CURRENT_TIMESTAMP) "
                "WHERE created_at IS NULL"
            )
        )

    columns = {c["name"] for c in inspector.get_columns("policy_version")}
    if "change_request_id" not in columns:
        op.add_column(
            "policy_version",
            sa.Column(
                "change_request_id",
                sa.String(36),
                sa.ForeignKey("change_request.id"),
                nullable=True,
            ),
        )

    for code, name, unit, direction in DEFAULT_INDICATORS:
        bind.execute(
            sa.text(
                "INSERT INTO indicator (id, code, name, unit, desired_direction, is_active) "
                "SELECT :id, :code, :name, :unit, :direction, 1 "
                "WHERE NOT EXISTS (SELECT 1 FROM indicator WHERE code = :code)"
            ),
            {
                "id": str(uuid.uuid4()),
                "code": code,
                "name": name,
                "unit": unit,
                "direction": direction,
            },
        )


def downgrade() -> None:
    bind = op.get_bind()
    op.drop_column("release", "created_at")
    op.drop_column("policy_version", "change_request_id")
    for name in reversed(V1_TABLES):
        Base.metadata.tables[name].drop(bind=bind, checkfirst=True)
