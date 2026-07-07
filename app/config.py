"""Configuração da aplicação.

Ordem de precedência: variáveis de ambiente (prefixo CREDITOPS_) >
config/settings.toml > defaults. Segredos ficam apenas em env vars —
nunca no banco, no código ou no repositório.
"""

from __future__ import annotations

import tomllib
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent
SETTINGS_TOML = BASE_DIR / "config" / "settings.toml"


def _toml_defaults() -> dict[str, Any]:
    if not SETTINGS_TOML.exists():
        return {}
    with SETTINGS_TOML.open("rb") as fh:
        raw = tomllib.load(fh)
    flat: dict[str, Any] = {}
    for section in raw.values():
        if isinstance(section, dict):
            flat.update(section)
    return flat


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CREDITOPS_", env_file=".env", extra="ignore")

    app_name: str = "CreditOps"
    version: str = "0.1.0"
    secret_key: str = "dev-secret-key-change-me"
    db_path: str = "data/creditops.db"
    data_dir: str = "data"
    cookie_secure: bool = True
    session_max_age_seconds: int = 8 * 3600  # expiração por inatividade: 8h
    login_max_failures: int = 5
    login_lockout_minutes: int = 15
    attachment_max_bytes: int = 20 * 1024 * 1024
    attachment_allowed_extensions: str = "pdf,docx,xlsx,png,jpg,jpeg,csv,txt,md"

    # ── v1: notificações por e-mail (plugin SMTP) ────────────────────────────
    notify_email: bool = False
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_from: str = "creditops@example.com"
    smtp_starttls: bool = True
    smtp_username: str = ""
    smtp_password: str = ""  # apenas via env CREDITOPS_SMTP_PASSWORD
    smtp_timeout_seconds: int = 10
    app_base_url: str = "http://localhost:8000"  # links nos e-mails

    # ── v1: exportação PDF (plugin sem dependência externa) ─────────────────
    export_pdf: bool = True

    # ── v1: dashboard — política "parada" após N meses sem revisão ──────────
    stale_policy_months: int = 12

    def __init__(self, **values: Any) -> None:
        merged = {**_toml_defaults(), **values}
        super().__init__(**merged)

    @property
    def database_url(self) -> str:
        path = Path(self.db_path)
        if not path.is_absolute():
            path = BASE_DIR / path
        return f"sqlite:///{path}"

    @property
    def data_path(self) -> Path:
        path = Path(self.data_dir)
        if not path.is_absolute():
            path = BASE_DIR / path
        return path

    @property
    def allowed_extensions(self) -> set[str]:
        parts = self.attachment_allowed_extensions.split(",")
        return {e.strip().lower().lstrip(".") for e in parts}


@lru_cache
def get_settings() -> Settings:
    return Settings()
