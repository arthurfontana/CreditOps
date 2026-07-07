"""Adapter Google Gemini (generateContent) — HTTP puro via httpx."""

from __future__ import annotations

import time

import httpx

from app.config import Settings
from app.plugins.base import AIResult

DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com"


class GeminiProvider:
    def __init__(self, settings: Settings) -> None:
        self.model = settings.ai_model or "gemini-2.0-flash"
        self.base_url = (settings.ai_base_url or DEFAULT_BASE_URL).rstrip("/")
        self.api_key = settings.ai_resolved_api_key
        self.timeout = settings.ai_timeout_seconds

    def complete(
        self, prompt: str, *, system: str | None = None, max_tokens: int = 1024
    ) -> AIResult:
        body: dict = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"maxOutputTokens": max_tokens},
        }
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        started = time.monotonic()
        response = httpx.post(
            f"{self.base_url}/v1beta/models/{self.model}:generateContent",
            params={"key": self.api_key},
            json=body,
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = response.json()
        candidates = data.get("candidates") or []
        parts = (candidates[0].get("content") or {}).get("parts", []) if candidates else []
        usage = data.get("usageMetadata") or {}
        return AIResult(
            text="".join(p.get("text", "") for p in parts),
            provider="gemini",
            model=self.model,
            input_tokens=usage.get("promptTokenCount"),
            output_tokens=usage.get("candidatesTokenCount"),
            latency_ms=int((time.monotonic() - started) * 1000),
        )

    def health(self) -> bool:
        try:
            response = httpx.get(
                f"{self.base_url}/v1beta/models",
                params={"key": self.api_key},
                timeout=self.timeout,
            )
            return response.status_code < 500
        except httpx.HTTPError:
            return False
