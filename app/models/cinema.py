"""Cineminha: matriz de política (interseção de duas variáveis de decisão).

Biblioteca versionada e imutável, no mesmo espírito do catálogo de
políticas: a entrada `Cinema` é o contêiner estável; `CinemaVersion` é o
snapshot imutável da matriz; `CinemaInstance` é a cópia de trabalho dentro
de uma demanda — editável à vontade sem tocar na biblioteca. Quando a
versão de política vinculada à demanda entra em vigor, a instância é
promovida a nova `CinemaVersion` (retroalimentação da biblioteca).

Células (`cells_json`): dict {"<valorLinha>|<valorColuna>": valor}.
- tipo `eligibility`: valor 0 (não elegível) ou 1 (elegível); ausente = 1.
- tipo `offer`: valor numérico >= 0 (corte/oferta); ausente = 0.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.org import new_uuid


class DecisionVariable(Base):
    """Catálogo de variáveis de decisão usáveis como dimensão de cineminha.

    O domínio padrão (lista ordenada de valores, ex.: R01..R20, R99) é a
    referência ao montar eixos de novas matrizes.
    """

    __tablename__ = "decision_variable"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(100), unique=True)  # ex.: FAIXA_SCORE
    label: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    domain_json: Mapped[str] = mapped_column(Text, default="[]")  # lista ordenada de valores
    is_ordinal: Mapped[bool] = mapped_column(Boolean, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[str] = mapped_column(String(36), ForeignKey("user.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    creator = relationship("User")


class Cinema(Base):
    """Entrada da biblioteca — contêiner estável de uma matriz de política."""

    __tablename__ = "cinema"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(255), unique=True)  # ex.: Cortes Digital G7
    description: Mapped[str | None] = mapped_column(Text)
    cinema_type: Mapped[str] = mapped_column(String(20))  # enums.CinemaType
    row_variable_id: Mapped[str] = mapped_column(String(36), ForeignKey("decision_variable.id"))
    col_variable_id: Mapped[str] = mapped_column(String(36), ForeignKey("decision_variable.id"))
    current_version_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey("cinema_version.id", use_alter=True, name="fk_cinema_current_version"),
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[str] = mapped_column(String(36), ForeignKey("user.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    row_variable = relationship("DecisionVariable", foreign_keys=[row_variable_id])
    col_variable = relationship("DecisionVariable", foreign_keys=[col_variable_id])
    current_version = relationship(
        "CinemaVersion", foreign_keys=[current_version_id], post_update=True
    )
    versions: Mapped[list[CinemaVersion]] = relationship(
        "CinemaVersion",
        back_populates="cinema",
        foreign_keys="CinemaVersion.cinema_id",
        order_by="CinemaVersion.version_number",
    )
    creator = relationship("User", foreign_keys=[created_by])


class CinemaVersion(Base):
    """Snapshot imutável da matriz. Nasce de carga manual ou de promoção."""

    __tablename__ = "cinema_version"
    __table_args__ = (
        UniqueConstraint("cinema_id", "version_number", name="uq_cinema_version_number"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    cinema_id: Mapped[str] = mapped_column(String(36), ForeignKey("cinema.id"))
    version_number: Mapped[int] = mapped_column(Integer)
    row_domain_json: Mapped[str] = mapped_column(Text, default="[]")
    col_domain_json: Mapped[str] = mapped_column(Text, default="[]")
    cells_json: Mapped[str] = mapped_column(Text, default="{}")
    origin: Mapped[str] = mapped_column(String(20))  # enums.CinemaVersionOrigin
    # rastreabilidade da promoção (nulos em carga manual)
    change_request_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("change_request.id")
    )
    policy_version_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("policy_version.id")
    )
    created_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("user.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    cinema = relationship("Cinema", back_populates="versions", foreign_keys=[cinema_id])
    change_request = relationship("ChangeRequest")
    policy_version = relationship("PolicyVersion")
    creator = relationship("User")


class CinemaInstance(Base):
    """Cópia de trabalho de um cineminha dentro de uma demanda."""

    __tablename__ = "cinema_instance"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    change_request_id: Mapped[str] = mapped_column(String(36), ForeignKey("change_request.id"))
    cinema_id: Mapped[str] = mapped_column(String(36), ForeignKey("cinema.id"))
    source_version_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("cinema_version.id")
    )  # nulo = biblioteca ainda sem versão vigente ao puxar
    row_domain_json: Mapped[str] = mapped_column(Text, default="[]")
    col_domain_json: Mapped[str] = mapped_column(Text, default="[]")
    cells_json: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(String(20), default="draft")  # enums.CinemaInstanceStatus
    promoted_version_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("cinema_version.id")
    )
    notes: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(String(36), ForeignKey("user.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    change_request = relationship("ChangeRequest", backref="cinema_instances")
    cinema = relationship("Cinema")
    source_version = relationship("CinemaVersion", foreign_keys=[source_version_id])
    promoted_version = relationship("CinemaVersion", foreign_keys=[promoted_version_id])
    creator = relationship("User")
