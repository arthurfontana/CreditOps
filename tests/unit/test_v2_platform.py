"""v2 "Plataforma da empresa": tokens/API, SSO, grafo, recertificação,
leitura, piloto, webhooks e IA plugável."""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import select

from app.models import (
    AuditLog,
    PolicyVersion,
    Publication,
    ReadReceipt,
    VersionStatus,
    WebhookDelivery,
)
from app.plugins import registry
from app.plugins.base import AIResult
from app.services import (
    read_receipt_service,
    recertification_service,
    reference_service,
    service_token_service,
    user_service,
    webhook_service,
    workflow_service,
)
from app.services.errors import PermissionDenied, ValidationFailed
from app.services.user_service import AuthenticationFailed
from tests.helpers import approve_and_publish, draft_of, make_policy, to_approval


def _audit_actions(db) -> list[str]:
    return [a.action for a in db.scalars(select(AuditLog))]


# ─── tokens de serviço + API de consumo ──────────────────────────────────────


def test_service_token_lifecycle(db, admin):
    token, plaintext = service_token_service.create_token(db, admin, "motor-x")
    db.commit()
    assert plaintext.startswith("cok_")
    assert token.token_hash != plaintext  # nunca em claro no banco

    assert service_token_service.verify_token(db, plaintext) is not None
    assert service_token_service.verify_token(db, "cok_invalido") is None

    service_token_service.revoke_token(db, admin, token.id)
    db.commit()
    assert service_token_service.verify_token(db, plaintext) is None
    actions = _audit_actions(db)
    assert "api.token_created" in actions and "api.token_revoked" in actions


def test_service_token_requires_admin(db, author):
    with pytest.raises(PermissionDenied):
        service_token_service.create_token(db, author, "nao-pode")


def test_api_requires_token(client, db):
    assert client.get("/api/v1/policies").status_code == 401
    assert client.get(
        "/api/v1/policies", headers={"Authorization": "Bearer cok_falso"}
    ).status_code == 401


def test_api_serves_effective_policy(client, db, author, reviewer, approver, area):
    policy = make_policy(db, author, area)
    approve_and_publish(db, author, reviewer, approver, draft_of(policy))
    _, plaintext = service_token_service.create_token(db, None, "consumidor")
    db.commit()
    headers = {"Authorization": f"Bearer {plaintext}"}

    listing = client.get("/api/v1/policies", headers=headers).json()
    assert listing["count"] == 1
    code = listing["policies"][0]["code"]

    detail = client.get(f"/api/v1/policies/{code}", headers=headers).json()
    assert detail["version"]["status"] == "effective"
    assert detail["version"]["body_md"]
    assert detail["publication"]["rollout_scope"] == "full"

    versions = client.get(f"/api/v1/policies/{code}/versions", headers=headers).json()
    assert versions["count"] == 1

    today = date.today().isoformat()
    at = client.get(
        f"/api/v1/policies/{code}/effective?at={today}", headers=headers
    ).json()
    assert at["version"]["number"] == 1
    # antes da vigência: 404
    past = (date.today() - timedelta(days=30)).isoformat()
    assert client.get(
        f"/api/v1/policies/{code}/effective?at={past}", headers=headers
    ).status_code == 404


def test_api_never_serves_drafts(client, db, author, area):
    policy = make_policy(db, author, area)  # v1 fica em draft
    _, plaintext = service_token_service.create_token(db, None, "consumidor-2")
    db.commit()
    headers = {"Authorization": f"Bearer {plaintext}"}
    listing = client.get("/api/v1/policies", headers=headers).json()
    assert listing["count"] == 0  # sem versão vigente, não aparece
    detail = client.get(f"/api/v1/policies/{policy.code}", headers=headers)
    assert detail.status_code == 404
    versions = client.get(
        f"/api/v1/policies/{policy.code}/versions", headers=headers
    ).json()
    assert versions["count"] == 0


# ─── SSO via plugin de auth ──────────────────────────────────────────────────


class FakeDirectory:
    """AuthPlugin de teste."""

    def __init__(self, accept: bool):
        self.accept = accept
        self.calls: list[tuple[str, str]] = []

    def authenticate(self, username: str, password: str) -> bool:
        self.calls.append((username, password))
        return self.accept


def test_sso_user_authenticates_via_plugin(db, admin):
    sso_user = user_service.create_user(
        db, admin, username="maria.sso", email="maria@corp.com",
        display_name="Maria", role="author", password=None,
    )
    db.commit()
    assert sso_user.password_hash is None

    registry.register_plugin("auth", FakeDirectory(accept=True))
    try:
        authenticated = user_service.authenticate(db, "maria.sso", "senha-do-ad")
        assert authenticated.id == sso_user.id
    finally:
        registry.unregister_plugin("auth")


def test_sso_user_rejected_without_plugin_or_on_directory_refusal(db, admin):
    user_service.create_user(
        db, admin, username="joao.sso", email="joao@corp.com",
        display_name="João", role="reader", password=None,
    )
    db.commit()
    # sem plugin: usuário SSO não autentica
    with pytest.raises(AuthenticationFailed):
        user_service.authenticate(db, "joao.sso", "qualquer")
    # diretório recusa: falha também
    registry.register_plugin("auth", FakeDirectory(accept=False))
    try:
        with pytest.raises(AuthenticationFailed):
            user_service.authenticate(db, "joao.sso", "senha-errada")
    finally:
        registry.unregister_plugin("auth")


def test_local_password_still_works_with_sso_plugin_active(db, admin):
    registry.register_plugin("auth", FakeDirectory(accept=False))
    try:
        authenticated = user_service.authenticate(db, "admin", "senha-forte-123")
        assert authenticated.id == admin.id  # fallback local não passa pelo diretório
    finally:
        registry.unregister_plugin("auth")


def test_ldap_filter_escaping():
    from app.plugins.auth_ldap import escape_filter_value

    assert escape_filter_value("a*b(c)d\\e") == r"a\2ab\28c\29d\5ce"


# ─── grafo de referências + análise de impacto ───────────────────────────────


def test_reference_graph_and_impact(db, author, area):
    base = make_policy(db, author, area, title="Política de Score")
    mid = make_policy(db, author, area, title="Concessão PF")
    top = make_policy(db, author, area, title="Limite Cartão")

    reference_service.add_reference(
        db, author, mid.id, relation="depende_de", to_policy_id=base.id
    )
    reference_service.add_reference(db, author, top.id, relation="usa", to_policy_id=mid.id)
    reference_service.add_reference(
        db, author, mid.id, relation="usa", artifact_name="Score Serasa"
    )
    db.commit()

    assert len(reference_service.outgoing(db, mid.id)) == 2
    assert len(reference_service.incoming(db, base.id)) == 1
    assert reference_service.artifact_names(db) == ["Score Serasa"]

    # impacto da política base: mid (nível 1) e top (nível 2, transitivo)
    hits = reference_service.impact_analysis(db, policy_id=base.id)
    assert [(h.policy.id, h.depth) for h in hits] == [(mid.id, 1), (top.id, 2)]

    # impacto do artefato: quem usa o Score Serasa (e quem depende de quem usa)
    hits = reference_service.impact_analysis(db, artifact_name="score serasa")
    assert {h.policy.id for h in hits} == {mid.id, top.id}

    assert "policy.reference_added" in _audit_actions(db)


def test_reference_validations(db, author, area):
    policy = make_policy(db, author, area)
    other = make_policy(db, author, area, title="Outra")
    with pytest.raises(ValidationFailed):  # auto-referência
        reference_service.add_reference(
            db, author, policy.id, relation="usa", to_policy_id=policy.id
        )
    with pytest.raises(ValidationFailed):  # alvo duplo
        reference_service.add_reference(
            db, author, policy.id, relation="usa",
            to_policy_id=other.id, artifact_name="Motor X",
        )
    with pytest.raises(ValidationFailed):  # sem alvo
        reference_service.add_reference(db, author, policy.id, relation="usa")
    reference_service.add_reference(
        db, author, policy.id, relation="usa", to_policy_id=other.id
    )
    with pytest.raises(ValidationFailed):  # duplicada
        reference_service.add_reference(
            db, author, policy.id, relation="usa", to_policy_id=other.id
        )


def test_impact_handles_cycles(db, author, area):
    a = make_policy(db, author, area, title="A")
    b = make_policy(db, author, area, title="B")
    reference_service.add_reference(db, author, a.id, relation="usa", to_policy_id=b.id)
    reference_service.add_reference(db, author, b.id, relation="usa", to_policy_id=a.id)
    db.commit()
    hits = reference_service.impact_analysis(db, policy_id=a.id)
    assert [h.policy.id for h in hits] == [b.id]  # ciclo não repete nem trava


# ─── recertificação periódica ────────────────────────────────────────────────


def test_recertification_cycle(db, author, reviewer, approver, area):
    policy = make_policy(db, author, area)
    approve_and_publish(db, author, reviewer, approver, draft_of(policy))

    overdue = datetime.utcnow() - timedelta(days=1)
    recertification_service.set_review_due(db, author, policy.id, overdue)
    db.commit()
    report = recertification_service.report(db)
    assert policy.id in [p.id for p in report.overdue]

    recertification_service.recertify(db, approver, policy.id, months=6, note="revisão ok")
    db.commit()
    db.refresh(policy)
    assert policy.review_due_at > datetime.utcnow() + timedelta(days=150)
    report = recertification_service.report(db)
    assert policy.id in [p.id for p in report.scheduled]
    assert "policy.recertified" in _audit_actions(db)


def test_recertify_requires_effective_version_and_approver(db, author, approver, area):
    policy = make_policy(db, author, area)  # sem versão vigente
    with pytest.raises(ValidationFailed):
        recertification_service.recertify(db, approver, policy.id)
    with pytest.raises(PermissionDenied):
        recertification_service.recertify(db, author, policy.id)


# ─── trilha de leitura ───────────────────────────────────────────────────────


def test_read_receipt_flow(db, author, reviewer, approver, reader, area):
    policy = make_policy(db, author, area)
    approve_and_publish(db, author, reviewer, approver, draft_of(policy))

    assert policy.id in [p.id for p in read_receipt_service.pending_for_user(db, reader)]
    receipt = read_receipt_service.acknowledge(db, reader, policy.id)
    db.commit()
    # idempotente
    again = read_receipt_service.acknowledge(db, reader, policy.id)
    assert again.id == receipt.id
    assert len(db.scalars(select(ReadReceipt)).all()) == 1
    assert policy.id not in [p.id for p in read_receipt_service.pending_for_user(db, reader)]

    report = read_receipt_service.policy_report(db, policy.id)
    assert reader.id in {r.user_id for r in report.receipts}
    assert reader.id not in {u.id for u in report.pending_users}
    assert "version.acknowledged" in _audit_actions(db)

    # nova versão em vigor → ciência volta a ser pendente
    from app.services import version_service

    revision = version_service.create_revision(db, author, policy.id)
    revision.body_md += "\nNova regra."
    db.commit()
    approve_and_publish(db, author, reviewer, approver, revision)
    assert policy.id in [p.id for p in read_receipt_service.pending_for_user(db, reader)]


def test_acknowledge_requires_effective_version(db, author, reader, area):
    policy = make_policy(db, author, area)
    with pytest.raises(ValidationFailed):
        read_receipt_service.acknowledge(db, reader, policy.id)


# ─── publicação-experimento (piloto) ─────────────────────────────────────────


def test_pilot_publication(db, author, reviewer, approver, area):
    policy = make_policy(db, author, area)
    version = to_approval(db, author, reviewer, draft_of(policy))
    workflow_service.approve(db, approver, version.id)
    workflow_service.publish(
        db, approver, version.id, date.today(),
        rollout_scope="pilot",
        pilot_description="10% da esteira PF Sul; sucesso = FPD30 estável",
        pilot_ends_at=date.today() + timedelta(days=60),
    )
    db.commit()
    publication = db.scalars(
        select(Publication).where(Publication.version_id == version.id)
    ).one()
    assert publication.rollout_scope == "pilot"
    assert version.status == VersionStatus.EFFECTIVE  # piloto entra em vigor normalmente
    pilots = workflow_service.active_pilots(db)
    assert [p.version_id for p in pilots] == [version.id]


def test_pilot_requires_scope_and_deadline(db, author, reviewer, approver, area):
    policy = make_policy(db, author, area)
    version = to_approval(db, author, reviewer, draft_of(policy))
    workflow_service.approve(db, approver, version.id)
    with pytest.raises(ValidationFailed):
        workflow_service.publish(
            db, approver, version.id, date.today(), rollout_scope="pilot"
        )
    with pytest.raises(ValidationFailed):
        workflow_service.publish(
            db, approver, version.id, date.today(),
            rollout_scope="pilot", pilot_description="escopo",
            pilot_ends_at=date.today(),  # prazo deve ser posterior à vigência
        )
    with pytest.raises(ValidationFailed):
        workflow_service.publish(
            db, approver, version.id, date.today(), rollout_scope="invalido"
        )


# ─── webhooks de publicação ──────────────────────────────────────────────────


class FakeWebhookSender:
    def __init__(self, fail_urls: set[str] | None = None):
        self.sent: list[tuple[str, str]] = []
        self.fail_urls = fail_urls or set()

    def send(self, url: str, event: str, payload_json: str) -> None:
        if url in self.fail_urls:
            raise RuntimeError("consumidor fora do ar")
        self.sent.append((url, event))


def test_webhook_queue_and_retry(db, author, reviewer, approver, area, monkeypatch):
    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(
        settings, "webhook_urls",
        "https://motor.example/hook,https://lake.example/hook",
    )
    from app import subscribers

    subscribers.register()
    policy = make_policy(db, author, area)
    approve_and_publish(db, author, reviewer, approver, draft_of(policy))

    # published + effective × 2 endpoints = 4 entregas na fila
    deliveries = db.scalars(select(WebhookDelivery)).all()
    assert len(deliveries) == 4
    assert {d.event for d in deliveries} == {"version.published", "version.effective"}
    assert '"code"' in deliveries[0].payload  # payload traz a política

    sender = FakeWebhookSender(fail_urls={"https://lake.example/hook"})
    registry.register_plugin("webhook", sender)
    try:
        delivered = webhook_service.process_queue(db)
        db.commit()
        assert delivered == 2  # só o motor recebeu
        remaining = webhook_service.pending(db)
        assert len(remaining) == 2
        assert all(d.attempts == 1 and d.last_error for d in remaining)

        sender.fail_urls = set()  # consumidor voltou: retry entrega o resto
        assert webhook_service.process_queue(db) == 2
        db.commit()
        assert webhook_service.pending(db) == []
    finally:
        registry.unregister_plugin("webhook")


def test_webhook_signature():
    from app.config import Settings
    from app.plugins.webhook import WebhookSender

    sender = WebhookSender(Settings(webhook_secret="segredo"))
    signature = sender._signature(b'{"event":"x"}')
    assert signature.startswith("sha256=") and len(signature) == 71


# ─── módulo de IA plugável ───────────────────────────────────────────────────


class FakeProvider:
    """AIProvider de teste — devolve resposta fixa."""

    def __init__(self, text: str):
        self.text = text
        self.prompts: list[str] = []

    def complete(self, prompt, *, system=None, max_tokens=1024):
        self.prompts.append(prompt)
        return AIResult(text=self.text, provider="fake", model="fake-1")

    def health(self):
        return True


def _fake_ai(text: str, **features):
    """AIService com provider fake e features ligadas."""
    from app.config import Settings
    from app.plugins.ai.service import AIService

    settings = Settings(ai_provider="internal", ai_base_url="http://fake", **features)
    service = AIService.__new__(AIService)
    service.settings = settings
    service.provider = FakeProvider(text)
    return service


def test_ai_none_provider_is_default_and_unavailable(db):
    from app.config import Settings
    from app.plugins.ai.service import AIService, AIUnavailable

    service = AIService(Settings())
    assert service.provider_name == "none"
    assert not service.feature_enabled("summarize_diff")
    with pytest.raises(AIUnavailable):
        service.complete("qualquer coisa")


def test_ai_summarize_diff_and_audit(db, author, reviewer, approver, area):
    from app.plugins.ai import tasks

    policy = make_policy(db, author, area)
    approve_and_publish(db, author, reviewer, approver, draft_of(policy))
    from app.services import version_service

    revision = version_service.create_revision(db, author, policy.id)
    revision.body_md += "\nScore mínimo sobe de 600 para 650."
    db.commit()

    ai = _fake_ai("O score mínimo subiu de 600 para 650.", ai_summarize_diff=True)
    suggestion = tasks.summarize_diff(db, ai, author, revision)
    db.commit()
    assert "650" in suggestion
    prompt = ai.provider.prompts[0]
    assert "Score mínimo sobe" in prompt and policy.code in prompt
    entry = db.scalars(
        select(AuditLog).where(AuditLog.action == "ai.suggestion_generated")
    ).one()
    assert '"summarize_diff"' in entry.payload


def test_ai_suggest_tags_filters_to_catalog(db, author, area):
    from app.models import Tag
    from app.plugins.ai import tasks

    db.add_all([Tag(name="cartao"), Tag(name="limite")])
    db.commit()
    policy = make_policy(db, author, area)
    version = draft_of(policy)
    ai = _fake_ai('{"tags": ["cartao", "inexistente", "LIMITE"]}', ai_suggest_tags=True)
    tags = tasks.suggest_tags(db, ai, author, version)
    db.commit()
    assert tags == ["cartao", "limite"]  # só tags do catálogo, case-insensitive


def test_ai_feature_flag_blocks_task(db, author, area):
    from app.plugins.ai import tasks
    from app.plugins.ai.service import AIUnavailable

    policy = make_policy(db, author, area)
    ai = _fake_ai("x")  # nenhuma feature ligada
    with pytest.raises(AIUnavailable):
        tasks.summarize_diff(db, ai, author, draft_of(policy))


def test_runtime_prompts_parse():
    from app.plugins.ai import tasks

    for name in ("summarize_diff", "suggest_tags", "draft_from_document", "qa_answer"):
        system, user = tasks.load_runtime_prompt(name)
        assert system and user


# ─── RAG local (qa_answer) ───────────────────────────────────────────────────


def test_qa_answer_with_and_without_provider(db, author, reviewer, approver, reader, area):
    from app.plugins.ai import tasks
    from app.services import search_service

    policy = make_policy(db, author, area, title="Política de Limite Cartão")
    version = draft_of(policy)
    version.body_md = "## Regras\nScore mínimo de 620 para cartão PF."
    db.commit()
    approve_and_publish(db, author, reviewer, approver, version)

    hits = search_service.search(db, "score mínimo cartão", reader)
    assert hits

    # sem feature ligada: retrieval vira busca melhorada (answer=None, fontes presentes)
    ai_off = _fake_ai("não deveria ser chamado")
    result = tasks.qa_answer(db, ai_off, reader, "qual o score mínimo?", hits)
    assert result.answer is None
    assert result.sources and result.sources[0]["code"] == policy.code

    ai_on = _fake_ai(f"O score mínimo é 620 ({policy.code} v1).", ai_qa_search=True)
    result = tasks.qa_answer(db, ai_on, reader, "qual o score mínimo?", hits)
    db.commit()
    assert "620" in result.answer
    assert policy.code in ai_on.provider.prompts[0]  # excertos citáveis no prompt


# ─── imutabilidade preservada nas novas tabelas de apoio ─────────────────────


def test_v2_tables_do_not_touch_version_immutability(db, author, reviewer, approver, area):
    """Sanidade: fluxo v2 completo não altera conteúdo de versão publicada."""
    policy = make_policy(db, author, area)
    version = draft_of(policy)
    approve_and_publish(db, author, reviewer, approver, version)
    db.refresh(version)
    frozen_hash = version.content_hash
    read_receipt_service.acknowledge(db, author, policy.id)
    recertification_service.set_review_due(
        db, author, policy.id, datetime.utcnow() + timedelta(days=90)
    )
    db.commit()
    db.refresh(version)
    assert version.content_hash == frozen_hash
    assert db.get(PolicyVersion, version.id).status == VersionStatus.EFFECTIVE
