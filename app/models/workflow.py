"""Eventos do workflow: Approval, Publication, StatusTransition, Release.

Aprovação, publicação e transição são REGISTROS datados (evidência),
não flags — e são imutáveis por trigger no banco.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.org import new_uuid


class StatusTransition(Base):
    __tablename__ = "status_transition"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    version_id: Mapped[str] = mapped_column(String(36), ForeignKey("policy_version.id"))
    from_status: Mapped[str] = mapped_column(String(20))
    to_status: Mapped[str] = mapped_column(String(20))
    actor_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("user.id"))  # null=sistema
    reason: Mapped[str | None] = mapped_column(Text)  # obrigatório em rejeição/rollback
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    actor = relationship("User")
    version = relationship("PolicyVersion")


class Approval(Base):
    __tablename__ = "approval"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    version_id: Mapped[str] = mapped_column(String(36), ForeignKey("policy_version.id"))
    approver_id: Mapped[str] = mapped_column(String(36), ForeignKey("user.id"))
    decision: Mapped[str] = mapped_column(String(20))  # enums.ApprovalDecision
    level: Mapped[int] = mapped_column(Integer, default=1)  # multinível na v1
    justification: Mapped[str | None] = mapped_column(Text)  # obrigatória em rejeição
    decided_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    delegated_from_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("user.id"))  # v1

    approver = relationship("User", foreign_keys=[approver_id])
    version = relationship("PolicyVersion")


class Publication(Base):
    __tablename__ = "publication"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    version_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("policy_version.id"), unique=True
    )
    published_by: Mapped[str] = mapped_column(String(36), ForeignKey("user.id"))
    published_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    effective_from: Mapped[date] = mapped_column(Date)
    effective_until: Mapped[date | None] = mapped_column(Date)  # preenchida na substituição
    release_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("release.id"))  # v1
    rollout_scope: Mapped[str] = mapped_column(String(10), default="full")  # full | pilot (v2)
    pilot_description: Mapped[str | None] = mapped_column(Text)  # v2
    pilot_ends_at: Mapped[date | None] = mapped_column(Date)  # v2

    publisher = relationship("User")
    version = relationship("PolicyVersion")


class Release(Base):
    __tablename__ = "release"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(String(36), ForeignKey("user.id"))
    published_at: Mapped[datetime | None] = mapped_column(DateTime)
