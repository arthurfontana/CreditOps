"""Módulo de IA plugável (v2).

O core funciona 100% sem IA: com provider "none" (padrão) toda chamada
retorna "indisponível" e nenhuma feature aparece na UI. Toda saída de IA
é SUGESTÃO que um humano confirma — IA nunca grava direto em versão,
aprovação ou auditoria.
"""

from app.plugins.ai.service import AIService, AIUnavailable

__all__ = ["AIService", "AIUnavailable"]
