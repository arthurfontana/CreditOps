"""Cineminha: catálogo de variáveis, biblioteca, instâncias e retroalimentação."""

from __future__ import annotations

from datetime import date

import pytest

from app.models import ChangeRequestStatus, CinemaInstanceStatus
from app.services import change_request_service, cinema_service
from app.services.errors import PermissionDenied, ValidationFailed
from tests.helpers import approve_and_publish, draft_of, make_policy


@pytest.fixture()
def score_var(db, author):
    var = cinema_service.create_variable(
        db, author, name="faixa_score", label="Faixa de Score",
        domain="R01, R02, R03, R99", is_ordinal=True,
    )
    db.commit()
    return var


@pytest.fixture()
def grupo_var(db, author):
    var = cinema_service.create_variable(
        db, author, name="GRUPO", label="Grupo", domain=["G1", "G7"], is_ordinal=False,
    )
    db.commit()
    return var


@pytest.fixture()
def cinema(db, author, score_var, grupo_var):
    c = cinema_service.create_cinema(
        db, author, name="Cortes Digital G7", cinema_type="offer",
        row_variable_id=grupo_var.id, col_variable_id=score_var.id,
    )
    db.commit()
    return c


@pytest.fixture()
def demanda(db, author, area):
    cr = change_request_service.create(
        db, author, title="Ajuste cineminha Digital", area_id=area.id,
        description_html="<p>Ajustar cortes do <strong>G7</strong>.</p>",
    )
    db.commit()
    return cr


# ── Catálogo de variáveis ────────────────────────────────────────────────────


def test_variavel_normaliza_nome_e_dominio(db, score_var):
    assert score_var.name == "FAIXA_SCORE"
    assert cinema_service.variable_domain(score_var) == ["R01", "R02", "R03", "R99"]


def test_variavel_dominio_vazio_ou_com_separador_falha(db, author):
    with pytest.raises(ValidationFailed):
        cinema_service.create_variable(db, author, name="X", label="X", domain="")
    with pytest.raises(ValidationFailed):
        cinema_service.create_variable(db, author, name="Y", label="Y", domain="a|b, c")


def test_variavel_duplicada_falha(db, author, score_var):
    with pytest.raises(ValidationFailed):
        cinema_service.create_variable(
            db, author, name="faixa_score", label="dup", domain="R01"
        )


def test_leitor_nao_cria_variavel(db, reader):
    with pytest.raises(PermissionDenied):
        cinema_service.create_variable(db, reader, name="V", label="V", domain="a")


# ── Biblioteca ───────────────────────────────────────────────────────────────


def test_cinema_tipo_invalido_falha(db, author, score_var, grupo_var):
    with pytest.raises(ValidationFailed):
        cinema_service.create_cinema(
            db, author, name="X", cinema_type="banana",
            row_variable_id=grupo_var.id, col_variable_id=score_var.id,
        )


def test_carga_manual_vira_versao_vigente(db, author, cinema):
    version = cinema_service.create_manual_version(
        db, author, cinema.id, cells={"G7|R01": 8, "G7|R99": 0},
    )
    db.commit()
    assert version.version_number == 1
    assert cinema.current_version_id == version.id
    assert version.origin == "manual"


def test_carga_manual_valida_dominio_e_valores(db, author, cinema):
    with pytest.raises(ValidationFailed):
        cinema_service.create_manual_version(db, author, cinema.id, cells={"G9|R01": 8})
    with pytest.raises(ValidationFailed):
        cinema_service.create_manual_version(db, author, cinema.id, cells={"G7|R01": -2})
    with pytest.raises(ValidationFailed):
        cinema_service.create_manual_version(db, author, cinema.id, cells={"G7|R01": "abc"})


def test_elegibilidade_so_aceita_0_ou_1(db, author, score_var, grupo_var):
    c = cinema_service.create_cinema(
        db, author, name="Elegibilidade PF", cinema_type="eligibility",
        row_variable_id=grupo_var.id, col_variable_id=score_var.id,
    )
    with pytest.raises(ValidationFailed):
        cinema_service.create_manual_version(db, author, c.id, cells={"G1|R01": 5})
    version = cinema_service.create_manual_version(db, author, c.id, cells={"G1|R01": 0})
    assert version.cells_json == '{"G1|R01": 0}'


# ── matrix_view / defaults ───────────────────────────────────────────────────


def test_matrix_view_defaults_e_diff():
    view = cinema_service.matrix_view(
        cinema_type="offer",
        row_domain_json='["G1", "G7"]',
        col_domain_json='["R01", "R02"]',
        cells_json='{"G7|R01": 8}',
        baseline_cells_json='{"G7|R01": 5, "G1|R02": 3}',
    )
    # default de oferta é 0; diff marca G7|R01 (5→8) e G1|R02 (3→0)
    assert view["grid"][1][0] == 8
    assert view["grid"][0][0] == 0
    assert view["changed_count"] == 2
    assert view["max_value"] == 8


def test_matrix_view_eligibility_default_elegivel():
    view = cinema_service.matrix_view(
        cinema_type="eligibility",
        row_domain_json='["G1"]',
        col_domain_json='["R01", "R02"]',
        cells_json='{"G1|R02": 0}',
    )
    assert view["grid"][0] == [1, 0]
    assert view["changed_count"] == 0  # sem baseline, nada marcado


# ── Instâncias na demanda ────────────────────────────────────────────────────


def test_puxar_da_biblioteca_congela_origem(db, author, cinema, demanda):
    cinema_service.create_manual_version(db, author, cinema.id, cells={"G7|R01": 8})
    db.commit()
    instance = cinema_service.add_instance(db, author, demanda.id, cinema.id)
    db.commit()
    assert instance.source_version_id == cinema.current_version_id
    assert '"G7|R01": 8' in instance.cells_json
    # editar a instância não toca a biblioteca
    cinema_service.update_instance_cells(db, author, instance.id, {"G7|R01": 3})
    db.commit()
    assert '"G7|R01": 8' in cinema.current_version.cells_json
    assert len(cinema_service.diff_cells(instance)) == 1


def test_biblioteca_sem_versao_gera_matriz_default(db, author, cinema, demanda):
    instance = cinema_service.add_instance(db, author, demanda.id, cinema.id)
    assert instance.source_version_id is None
    view = cinema_service.instance_view(instance)
    assert view["row_domain"] == ["G1", "G7"]
    assert view["col_domain"] == ["R01", "R02", "R03", "R99"]


def test_instancia_celula_fora_do_dominio_falha(db, author, cinema, demanda):
    instance = cinema_service.add_instance(db, author, demanda.id, cinema.id)
    with pytest.raises(ValidationFailed):
        cinema_service.update_instance_cells(db, author, instance.id, {"G7|R42": 1})


def test_leitor_que_nao_e_solicitante_nao_edita(db, author, reader, cinema, demanda):
    instance = cinema_service.add_instance(db, author, demanda.id, cinema.id)
    db.commit()
    with pytest.raises(PermissionDenied):
        cinema_service.update_instance_cells(db, reader, instance.id, {"G7|R01": 1})


def test_demanda_encerrada_nao_recebe_cineminha(db, author, approver, cinema, demanda):
    change_request_service.reject(db, approver, demanda.id, "fora de escopo")
    db.commit()
    with pytest.raises(ValidationFailed):
        cinema_service.add_instance(db, author, demanda.id, cinema.id)


def test_remover_instancia(db, author, cinema, demanda):
    instance = cinema_service.add_instance(db, author, demanda.id, cinema.id)
    db.commit()
    cinema_service.remove_instance(db, author, instance.id)
    db.commit()
    assert cinema_service.list_instances(db, demanda.id) == []


# ── Base defasada e re-base ──────────────────────────────────────────────────


def test_stale_e_rebase_preserva_edicoes(db, author, cinema, demanda):
    cinema_service.create_manual_version(
        db, author, cinema.id, cells={"G7|R01": 8, "G7|R02": 5}
    )
    db.commit()
    instance = cinema_service.add_instance(db, author, demanda.id, cinema.id)
    cinema_service.update_instance_cells(db, author, instance.id, {"G7|R01": 3, "G7|R02": 5})
    db.commit()
    assert not cinema_service.is_stale(instance)

    # biblioteca avança (outra carga) → instância fica defasada
    cinema_service.create_manual_version(
        db, author, cinema.id, cells={"G7|R01": 8, "G7|R02": 5, "G7|R99": 2}
    )
    db.commit()
    assert cinema_service.is_stale(instance)

    cinema_service.rebase_instance(db, author, instance.id)
    db.commit()
    assert not cinema_service.is_stale(instance)
    view = cinema_service.instance_view(instance)
    cells = view["cells"]
    assert cells["G7|R01"] == 3  # edição preservada
    assert cells["G7|R99"] == 2  # novidade da biblioteca incorporada


def test_rebase_sem_defasagem_falha(db, author, cinema, demanda):
    cinema_service.create_manual_version(db, author, cinema.id, cells={"G7|R01": 8})
    db.commit()
    instance = cinema_service.add_instance(db, author, demanda.id, cinema.id)
    with pytest.raises(ValidationFailed):
        cinema_service.rebase_instance(db, author, instance.id)


# ── Retroalimentação pela vigência (F3) ──────────────────────────────────────


def test_vigencia_promove_instancia_para_biblioteca(
    db, author, reviewer, approver, area, cinema, demanda
):
    cinema_service.create_manual_version(db, author, cinema.id, cells={"G7|R01": 8})
    db.commit()
    instance = cinema_service.add_instance(db, author, demanda.id, cinema.id)
    cinema_service.update_instance_cells(db, author, instance.id, {"G7|R01": 3})
    db.commit()

    policy = make_policy(db, author, area)
    version = draft_of(policy)
    change_request_service.link_version(db, author, version.id, demanda.id)
    db.commit()
    approve_and_publish(db, author, reviewer, approver, version, date.today())

    db.refresh(instance)
    db.refresh(demanda)
    db.refresh(cinema)
    assert demanda.status == ChangeRequestStatus.DONE
    assert instance.status == CinemaInstanceStatus.PROMOTED
    assert instance.promoted_version_id == cinema.current_version_id
    current = cinema.current_version
    assert current.version_number == 2
    assert current.origin == "promotion"
    assert current.change_request_id == demanda.id
    assert '"G7|R01": 3' in current.cells_json
    # instância promovida vira imutável
    with pytest.raises(ValidationFailed):
        cinema_service.update_instance_cells(db, author, instance.id, {"G7|R01": 1})


def test_promocao_ignora_instancias_ja_promovidas(db, author, cinema, demanda):
    instance = cinema_service.add_instance(db, author, demanda.id, cinema.id)
    db.commit()
    n1 = cinema_service.promote_for_change_request(db, demanda.id, None)
    db.commit()
    assert n1 == 1
    n2 = cinema_service.promote_for_change_request(db, demanda.id, None)
    assert n2 == 0
    db.refresh(instance)
    assert instance.status == CinemaInstanceStatus.PROMOTED
