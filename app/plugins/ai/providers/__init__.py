"""Adapters de provedor — uma primitiva (`complete`), N adapters.

Todos usam HTTP puro (httpx) contra as APIs, sem SDKs pesados. Adicionar
um provedor novo = 1 arquivo de ~50 linhas registrado em PROVIDERS.
"""

from __future__ import annotations

from collections.abc import Callable

from app.config import Settings
from app.plugins.base import AIProvider


def _none(settings: Settings) -> AIProvider:
    from app.plugins.ai.providers.none import NoneProvider

    return NoneProvider()


def _openai(settings: Settings) -> AIProvider:
    from app.plugins.ai.providers.openai import OpenAIProvider

    return OpenAIProvider(settings)


def _anthropic(settings: Settings) -> AIProvider:
    from app.plugins.ai.providers.anthropic import AnthropicProvider

    return AnthropicProvider(settings)


def _gemini(settings: Settings) -> AIProvider:
    from app.plugins.ai.providers.gemini import GeminiProvider

    return GeminiProvider(settings)


def _internal(settings: Settings) -> AIProvider:
    from app.plugins.ai.providers.internal import InternalProvider

    return InternalProvider(settings)


PROVIDERS: dict[str, Callable[[Settings], AIProvider]] = {
    "none": _none,
    "openai": _openai,
    "anthropic": _anthropic,
    "gemini": _gemini,
    "internal": _internal,
}
