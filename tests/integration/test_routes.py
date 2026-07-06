"""Fluxos completos pela camada web (rotas + templates + CSRF)."""

from datetime import date

from app.models import VersionStatus
from app.web.csrf import make_csrf_token
from tests.conftest import login_as
from tests.helpers import draft_of, make_policy


def _csrf(user) -> dict:
    return {"csrf_token": make_csrf_token(user.id)}


def test_full_cycle_through_routes(client, db, author, reviewer, approver, area):
    # autor cria política pela UI
    login_as(client, author)
    response = client.post(
        "/policies",
        data={
            "title": "Política de Limite PF",
            "policy_type": "limite",
            "area_id": area.id,
            "owner_id": author.id,
            **_csrf(author),
        },
    )
    assert response.status_code == 303
    policy_url = response.headers["location"].split("?")[0]
    policy_id = policy_url.rsplit("/", 1)[-1]

    detail = client.get(policy_url)
    assert detail.status_code == 200
    assert "Política de Limite PF" in detail.text

    from app.models import Policy

    policy = db.get(Policy, policy_id)
    version = draft_of(policy)

    # edita conteúdo e campos de submissão
    response = client.post(
        f"/versions/{version.id}/edit",
        data={"body_md": "## Regras\nScore mínimo 700", **_csrf(author)},
    )
    assert response.status_code == 303
    response = client.post(
        f"/versions/{version.id}/fields",
        data={
            "change_summary": "Primeira versão da política",
            "expected_impact": "Base de governança",
            **_csrf(author),
        },
    )
    assert response.status_code == 303

    # submete para revisão
    response = client.post(f"/versions/{version.id}/submit", data=_csrf(author))
    assert response.status_code == 303
    db.expire_all()
    assert draft_of(db.get(Policy, policy_id)).status == VersionStatus.IN_REVIEW

    # revisor envia para aprovação
    login_as(client, reviewer)
    response = client.post(f"/versions/{version.id}/send-to-approval", data=_csrf(reviewer))
    assert response.status_code == 303

    # aprovador vê a tela de decisão com diff/justificativa
    login_as(client, approver)
    review = client.get(f"/versions/{version.id}/review")
    assert review.status_code == 200
    assert "Primeira versão da política" in review.text

    response = client.post(f"/versions/{version.id}/approve", data=_csrf(approver))
    assert response.status_code == 303

    # publica com vigência imediata
    response = client.post(
        f"/versions/{version.id}/publish",
        data={"effective_from": date.today().isoformat(), **_csrf(approver)},
    )
    assert response.status_code == 303
    db.expire_all()
    policy = db.get(Policy, policy_id)
    assert policy.current_version_id == version.id

    # catálogo mostra selo EM VIGOR
    catalog = client.get("/policies")
    assert "EM VIGOR v1" in catalog.text

    # busca encontra
    result = client.get("/search", params={"q": "score 700"})
    assert policy.code in result.text

    # histórico e time travel
    history = client.get(f"/policies/{policy_id}/history")
    assert history.status_code == 200
    at = client.get(
        f"/policies/{policy_id}/history", params={"at": date.today().isoformat()}
    )
    assert "v1" in at.text

    # exportações
    assert client.get(f"/policies/{policy_id}/export.md").status_code == 200
    assert client.get(f"/policies/{policy_id}/export.json").status_code == 200
    dossier = client.get(f"/policies/{policy_id}/dossier")
    assert dossier.status_code == 200
    assert dossier.headers["content-type"] == "application/zip"


def test_csrf_required_on_mutations(client, db, author, area):
    login_as(client, author)
    response = client.post(
        "/policies",
        data={
            "title": "Sem CSRF",
            "policy_type": "limite",
            "area_id": area.id,
            "owner_id": author.id,
        },
    )
    assert response.status_code == 400


def test_reader_cannot_access_admin_or_new_policy(client, db, reader):
    login_as(client, reader)
    assert client.get("/admin/users").status_code == 403
    assert client.get("/policies/new").status_code == 403
    assert client.get("/audit").status_code == 403


def test_auditor_reader_can_access_audit(client, db, reader):
    reader.is_auditor = True
    db.commit()
    login_as(client, reader)
    assert client.get("/audit").status_code == 200
    export = client.get("/audit/export.csv")
    assert export.status_code == 200
    assert "acao" in export.text


def test_admin_manages_users_and_catalogs(client, db, admin):
    login_as(client, admin)
    response = client.post(
        "/admin/users",
        data={
            "username": "novo",
            "email": "novo@example.com",
            "display_name": "Novo Usuário",
            "role": "reader",
            "password": "senha-nova-123",
            **_csrf(admin),
        },
    )
    assert response.status_code == 303
    users = client.get("/admin/users")
    assert "Novo Usuário" in users.text

    response = client.post(
        "/admin/catalogs/areas",
        data={"name": "Riscos", "code": "RSK", **_csrf(admin)},
    )
    assert response.status_code == 303
    areas = client.get("/admin/catalogs/areas")
    assert "Riscos" in areas.text

    response = client.post("/admin/tags", data={"name": "bacen", **_csrf(admin)})
    assert response.status_code == 303


def test_markdown_is_sanitized(client, db, author, area):
    login_as(client, author)
    policy = make_policy(db, author, area)
    version = draft_of(policy)
    client.post(
        f"/versions/{version.id}/edit",
        data={"body_md": "<script>alert('xss')</script>\n\n## Ok", **_csrf(author)},
    )
    page = client.get(f"/versions/{version.id}")
    assert "<script>alert" not in page.text
    assert "&lt;script&gt;" in page.text


def test_404_page(client, db, author):
    login_as(client, author)
    response = client.get("/policies/nao-existe")
    assert response.status_code == 404
