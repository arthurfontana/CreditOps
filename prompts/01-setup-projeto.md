# Prompt 01 — Setup do projeto

> **Anexar ao contexto**: `docs/wiki/04-arquitetura.md`, `docs/wiki/10-estrutura-do-repositorio.md` e o "Prompt de contexto" do `prompts/README.md`.

---

Crie o esqueleto do projeto CreditOps exatamente com a estrutura de diretórios definida em `docs/wiki/10-estrutura-do-repositorio.md`. Nesta etapa, entregue:

1. **Arquivos de projeto**
   - `pyproject.toml` com: nome `creditops`, Python >= 3.11, dependências (`fastapi`, `uvicorn[standard]`, `sqlalchemy>=2`, `alembic`, `jinja2`, `python-multipart`, `argon2-cffi`, `itsdangerous`, `pydantic-settings`, `httpx`) e dev (`pytest`, `pytest-cov`, `ruff`). Configure ruff (line-length 100) e pytest (`tests/`).
   - `requirements.txt` e `requirements-dev.txt` pinados.
   - `.gitignore` cobrindo `data/`, `logs/`, `.env`, `__pycache__/`, `.venv/`.
   - `.env.example` com variáveis documentadas: `CREDITOPS_SECRET_KEY`, `CREDITOPS_DB_PATH`, `CREDITOPS_DATA_DIR`.

2. **Aplicação mínima**
   - `app/config.py`: settings com Pydantic Settings, lendo `config/settings.toml` se existir + env vars com prefixo `CREDITOPS_`.
   - `app/db.py`: engine SQLAlchemy para SQLite com PRAGMAs `journal_mode=WAL`, `foreign_keys=ON`, `busy_timeout=5000` aplicados por event listener; `SessionLocal`; dependency `get_db` para FastAPI.
   - `app/main.py`: instancia FastAPI, monta `app/web/static/`, registra rota `GET /health` retornando `{"status": "ok", "version": "0.1.0"}`.
   - `app/web/templates/base.html`: layout base com bloco de conteúdo, CSS próprio simples em `app/web/static/css/app.css` (sem frameworks externos) e `htmx.min.js` vendorizado em `app/web/static/js/` (crie o arquivo com comentário indicando para baixar a versão 1.9.x oficial e colocar ali).
   - Diretórios vazios com `.gitkeep`: `data/attachments/`, `data/exports/`, `logs/`, `app/plugins/ai/providers/`, `migrations/versions/`, `examples/policies/`.

3. **Alembic**
   - `alembic.ini` + `migrations/env.py` configurados para usar a URL do `app/config.py` e o metadata de `app/models` (crie `app/models/__init__.py` vazio por enquanto).

4. **Testes e CI**
   - `tests/conftest.py`: fixture de app de teste com banco SQLite em memória.
   - `tests/unit/test_health.py`: testa `GET /health`.
   - `.github/workflows/ci.yml`: em push/PR roda `ruff check` e `pytest`.

**Critérios de aceite** (verifique antes de terminar):
- `uvicorn app.main:app` sobe sem erro e `/health` responde.
- `alembic upgrade head` roda sem erro (mesmo sem migrações ainda).
- `pytest` passa; `ruff check .` sem erros.

Entregue todos os arquivos completos, sem placeholders.
