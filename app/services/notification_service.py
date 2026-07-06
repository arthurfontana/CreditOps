"""Notificações (v1): fila persistente + envio via plugin de e-mail.

O core enfileira (tabela `notification`) a partir dos eventos de domínio;
o envio é responsabilidade do plugin `notifier` (SMTP). Falha de envio
mantém a linha na fila — retry pela tarefa periódica, sem perder eventos.
Com `notify_email` desligado nada é enfileirado (a home cobre o essencial).
"""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Notification, PolicyVersion, Role, User
from app.services import authz

logger = logging.getLogger("creditops.notifications")

# eventos de domínio que geram notificação (wiki 03: submissão,
# aprovação pendente, publicação, rejeição — e vigência fecha o ciclo)
SUBJECTS = {
    "version.submitted": "Nova versão para revisão",
    "version.sent_to_approval": "Versão aguardando sua aprovação",
    "version.approval_level": "Versão aguardando o próximo nível de aprovação",
    "version.approved": "Sua versão foi aprovada",
    "version.rejected": "Sua versão foi rejeitada",
    "version.published": "Versão publicada",
    "version.effective": "Versão em vigor",
}


def _workflow_users(db: Session, role: Role, area_id: str | None) -> list[User]:
    """Usuários ativos do papel com escopo na área da política."""
    users = db.scalars(select(User).where(User.role == role.value, User.is_active))
    return [u for u in users if authz.in_area_scope(u, area_id)]


def _recipients(db: Session, event: str, version: PolicyVersion) -> list[User]:
    policy = version.policy
    area_id = policy.area_id
    if event == "version.submitted":
        return _workflow_users(db, Role.REVIEWER, area_id)
    if event in ("version.sent_to_approval", "version.approval_level"):
        return _workflow_users(db, Role.APPROVER, area_id)
    if event in ("version.approved", "version.rejected"):
        author = db.get(User, version.created_by)
        return [author] if author and author.is_active else []
    if event in ("version.published", "version.effective"):
        ids = {version.created_by, policy.owner_id}
        users = [db.get(User, uid) for uid in ids]
        return [u for u in users if u is not None and u.is_active]
    return []


def enqueue_for_event(db: Session, event: str, payload: dict[str, Any]) -> list[Notification]:
    """Cria as linhas da fila para um evento de domínio. Não envia."""
    if event not in SUBJECTS or not get_settings().notify_email:
        return []
    version = db.get(PolicyVersion, payload.get("version_id"))
    if version is None:
        return []
    policy = version.policy
    body_payload = json.dumps(
        {
            "version_id": version.id,
            "policy_code": policy.code,
            "policy_title": policy.title,
            "version_number": version.version_number,
        },
        ensure_ascii=False,
    )
    notifications = []
    for user in _recipients(db, event, version):
        notification = Notification(recipient_id=user.id, event=event, payload=body_payload)
        db.add(notification)
        notifications.append(notification)
    db.flush()
    return notifications


def render_message(db: Session, notification: Notification) -> tuple[str, str]:
    data = json.loads(notification.payload or "{}")
    settings = get_settings()
    code = data.get("policy_code", "?")
    title = data.get("policy_title", "")
    number = data.get("version_number", "?")
    label = SUBJECTS.get(notification.event, notification.event)
    subject = f"[{settings.app_name}] {label}: {code} v{number}"
    link = f"{settings.app_base_url.rstrip('/')}/versions/{data.get('version_id', '')}"
    body = (
        f"Política: {code} — {title}\n"
        f"Versão: v{number}\n"
        f"Evento: {SUBJECTS.get(notification.event, notification.event)}\n\n"
        f"Acesse: {link}\n\n"
        f"— {settings.app_name} (mensagem automática; não responda)"
    )
    return subject, body


def pending(db: Session, limit: int = 200) -> list[Notification]:
    return list(
        db.scalars(
            select(Notification)
            .where(Notification.sent_at.is_(None))
            .order_by(Notification.id)
            .limit(limit)
        )
    )


def process_queue(db: Session) -> int:
    """Envia a fila pelo plugin `notifier`. Falha mantém na fila (retry).

    Retorna quantas notificações foram enviadas.
    """
    from datetime import datetime

    from app.plugins import registry

    notifier = registry.get_plugin("notifier")
    if notifier is None:
        return 0
    sent = 0
    for notification in pending(db):
        recipient = db.get(User, notification.recipient_id)
        if recipient is None or not recipient.is_active:
            notification.sent_at = datetime.utcnow()  # descarta destinatário inválido
            continue
        subject, body = render_message(db, notification)
        try:
            notifier.notify(recipient.email, subject, body)
        except Exception:  # noqa: BLE001 - indisponibilidade de SMTP não derruba o core
            logger.exception("falha ao enviar notificação %s", notification.id)
            continue
        notification.sent_at = datetime.utcnow()
        sent += 1
    db.flush()
    return sent
