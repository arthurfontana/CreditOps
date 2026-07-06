"""Carga de demonstração: usuários, cadastros e políticas com histórico.

Uso:
    alembic upgrade head && python scripts/seed_demo.py

Cria (idempotência simples: aborta se já houver usuários):
- 3 áreas, 4 produtos, 3 segmentos, tags;
- 6 usuários (senha de todos: demo1234);
- 8 políticas realistas, incluindo: uma com 4 versões e rollback,
  uma aguardando aprovação e uma com vigência futura.
"""

from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from sqlalchemy import select  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.models import Area, Product, Segment, Tag, User  # noqa: E402
from app.services import (  # noqa: E402
    comment_service,
    policy_service,
    search_service,
    user_service,
    version_service,
    workflow_service,
)

EXAMPLES = BASE_DIR / "examples"
PASSWORD = "demo1234"


def example_body(name: str) -> str:
    path = EXAMPLES / "policies" / name
    return path.read_text(encoding="utf-8") if path.exists() else "## Regras\n(exemplo)"


def publish_flow(db, author, reviewer, approver, version, effective_from=None):
    version_service.update_submission_fields(
        db, author, version.id,
        change_summary="Revisão de parâmetros conforme comitê de crédito",
        expected_impact="Manutenção da inadimplência com ganho de conversão",
    )
    workflow_service.submit_for_review(db, author, version.id)
    workflow_service.send_to_approval(db, reviewer, version.id)
    workflow_service.approve(db, approver, version.id)
    workflow_service.publish(db, approver, version.id, effective_from or date.today())
    db.commit()


def main() -> int:
    db = SessionLocal()
    try:
        if db.scalars(select(User)).first() is not None:
            print("Banco já contém usuários — seed abortado (use um banco limpo).")
            return 1

        seed = json.loads((EXAMPLES / "seed.json").read_text(encoding="utf-8"))

        areas = {a["code"]: Area(**a) for a in seed["areas"]}
        products = {p["code"]: Product(**p) for p in seed["products"]}
        segments = {s["code"]: Segment(**s) for s in seed["segments"]}
        tags = {t: Tag(name=t) for t in seed["tags"]}
        for obj in (*areas.values(), *products.values(), *segments.values(), *tags.values()):
            db.add(obj)
        db.commit()

        users: dict[str, User] = {}
        for u in seed["users"]:
            users[u["username"]] = user_service.create_user(
                db, None,
                username=u["username"],
                email=f"{u['username']}@example.com",
                display_name=u["name"],
                role=u["role"],
                password=PASSWORD,
                is_auditor=u.get("is_auditor", False),
                must_change_password=False,
            )
        db.commit()
        ana, rafael, carlos = users["ana"], users["rafael"], users["carlos"]

        def new_policy(
            title, ptype, area_code, body, product_codes=(), segment_codes=(), tag_names=()
        ):
            policy = policy_service.create_policy(
                db, ana,
                title=title, policy_type=ptype,
                area_id=areas[area_code].id, owner_id=ana.id,
                product_ids=[products[c].id for c in product_codes],
                segment_ids=[segments[c].id for c in segment_codes],
                tag_ids=[tags[t].id for t in tag_names],
            )
            draft = policy.versions[0]
            version_service.update_draft(db, ana, draft.id, body_md=body)
            db.commit()
            return policy, draft

        # 1. Limite PF — 4 versões, com rollback (v4 restaura v2)
        p1, v1 = new_policy(
            "Política de Limite de Cartão PF", "limite", "CRD",
            example_body("limite-pf.md"), ("CARD",), ("PF",), ("limite", "bacen"),
        )
        publish_flow(db, ana, rafael, carlos, v1)
        v2 = version_service.create_revision(db, ana, p1.id)
        version_service.update_draft(db, ana, v2.id, body_md=v1.body_md.replace("620", "650"))
        publish_flow(db, ana, rafael, carlos, v2)
        v3 = version_service.create_revision(db, ana, p1.id)
        version_service.update_draft(db, ana, v3.id, body_md=v2.body_md.replace("650", "580"))
        publish_flow(db, ana, rafael, carlos, v3)
        v4 = workflow_service.rollback(
            db, carlos, p1.id, v2.id, "Score 580 elevou FPD30 em 0,8 p.p. no piloto"
        )
        workflow_service.approve(db, carlos, v4.id)
        workflow_service.publish(db, carlos, v4.id, date.today())
        db.commit()

        # 2. Concessão PJ — vigente, com comentário de revisão
        p2, c1 = new_policy(
            "Política de Concessão de Capital de Giro PJ", "concessao", "ATA",
            example_body("concessao-pj.md"), ("KGIRO",), ("PJ",), ("score",),
        )
        comment_service.add(
            db, rafael, c1.id,
            "Validar teto do comitê regional com a diretoria", anchor="Alçadas",
        )
        db.commit()
        publish_flow(db, ana, rafael, carlos, c1)

        # 3. Renegociação varejo — vigente
        p3, r1 = new_policy(
            "Política de Renegociação Varejo", "renegociacao", "COB",
            example_body("renegociacao-varejo.md"), ("CARD", "CDC"), ("PF",), ("renegociacao",),
        )
        publish_flow(db, ana, rafael, carlos, r1)

        # 4. Aguardando aprovação (fila do Carlos)
        p4, a1 = new_policy(
            "Política de Alçadas de Crédito Varejo", "alcada", "CRD",
            "## Objetivo\nDefinir alçadas de decisão do varejo.\n\n## Regras\n"
            "| Valor | Alçada |\n|---|---|\n| Até R$ 50 mil | Gerente |\n| Acima | Comitê |",
            ("CARD", "CDC"), ("PF", "MEI"), ("alcada",),
        )
        version_service.update_submission_fields(
            db, ana, a1.id,
            change_summary="Primeira formalização das alçadas do varejo",
            expected_impact="Padronização das decisões da mesa",
        )
        workflow_service.submit_for_review(db, ana, a1.id)
        workflow_service.send_to_approval(db, rafael, a1.id)
        db.commit()

        # 5. Publicada com vigência futura (30 dias)
        p5, f1 = new_policy(
            "Política de Score Mínimo Consignado", "score", "CRD",
            "## Objetivo\nScore mínimo do consignado.\n\n## Regras\nScore mínimo: 600.",
            ("CONS",), ("PF",), ("score",),
        )
        version_service.update_submission_fields(
            db, ana, f1.id,
            change_summary="Novo corte de score para consignado",
            expected_impact="Redução de perda esperada em 0,2 p.p.",
        )
        workflow_service.submit_for_review(db, ana, f1.id)
        workflow_service.send_to_approval(db, rafael, f1.id)
        workflow_service.approve(db, carlos, f1.id)
        workflow_service.publish(db, carlos, f1.id, date.today() + timedelta(days=30))
        db.commit()

        # 6-8. Demais políticas em estágios variados
        p6, d6 = new_policy(
            "Política de Cobrança Preventiva", "cobranca", "COB",
            "## Objetivo\nRégua de cobrança preventiva.\n\n"
            "## Regras\nContato em D-3 do vencimento.",
            ("CARD",), ("PF",), (),
        )
        publish_flow(db, ana, rafael, carlos, d6)

        p7, d7 = new_policy(
            "Política de Limite MEI", "limite", "CRD",
            "## Objetivo\nLimites para MEI.\n\n## Regras\nLimite máximo inicial: R$ 5.000.",
            ("CARD",), ("MEI",), ("limite",),
        )
        version_service.update_submission_fields(
            db, ana, d7.id,
            change_summary="Primeira versão da política MEI",
            expected_impact="Abertura controlada do segmento",
        )
        workflow_service.submit_for_review(db, ana, d7.id)
        db.commit()  # fila do revisor

        new_policy(
            "Política de Score Comportamental", "score", "CRD",
            "## Objetivo\n(rascunho em elaboração)\n\n## Regras\nA definir.",
            (), ("PF",), ("score",),
        )  # rascunho puro — fila da autora

        search_service.reindex_all(db)
        db.commit()

        print("Seed concluído. Usuários (senha demo1234):")
        for u in seed["users"]:
            print(f"  {u['username']:8s} {u['role']:9s} {u['name']}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
