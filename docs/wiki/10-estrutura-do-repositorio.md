# 10. Estrutura de Diretórios do Repositório

Estrutura pensada para desenvolvimento incremental: o MVP usa um subconjunto; as pastas de plugins/integrações já existem como pontos de extensão vazios.

```
creditops/
├── README.md                     # visão geral, quickstart, links para a wiki
├── LICENSE
├── pyproject.toml                # metadados do projeto, deps, ferramentas (ruff, pytest)
├── requirements.txt              # deps pinadas (gerado; usado em instalação offline)
├── requirements-dev.txt
├── .env.example                  # variáveis de ambiente documentadas (nunca commitar .env)
├── .gitignore                    # ignora data/, logs/, .env, __pycache__ ...
│
├── app/                          # ═══ BACKEND (código-fonte) ═══
│   ├── main.py                   # cria FastAPI, monta routers, inicializa plugins
│   ├── cli.py                    # comandos: create-admin, import-legacy, verify-audit
│   ├── config.py                 # carrega settings.toml + env vars (Pydantic Settings)
│   ├── db.py                     # engine SQLAlchemy, sessão, PRAGMAs SQLite (WAL, FK)
│   │
│   ├── models/                   # entidades SQLAlchemy (1 arquivo por agregado)
│   │   ├── policy.py             # Policy, PolicyVersion, Tag, vínculos N:M
│   │   ├── workflow.py           # Approval, Publication, StatusTransition, Release
│   │   ├── collaboration.py      # Comment, Attachment, ImpactRecord
│   │   ├── org.py                # User, Area, Product, Segment
│   │   └── audit.py              # AuditLog, Setting, Notification
│   │
│   ├── services/                 # ═ CORE: regras de negócio puras (sem HTTP) ═
│   │   ├── policy_service.py
│   │   ├── version_service.py    # criação/snapshot/imutabilidade
│   │   ├── workflow_service.py   # máquina de estados, transições, segregação
│   │   ├── diff_service.py       # difflib: unified + side-by-side + campos
│   │   ├── audit_service.py      # append-only + hash chain
│   │   ├── search_service.py     # FTS5
│   │   ├── export_service.py     # Markdown/JSON/dossiê
│   │   └── events.py             # eventos de domínio (pub/sub interno)
│   │
│   ├── web/                      # rotas HTML (Jinja2 + HTMX)
│   │   ├── routes/               # policies.py, versions.py, workflow.py, admin.py, auth.py
│   │   ├── templates/            # base.html, policy/, version/, admin/, auth/
│   │   └── static/               # css/app.css, js/htmx.min.js (vendorizado), img/
│   │
│   ├── api/                      # rotas JSON (v2) — API de consumo somente leitura
│   │   └── v1/
│   │
│   ├── auth/                     # sessões, hash de senha, dependências de RBAC
│   │
│   └── plugins/                  # ═ OPCIONAL: pontos de extensão ═
│       ├── base.py               # interfaces (NotifierPlugin, AuthPlugin, AIProvider)
│       ├── registry.py           # carrega plugins conforme settings.toml
│       ├── ai/                   # service.py, tasks/ (summarize, classify, draft, qa)
│       │   └── providers/        # none.py, openai.py, anthropic.py, gemini.py, internal.py
│       ├── notify/               # email_smtp.py
│       └── auth_ldap/            # (v2)
│
├── migrations/                   # Alembic (versões numeradas do esquema)
│   ├── env.py
│   └── versions/
│
├── frontend/                     # (reservado) SPA futura, se algum dia necessária;
│   └── README.md                 # MVP usa app/web/ server-side — decisão em ADR-002
│
├── tests/
│   ├── conftest.py               # fixtures: banco em memória, usuários por papel
│   ├── unit/                     # services (workflow, diff, audit, imutabilidade)
│   ├── integration/              # rotas + banco (fluxos completos)
│   └── e2e/                      # cenários: criar→revisar→aprovar→publicar→rollback
│
├── config/
│   ├── settings.example.toml     # template comentado de configuração
│   └── logging.toml
│
├── scripts/
│   ├── backup.py                 # snapshot consistente de data/
│   ├── restore.py
│   ├── verify_audit.py           # valida hash chain da trilha
│   ├── import_legacy.py          # importação em lote de documentos antigos
│   └── seed_demo.py              # carrega dados de exemplo
│
├── data/                         # ═ RUNTIME (gitignored; só .gitkeep) ═
│   ├── creditops.db              # SQLite
│   ├── attachments/              # anexos por hash: ab/cd/abcd1234...pdf
│   └── exports/                  # dossiês e exportações geradas
│
├── logs/                         # runtime (gitignored)
│
├── docs/                         # ═ DOCUMENTAÇÃO ═
│   ├── wiki/                     # esta wiki (00-indice.md ... 15-conclusao.md)
│   ├── adr/                      # Architecture Decision Records (ADR-001...)
│   ├── runbook.md                # operação: instalar, backup, restore, upgrade
│   └── templates/                # templates de política (limite.md, concessao.md...)
│
├── prompts/                      # ═ PROMPTS ═
│   ├── README.md                 # ordem de execução dos prompts de implementação
│   ├── 01-setup-projeto.md       # prompts p/ modelos mais baratos construírem o app
│   ├── ...                       # (ver prompts/README.md)
│   └── runtime/                  # prompts usados PELO sistema (módulo de IA)
│       ├── summarize_diff.md
│       ├── suggest_tags.md
│       ├── draft_from_document.md
│       └── qa_answer.md
│
└── examples/                     # dados de exemplo (políticas fictícias p/ demo/testes)
    ├── policies/                 # markdown de políticas de exemplo
    └── seed.json                 # usuários, áreas, produtos, segmentos de demo
```

## Convenções

- **`app/services/` não importa nada de `app/web/`, `app/api/` nem `app/plugins/`** — dependência sempre aponta para o core, nunca a partir dele (plugins assinam eventos).
- `data/` e `logs/` nunca entram no Git (apenas `.gitkeep`).
- Migrações **sempre** via Alembic — nunca alterar esquema à mão.
- Cada ADR documenta uma decisão irreversível ou cara de mudar.
- `prompts/` tem dois públicos distintos: raiz = prompts para **construir** o sistema (executados por você em um modelo barato); `runtime/` = prompts que o **sistema usa** em produção no módulo de IA.
