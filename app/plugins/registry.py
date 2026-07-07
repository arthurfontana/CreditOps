"""Registro de plugins — carregados conforme configuração.

Regra arquitetural: o core nunca importa plugin diretamente; ele consulta
o registro (`get_plugin`) e emite eventos de domínio. Falha de plugin é
logada e nunca propaga — o core opera sozinho.

Plugins da v1:
- `notifier`   → e-mail SMTP (settings: notify_email = true)
- `export_pdf` → exportação PDF sem dependência externa (default: ativo)
"""

from __future__ import annotations

import logging

logger = logging.getLogger("creditops.plugins")

_plugins: dict[str, object] = {}


def load_plugins() -> None:
    """Descoberta por configuração. Falha de plugin é logada, nunca propaga."""
    from app.config import get_settings

    settings = get_settings()
    _plugins.clear()

    if settings.notify_email:
        try:
            from app.plugins.notify.email_smtp import SmtpNotifier

            _plugins["notifier"] = SmtpNotifier(settings)
            logger.info("plugin notifier (SMTP) ativo: %s", settings.smtp_host)
        except Exception:  # noqa: BLE001
            logger.exception("falha ao carregar plugin de e-mail — core segue sem ele")

    if settings.export_pdf:
        try:
            from app.plugins.export_pdf import PdfExporter

            _plugins["export_pdf"] = PdfExporter()
        except Exception:  # noqa: BLE001
            logger.exception("falha ao carregar plugin de PDF — core segue sem ele")

    if not _plugins:
        logger.debug("nenhum plugin configurado (core opera sozinho)")


def register_plugin(name: str, plugin: object) -> None:
    """Registro manual — usado em testes e por extensões."""
    _plugins[name] = plugin


def unregister_plugin(name: str) -> None:
    _plugins.pop(name, None)


def get_plugin(name: str) -> object | None:
    return _plugins.get(name)
