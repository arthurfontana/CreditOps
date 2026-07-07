"""Provider padrão: IA desligada por construção.

Com ele ativo, é garantido que nenhum conteúdo de política sai do
ambiente (wiki 08). Ativar IA externa é decisão consciente do admin.
"""

from __future__ import annotations

from app.plugins.base import AIResult


class NoneProvider:
    def complete(
        self, prompt: str, *, system: str | None = None, max_tokens: int = 1024
    ) -> AIResult:
        from app.plugins.ai.service import AIUnavailable

        raise AIUnavailable("nenhum provedor de IA configurado (provider = none)")

    def health(self) -> bool:
        return False
