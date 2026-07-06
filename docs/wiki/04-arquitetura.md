# 4. Arquitetura Técnica

## Premissas do ambiente

- Pode existir **apenas um servidor Python** (Linux ou Windows), sem Docker, sem cloud.
- Sem dependência obrigatória de SaaS externo ou IA.
- Restrições de segurança: rede interna, proxy, sem portas expostas à internet.
- TI com pouca disponibilidade: instalação e operação precisam ser triviais.

## Decisão central

> **Monólito modular em Python: FastAPI + SQLite + filesystem, um único processo, zero dependências de infraestrutura.**

Backup = copiar uma pasta. Instalação = `pip install` + um comando. Upgrade = substituir o código e rodar migrações. Essa simplicidade é uma *feature de produto*, não uma limitação.

## Visão em camadas

```
┌─────────────────────────────────────────────────────────────┐
│  Cliente (navegador)                                         │
│  HTML renderizado no servidor (Jinja2) + HTMX + CSS leve     │
└──────────────────────────────┬───────────────────────────────┘
                               │ HTTP (rede interna / proxy TLS)
┌──────────────────────────────▼───────────────────────────────┐
│  FastAPI (processo único, uvicorn)                            │
│                                                               │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌────────────┐ │
│  │  web/      │ │  api/      │ │  auth      │ │  admin     │ │
│  │  páginas   │ │  JSON (v2) │ │  sessões   │ │  usuários  │ │
│  └─────┬──────┘ └─────┬──────┘ └─────┬──────┘ └─────┬──────┘ │
│        └──────────────┴──────┬───────┴──────────────┘        │
│                    ┌─────────▼──────────┐                    │
│                    │  services/ (core)   │  ← regras de       │
│                    │  policy, version,   │    negócio puras,  │
│                    │  workflow, audit,   │    sem HTTP        │
│                    │  diff, search       │                    │
│                    └─────────┬──────────┘                    │
│        ┌─────────────────────┼─────────────────────┐         │
│  ┌─────▼─────┐        ┌──────▼──────┐       ┌──────▼──────┐  │
│  │ SQLite     │        │ Filesystem  │       │ plugins/    │  │
│  │ (WAL+FTS5) │        │ anexos,     │       │ ai/, notify/│  │
│  │            │        │ exports     │       │ (opcionais) │  │
│  └───────────┘        └─────────────┘       └─────────────┘  │
└───────────────────────────────────────────────────────────────┘
```

## Stack e justificativas

| Camada | Escolha | Por quê | Alternativa aceitável |
|---|---|---|---|
| Web framework | **FastAPI** | Tipagem, validação Pydantic, docs automáticas, futuro de API já embutido | Flask (mais simples, menos validação) |
| Templates | **Jinja2 + HTMX** | Server-side rendering: sem build de frontend, sem Node no servidor, funciona em qualquer navegador corporativo | Frontend estático + fetch |
| Banco | **SQLite (WAL, FTS5)** | Zero administração, transacional, busca full-text nativa, um arquivo | Postgres se já existir na empresa |
| ORM/Migrações | **SQLAlchemy + Alembic** | Abstração que permite trocar SQLite→Postgres sem reescrever | SQL puro com scripts de migração numerados |
| Conteúdo | **Markdown** (corpo) + campos estruturados (metadados) | Diff legível, exportável, editável por humanos, não prende a fornecedor | — |
| Anexos | Filesystem (`data/attachments/`) com hash SHA-256 no banco | Simples, backup trivial, integridade verificável | — |
| Auth | Sessões com cookie assinado; senhas com argon2/bcrypt | Sem dependência externa | LDAP na v2 |
| Servidor | uvicorn atrás de proxy interno (nginx/IIS) ou direto | — | — |

### Por que server-side rendering + HTMX (e não SPA React)?

- Ambiente restrito pode não ter Node, npm nem acesso a CDNs.
- HTMX (um arquivo JS de ~14 KB, versionado no repo) dá interatividade suficiente: filas que atualizam, formulários sem reload, preview de Markdown.
- Menos superfície de ataque, menos build, menos manutenção.
- Se um dia precisar de SPA, a camada `api/` JSON já existirá (v2) — o frontend é substituível.

## Core obrigatório vs. opcional

### Core (funciona sozinho, sem rede externa)

- `services/policies` — CRUD de políticas e metadados.
- `services/versions` — criação de versões imutáveis, snapshot de conteúdo.
- `services/workflow` — máquina de estados, transições, validações de papel.
- `services/diff` — diff textual entre versões (biblioteca padrão `difflib`).
- `services/audit` — trilha append-only.
- `services/search` — busca FTS5.
- `services/export` — Markdown/JSON/dossiê.
- Autenticação local e RBAC.

### Opcional / plugável (a aplicação sobe e funciona sem eles)

| Plugin | Depende de | Fase |
|---|---|---|
| `plugins/notify_email` | SMTP corporativo | v1 |
| `plugins/auth_ldap` | AD/LDAP | v2 |
| `plugins/ai_*` | Provedor de IA (externo ou local) | v2 |
| `plugins/export_pdf` | wkhtmltopdf/weasyprint se permitido | v1 |
| `plugins/webhook` | Sistemas consumidores | v2 |

Regra arquitetural: **plugins são descobertos por configuração** (`config/settings.toml`), implementam interfaces definidas em `app/plugins/base.py` e falham de forma silenciosa e logada — indisponibilidade de plugin nunca derruba o core. Nenhum módulo do core importa um plugin diretamente; o core emite **eventos de domínio** (ex.: `version.published`) e os plugins assinam esses eventos.

### O que depende de IA vs. o que não depende

| Funcionalidade | Sem IA | Com IA (acelerado) |
|---|---|---|
| Escrever política | Editor + template | Sugestão de rascunho a partir de doc legado |
| Resumo de mudança | Autor escreve justificativa | Resumo automático do diff (autor revisa) |
| Classificação/tags | Manual | Sugestão automática |
| Busca | FTS5 (palavras-chave) | Busca semântica / perguntas em linguagem natural |
| Auditoria | Exportação estruturada | Narrativa do histórico gerada |

Nenhuma linha da coluna "Sem IA" é degradada quando a IA está desligada — a IA só **preenche sugestões que o humano confirma**.

## Fluxo de dados de escrita (exemplo: publicar versão)

1. Handler HTTP valida sessão e papel (`aprovador`).
2. Chama `workflow_service.publish(version_id, effective_date, actor)`.
3. Service, **em uma única transação**:
   - valida transição de estado (Aprovado → Publicado);
   - grava `publication` com datas;
   - agenda/aplica vigência (Em vigor + Substituída na anterior);
   - grava evento na `audit_log` (com hash encadeado a partir da v1).
4. Publica evento de domínio `version.published` → plugins (e-mail, webhook, IA) reagem fora da transação.

## Concorrência e escala

- SQLite em modo WAL atende confortavelmente dezenas de usuários simultâneos em workload de leitura dominante (este caso). Escritas são serializadas — irrelevante para o volume de um time de políticas.
- Gatilho de migração para Postgres: > ~200 usuários ativos, necessidade de HA, ou exigência da TI. Alembic + SQLAlchemy tornam a migração um exercício de `pg_dump`-like, não uma reescrita.

## Instalação e operação

```bash
# Instalação (servidor corporativo, Python 3.11+)
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt          # ou pip install --no-index com wheelhouse offline
alembic upgrade head                      # cria/migra o banco
python -m app.cli create-admin            # primeiro usuário
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

- **Backup**: copiar `data/` (banco + anexos). Script `scripts/backup.py` faz snapshot consistente (SQLite backup API) + verificação de hash.
- **Ambiente sem internet**: dependências entregues como *wheelhouse* (`pip download` feito fora, instalado com `--no-index`).
- **Logs**: arquivo rotacionado em `logs/`, formato estruturado (JSON opcional).

## Decisões registradas (ADRs a criar)

1. ADR-001: SQLite como banco padrão do MVP (vs. Postgres).
2. ADR-002: Server-side rendering + HTMX (vs. SPA).
3. ADR-003: Versionamento por snapshot no banco (vs. Git como storage — ver [Alternativas](14-alternativas.md)).
4. ADR-004: Plugins por eventos de domínio + configuração (vs. import direto).
5. ADR-005: Markdown como formato canônico do corpo da política.
