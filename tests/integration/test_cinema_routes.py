"""Rotas web do editor rico, biblioteca de cineminhas e export da demanda."""

from __future__ import annotations

import json

from app.services import change_request_service, cinema_service
from tests.conftest import login_as


def _make_library(db, author):
    var_g = cinema_service.create_variable(db, author, name="GRUPO", label="Grupo", domain="G7")
    var_s = cinema_service.create_variable(
        db, author, name="SCORE", label="Score", domain="R01, R02"
    )
    cinema = cinema_service.create_cinema(
        db, author, name="Cortes G7", cinema_type="offer",
        row_variable_id=var_g.id, col_variable_id=var_s.id,
    )
    cinema_service.create_manual_version(db, author, cinema.id, cells={"G7|R01": 8})
    db.commit()
    return cinema


def _make_demand(db, author, area):
    cr = change_request_service.create(
        db, author, title="Ajuste Digital", area_id=area.id,
        description_html="<p>Ajuste dos <strong>cortes</strong>.</p>",
    )
    db.commit()
    return cr


def _csrf(client, path="/change-requests"):
    page = client.get(path)
    import re

    m = re.search(r'name="csrf_token" value="([^"]+)"', page.text)
    return m.group(1) if m else ""


def test_biblioteca_e_detalhe(client, db, author, area):
    cinema = _make_library(db, author)
    login_as(client, author)
    resp = client.get("/cinemas")
    assert resp.status_code == 200
    assert "Cortes G7" in resp.text
    resp = client.get(f"/cinemas/{cinema.id}")
    assert resp.status_code == 200
    assert "Trilha de versões" in resp.text
    assert "cinema-matrix" in resp.text


def test_catalogo_de_variaveis(client, db, author):
    login_as(client, author)
    token = _csrf(client, "/variables")
    resp = client.post(
        "/variables",
        data={
            "csrf_token": token,
            "name": "faixa_score",
            "label": "Faixa de Score",
            "domain": "R01, R02, R99",
            "is_ordinal": "1",
        },
    )
    assert resp.status_code == 303
    page = client.get("/variables")
    assert "FAIXA_SCORE" in page.text
    assert "R99" in page.text


def test_demanda_detalhe_com_editor_e_matriz(client, db, author, area):
    cinema = _make_library(db, author)
    cr = _make_demand(db, author, area)
    instance = cinema_service.add_instance(db, author, cr.id, cinema.id)
    db.commit()
    login_as(client, author)

    page = client.get(f"/change-requests/{cr.id}")
    assert page.status_code == 200
    assert "cinema-matrix" in page.text
    assert "Registro de alterações" in page.text
    assert "Exportar Word" in page.text

    editor = client.get(f"/cinema-instances/{instance.id}")
    assert editor.status_code == 200
    assert "grid-config" in editor.text


def test_editar_demanda_e_salvar_caselas(client, db, author, area):
    cinema = _make_library(db, author)
    cr = _make_demand(db, author, area)
    instance = cinema_service.add_instance(db, author, cr.id, cinema.id)
    db.commit()
    login_as(client, author)
    token = _csrf(client)

    resp = client.post(
        f"/change-requests/{cr.id}/edit",
        data={
            "csrf_token": token,
            "title": "Ajuste Digital v2",
            "description_html": "<h2>Objetivo</h2><p>Novos cortes.</p>",
            "priority": "high",
        },
    )
    assert resp.status_code == 303
    db.expire_all()
    updated = change_request_service.get(db, cr.id)
    assert updated.title == "Ajuste Digital v2"
    assert "<h2>Objetivo</h2>" in updated.description_html

    resp = client.post(
        f"/cinema-instances/{instance.id}",
        data={
            "csrf_token": token,
            "cells_json": json.dumps({"G7|R01": 5, "G7|R02": 0}),
            "notes": "válido até 30/06",
        },
    )
    assert resp.status_code == 303
    db.expire_all()
    refreshed = cinema_service.get_instance(db, instance.id)
    assert json.loads(refreshed.cells_json) == {"G7|R01": 5, "G7|R02": 0}


def test_export_docx_e_print(client, db, author, area):
    cinema = _make_library(db, author)
    cr = _make_demand(db, author, area)
    cinema_service.add_instance(db, author, cr.id, cinema.id)
    db.commit()
    login_as(client, author)

    resp = client.get(f"/change-requests/{cr.id}/export.docx")
    assert resp.status_code == 200
    assert resp.content[:2] == b"PK"
    assert "wordprocessingml" in resp.headers["content-type"]

    resp = client.get(f"/change-requests/{cr.id}/print")
    assert resp.status_code == 200
    assert "Solicitação de Mudança em Políticas" in resp.text


def test_upload_anexo_na_demanda(client, db, author, area):
    cr = _make_demand(db, author, area)
    login_as(client, author)
    token = _csrf(client)
    resp = client.post(
        f"/change-requests/{cr.id}/attachments",
        data={"csrf_token": token},
        files={"file": ("dados.csv", b"a;b\n1;2\n", "text/csv")},
    )
    assert resp.status_code == 303
    page = client.get(f"/change-requests/{cr.id}")
    assert "dados.csv" in page.text
