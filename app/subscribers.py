"""Subscribers de eventos de domínio do core.

Handlers rodam APÓS o commit, cada um com a própria sessão. Na v1 os
mesmos eventos alimentam a fila de notificações (plugin de e-mail);
falha de handler é logada e nunca derruba o core.
"""

from __future__ import annotations

import logging
from typing import Any

from app.services import events

logger = logging.getLogger("creditops.domain")

_registered = False

DOMAIN_EVENTS = (
    "version.submitted",
    "version.sent_to_approval",
    "version.approval_level",
    "version.approved",
    "version.rejected",
    "version.published",
    "version.effective",
)


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


def _notify(event_name: str):
    """Enfileira notificações do evento e tenta enviar imediatamente.

    Envio falho fica na fila — a tarefa periódica faz o retry.
    """

    def handler(payload: dict[str, Any]) -> None:
        from app.db import SessionLocal
        from app.services import notification_service

        db = SessionLocal()
        try:
            queued = notification_service.enqueue_for_event(db, event_name, payload)
            if queued:
                notification_service.process_queue(db)
            db.commit()
        finally:
            db.close()

    return handler


def _webhook(event_name: str):
    """Enfileira entregas de webhook do evento e tenta enviar imediatamente.

    Entrega falha fica na fila — a tarefa periódica faz o retry (v2).
    """

    def handler(payload: dict[str, Any]) -> None:
        from app.db import SessionLocal
        from app.services import webhook_service

        db = SessionLocal()
        try:
            queued = webhook_service.enqueue_for_event(db, event_name, payload)
            if queued:
                webhook_service.process_queue(db)
            db.commit()
        finally:
            db.close()

    return handler


def register() -> None:
    global _registered
    if _registered:
        return
    _registered = True
    for name in DOMAIN_EVENTS:
        events.subscribe(name, _log_event(name))
        events.subscribe(name, _notify(name))
    events.subscribe("version.effective", _reindex_on_effective)
    for name in ("version.published", "version.effective"):
        events.subscribe(name, _webhook(name))
