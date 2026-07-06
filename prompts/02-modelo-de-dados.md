# Prompt 02 — Modelo de dados e migração inicial

> **Anexar ao contexto**: `docs/wiki/05-modelo-de-dados.md` e o "Prompt de contexto" do `prompts/README.md`. Pré-requisito: prompt 01 concluído.

---

Implemente o modelo de dados completo definido em `docs/wiki/05-modelo-de-dados.md`.

1. **Models SQLAlchemy 2.x** (estilo declarativo com `Mapped`/`mapped_column`), distribuídos em:
   - `app/models/org.py`: `User`, `Area`, `Product`, `Segment`.
   - `app/models/policy.py`: `Policy`, `PolicyVersion`, `Tag` + tabelas N:M `policy_product`, `policy_segment`, `policy_tag`.
   - `app/models/workflow.py`: `Approval`, `Publication`, `StatusTransition`, `Release`.
   - `app/models/collaboration.py`: `Comment`, `Attachment`, `ImpactRecord`.
   - `app/models/audit.py`: `AuditLog`, `Setting`, `Notification`.
   - `app/models/__init__.py` exporta todos e o `Base.metadata`.

   Detalhes obrigatórios:
   - IDs: UUID como `String(36)` gerado por `uuid4` (compatível SQLite), **exceto** `AuditLog.id` = integer autoincrement.
   - Enums de status/papéis como `String` + `Enum` Python validado na aplicação (evitar ALTER de enum no futuro).
   - Campos, nullability e uniques exatamente como na wiki, incluindo `Policy.current_version_id` (FK nullable para `policy_version`, use `use_alter=True`) e `PolicyVersion.based_on_version_id`.
   - Índice único parcial: **no máximo uma versão `effective` por política** (`Index` com `sqlite_where=text("status = 'effective'")` sobre `(policy_id)`).
   - Unique `(policy_id, version_number)`.

2. **Migração Alembic inicial** criando todas as tabelas, índices e **estes triggers SQLite** (via `op.execute`):
   - `policy_version`: bloquear UPDATE de `body_md`, `structured_fields`, `change_summary`, `expected_impact` quando `OLD.status != 'draft'` → `RAISE(ABORT, 'immutable version')`. Bloquear DELETE quando `OLD.status != 'draft'`.
   - `audit_log`: bloquear qualquer UPDATE e DELETE → `RAISE(ABORT, 'audit log is append-only')`.
   - `approval`, `publication`, `status_transition`: bloquear UPDATE e DELETE.
   - Tabela virtual FTS5 `policy_search` (colunas `code`, `title`, `body`) + triggers de sincronização serão feitos no prompt 08 — **não** criar agora.

3. **Constantes de domínio** em `app/models/enums.py`: `VersionStatus`, `Role`, `PolicyType`, `ApprovalDecision`, `PolicyLifecycle` — valores exatamente como na wiki.

4. **Testes** (`tests/unit/test_models.py`, banco de arquivo temporário — triggers não funcionam igual em memória compartilhada):
   - criar política + versão draft funciona;
   - UPDATE de `body_md` em versão com status `approved` falha com erro de trigger;
   - DELETE em `audit_log` falha;
   - segunda versão `effective` para a mesma política viola o índice único;
   - `(policy_id, version_number)` duplicado falha.

**Critérios de aceite**: `alembic upgrade head` cria tudo do zero; todos os testes passam; `alembic downgrade base` remove tudo.
