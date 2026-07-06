# Prompt 08 — Busca full-text e polimento de UX

> **Anexar ao contexto**: `docs/wiki/02-personas-e-fluxo-do-usuario.md` e o "Prompt de contexto". Pré-requisitos: prompts 01–07.

---

1. **Busca FTS5**:
   - migração criando tabela virtual `policy_search` (FTS5, colunas `policy_id UNINDEXED`, `code`, `title`, `body`, tokenizer `unicode61 remove_diacritics 2`);
   - `app/services/search_service.py`: `reindex_policy(db, policy_id)` (indexa código, título e corpo da **versão vigente**; remove se arquivada) e `search(db, query, viewer, limit=20)` retornando trechos com `snippet()`;
   - reindexação disparada pelo evento `version.effective` (subscriber em `events.py`) + comando CLI `reindex-all`;
   - UI: caixa de busca no topo de todas as páginas (base.html); resultados com código, título, selo de vigência e trecho destacado.

2. **Home por perfil** (refinar a do prompt 06):
   - cartões de contagem (minhas pendências) + listas; ações de 1 clique direto da fila;
   - leitor: busca + últimas políticas que entraram em vigor (30 dias).

3. **Polimento**:
   - breadcrumbs (Catálogo → Política → vN);
   - selo de status colorido consistente em todas as telas (draft cinza, em aprovação âmbar, em vigor verde, substituída azul, rejeição vermelho);
   - mensagens flash pós-ação ("Versão v3 enviada para aprovação");
   - confirmação com resumo antes de ações irreversíveis (publicar, rollback, arquivar);
   - página 403 explicando o papel necessário; 404 amigável;
   - tabelas com ordenação e paginação server-side.

4. **Acessibilidade e navegador corporativo**: sem JS além do HTMX vendorizado; funciona com JS desabilitado degradando para formulários normais (HTMX progressivo); labels em todos os inputs; contraste adequado.

5. **Testes**: busca encontra por título/corpo/código com acentos ("concessão" ~ "concessao"); rascunho não aparece para leitor na busca; reindexação após nova vigência.

**Critérios de aceite**: um usuário leigo encontra a política vigente em < 30s partindo da home; testes passam.
