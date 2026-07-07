"""Fachada única do módulo de IA (wiki 08).

Se provider = none (padrão), toda chamada levanta AIUnavailable — que a
UI traduz em "sugestão indisponível", nunca em erro de sistema. Trocar
de provedor é mudança de configuração, não de código.
"""

from __future__ import annotations

import logging

from app.config import Settings
from app.plugins.base import AIProvider, AIResult

logger = logging.getLogger("creditops.ai")

FEATURES = ("summarize_diff", "suggest_tags", "draft_from_document", "qa_search")


class AIUnavailable(Exception):
    """IA não configurada ou provedor indisponível — fail-soft, nunca erro 500."""


def build_provider(settings: Settings) -> AIProvider:
    from app.plugins.ai.providers import PROVIDERS

    factory = PROVIDERS.get(settings.ai_provider)
    if factory is None:
        raise AIUnavailable(f"provedor de IA desconhecido: {settings.ai_provider}")
    return factory(settings)


class AIService:
    """Fachada: valida feature ligada + provider configurado e delega."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.provider: AIProvider = build_provider(settings)

    @property
    def provider_name(self) -> str:
        return self.settings.ai_provider

    def feature_enabled(self, feature: str) -> bool:
        if self.settings.ai_provider == "none":
            return False
        return bool(getattr(self.settings, f"ai_{feature}", False))

    def complete(
        self, prompt: str, *, system: str | None = None, max_tokens: int | None = None
    ) -> AIResult:
        """Chama o provider com timeout curto. Qualquer falha vira AIUnavailable."""
        try:
            return self.provider.complete(
                prompt,
                system=system,
                max_tokens=max_tokens or self.settings.ai_max_tokens,
            )
        except AIUnavailable:
            raise
        except Exception as exc:  # noqa: BLE001 - fail-soft por contrato (wiki 08)
            logger.exception("provedor de IA falhou (%s)", self.settings.ai_provider)
            raise AIUnavailable(f"sugestão indisponível: {exc}") from exc

    def health(self) -> bool:
        try:
            return self.provider.health()
        except Exception:  # noqa: BLE001
            return False
