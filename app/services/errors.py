"""Exceções de domínio. Rotas convertem em respostas HTTP (403/404/400)."""

from __future__ import annotations


class DomainError(Exception):
    """Base das exceções de negócio."""


class PermissionDenied(DomainError):
    """Ator sem papel/escopo para a operação."""


class NotFound(DomainError):
    """Entidade não encontrada."""


class ValidationFailed(DomainError):
    """Dados inválidos ou pré-condição de negócio não atendida."""


class InvalidTransition(DomainError):
    """Transição de estado fora da whitelist do workflow."""
