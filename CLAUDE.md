# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

CreditOps is a credit-policy governance platform: a policy catalog with immutable versioning, a formal approval workflow, effective-date publication, and an append-only audit trail. It is built to run in a locked-down corporate environment: one Python process, one SQLite file, server-side rendering, no mandatory SaaS or AI. All code comments, docstrings, UI text, docs, and commit history are in **Portuguese (pt-BR)** — keep new code and user-facing text consistent with that.

## Commands

```bash
# Setup
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env                 # set CREDITOPS_SECRET_KEY
alembic upgrade head                 # creates SQLite DB + triggers + FTS5
python -m app.cli create-admin --email admin@empresa.com --name "Admin"

# Run
uvicorn app.main:app --host 0.0.0.0 --port 8000
python scripts/seed_demo.py          # demo data (all passwords: demo1234)

# Tests and lint (CI runs exactly these; coverage gate is on app.services >= 80%)
pytest
pytest tests/unit/test_workflow.py               # single file
pytest tests/unit/test_workflow.py::test_name    # single test
pytest --cov=app.services --cov-report=term-missing --cov-fail-under=80
ruff check .

# CLI (argparse, via python -m app.cli): create-admin, reindex-all,
# apply-effectiveness, create-token, list-tokens, revoke-token
# Ops scripts: scripts/backup.py, restore.py, verify_audit.py, verify_data.py
```

## Architecture

Layered, with a strict dependency rule: **`app/services/` must never import from `app/web/`, `app/api/`, or `app/plugins/`** — dependencies always point inward to the core. Plugins integrate by subscribing to domain events, never the other way around.

- `app/services/` — the core: pure business rules, plain functions taking a `Session` as first argument, no HTTP concerns. Raise typed errors from `app/services/errors.py` (`NotFound`, `PermissionDenied`, `ValidationFailed`, `InvalidTransition`); `app/main.py` maps them to HTTP responses globally.
- `app/web/` — HTML routes (Jinja2 + HTMX, server-rendered; ADR-002). Routes handle auth/CSRF/rendering and delegate all logic to services.
- `app/api/v1.py` — read-only JSON API, authenticated with Bearer service tokens (`app/api/deps.py`); mounted only when `api_enabled` is set.
- `app/models/` — SQLAlchemy models, one file per aggregate (policy, workflow, collaboration, org, change, platform, audit). Enums in `app/models/enums.py`.
- `app/plugins/` — optional extensions (SMTP notifier, PDF export, LDAP SSO, webhooks, AI providers). Loaded by `app/plugins/registry.py` based on settings; the core looks plugins up via `registry.get_plugin` and never imports them directly. Plugin failure is logged and never propagates.
- `app/auth/` — session cookies (itsdangerous), argon2 passwords, RBAC dependencies. Roles: admin, author, reviewer, approver, reader.

### Domain events (`app/services/events.py`)

In-memory pub/sub bound to the SQLAlchemy session: `emit(db, name, payload)` queues events in `session.info`, and handlers run **only after commit** (rollback discards them). `app/subscribers.py` registers core subscribers; plugins register theirs at load. Handler exceptions are logged and never propagate. When adding side effects (notifications, webhooks, AI, audit reactions), emit an event rather than calling the plugin.

### Database

SQLite with WAL, `foreign_keys=ON`, and `busy_timeout` set per connection (`app/db.py`). Schema changes go **only through Alembic migrations** (`migrations/versions/`), never by hand. `app/schema_guards.py` defines the SQL triggers and the FTS5 table; it is the single source used by both migrations and test fixtures.

### Invariants (enforce in service layer AND database)

These are guaranteed by construction — do not weaken them:

- A version outside `draft` is immutable and undeletable (service checks + DB triggers).
- `audit_log`, `approval`, and `status_transition` are append-only (triggers); audit uses a hash chain (`scripts/verify_audit.py`).
- At most one `effective` version per policy (partial unique index).
- An author never approves their own version (segregation of duties).
- Status transitions only through the state-machine whitelist in `workflow_service.py` (draft → in_review → in_approval → approved → published → effective → superseded; rejection returns to draft as a recorded decision).
- Effectiveness is never retroactive; "what was valid on date X" is answered by time-travel queries over publications.

## Configuration

Pydantic Settings with precedence: env vars (`CREDITOPS_` prefix) > `config/settings.toml` > defaults (`app/config.py`). Secrets (SMTP/LDAP passwords, AI API keys, webhook HMAC secret) live **only** in env vars — never in settings.toml, the DB, or the repo. `.env.example` documents them.

## Testing

`tests/conftest.py` sets `CREDITOPS_*` env vars **before importing any app module**, migrates a file-backed template DB once via Alembic, and copies it per test — so every test gets a clean DB with real triggers and FTS5 (in-memory SQLite would not exercise them). Use the provided fixtures: `db`, per-role users (`admin`, `author`, `reviewer`, `approver`, `reader`), `area`/`product`/`segment`, `client` (TestClient), and `helpers.py` / `login_as` for authenticated requests. Layout: `tests/unit/` (services), `tests/integration/` (routes), `tests/e2e/test_invariants.py` (full lifecycle scenarios).

## Conventions

- Ruff: line length 100, target py311, rules `E, F, W, I, UP, B` (B008 ignored for FastAPI `Depends`).
- `data/` and `logs/` are runtime-only and gitignored.
- Architectural decisions that are expensive to reverse get an ADR in `docs/adr/`; product/design docs live in `docs/wiki/` and operations in `docs/runbook.md`.
- `prompts/` has two audiences: the root files are build-time implementation prompts; `prompts/runtime/` contains the prompts the AI module uses in production.
- AI output (diff summaries, tag suggestions, drafts, RAG answers) is always a suggestion that a human confirms, and is audited — the core must work with `ai_provider = "none"`.
