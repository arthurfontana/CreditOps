"""Webhooks de publicação (v2): fila persistente + envio via plugin.

Espelha o padrão do notification_service (v1): o core enfileira
(`webhook_delivery`) a partir dos eventos de domínio; a entrega é do
plugin `webhook`. Falha mantém a linha na fila — retry pela tarefa
periódica até webhook_max_attempts, sem perder eventos.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import PolicyVersion, Publication, WebhookDelivery

logger = logging.getLogger("creditops.webhooks")

# eventos entregues a consumidores externos
WEBHOOK_EVENTS = ("version.published", "version.effective")


def _event_body(db: Session, event: str, version: PolicyVersion) -> str:
    policy = version.policy
    publication = db.scalars(
        select(Publication).where(Publication.version_id == version.id)
    ).first()
    return json.dumps(
        {
            "event": event,
            "occurred_at": datetime.utcnow().isoformat() + "Z",
            "policy": {
                "id": policy.id,
                "code": policy.code,
                "title": policy.title,
                "type": policy.policy_type,
                "area": policy.area.code if policy.area else None,
            },
            "version": {
                "id": version.id,
                "number": version.version_number,
                "status": version.status,
                "content_hash": version.content_hash,
            },
            "publication": {
                "effective_from": publication.effective_from.isoformat()
                if publication
                else None,
                "rollout_scope": publication.rollout_scope if publication else None,
                "pilot_ends_at": publication.pilot_ends_at.isoformat()
                if publication and publication.pilot_ends_at
                else None,
            },
        },
        ensure_ascii=False,
    )


def enqueue_for_event(db: Session, event: str, payload: dict[str, Any]) -> list[WebhookDelivery]:
    """Cria uma entrega por endpoint configurado. Não envia."""
    settings = get_settings()
    urls = settings.webhook_url_list
    if event not in WEBHOOK_EVENTS or not urls:
        return []
    version = db.get(PolicyVersion, payload.get("version_id"))
    if version is None:
        return []
    body = _event_body(db, event, version)
    deliveries = []
    for url in urls:
        delivery = WebhookDelivery(url=url, event=event, payload=body)
        db.add(delivery)
        deliveries.append(delivery)
    db.flush()
    return deliveries


def pending(db: Session, limit: int = 200) -> list[WebhookDelivery]:
    settings = get_settings()
    return list(
        db.scalars(
            select(WebhookDelivery)
            .where(
                WebhookDelivery.delivered_at.is_(None),
                WebhookDelivery.attempts < settings.webhook_max_attempts,
            )
            .order_by(WebhookDelivery.id)
            .limit(limit)
        )
    )


def process_queue(db: Session) -> int:
    """Entrega a fila pelo plugin `webhook`. Retorna quantas foram entregues."""
    from app.plugins import registry

    sender = registry.get_plugin("webhook")
    if sender is None:
        return 0
    delivered = 0
    for delivery in pending(db):
        try:
            sender.send(delivery.url, delivery.event, delivery.payload)
        except Exception as exc:  # noqa: BLE001 - consumidor fora do ar não derruba o core
            delivery.attempts += 1
            delivery.last_error = str(exc)[:500]
            logger.warning(
                "webhook %s falhou (tentativa %d): %s",
                delivery.url, delivery.attempts, exc,
            )
            continue
        delivery.delivered_at = datetime.utcnow()
        delivery.attempts += 1
        delivery.last_error = None
        delivered += 1
    db.flush()
    return delivered
