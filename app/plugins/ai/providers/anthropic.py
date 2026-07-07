"""Adapter Anthropic (Messages API) — HTTP puro via httpx."""

from __future__ import annotations

import time

import httpx

from app.config import Settings
from app.plugins.base import AIResult

DEFAULT_BASE_URL = "https://api.anthropic.com"
API_VERSION = "2023-06-01"


class AnthropicProvider:
    def __init__(self, settings: Settings) -> None:
        self.model = settings.ai_model or "claude-haiku-4-5-20251001"
        self.base_url = (settings.ai_base_url or DEFAULT_BASE_URL).rstrip("/")
        self.api_key = settings.ai_resolved_api_key
        self.timeout = settings.ai_timeout_seconds

    def _headers(self) -> dict[str, str]:
        return {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": API_VERSION,
        }

    def complete(
        self, prompt: str, *, system: str | None = None, max_tokens: int = 1024
    ) -> AIResult:
        body: dict = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            body["system"] = system
        started = time.monotonic()
        response = httpx.post(
            f"{self.base_url}/v1/messages",
            headers=self._headers(),
            json=body,
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = response.json()
        usage = data.get("usage") or {}
        text = "".join(
            block.get("text", "")
            for block in data.get("content", [])
            if block.get("type") == "text"
        )
        return AIResult(
            text=text,
            provider="anthropic",
            model=data.get("model", self.model),
            input_tokens=usage.get("input_tokens"),
            output_tokens=usage.get("output_tokens"),
            latency_ms=int((time.monotonic() - started) * 1000),
        )

    def health(self) -> bool:
        try:
            response = httpx.get(f"{self.base_url}/v1/models", headers=self._headers(),
                                 timeout=self.timeout)
            return response.status_code < 500
        except httpx.HTTPError:
            return False
