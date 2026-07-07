"""Rotas web da v1: demandas, releases, dashboard, delegações e admin."""

from __future__ import annotations

from datetime import date

from app.services import dashboard_service
from tests.conftest import login_as
from tests.helpers import approve_and_publish, draft_of, make_policy


def test_dashboard_page(client, db, admin, author, reviewer, approver, area):
    policy = make_policy(db, author, area)
    approve_and_publish(db, author, reviewer, approver, draft_of(policy))
    login_as(client, approver)
    response = client.get("/dashboard")
    assert response.status_code == 200
    assert "Dashboard de governança" in response.text


def test_dashboard_overview_counts(db, admin, author, reviewer, approver, area):
    policy = make_policy(db, author, area)
    approve_and_publish(db, author, reviewer, approver, draft_of(policy))
    overview = dashboard_service.overview(db, approver)
    assert overview.versions_by_status.get("effective") == 1
    assert overview.avg_cycle_days is not None


def test_change_request_flow_via_web(client, db, author, area):
    login_as(client, author)
    page = client.get("/change-requests/new")
    assert page.status_code == 200

    csrf = page.text.split('name="csrf_token" value="')[1].split('"')[0]
    response = client.post(
        "/change-requests",
        data={
            "title": "Nova regra de renegociação",
            "description_md": "Motivação",
            "area_id": area.id,
            "priority": "high",
            "csrf_token": csrf,
        },
    )
    assert response.status_code == 303

    listing = client.get("/change-requests")
    assert "DEM-" in listing.text


def test_releases_page(client, db, approver):
    login_as(client, approver)
    assert client.get("/releases").status_code == 200


def test_delegations_page(client, db, approver):
    login_as(client, approver)
    response = client.get("/delegations")
    assert response.status_code == 200
    assert "Delegar minha aprovação" in response.text


def test_admin_indicator_and_rules_pages(client, db, admin):
    login_as(client, admin)
    assert client.get("/admin/indicators").status_code == 200
    assert client.get("/admin/approval-rules").status_code == 200


def test_import_page_requires_author(client, db, reader, author):
    login_as(client, reader)
    assert client.get("/policies/import").status_code == 403
    login_as(client, author)
    assert client.get("/policies/import").status_code == 200


def test_pdf_export_route(client, db, author, reviewer, approver, area):
    policy = make_policy(db, author, area)
    approve_and_publish(
        db, author, reviewer, approver, draft_of(policy), effective_from=date.today()
    )
    login_as(client, author)
    response = client.get(f"/policies/{policy.id}/export.pdf")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF-1.4")
