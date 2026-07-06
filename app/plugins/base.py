"""Interfaces dos plugins opcionais.

Regra arquitetural: nenhum módulo do core importa um plugin diretamente.
O core emite eventos de domínio (app/services/events.py) e os plugins
assinam. Plugins são descobertos por configuração (config/settings.toml)
e falham de forma silenciosa e logada — indisponibilidade de plugin
nunca derruba o core.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class NotifierPlugin(Protocol):
    """Notificações (e-mail SMTP na v1)."""

    def notify(self, recipient: str, subject: str, body: str) -> None: ...

    def health(self) -> bool: ...


class AuthPlugin(Protocol):
    """Autenticação externa (LDAP/AD na v2)."""

    def authenticate(self, username: str, password: str) -> bool: ...


@dataclass
class AIResult:
    text: str
    provider: str
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_ms: int | None = None


class AIProvider(Protocol):
    """Contrato único do módulo de IA (v2). Uma primitiva; casos de uso
    ficam acima do provider, com prompts versionados em prompts/runtime/."""

    def complete(
        self, prompt: str, *, system: str | None = None, max_tokens: int = 1024
    ) -> AIResult: ...

    def health(self) -> bool: ...
