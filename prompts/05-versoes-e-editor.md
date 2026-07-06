# Prompt 05 — Versões, editor e diff

> **Anexar ao contexto**: `docs/wiki/07-versionamento-e-historico.md`, `docs/wiki/05-modelo-de-dados.md` (policy_version, attachment, comment) e o "Prompt de contexto". Pré-requisitos: prompts 01–04.

---

Implemente edição de rascunhos, criação de novas revisões, anexos e diff.

1. **`app/services/version_service.py`**:
   - `update_draft(db, actor, version_id, *, body_md, structured_fields=None)`: só o autor (ou admin) edita; só quando `status='draft'`; audita `version.updated` (sem payload do corpo inteiro — grave apenas o hash).
   - `create_revision(db, actor, policy_id) -> PolicyVersion`: cria rascunho copiando conteúdo da versão vigente; `version_number = max+1`; `based_on_version_id = vigente`; **falha se já existir versão aberta** (status não-terminal: draft/in_review/in_approval/approved/published) para a política; audita.
   - `freeze(version)`: calcula `content_hash = sha256(body_md + json(structured_fields))` — será chamado pelo workflow (prompt 06) ao entrar em aprovação.

2. **Editor (web)**: `GET/POST /versions/{id}/edit` — textarea de Markdown com preview lado a lado (HTMX: POST parcial renderiza preview sanitizado); salvamento automático a cada 30s via HTMX; indicador "salvo às HH:MM".

3. **`app/services/diff_service.py`**:
   - `unified(a: PolicyVersion, b: PolicyVersion) -> str` com `difflib.unified_diff`;
   - `side_by_side(a, b) -> list[Row]` (estrutura para o template: linhas pareadas com marcação added/removed/changed usando `difflib.SequenceMatcher`);
   - view `GET /policies/{id}/compare?from=v3&to=v7` com seletor de versões e as duas visualizações.

4. **Anexos** (`app/services/attachment_service.py` + rotas):
   - upload só em `draft`; extensões permitidas configuráveis (default: pdf, docx, xlsx, png, jpg, csv, txt); tamanho máx 20MB;
   - armazenar em `data/attachments/<h[:2]>/<h[2:4]>/<sha256><ext>`; deduplicação por hash;
   - download autenticado com `Content-Disposition: attachment`; audita `attachment.uploaded`/`attachment.downloaded`.

5. **Comentários** (`app/services/comment_service.py` + UI na página da versão): criar (qualquer papel exceto leitor — configurável), resolver, listar; `anchor` opcional = heading do Markdown; audita.

6. **Testes**: edição bloqueada fora de draft (service E trigger); `create_revision` copia conteúdo e falha com versão aberta; diff de casos conhecidos; upload rejeita extensão/tamanho inválidos; hash de anexo confere.

**Critérios de aceite**: fluxo editar→preview→salvar→comparar versões funciona na UI; testes passam.
