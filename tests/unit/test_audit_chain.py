"""Hash chain da trilha de auditoria (v1): encadeamento e detecção de adulteração."""

from __future__ import annotations

from sqlalchemy import text

from app.services import audit_service


def test_records_are_chained(db, admin):
    first = audit_service.record(db, admin.id, "test.one", "policy", None, {"n": 1})
    second = audit_service.record(db, admin.id, "test.two", "policy", None, {"n": 2})
    db.commit()

    assert first.row_hash and second.row_hash
    assert second.prev_hash == first.row_hash


def test_verify_chain_ok(db, admin):
    for n in range(5):
        audit_service.record(db, admin.id, "test.event", "policy", None, {"n": n})
    db.commit()

    report = audit_service.verify_chain(db)
    assert report.ok
    assert report.chained >= 5
    assert report.broken == []


def test_tampering_breaks_chain(db, admin):
    audit_service.record(db, admin.id, "test.event", "policy", None, {"valor": "original"})
    db.commit()

    # simula adulteração direta no arquivo do banco (trigger removido pelo atacante)
    db.execute(text("DROP TRIGGER trg_audit_log_no_update"))
    db.execute(text("UPDATE audit_log SET payload = '{\"valor\": \"adulterado\"}'"))
    db.commit()

    report = audit_service.verify_chain(db)
    assert not report.ok
    assert any("row_hash" in v["error"] for v in report.broken)


def test_deleting_row_breaks_chain(db, admin):
    audit_service.record(db, admin.id, "test.a", "policy", None, None)
    middle = audit_service.record(db, admin.id, "test.b", "policy", None, None)
    audit_service.record(db, admin.id, "test.c", "policy", None, None)
    db.commit()

    db.execute(text("DROP TRIGGER trg_audit_log_no_delete"))
    db.execute(text("DELETE FROM audit_log WHERE id = :id"), {"id": middle.id})
    db.commit()

    report = audit_service.verify_chain(db)
    assert not report.ok
