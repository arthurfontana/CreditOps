"""Trilha de auditoria (append-only), Setting e Notification."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class AuditLog(Base):
    __tablename__ = "audit_log"

    # integer autoincrement = ordem total dos eventos
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    actor_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("user.id"))  # null=sistema
    action: Mapped[str] = mapped_column(String(100))  # ex.: version.published
    entity_type: Mapped[str] = mapped_column(String(50))
    entity_id: Mapped[str | None] = mapped_column(String(36))
    payload: Mapped[str | None] = mapped_column(Text)  # JSON
    prev_hash: Mapped[str | None] = mapped_column(String(64))  # hash chain (v1)
    row_hash: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    actor = relationship("User")


class Setting(Base):
    """Configuração administrável. Segredos ficam FORA do banco (env vars)."""

    __tablename__ = "setting"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str | None] = mapped_column(Text)


class Notification(Base):
    """Fila persistente de notificações para o plugin de e-mail (v1)."""

    __tablename__ = "notification"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    recipient_id: Mapped[str] = mapped_column(String(36), ForeignKey("user.id"))
    event: Mapped[str] = mapped_column(String(100))
    payload: Mapped[str | None] = mapped_column(Text)  # JSON
    sent_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
