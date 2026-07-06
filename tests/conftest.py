"""Fixtures compartilhadas.

O ambiente de teste é configurado ANTES de importar módulos da app:
banco SQLite em arquivo temporário (triggers e FTS5 não funcionam
igual em memória compartilhada), migrado uma vez via Alembic e copiado
por teste — cada teste roda em banco limpo e migrado.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="creditops-tests-"))
os.environ.setdefault("CREDITOPS_SECRET_KEY", "test-secret-key")
os.environ.setdefault("CREDITOPS_DB_PATH", str(_TMP / "test.db"))
os.environ.setdefault("CREDITOPS_DATA_DIR", str(_TMP / "data"))
os.environ.setdefault("CREDITOPS_COOKIE_SECURE", "false")

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config as AlembicConfig  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.auth.sessions import COOKIE_NAME, create_session_token  # noqa: E402
from app.db import SessionLocal, engine  # noqa: E402
from app.models import Area, Product, Role, Segment, User  # noqa: E402
from app.services import user_service  # noqa: E402

TEMPLATE_DB = _TMP / "template.db"
ACTIVE_DB = Path(os.environ["CREDITOPS_DB_PATH"])
BASE_DIR = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session", autouse=True)
def _migrated_template() -> None:
    """Roda as migrações Alembic uma vez, gerando o banco-template."""
    cfg = AlembicConfig(str(BASE_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BASE_DIR / "migrations"))
    cfg.cmd_opts = None
    os.environ["CREDITOPS_DB_URL"] = f"sqlite:///{TEMPLATE_DB}"
    command.upgrade(cfg, "head")
    del os.environ["CREDITOPS_DB_URL"]


@pytest.fixture()
def db(_migrated_template) -> Session:
    """Banco limpo e migrado por teste (cópia do template)."""
    engine.dispose()
    for suffix in ("", "-wal", "-shm"):
        p = Path(str(ACTIVE_DB) + suffix)
        if p.exists():
            p.unlink()
    shutil.copy(TEMPLATE_DB, ACTIVE_DB)
    session = SessionLocal()
    yield session
    session.rollback()
    session.close()
    engine.dispose()


def _make_user(db: Session, role: Role, name: str) -> User:
    user = user_service.create_user(
        db,
        None,
        username=name,
        email=f"{name}@example.com",
        display_name=name.capitalize(),
        role=role.value,
        password="senha-forte-123",
        must_change_password=False,
    )
    db.commit()
    return user


@pytest.fixture()
def admin(db) -> User:
    return _make_user(db, Role.ADMIN, "admin")


@pytest.fixture()
def author(db) -> User:
    return _make_user(db, Role.AUTHOR, "autor")


@pytest.fixture()
def author2(db) -> User:
    return _make_user(db, Role.AUTHOR, "autor2")


@pytest.fixture()
def reviewer(db) -> User:
    return _make_user(db, Role.REVIEWER, "revisor")


@pytest.fixture()
def approver(db) -> User:
    return _make_user(db, Role.APPROVER, "aprovador")


@pytest.fixture()
def reader(db) -> User:
    return _make_user(db, Role.READER, "leitor")


@pytest.fixture()
def area(db) -> Area:
    area = Area(name="Crédito", code="CRD")
    db.add(area)
    db.commit()
    return area


@pytest.fixture()
def product(db) -> Product:
    product = Product(name="Cartão", code="CARD")
    db.add(product)
    db.commit()
    return product


@pytest.fixture()
def segment(db) -> Segment:
    segment = Segment(name="Pessoa Física", code="PF")
    db.add(segment)
    db.commit()
    return segment


@pytest.fixture()
def client(db) -> TestClient:
    from app.main import app

    return TestClient(app, follow_redirects=False)


def login_as(client: TestClient, user: User) -> None:
    client.cookies.set(COOKIE_NAME, create_session_token(user.id))
