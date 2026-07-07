"""Plugin de notificação por e-mail via SMTP corporativo (v1).

Implementa o contrato NotifierPlugin (app/plugins/base.py). Configuração
em settings (smtp_host, smtp_port, smtp_from, smtp_starttls, smtp_username);
a senha vem APENAS de variável de ambiente (CREDITOPS_SMTP_PASSWORD).
"""

from __future__ import annotations

import smtplib
from email.message import EmailMessage

from app.config import Settings


class SmtpNotifier:
    def __init__(self, settings: Settings) -> None:
        if not settings.smtp_host:
            raise ValueError("notify_email ativo mas smtp_host não configurado")
        self._host = settings.smtp_host
        self._port = settings.smtp_port
        self._from = settings.smtp_from
        self._starttls = settings.smtp_starttls
        self._username = settings.smtp_username
        self._password = settings.smtp_password
        self._timeout = settings.smtp_timeout_seconds

    def _connect(self) -> smtplib.SMTP:
        client = smtplib.SMTP(self._host, self._port, timeout=self._timeout)
        client.ehlo()
        if self._starttls:
            client.starttls()
            client.ehlo()
        if self._username:
            client.login(self._username, self._password)
        return client

    def notify(self, recipient: str, subject: str, body: str) -> None:
        message = EmailMessage()
        message["From"] = self._from
        message["To"] = recipient
        message["Subject"] = subject
        message.set_content(body)
        with self._connect() as client:
            client.send_message(message)

    def health(self) -> bool:
        try:
            with self._connect() as client:
                client.noop()
            return True
        except Exception:  # noqa: BLE001
            return False
