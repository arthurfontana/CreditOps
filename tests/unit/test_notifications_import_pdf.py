"""Notificações (fila + plugin), importador de legado e exportação PDF (v1)."""

from __future__ import annotations

import pytest

from app.config import get_settings
from app.plugins import registry
from app.plugins.export_pdf import PdfExporter
from app.services import import_service, notification_service, workflow_service
from tests.helpers import draft_of, fill_and_submit, make_policy

# ── notificações ─────────────────────────────────────────────────────────────


class FakeNotifier:
    def __init__(self, fail: bool = False):
        self.fail = fail
        self.sent: list[tuple[str, str]] = []

    def notify(self, recipient: str, subject: str, body: str) -> None:
        if self.fail:
            raise ConnectionError("SMTP fora do ar")
        self.sent.append((recipient, subject))

    def health(self) -> bool:
        return not self.fail


@pytest.fixture()
def email_enabled(monkeypatch):
    """Ativa notify_email SÓ depois do workflow — o subscriber real também
    enfileira no commit quando ligado, o que duplicaria as filas do teste."""

    def enable():
        monkeypatch.setattr(get_settings(), "notify_email", True)

    return enable


def test_submission_queues_notification_for_reviewers(
    db, author, reviewer, area, email_enabled
):
    policy = make_policy(db, author, area)
    draft = draft_of(policy)
    fill_and_submit(db, author, draft)
    email_enabled()

    queued = notification_service.enqueue_for_event(
        db, "version.submitted", {"version_id": draft.id}
    )
    db.commit()
    assert [n.recipient_id for n in queued] == [reviewer.id]
    subject, body = notification_service.render_message(db, queued[0])
    assert policy.code in subject
    assert draft.id in body


def test_queue_disabled_by_default(db, author, reviewer, area):
    policy = make_policy(db, author, area)
    draft = draft_of(policy)
    fill_and_submit(db, author, draft)
    assert notification_service.enqueue_for_event(
        db, "version.submitted", {"version_id": draft.id}
    ) == []


def test_process_queue_sends_and_marks(db, author, reviewer, area, email_enabled):
    policy = make_policy(db, author, area)
    draft = draft_of(policy)
    fill_and_submit(db, author, draft)
    email_enabled()
    notification_service.enqueue_for_event(db, "version.submitted", {"version_id": draft.id})
    db.commit()

    notifier = FakeNotifier()
    registry.register_plugin("notifier", notifier)
    try:
        sent = notification_service.process_queue(db)
        db.commit()
    finally:
        registry.unregister_plugin("notifier")

    assert sent == 1
    assert notifier.sent[0][0] == reviewer.email
    assert notification_service.pending(db) == []


def test_failed_send_stays_in_queue_for_retry(db, author, reviewer, area, email_enabled):
    policy = make_policy(db, author, area)
    draft = draft_of(policy)
    fill_and_submit(db, author, draft)
    email_enabled()
    notification_service.enqueue_for_event(db, "version.submitted", {"version_id": draft.id})
    db.commit()

    registry.register_plugin("notifier", FakeNotifier(fail=True))
    try:
        assert notification_service.process_queue(db) == 0
    finally:
        registry.unregister_plugin("notifier")
    assert len(notification_service.pending(db)) == 1  # retry posterior


def test_rejection_notifies_author(db, author, reviewer, approver, area, email_enabled):
    policy = make_policy(db, author, area)
    draft = draft_of(policy)
    fill_and_submit(db, author, draft)
    workflow_service.send_to_approval(db, reviewer, draft.id)
    workflow_service.reject(db, approver, draft.id, "revisar corte")
    db.commit()
    email_enabled()
    queued = notification_service.enqueue_for_event(
        db, "version.rejected", {"version_id": draft.id}
    )
    assert [n.recipient_id for n in queued] == [author.id]


# ── importador de legado ─────────────────────────────────────────────────────


def test_import_batch_creates_policies_with_attachments(db, author, area):
    results = import_service.import_batch(
        db, author,
        files=[
            ("politica-limite-pf.md", b"## Regras\n\nScore >= 600\n"),
            ("norma antiga.txt", b"Texto legado"),
        ],
        area_id=area.id,
        policy_type="limite",
    )
    db.commit()

    assert all(r.ok for r in results)
    from sqlalchemy import select

    from app.models import Attachment, Policy

    first = db.get(Policy, results[0].policy_id)
    assert first.title == "Politica limite pf"
    draft = first.versions[0]
    assert "Score >= 600" in draft.body_md  # .md vira corpo
    attachments = list(
        db.scalars(select(Attachment).where(Attachment.version_id == draft.id))
    )
    assert len(attachments) == 1  # original anexado com hash


def test_import_batch_partial_failure(db, author, area):
    results = import_service.import_batch(
        db, author,
        files=[
            ("ok.md", b"# Conteudo"),
            ("proibido.exe", b"MZ..."),  # extensão fora da lista
        ],
        area_id=area.id,
        policy_type="outro",
    )
    db.commit()
    by_name = {r.filename: r for r in results}
    assert by_name["ok.md"].ok
    assert not by_name["proibido.exe"].ok


# ── exportação PDF ───────────────────────────────────────────────────────────


def test_pdf_exporter_renders_valid_pdf():
    pdf = PdfExporter().render("POL-CRD-001 — Título", ["linha um", "linha (dois) é ção"])
    assert pdf.startswith(b"%PDF-1.4")
    assert pdf.rstrip().endswith(b"%%EOF")
    assert pdf.count(b"/Type /Page ") == 1
