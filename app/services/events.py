"""Eventos de domínio — pub/sub em memória, entregues APÓS o commit.

Base dos plugins (e-mail, webhook, IA): o core emite, plugins assinam.
Erro em handler é logado e nunca propaga — indisponibilidade de plugin
não derruba o core.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Callable
from typing import Any

from sqlalchemy import event as sa_event
from sqlalchemy.orm import Session

logger = logging.getLogger("creditops.events")

Handler = Callable[[dict[str, Any]], None]

_subscribers: dict[str, list[Handler]] = defaultdict(list)
_QUEUE_KEY = "creditops_pending_events"


def subscribe(event_name: str, handler: Handler) -> None:
    _subscribers[event_name].append(handler)


def clear_subscribers() -> None:
    """Uso em testes."""
    _subscribers.clear()


def emit(db: Session, event_name: str, payload: dict[str, Any]) -> None:
    """Enfileira o evento na sessão; handlers rodam só depois do commit."""
    # garante transação ativa para que commit/rollback subsequente
    # despache ou descarte a fila (autobegin não ocorre via session.info)
    if not db.in_transaction():
        db.begin()
    db.info.setdefault(_QUEUE_KEY, []).append((event_name, payload))


def _dispatch(session: Session) -> None:
    pending = session.info.pop(_QUEUE_KEY, [])
    for event_name, payload in pending:
        for handler in _subscribers.get(event_name, []):
            try:
                handler(payload)
            except Exception:  # noqa: BLE001 - plugin nunca derruba o core
                logger.exception("handler de evento falhou: %s", event_name)


def _discard(session: Session, *args) -> None:
    session.info.pop(_QUEUE_KEY, None)


sa_event.listen(Session, "after_commit", _dispatch)
sa_event.listen(Session, "after_rollback", _discard)
# soft rollback: cobre rollback() sem transação DBAPI ativa
sa_event.listen(Session, "after_soft_rollback", _discard)
