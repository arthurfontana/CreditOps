"""Registro de plugins — carregados conforme configuração.

Regra arquitetural: o core nunca importa plugin diretamente; ele consulta
o registro (`get_plugin`) e emite eventos de domínio. Falha de plugin é
logada e nunca propaga — o core opera sozinho.

Plugins da v1:
- `notifier`   → e-mail SMTP (settings: notify_email = true)
- `export_pdf` → exportação PDF sem dependência externa (default: ativo)

Plugins da v2:
- `auth`    → SSO LDAP/AD (settings: auth_sso = "ldap")
- `webhook` → entrega de eventos de publicação (settings: webhook_urls)
- `ai`      → módulo de IA plugável (settings: ai_provider != "none")
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

    if settings.auth_sso == "ldap":
        try:
            from app.plugins.auth_ldap import LdapAuthenticator

            _plugins["auth"] = LdapAuthenticator(settings)
            logger.info("plugin auth (LDAP) ativo: %s", settings.ldap_server)
        except Exception:  # noqa: BLE001
            logger.exception(
                "falha ao carregar plugin LDAP — apenas senha local funcionará"
            )

    if settings.webhook_url_list:
        try:
            from app.plugins.webhook import WebhookSender

            _plugins["webhook"] = WebhookSender(settings)
            logger.info("plugin webhook ativo: %d endpoint(s)", len(settings.webhook_url_list))
        except Exception:  # noqa: BLE001
            logger.exception("falha ao carregar plugin webhook — core segue sem ele")

    if settings.ai_provider != "none":
        try:
            from app.plugins.ai import AIService

            _plugins["ai"] = AIService(settings)
            logger.info(
                "plugin ai ativo: provider=%s model=%s",
                settings.ai_provider, settings.ai_model or "(padrão)",
            )
        except Exception:  # noqa: BLE001
            logger.exception("falha ao carregar plugin de IA — core segue sem ele")

    if not _plugins:
        logger.debug("nenhum plugin configurado (core opera sozinho)")


def register_plugin(name: str, plugin: object) -> None:
    """Registro manual — usado em testes e por extensões."""
    _plugins[name] = plugin


def unregister_plugin(name: str) -> None:
    _plugins.pop(name, None)


def get_plugin(name: str) -> object | None:
    return _plugins.get(name)
