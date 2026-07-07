"""Plugin de webhooks de publicação (v2).

Entrega eventos de domínio (version.published / version.effective) a
sistemas consumidores (motores de decisão, data lake). O corpo é assinado
com HMAC-SHA256 (header X-CreditOps-Signature) quando há segredo
configurado — o consumidor valida a origem sem canal extra.
"""

from __future__ import annotations

import hashlib
import hmac

import httpx

from app.config import Settings


class WebhookSender:
    def __init__(self, settings: Settings) -> None:
        self.secret = settings.webhook_secret
        self.timeout = settings.webhook_timeout_seconds

    def _signature(self, body: bytes) -> str:
        digest = hmac.new(self.secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
        return f"sha256={digest}"

    def send(self, url: str, event: str, payload_json: str) -> None:
        """Entrega um evento. Levanta exceção em falha — o chamador faz retry."""
        body = payload_json.encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "CreditOps-Webhook/1.0",
            "X-CreditOps-Event": event,
        }
        if self.secret:
            headers["X-CreditOps-Signature"] = self._signature(body)
        response = httpx.post(url, content=body, headers=headers, timeout=self.timeout)
        response.raise_for_status()

    def health(self) -> bool:
        return True
