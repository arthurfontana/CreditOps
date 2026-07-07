"""Constantes de domínio.

Valores gravados como String no banco (evita ALTER de enum no futuro);
a validação acontece na aplicação.
"""

from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    ADMIN = "admin"
    AUTHOR = "author"
    REVIEWER = "reviewer"
    APPROVER = "approver"
    READER = "reader"


class VersionStatus(StrEnum):
    DRAFT = "draft"
    IN_REVIEW = "in_review"
    IN_APPROVAL = "in_approval"
    APPROVED = "approved"
    PUBLISHED = "published"
    EFFECTIVE = "effective"
    SUPERSEDED = "superseded"
    ARCHIVED = "archived"
    REJECTED = "rejected"  # registrado como decisão; o status volta a draft


# Estados em que a versão ainda está "aberta" (bloqueiam novo rascunho na política)
OPEN_STATUSES = frozenset(
    {
        VersionStatus.DRAFT,
        VersionStatus.IN_REVIEW,
        VersionStatus.IN_APPROVAL,
        VersionStatus.APPROVED,
        VersionStatus.PUBLISHED,
    }
)


class PolicyType(StrEnum):
    LIMITE = "limite"
    CONCESSAO = "concessao"
    RENEGOCIACAO = "renegociacao"
    COBRANCA = "cobranca"
    SCORE = "score"
    ALCADA = "alcada"
    OUTRO = "outro"


class PolicyLifecycle(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class ApprovalDecision(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"


class ChangeRequestPriority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    REGULATORY = "regulatory"


class ChangeRequestStatus(StrEnum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    REJECTED = "rejected"  # rejeição com justificativa — também é decisão registrada


class IndicatorDirection(StrEnum):
    UP = "up"
    DOWN = "down"
    CONTEXTUAL = "contextual"


class RolloutScope(StrEnum):
    """Escopo da publicação (v2): total ou experimento/piloto."""

    FULL = "full"
    PILOT = "pilot"


class ReferenceRelation(StrEnum):
    """Aresta do grafo de referências entre políticas/artefatos (v2)."""

    USA = "usa"
    DEPENDE_DE = "depende_de"
    SUBSTITUI = "substitui"


class ReferenceTargetType(StrEnum):
    POLICY = "policy"
    ARTIFACT = "artifact"  # ex.: "Score Serasa", "Motor Antifraude"


# Janelas de observação do impacto (dias após a vigência)
IMPACT_WINDOWS = (30, 60, 90)


class CinemaType(StrEnum):
    """Tipo de cineminha (espelha o simulador): elegibilidade ou oferta."""

    ELIGIBILITY = "eligibility"  # casela 0/1 (não elegível / elegível)
    OFFER = "offer"  # casela com valor numérico (corte/oferta)


class CinemaVersionOrigin(StrEnum):
    MANUAL = "manual"  # carga inicial/AS IS feita direto na biblioteca
    PROMOTION = "promotion"  # retroalimentação: demanda cuja política entrou em vigor


class CinemaInstanceStatus(StrEnum):
    DRAFT = "draft"  # em edição dentro da demanda
    PROMOTED = "promoted"  # já retroalimentou a biblioteca
