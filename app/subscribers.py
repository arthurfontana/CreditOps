"""Subscribers de eventos de domínio do core.

Plugins (e-mail, webhook, IA) assinarão os mesmos eventos nas próximas
fases; por ora: log estruturado + reindexação de busca na vigência.
"""

from __future__ import annotations

import logging
from typing import Any

from app.services import events

logger = logging.getLogger("creditops.domain")

_registered = False


def _log_event(name: str):
    def handler(payload: dict[str, Any]) -> None:
        logger.info("evento de domínio: %s %s", name, payload)

    return handler


def _reindex_on_effective(payload: dict[str, Any]) -> None:
    from app.db import SessionLocal
    from app.services import search_service

    db = SessionLocal()
    try:
        search_service.reindex_policy(db, payload["policy_id"])
        db.commit()
    finally:
        db.close()


def register() -> None:
    global _registered
    if _registered:
        return
    _registered = True
    for name in (
        "version.submitted",
        "version.approved",
        "version.rejected",
        "version.published",
        "version.effective",
    ):
        events.subscribe(name, _log_event(name))
    events.subscribe("version.effective", _reindex_on_effective)
