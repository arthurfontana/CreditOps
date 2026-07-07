"""v2 "Plataforma da empresa": API de consumo, grafo, leitura, webhooks e piloto.

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-07

Novas tabelas: service_token, policy_reference, read_receipt, webhook_delivery.
Colunas garantidas (bancos anteriores à v2): policy.review_due_at,
publication.rollout_scope / pilot_description / pilot_ends_at.

Idempotente como a 0002: em bancos novos a 0001 já cria o esquema completo a
partir do metadata dos models; aqui só se adiciona o que faltar.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from app.models import Base

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

V2_TABLES = [
    "service_token",
    "policy_reference",
    "read_receipt",
    "webhook_delivery",
]


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = set(inspector.get_table_names())

    for name in V2_TABLES:
        if name not in existing:
            Base.metadata.tables[name].create(bind=bind)

    policy_columns = {c["name"] for c in inspector.get_columns("policy")}
    if "review_due_at" not in policy_columns:
        op.add_column("policy", sa.Column("review_due_at", sa.DateTime(), nullable=True))

    publication_columns = {c["name"] for c in inspector.get_columns("publication")}
    if "rollout_scope" not in publication_columns:
        op.add_column(
            "publication",
            sa.Column("rollout_scope", sa.String(10), nullable=False, server_default="full"),
        )
    if "pilot_description" not in publication_columns:
        op.add_column("publication", sa.Column("pilot_description", sa.Text(), nullable=True))
    if "pilot_ends_at" not in publication_columns:
        op.add_column("publication", sa.Column("pilot_ends_at", sa.Date(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    for name in reversed(V2_TABLES):
        Base.metadata.tables[name].drop(bind=bind, checkfirst=True)
