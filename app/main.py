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
from app.web.routes import admin, audit, auth, exports, home, policies, versions, workflow
from app.web.templating import templates

logger = logging.getLogger("creditops")

EFFECTIVENESS_CHECK_SECONDS = 600  # 10 min


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


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    (settings.data_path / "attachments").mkdir(parents=True, exist_ok=True)
    (settings.data_path / "exports").mkdir(parents=True, exist_ok=True)
    task = asyncio.create_task(_effectiveness_loop())
    yield
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
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'",
        )
        return response

    return app


app = create_app()
