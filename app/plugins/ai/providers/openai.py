"""Adapter OpenAI (Chat Completions) — HTTP puro via httpx."""

from __future__ import annotations

import time

import httpx

from app.config import Settings
from app.plugins.base import AIResult

DEFAULT_BASE_URL = "https://api.openai.com"


class OpenAIProvider:
    def __init__(self, settings: Settings, *, base_url: str | None = None) -> None:
        self.model = settings.ai_model or "gpt-4o-mini"
        self.base_url = (base_url or settings.ai_base_url or DEFAULT_BASE_URL).rstrip("/")
        self.api_key = settings.ai_resolved_api_key
        self.timeout = settings.ai_timeout_seconds
        self.name = settings.ai_provider

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def complete(
        self, prompt: str, *, system: str | None = None, max_tokens: int = 1024
    ) -> AIResult:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        started = time.monotonic()
        response = httpx.post(
            f"{self.base_url}/v1/chat/completions",
            headers=self._headers(),
            json={"model": self.model, "messages": messages, "max_tokens": max_tokens},
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = response.json()
        usage = data.get("usage") or {}
        return AIResult(
            text=data["choices"][0]["message"]["content"],
            provider=self.name,
            model=data.get("model", self.model),
            input_tokens=usage.get("prompt_tokens"),
            output_tokens=usage.get("completion_tokens"),
            latency_ms=int((time.monotonic() - started) * 1000),
        )

    def health(self) -> bool:
        try:
            response = httpx.get(
                f"{self.base_url}/v1/models", headers=self._headers(), timeout=self.timeout
            )
            return response.status_code < 500
        except httpx.HTTPError:
            return False
