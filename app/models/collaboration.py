"""Colaboração: Comment, Attachment, ImpactRecord."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.org import new_uuid


class Comment(Base):
    __tablename__ = "comment"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    version_id: Mapped[str] = mapped_column(String(36), ForeignKey("policy_version.id"))
    author_id: Mapped[str] = mapped_column(String(36), ForeignKey("user.id"))
    body_md: Mapped[str] = mapped_column(Text)
    anchor: Mapped[str | None] = mapped_column(String(255))  # heading/trecho opcional
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    author = relationship("User")


class Attachment(Base):
    __tablename__ = "attachment"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    # anexo pertence a UMA das âncoras: versão de política OU demanda
    version_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("policy_version.id"))
    change_request_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("change_request.id")
    )
    filename: Mapped[str] = mapped_column(String(255))
    stored_path: Mapped[str] = mapped_column(String(500))
    sha256: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(Integer)
    content_type: Mapped[str | None] = mapped_column(String(120))
    uploaded_by: Mapped[str] = mapped_column(String(36), ForeignKey("user.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    uploader = relationship("User")


class ImpactRecord(Base):
    """Impacto observado pós-publicação (v1) — tabela criada desde já."""

    __tablename__ = "impact_record"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    publication_id: Mapped[str] = mapped_column(String(36), ForeignKey("publication.id"))
    observed_impact: Mapped[str] = mapped_column(Text)
    metrics: Mapped[str | None] = mapped_column(Text)  # JSON livre
    recorded_by: Mapped[str] = mapped_column(String(36), ForeignKey("user.id"))
    recorded_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
