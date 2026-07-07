"""Rotas web da v2: recertificação, leitura, comparação, impacto, perguntas, IA."""

from __future__ import annotations

from datetime import date, timedelta

from tests.conftest import login_as
from tests.helpers import approve_and_publish, draft_of, make_policy, to_approval


def _published_policy(db, author, reviewer, approver, area, title="Política Vigente"):
    policy = make_policy(db, author, area, title=title)
    approve_and_publish(db, author, reviewer, approver, draft_of(policy))
    return policy


def test_v2_pages_render(client, db, author, reviewer, approver, reader, area):
    _published_policy(db, author, reviewer, approver, area)
    login_as(client, reader)
    for path in ("/recertification", "/reading", "/compare-policies", "/impact", "/ask"):
        response = client.get(path)
        assert response.status_code == 200, path


def test_ask_without_ai_is_enhanced_search(client, db, author, reviewer, approver, reader, area):
    policy = make_policy(db, author, area, title="Limite Cartão PF")
    version = draft_of(policy)
    version.body_md = "## Regras\nScore mínimo de 640 para cartão."
    db.commit()
    approve_and_publish(db, author, reviewer, approver, version)
    login_as(client, reader)
    response = client.get("/ask?q=score+cartao")
    assert response.status_code == 200
    assert policy.code in response.text  # fonte listada mesmo sem IA


def test_acknowledge_and_readers_page(client, db, author, reviewer, approver, reader, area):
    policy = _published_policy(db, author, reviewer, approver, area)
    login_as(client, reader)
    page = client.get(f"/policies/{policy.id}")
    assert "Li e estou ciente" in page.text
    csrf = page.text.split('name="csrf_token" value="')[1].split('"')[0]
    response = client.post(
        f"/policies/{policy.id}/acknowledge", data={"csrf_token": csrf}
    )
    assert response.status_code == 303
    page = client.get(f"/policies/{policy.id}")
    assert "Ciência registrada" in page.text
    readers = client.get(f"/policies/{policy.id}/readers")
    assert "Leitor" in readers.text or "leitor" in readers.text


def test_compare_two_policies(client, db, author, reviewer, approver, reader, area):
    a = _published_policy(db, author, reviewer, approver, area, title="Política A")
    b = _published_policy(db, author, reviewer, approver, area, title="Política B")
    login_as(client, reader)
    response = client.get(f"/compare-policies?policy_a={a.id}&policy_b={b.id}")
    assert response.status_code == 200
    assert a.code in response.text and b.code in response.text


def test_reference_form_and_impact_page(client, db, author, area):
    source = make_policy(db, author, area, title="Concessão")
    target = make_policy(db, author, area, title="Score Base")
    login_as(client, author)
    page = client.get(f"/policies/{source.id}")
    csrf = page.text.split('name="csrf_token" value="')[1].split('"')[0]
    response = client.post(
        f"/policies/{source.id}/references",
        data={"csrf_token": csrf, "relation": "depende_de", "to_policy_id": target.id,
              "artifact_name": "", "note": ""},
    )
    assert response.status_code == 303
    impact = client.get(f"/impact?policy_id={target.id}")
    assert source.code in impact.text


def test_pilot_publish_via_route(client, db, author, reviewer, approver, area):
    policy = make_policy(db, author, area)
    version = to_approval(db, author, reviewer, draft_of(policy))
    from app.services import workflow_service

    workflow_service.approve(db, approver, version.id)
    db.commit()
    login_as(client, approver)
    page = client.get(f"/versions/{version.id}/review")
    csrf = page.text.split('name="csrf_token" value="')[1].split('"')[0]
    response = client.post(
        f"/versions/{version.id}/publish",
        data={
            "csrf_token": csrf,
            "effective_from": date.today().isoformat(),
            "release_id": "",
            "rollout_scope": "pilot",
            "pilot_description": "20% da esteira PJ; sucesso = conversão +1 p.p.",
            "pilot_ends_at": (date.today() + timedelta(days=45)).isoformat(),
        },
    )
    assert response.status_code == 303
    detail = client.get(f"/policies/{policy.id}")
    assert "PILOTO" in detail.text
    dash = client.get("/dashboard")
    assert "Pilotos em vigor" in dash.text and policy.code in dash.text


def test_recertification_actions(client, db, author, reviewer, approver, area):
    policy = _published_policy(db, author, reviewer, approver, area)
    login_as(client, approver)
    page = client.get(f"/policies/{policy.id}")
    csrf = page.text.split('name="csrf_token" value="')[1].split('"')[0]
    response = client.post(
        f"/policies/{policy.id}/recertify",
        data={"csrf_token": csrf, "months": "12", "note": "ok"},
    )
    assert response.status_code == 303
    report = client.get("/recertification")
    assert policy.code in report.text


def test_ai_endpoints_fail_soft_without_provider(client, db, author, area):
    policy = make_policy(db, author, area)
    version = draft_of(policy)
    login_as(client, author)
    page = client.get(f"/versions/{version.id}")
    csrf = page.text.split('name="csrf_token" value="')[1].split('"')[0]
    response = client.post(
        f"/ai/versions/{version.id}/summarize-diff", data={"csrf_token": csrf}
    )
    assert response.status_code == 200
    assert "indisponível" in response.text  # nunca erro 500
    draft_page = client.get("/ai/draft")
    assert draft_page.status_code == 200
    assert "desligada" in draft_page.text
