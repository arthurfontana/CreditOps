"""Adapter para modelo interno via endpoint OpenAI-compatible (Ollama/vLLM/LiteLLM).

Reusa o adapter OpenAI: só muda a base_url (obrigatória) e a chave é opcional.
"""

from __future__ import annotations

from app.config import Settings
from app.plugins.ai.providers.openai import OpenAIProvider


class InternalProvider(OpenAIProvider):
    def __init__(self, settings: Settings) -> None:
        if not settings.ai_base_url:
            from app.plugins.ai.service import AIUnavailable

            raise AIUnavailable("provider 'internal' exige ai_base_url configurada")
        super().__init__(settings)
        self.model = settings.ai_model or "default"
