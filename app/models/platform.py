"""Entidades da v2 "Plataforma da empresa".

ServiceToken (API de consumo), PolicyReference (grafo de referências),
ReadReceipt (trilha de leitura) e WebhookDelivery (fila de webhooks).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.org import new_uuid


class ServiceToken(Base):
    """Token de serviço da API de consumo (somente leitura).

    O token em claro é exibido UMA vez na criação; o banco guarda apenas
    o SHA-256. Revogação é lógica (revoked_at) — o histórico permanece.
    """

    __tablename__ = "service_token"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    name: Mapped[str] = mapped_column(String(120), unique=True)  # ex.: "motor-powercurve"
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)  # sha256 do token
    created_by: Mapped[str | None] = mapped_column(String(36), ForeignKey("user.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime)

    creator = relationship("User")


class PolicyReference(Base):
    """Aresta do grafo: política → política ou política → artefato (v2).

    Habilita análise de impacto: "se eu mudar o Score X, quais políticas
    são afetadas?" — percorrendo as arestas no sentido inverso.
    """

    __tablename__ = "policy_reference"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    from_policy_id: Mapped[str] = mapped_column(String(36), ForeignKey("policy.id"))
    to_type: Mapped[str] = mapped_column(String(10))  # enums.ReferenceTargetType
    to_policy_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("policy.id"))
    artifact_name: Mapped[str | None] = mapped_column(String(255))  # quando to_type=artifact
    relation: Mapped[str] = mapped_column(String(20))  # enums.ReferenceRelation
    note: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[str] = mapped_column(String(36), ForeignKey("user.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    from_policy = relationship("Policy", foreign_keys=[from_policy_id])
    to_policy = relationship("Policy", foreign_keys=[to_policy_id])
    creator = relationship("User")


class ReadReceipt(Base):
    """Ciência da operação (v2): registro de que o usuário leu a versão vigente."""

    __tablename__ = "read_receipt"
    __table_args__ = (
        UniqueConstraint("version_id", "user_id", name="uq_read_receipt_version_user"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_uuid)
    policy_id: Mapped[str] = mapped_column(String(36), ForeignKey("policy.id"))
    version_id: Mapped[str] = mapped_column(String(36), ForeignKey("policy_version.id"))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("user.id"))
    acknowledged_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    policy = relationship("Policy")
    version = relationship("PolicyVersion")
    user = relationship("User")


class WebhookDelivery(Base):
    """Fila persistente de entregas de webhook (v2) — retry sem perder eventos.

    Espelha o padrão da tabela `notification` (v1): o core enfileira a
    partir dos eventos de domínio; o envio é do plugin `webhook`.
    """

    __tablename__ = "webhook_delivery"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    url: Mapped[str] = mapped_column(String(500))
    event: Mapped[str] = mapped_column(String(100))  # ex.: version.published
    payload: Mapped[str] = mapped_column(Text)  # JSON enviado no corpo
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str | None] = mapped_column(Text)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
