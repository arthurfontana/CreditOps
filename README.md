# CreditOps

**Plataforma de governança de políticas de crédito** — documentação, versionamento imutável, workflow de aprovação e trilha de auditoria. Uma mistura de wiki especializada, controle de versão estilo Git e catálogo de políticas, projetada para rodar em ambiente corporativo restrito (um servidor Python, SQLite, sem SaaS e sem IA obrigatória).

## Estado do projeto

🚀 **v1 implementada** ("Governança para valer" — ver [Roadmap](docs/wiki/11-roadmap.md)), sobre o MVP "Fonte de verdade":

- **MVP**: catálogo, versões imutáveis, workflow completo de aprovação, publicação com vigência, rollback, trilha de auditoria append-only, busca FTS5, time travel, exportação/dossiê, backup/restore e suíte de testes de invariantes.
- **v1**: notificações por e-mail (plugin SMTP com fila e retry), permissões por área, hash chain na auditoria (`scripts/verify_audit.py`), aprovação multinível por tipo de política, delegação de aprovação, releases (pacotes de publicação), campos estruturados por tipo + diff de campos, demanda de mudança com lead time ponta a ponta, catálogo de indicadores + hipótese × impacto observado (janelas 30/60/90d com cobrança pendente), referência de implementação (motor de decisão), dashboard de governança, importador de legado em lote e exportação PDF (plugin sem dependência externa).

## Quickstart

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env               # gere sua CREDITOPS_SECRET_KEY
alembic upgrade head               # cria o banco (SQLite + triggers + FTS5)
python -m app.cli create-admin --email admin@empresa.com --name "Admin"
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Para experimentar com dados fictícios (6 usuários, 8 políticas com histórico):

```bash
python scripts/seed_demo.py        # senha de todos: demo1234
```

Desenvolvimento: `pip install -r requirements-dev.txt && pytest && ruff check .`
Operação (backup, restore, TLS, upgrade): [docs/runbook.md](docs/runbook.md).

## Comece por aqui

| O que você quer | Onde ir |
|---|---|
| Entender o produto | [Wiki de desenvolvimento — índice](docs/wiki/00-indice.md) |
| Visão, problema e objetivos | [Visão Geral](docs/wiki/01-visao-geral.md) |
| Arquitetura técnica | [Arquitetura](docs/wiki/04-arquitetura.md) + [ADRs](docs/adr/) |
| Modelo de dados | [Modelo de Dados](docs/wiki/05-modelo-de-dados.md) |
| Fluxo de aprovação | [Workflow de Aprovação](docs/wiki/06-workflow-de-aprovacao.md) |
| Operar o sistema | [Runbook](docs/runbook.md) |
| Próximas fases (v1, v2, enterprise) | [Roadmap](docs/wiki/11-roadmap.md) · [Prompts de execução](prompts/README.md) |

## Resumo em 30 segundos

- **Problema**: políticas de crédito vivem em planilhas, e-mails e na memória das pessoas; ninguém sabe qual é a versão vigente nem quem aprovou.
- **Solução**: catálogo único com versões imutáveis, diff entre versões, aprovação formal do gerente de crédito, data de vigência explícita e auditoria append-only.
- **Stack**: Python 3.11+, FastAPI, SQLite (WAL+FTS5), Jinja2+HTMX. Um processo, um arquivo de banco, backup = copiar uma pasta.
- **IA**: módulo 100% opcional e plugável (OpenAI, Anthropic, Gemini ou modelo interno) — o core funciona sem nenhum modelo.

## Garantias por construção

- Versão fora de rascunho é **imutável** — validado no service layer **e** por trigger no banco.
- `audit_log`, aprovações e transições de status são **append-only** (triggers).
- No máximo **uma versão vigente por política** (índice único parcial).
- **Autor nunca aprova a própria versão** (segregação de funções no service layer).
- Transições de estado só pela **whitelist** da máquina de estados — não existe força bruta.
- Vigência **nunca retroativa**; "o que valia em 15/03?" responde-se com uma query (time travel).
