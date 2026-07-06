# Prompt 07 — Auditoria, linha do tempo e exportação

> **Anexar ao contexto**: `docs/wiki/09-seguranca-e-governanca.md` (Trilha de auditoria), `docs/wiki/07-versionamento-e-historico.md` e o "Prompt de contexto". Pré-requisitos: prompts 01–06.

---

1. **Linha do tempo da política** (`GET /policies/{id}/history`):
   - lista todas as versões (desc) com status atual, período de vigência, autor, aprovador(es), publicador e datas — conforme mock da wiki 07;
   - link para ver qualquer versão renderizada (somente leitura, com banner "versão histórica — vigente de X a Y");
   - botão "comparar" pré-preenchendo o compare do prompt 05.

2. **Time travel** (`GET /policies/{id}/at?date=YYYY-MM-DD`):
   - `version_service.version_at(db, policy_id, d)` retorna a versão com `effective_from <= d` e (`effective_until > d` ou null);
   - UI: campo de data na página de histórico.

3. **Consulta de auditoria** (`GET /audit`, papéis `admin` e `reader` com flag de auditor — adicione `is_auditor: bool` em `user` via migração):
   - filtros: período, ator, ação, tipo/id de entidade; paginação; export CSV.

4. **`app/services/export_service.py`**:
   - `export_version_md(version) -> str`: front matter YAML (código, título, versão, status, vigência, autor, aprovadores, hash) + corpo Markdown;
   - `export_policy_json(policy) -> dict`: metadados + todas as versões + aprovações + publicações + transições;
   - `export_dossier(policy) -> Path`: gera ZIP em `data/exports/` com: `politica.md` (versão vigente), `historico/vN.md` (cada versão), `metadados.json`, `trilha_auditoria.json` (eventos da política); audita `export.generated`;
   - rotas de download autenticadas.

5. **Eventos de domínio** (`app/services/events.py`) — base para plugins futuros:
   - pub/sub em memória: `subscribe(event_name, handler)`, `emit(event_name, payload)` com handlers executados **após o commit** (use `sqlalchemy.event` ou fila pós-commit simples); erros de handler são logados, nunca propagados;
   - emita: `version.submitted`, `version.approved`, `version.rejected`, `version.published`, `version.effective`;
   - nenhum subscriber ainda (plugins virão depois) — apenas um handler de log em `logs/`.

6. **Testes**: `version_at` com fronteiras exatas (dia da troca de vigência); dossiê contém todas as versões e trilha; filtros de auditoria; handlers só rodam após commit e erro de handler não quebra a transação.

**Critérios de aceite**: auditor consegue, pela UI, responder "o que valia em 15/03, quem aprovou e quando?" e baixar o dossiê; testes passam.
