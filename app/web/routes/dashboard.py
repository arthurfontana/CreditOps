"""Dashboard de governança (v1)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.auth.deps import current_user
from app.db import get_db
from app.models import User
from app.services import dashboard_service, impact_service
from app.web.templating import render

router = APIRouter()


@router.get("/dashboard")
def dashboard(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    overview = dashboard_service.overview(db, user)
    pending = impact_service.pending_observations(db, limit=20)
    return render(request, "dashboard.html", user, o=overview, pending=pending)
