# Prompt 04 — Catálogo de políticas e cadastros

> **Anexar ao contexto**: `docs/wiki/05-modelo-de-dados.md`, `docs/wiki/02-personas-e-fluxo-do-usuario.md` (F3) e o "Prompt de contexto". Pré-requisitos: prompts 01–03.

---

Implemente os cadastros de apoio e o catálogo de políticas.

1. **Cadastros (admin)** — rotas + telas para `Area`, `Product`, `Segment`, `Tag`: listar, criar, editar, ativar/desativar (lógico). Auditar tudo.

2. **`app/services/policy_service.py`**:
   - `create_policy(db, actor, *, title, policy_type, area_id, owner_id, product_ids, segment_ids, tag_ids) -> Policy`
     - valida papel `author`/`admin` via `authz.ensure`;
     - gera `code` sequencial por área: `POL-<AREA_CODE>-NNN` (transação com SELECT do maior NNN da área; trate corrida com retry);
     - cria automaticamente a **versão 1** com `status='draft'`, `version_number=1`, `body_md` inicial a partir do template do tipo (leia de `docs/templates/<tipo>.md`; se não existir, corpo vazio com headings padrão);
     - audita `policy.created`.
   - `update_policy_metadata(...)`: título, dono, produtos, segmentos, tags (não toca em versões); audita com before/after.
   - `archive_policy(db, actor, policy_id, reason)`: papel `approver`; audita.
   - `list_policies(db, *, filters, viewer)`: filtros por área, produto, segmento, tipo, tag, status de vigência e texto no título/código. Rascunhos só aparecem para autor/revisor/aprovador/admin.

3. **Catálogo (web)** — `GET /policies`:
   - tabela com código, título, área, tipo, selo de status (**EM VIGOR vN desde DD/MM/AAAA**, "sem versão vigente", "arquivada");
   - filtros via HTMX (atualiza a tabela sem reload);
   - `GET /policies/{id}`: página da política mostrando a **versão vigente** renderizada (Markdown → HTML **sanitizado**: use `markdown` + escape de HTML bruto do usuário; não permita tags HTML no corpo), metadados e botões conforme papel.

4. **Templates de política** — crie `docs/templates/limite.md`, `concessao.md`, `renegociacao.md`, `generico.md` com headings padrão: Objetivo, Escopo, Regras, Exceções, Alçadas, Referências.

5. **Testes**: geração de código sequencial por área (inclusive concorrência simulada); política nasce com v1 draft; filtros do catálogo; leitor não vê rascunho; metadados auditados.

**Critérios de aceite**: criar política pela UI, vê-la no catálogo com filtros funcionando; testes passam.
