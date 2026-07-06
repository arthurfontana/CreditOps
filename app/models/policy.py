"""Política (contêiner estável) e versão (snapshot imutável)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.enums import PolicyLifecycle, VersionStatus
from app.models.org import new_uuid

policy_product = Table(
    "policy_product",
    Base.metadata,
    Column("policy_id", String(36), ForeignKey("policy.id"), primary_key=True),
    Column("product_id", String(36), ForeignKey("product.id"), primary_key=True),
)

policy_segment = Table(
    "policy_segment",
    Base.metadata,
    Column("policy_id", String(36), ForeignKey("policy.id"), primary_key=True),
    Column("segment_id", String(36), ForeignKey("segment.id"), primary_key=True),
)

policy_tag = Table(
    "policy_tag",
    Base.metadata,
    Column("policy_id", String(36), ForeignKey("policy.id"), primary_key=True),
    Column("tag_id", String(36), ForeignKey("tag.id"), primary_key=True),
)


class Tag(Base):
    __tablename__ = "tag"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(100), unique=True)


class Policy(Base):
    __tablename__ = "policy"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    code: Mapped[str] = mapped_column(String(30), unique=True)  # POL-<AREA>-NNN
    title: Mapped[str] = mapped_column(String(255))
    policy_type: Mapped[str] = mapped_column(String(30))  # enums.PolicyType
    area_id: Mapped[str] = mapped_column(String(36), ForeignKey("area.id"))
    owner_id: Mapped[str] = mapped_column(String(36), ForeignKey("user.id"))
    current_version_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("policy_version.id", use_alter=True, name="fk_policy_current_version"),
    )
    lifecycle_status: Mapped[str] = mapped_column(String(20), default=PolicyLifecycle.ACTIVE)
    review_due_at: Mapped[datetime | None] = mapped_column(DateTime)  # recertificação (v2)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    area = relationship("Area")
    owner = relationship("User", foreign_keys=[owner_id])
    current_version = relationship(
        "PolicyVersion", foreign_keys=[current_version_id], post_update=True
    )
    versions: Mapped[list[PolicyVersion]] = relationship(
        "PolicyVersion",
        back_populates="policy",
        foreign_keys="PolicyVersion.policy_id",
        order_by="PolicyVersion.version_number",
    )
    products = relationship("Product", secondary=policy_product)
    segments = relationship("Segment", secondary=policy_segment)
    tags = relationship("Tag", secondary=policy_tag)


class PolicyVersion(Base):
    __tablename__ = "policy_version"
    __table_args__ = (
        UniqueConstraint("policy_id", "version_number", name="uq_policy_version_number"),
        # invariante: no máximo UMA versão vigente por política
        Index(
            "ux_one_effective_per_policy",
            "policy_id",
            unique=True,
            sqlite_where=text("status = 'effective'"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    policy_id: Mapped[str] = mapped_column(String(36), ForeignKey("policy.id"))
    version_number: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default=VersionStatus.DRAFT)
    body_md: Mapped[str] = mapped_column(Text, default="")
    structured_fields: Mapped[str | None] = mapped_column(Text)  # JSON (campos por tipo, v1)
    change_summary: Mapped[str | None] = mapped_column(Text)  # obrigatório para submeter
    expected_impact: Mapped[str | None] = mapped_column(Text)  # obrigatório para submeter
    based_on_version_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("policy_version.id")
    )
    is_rollback: Mapped[bool] = mapped_column(Boolean, default=False)
    content_hash: Mapped[str | None] = mapped_column(String(64))  # congelado ao sair de draft
    created_by: Mapped[str] = mapped_column(String(36), ForeignKey("user.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime)

    policy: Mapped[Policy] = relationship(
        "Policy", back_populates="versions", foreign_keys=[policy_id]
    )
    author = relationship("User", foreign_keys=[created_by])
    based_on = relationship("PolicyVersion", remote_side=[id])
