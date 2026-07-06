"""Registro de plugins — carregados conforme config/settings.toml.

MVP: nenhum plugin ativo; o registro existe como ponto de extensão
para v1 (notify_email) e v2 (auth_ldap, ai_*).
"""

from __future__ import annotations

import logging

logger = logging.getLogger("creditops.plugins")

_plugins: dict[str, object] = {}


def load_plugins() -> None:
    """Descoberta por configuração. Falha de plugin é logada, nunca propaga."""
    # v1+: ler [plugins] de settings.toml e instanciar adapters aqui.
    logger.debug("nenhum plugin configurado (core opera sozinho)")


def get_plugin(name: str) -> object | None:
    return _plugins.get(name)
