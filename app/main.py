"""Aplicação FastAPI: monta rotas web, estáticos e a tarefa de vigência."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.auth.deps import AuthRedirect, Forbidden
from app.config import get_settings
from app.db import SessionLocal
from app.services import workflow_service
from app.services.errors import (
    InvalidTransition,
    NotFound,
    PermissionDenied,
    ValidationFailed,
)
from app.web.csrf import CSRFError
from app.web.routes import (
    admin,
    ai,
    audit,
    auth,
    change_requests,
    cinemas,
    dashboard,
    delegations,
    exports,
    home,
    platform,
    policies,
    releases,
    versions,
    workflow,
)
from app.web.templating import templates

logger = logging.getLogger("creditops")

EFFECTIVENESS_CHECK_SECONDS = 600  # 10 min
NOTIFICATION_RETRY_SECONDS = 300  # 5 min
WEBHOOK_RETRY_SECONDS = 300  # 5 min


async def _effectiveness_loop() -> None:
    """Ativa vigências agendadas sem depender de cron externo."""
    while True:
        try:
            db = SessionLocal()
            try:
                activated = workflow_service.apply_due_publications(db)
                if activated:
                    db.commit()
                    logger.info("vigências ativadas: %d", activated)
            finally:
                db.close()
        except Exception:  # noqa: BLE001
            logger.exception("falha na ativação de vigências")
        await asyncio.sleep(EFFECTIVENESS_CHECK_SECONDS)


async def _notification_retry_loop() -> None:
    """Retry da fila de notificações (envios que falharam ficam na fila)."""
    from app.services import notification_service

    while True:
        await asyncio.sleep(NOTIFICATION_RETRY_SECONDS)
        try:
            db = SessionLocal()
            try:
                sent = notification_service.process_queue(db)
                if sent:
                    db.commit()
                    logger.info("notificações reenviadas: %d", sent)
            finally:
                db.close()
        except Exception:  # noqa: BLE001
            logger.exception("falha no retry de notificações")


async def _webhook_retry_loop() -> None:
    """Retry da fila de webhooks (entregas que falharam ficam na fila)."""
    from app.services import webhook_service

    while True:
        await asyncio.sleep(WEBHOOK_RETRY_SECONDS)
        try:
            db = SessionLocal()
            try:
                delivered = webhook_service.process_queue(db)
                if delivered:
                    db.commit()
                    logger.info("webhooks reenviados: %d", delivered)
            finally:
                db.close()
        except Exception:  # noqa: BLE001
            logger.exception("falha no retry de webhooks")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    (settings.data_path / "attachments").mkdir(parents=True, exist_ok=True)
    (settings.data_path / "exports").mkdir(parents=True, exist_ok=True)
    tasks = [asyncio.create_task(_effectiveness_loop())]
    if settings.notify_email:
        tasks.append(asyncio.create_task(_notification_retry_loop()))
    if settings.webhook_url_list:
        tasks.append(asyncio.create_task(_webhook_retry_loop()))
    yield
    for task in tasks:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


def create_app() -> FastAPI:
    settings = get_settings()

    from app import subscribers
    from app.plugins import registry

    subscribers.register()
    registry.load_plugins()

    app = FastAPI(title=settings.app_name, version=settings.version, lifespan=lifespan)

    static_dir = Path(__file__).resolve().parent / "web" / "static"
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "version": settings.version}

    app.include_router(auth.router)
    app.include_router(home.router)
    app.include_router(policies.router)
    app.include_router(versions.router)
    app.include_router(workflow.router)
    app.include_router(audit.router)
    app.include_router(exports.router)
    app.include_router(admin.router)
    app.include_router(releases.router)
    app.include_router(change_requests.router)
    app.include_router(cinemas.router)
    app.include_router(dashboard.router)
    app.include_router(delegations.router)
    app.include_router(platform.router)
    app.include_router(ai.router)
    if settings.api_enabled:
        from app.api import v1 as api_v1

        app.include_router(api_v1.router)

    @app.exception_handler(AuthRedirect)
    async def _auth_redirect(request: Request, exc: AuthRedirect):
        return RedirectResponse(f"/login?next={exc.next_url}", status_code=303)

    @app.exception_handler(Forbidden)
    async def _forbidden(request: Request, exc: Forbidden):
        return templates.TemplateResponse(
            request, "errors/403.html", {"request": request, "detail": exc.detail, "user": None},
            status_code=403,
        )

    @app.exception_handler(PermissionDenied)
    async def _permission_denied(request: Request, exc: PermissionDenied):
        return templates.TemplateResponse(
            request, "errors/403.html", {"request": request, "detail": str(exc), "user": None},
            status_code=403,
        )

    @app.exception_handler(NotFound)
    async def _not_found(request: Request, exc: NotFound):
        return templates.TemplateResponse(
            request, "errors/404.html", {"request": request, "detail": str(exc), "user": None},
            status_code=404,
        )

    @app.exception_handler(ValidationFailed)
    async def _validation_failed(request: Request, exc: ValidationFailed):
        return HTMLResponse(f"<div class='flash flash-error'>{exc}</div>", status_code=400)

    @app.exception_handler(InvalidTransition)
    async def _invalid_transition(request: Request, exc: InvalidTransition):
        return HTMLResponse(f"<div class='flash flash-error'>{exc}</div>", status_code=400)

    @app.exception_handler(CSRFError)
    async def _csrf_error(request: Request, exc: CSRFError):
        return HTMLResponse(
            "<div class='flash flash-error'>Sessão inválida — recarregue a página.</div>",
            status_code=400,
        )

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        # style-src permite inline: as cores das matrizes de cineminha e a
        # formatação de cor do editor WYSIWYG usam style="" (o HTML do editor é
        # sanitizado no servidor — nh3 restringe style a cor/alinhamento).
        # Scripts continuam estritos ('self', sem inline).
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; "
            "style-src 'self' 'unsafe-inline'; script-src 'self'",
        )
        return response

    return app


app = create_app()
