"""Diff, busca FTS5, exportação, anexos, comentários e eventos."""

import json
import zipfile

import pytest

from app.services import (
    attachment_service,
    comment_service,
    diff_service,
    events,
    export_service,
    search_service,
    version_service,
)
from app.services.errors import PermissionDenied, ValidationFailed
from tests.helpers import approve_and_publish, draft_of, make_policy

# ── diff ─────────────────────────────────────────────────────────────────────


def test_unified_diff_known_case(db, author, area):
    policy = make_policy(db, author, area)
    v1 = draft_of(policy)
    version_service.update_draft(db, author, v1.id, body_md="linha 1\nlinha 2\nlinha 3")

    class V:  # objeto mínimo compatível
        version_number = 99
        body_md = "linha 1\nlinha ALTERADA\nlinha 3\nlinha 4"

    result = diff_service.unified(v1, V())
    assert "-linha 2" in result
    assert "+linha ALTERADA" in result
    assert "+linha 4" in result


def test_side_by_side_marks_kinds(db, author, area):
    policy = make_policy(db, author, area)
    v1 = draft_of(policy)
    version_service.update_draft(db, author, v1.id, body_md="a\nb\nc")

    class V:
        version_number = 99
        body_md = "a\nX\nc\nd"

    rows = diff_service.side_by_side(v1, V())
    kinds = [r.kind for r in rows]
    assert "equal" in kinds
    assert "changed" in kinds
    assert "added" in kinds
    stats = diff_service.stats(v1, V())
    assert stats == {"added": 2, "removed": 1}


# ── busca ────────────────────────────────────────────────────────────────────


def test_search_finds_effective_policy(db, author, reviewer, approver, area):
    policy = make_policy(db, author, area, "Política de Concessão PJ")
    version = draft_of(policy)
    version_service.update_draft(
        db, author, version.id, body_md="Score mínimo de 650 para concessão"
    )
    approve_and_publish(db, author, reviewer, approver, version)
    search_service.reindex_policy(db, policy.id)
    db.commit()

    hits = search_service.search(db, "concessão", author)
    assert len(hits) == 1
    assert hits[0].code == policy.code
    # sem diacríticos também encontra (remove_diacritics 2)
    assert len(search_service.search(db, "concessao", author)) == 1
    # busca no corpo
    assert len(search_service.search(db, "score 650", author)) == 1


def test_draft_not_in_search(db, author, reader, area):
    policy = make_policy(db, author, area, "Rascunho Secreto de Limite")
    search_service.reindex_policy(db, policy.id)
    db.commit()
    assert search_service.search(db, "secreto", reader) == []


def test_archived_removed_from_index(db, author, reviewer, approver, area):
    from app.services import policy_service

    policy = make_policy(db, author, area, "Para Arquivar")
    approve_and_publish(db, author, reviewer, approver, draft_of(policy))
    search_service.reindex_policy(db, policy.id)
    db.commit()
    assert len(search_service.search(db, "arquivar", author)) == 1
    policy_service.archive_policy(db, approver, policy.id, "fim de linha")
    search_service.reindex_policy(db, policy.id)
    db.commit()
    assert search_service.search(db, "arquivar", author) == []


# ── exportação ───────────────────────────────────────────────────────────────


def test_export_md_has_front_matter(db, author, reviewer, approver, area):
    policy = make_policy(db, author, area)
    version = draft_of(policy)
    approve_and_publish(db, author, reviewer, approver, version)
    content = export_service.export_version_md(db, version)
    assert content.startswith("---")
    assert f"codigo: {policy.code}" in content
    assert "vigente_de:" in content
    assert "aprovacao: approved" in content


def test_export_json_complete(db, author, reviewer, approver, area):
    policy = make_policy(db, author, area)
    approve_and_publish(db, author, reviewer, approver, draft_of(policy))
    data = export_service.export_policy_json(db, policy)
    assert data["code"] == policy.code
    assert data["current_version"] == 1
    v = data["versions"][0]
    assert v["approvals"][0]["decision"] == "approved"
    assert v["publication"]["effective_from"]
    assert any(t["to"] == "effective" for t in v["transitions"])


def test_dossier_zip_contains_everything(db, author, reviewer, approver, area):
    policy = make_policy(db, author, area)
    v1 = draft_of(policy)
    approve_and_publish(db, author, reviewer, approver, v1)
    version_service.create_revision(db, author, policy.id)
    db.commit()
    path = export_service.export_dossier(db, approver, policy)
    db.commit()
    with zipfile.ZipFile(path) as zf:
        names = set(zf.namelist())
        assert "politica.md" in names
        assert "historico/v1.md" in names
        assert "historico/v2.md" in names
        assert "metadados.json" in names
        assert "trilha_auditoria.json" in names
        trail = json.loads(zf.read("trilha_auditoria.json"))
        assert any(e["action"] == "version.effective" for e in trail)


# ── anexos ───────────────────────────────────────────────────────────────────


def test_attachment_upload_download_hash(db, author, area):
    policy = make_policy(db, author, area)
    version = draft_of(policy)
    attachment = attachment_service.upload(
        db, author, version.id,
        filename="planilha.csv", content=b"col1,col2\n1,2\n",
    )
    assert len(attachment.sha256) == 64
    got, content = attachment_service.get_content(db, author, attachment.id)
    assert content == b"col1,col2\n1,2\n"
    assert got.filename == "planilha.csv"


def test_attachment_rejects_bad_extension_and_size(db, author, area, monkeypatch):
    policy = make_policy(db, author, area)
    version = draft_of(policy)
    with pytest.raises(ValidationFailed, match="extensão"):
        attachment_service.upload(
            db, author, version.id, filename="virus.exe", content=b"x"
        )
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "attachment_max_bytes", 10)
    with pytest.raises(ValidationFailed, match="tamanho"):
        attachment_service.upload(
            db, author, version.id, filename="grande.txt", content=b"x" * 11
        )


def test_attachment_only_in_draft(db, author, reviewer, approver, area):
    policy = make_policy(db, author, area)
    version = draft_of(policy)
    approve_and_publish(db, author, reviewer, approver, version)
    with pytest.raises(ValidationFailed, match="rascunho"):
        attachment_service.upload(
            db, author, version.id, filename="doc.txt", content=b"x"
        )


# ── comentários ──────────────────────────────────────────────────────────────


def test_comments_add_resolve_and_reader_denied(db, author, reviewer, reader, area):
    policy = make_policy(db, author, area)
    version = draft_of(policy)
    comment = comment_service.add(db, reviewer, version.id, "revisar seção X", anchor="Regras")
    assert comment.anchor == "Regras"
    with pytest.raises(PermissionDenied):
        comment_service.add(db, reader, version.id, "não posso")
    comment_service.resolve(db, author, comment.id)
    assert comment.resolved_at is not None


# ── eventos de domínio ──────────────────────────────────────────────────────


def test_events_fire_only_after_commit(db, author, area):
    received: list[dict] = []
    events.subscribe("test.event", received.append)
    try:
        events.emit(db, "test.event", {"n": 1})
        assert received == []  # antes do commit, nada
        db.commit()
        assert received == [{"n": 1}]
    finally:
        events._subscribers.pop("test.event", None)


def test_event_discarded_on_rollback(db):
    received: list[dict] = []
    events.subscribe("test.rollback", received.append)
    try:
        events.emit(db, "test.rollback", {"n": 1})
        db.rollback()
        db.commit()
        assert received == []
    finally:
        events._subscribers.pop("test.rollback", None)


def test_handler_error_does_not_propagate(db):
    def bad_handler(payload):
        raise RuntimeError("plugin quebrado")

    events.subscribe("test.bad", bad_handler)
    try:
        events.emit(db, "test.bad", {})
        db.commit()  # não deve levantar
    finally:
        events._subscribers.pop("test.bad", None)
