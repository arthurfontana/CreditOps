"""Esquema inicial do MVP: todas as tabelas, triggers de imutabilidade e FTS5.

Revision ID: 0001
Revises:
Create Date: 2026-07-06

Cria o esquema completo a partir do metadata dos models (fonte única) e
instala as proteções de integridade definidas em app/schema_guards.py.
"""
from __future__ import annotations

from alembic import op

from app import schema_guards
from app.models import Base

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.create_all(bind=bind)
    schema_guards.install(bind)


def downgrade() -> None:
    bind = op.get_bind()
    schema_guards.uninstall(bind)
    Base.metadata.drop_all(bind=bind)
