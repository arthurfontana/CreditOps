"""Ciclo de mudança (v1): ChangeRequest, Indicator, ImpactMetric, ImplementationRef.

Fecham o ciclo demanda → mudança → vigência → impacto observado
(ver wiki 16 — Domínio do Produto).
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.enums import ChangeRequestPriority, ChangeRequestStatus
from app.models.org import new_uuid


class ChangeRequest(Base):
    """Demanda de mudança — o pedido que antecede o rascunho."""

    __tablename__ = "change_request"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    code: Mapped[str] = mapped_column(String(30), unique=True)  # DEM-YYYY-NNN
    title: Mapped[str] = mapped_column(String(255))
    description_md: Mapped[str] = mapped_column(Text, default="")
    requested_by: Mapped[str] = mapped_column(String(36), ForeignKey("user.id"))
    area_id: Mapped[str] = mapped_column(String(36), ForeignKey("area.id"))
    policy_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("policy.id")
    )  # null = demanda de política nova
    priority: Mapped[str] = mapped_column(String(20), default=ChangeRequestPriority.MEDIUM)
    status: Mapped[str] = mapped_column(String(20), default=ChangeRequestStatus.OPEN)
    resolution: Mapped[str | None] = mapped_column(Text)  # justificativa de conclusão/rejeição
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime)

    requester = relationship("User", foreign_keys=[requested_by])
    area = relationship("Area")
    policy = relationship("Policy")
    versions = relationship(
        "PolicyVersion",
        primaryjoin="ChangeRequest.id == foreign(PolicyVersion.change_request_id)",
        viewonly=True,
    )


class Indicator(Base):
    """Catálogo administrável de indicadores de negócio (aprovacao, fpd30, over90…)."""

    __tablename__ = "indicator"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    code: Mapped[str] = mapped_column(String(30), unique=True)
    name: Mapped[str] = mapped_column(String(255))
    unit: Mapped[str | None] = mapped_column(String(30))  # ex.: p.p., %, R$
    desired_direction: Mapped[str] = mapped_column(String(15))  # enums.IndicatorDirection
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class ImpactMetric(Base):
    """Hipótese (esperado) e resultado (observado) por indicador e janela.

    Uma linha por (versão, indicador, janela). O sistema cobra e registra —
    não calcula (não é BI).
    """

    __tablename__ = "impact_metric"
    __table_args__ = (
        UniqueConstraint(
            "version_id", "indicator_id", "window_days", name="uq_impact_metric_window"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    version_id: Mapped[str] = mapped_column(String(36), ForeignKey("policy_version.id"))
    indicator_id: Mapped[str] = mapped_column(String(36), ForeignKey("indicator.id"))
    expected_change: Mapped[str] = mapped_column(Text)  # declarado na submissão
    observed_change: Mapped[str | None] = mapped_column(Text)  # preenchido pós-vigência
    window_days: Mapped[int] = mapped_column(Integer)  # 30 | 60 | 90
    recorded_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("user.id"))
    recorded_at: Mapped[datetime | None] = mapped_column(DateTime)

    indicator = relationship("Indicator")
    version = relationship("PolicyVersion")
    recorder = relationship("User", foreign_keys=[recorded_by])


class ImplementationRef(Base):
    """Referência manual da versão publicada ao artefato do motor de decisão."""

    __tablename__ = "implementation_ref"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    version_id: Mapped[str] = mapped_column(String(36), ForeignKey("policy_version.id"))
    system: Mapped[str] = mapped_column(String(120))  # ex.: PowerCurve, motor interno
    artifact: Mapped[str] = mapped_column(String(255))  # strategy / ruleset / arquivo
    artifact_version: Mapped[str] = mapped_column(String(60))
    node_path: Mapped[str | None] = mapped_column(String(255))
    url: Mapped[str | None] = mapped_column(String(500))
    deployed_at: Mapped[date | None] = mapped_column(Date)
    registered_by: Mapped[str] = mapped_column(String(36), ForeignKey("user.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    registrar = relationship("User", foreign_keys=[registered_by])
    version = relationship("PolicyVersion")
