"""Autorização no service layer.

TODA regra de negócio valida papel aqui — a UI apenas esconde botões.
Chamar um service com papel errado lança PermissionDenied mesmo sem HTTP.
"""

from __future__ import annotations

from app.models import Role, User
from app.services.errors import PermissionDenied

# papéis que enxergam versões não publicadas (rascunhos/fluxo)
WORKFLOW_ROLES = (Role.ADMIN, Role.AUTHOR, Role.REVIEWER, Role.APPROVER)


def ensure_active(actor: User) -> None:
    if not actor.is_active:
        raise PermissionDenied("usuário desativado")


def ensure_role(actor: User, *roles: Role, message: str | None = None) -> None:
    """Garante que o ator tem um dos papéis. Admin NÃO é curinga:
    ele só passa se estiver explicitamente na lista (não participa do workflow)."""
    ensure_active(actor)
    if Role(actor.role) not in roles:
        allowed = ", ".join(r.value for r in roles)
        raise PermissionDenied(message or f"operação requer papel: {allowed}")


def can_see_drafts(actor: User) -> bool:
    return Role(actor.role) in WORKFLOW_ROLES
