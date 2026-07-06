# Prompts de Execução — Como construir o CreditOps com modelos mais baratos

Esta pasta contém a sequência de prompts para implementar a aplicação usando modelos de IA mais baratos (ex.: Claude Haiku, GPT-4o-mini, ou o modelo que você tiver disponível). **A especificação completa já está pronta na wiki (`docs/wiki/`)** — o papel do modelo executor é implementar, não decidir arquitetura.

## Regras de uso (leia antes de começar)

1. **Execute os prompts na ordem** (01 → 10). Cada um assume que o anterior foi concluído e commitado.
2. **Sempre anexe/inclua no contexto os arquivos da wiki citados** no cabeçalho de cada prompt. Eles são a fonte de verdade — o modelo não deve inventar requisitos.
3. **Um prompt = uma sessão = um commit** (ou mais commits pequenos). Não misture etapas.
4. Ao final de cada etapa, **rode os testes** (`pytest`) antes de seguir. Se falharem, cole o erro no mesmo chat e peça correção antes de avançar.
5. Se o modelo propuser desviar da especificação (outra stack, outro esquema), **recuse e reaponte para a wiki**. Desvios só via edição consciente da wiki + ADR.
6. Modelos baratos se perdem em tarefas grandes: se uma etapa travar, divida o prompt nos sub-itens numerados e execute um por vez.

## Ordem de execução

| # | Prompt | O que produz | Arquivos da wiki a anexar |
|---|--------|--------------|---------------------------|
| 01 | [01-setup-projeto.md](01-setup-projeto.md) | Esqueleto do repo, FastAPI+SQLite+Alembic rodando, CI | 04, 10 |
| 02 | [02-modelo-de-dados.md](02-modelo-de-dados.md) | Models SQLAlchemy, migração inicial, triggers de imutabilidade | 05 |
| 03 | [03-auth-rbac.md](03-auth-rbac.md) | Login, sessões, papéis, CLI create-admin | 09, 05 |
| 04 | [04-catalogo-politicas.md](04-catalogo-politicas.md) | CRUD de políticas, cadastros (área/produto/segmento/tags), catálogo com filtros | 05, 02 |
| 05 | [05-versoes-e-editor.md](05-versoes-e-editor.md) | Editor Markdown, versões imutáveis, "Nova revisão", anexos, diff | 07, 05 |
| 06 | [06-workflow-aprovacao.md](06-workflow-aprovacao.md) | Máquina de estados, revisão, aprovação, publicação, vigência, rollback, filas | 06 |
| 07 | [07-auditoria-e-historico.md](07-auditoria-e-historico.md) | Trilha append-only, linha do tempo, time travel, exportação/dossiê | 09, 07 |
| 08 | [08-busca-e-ux.md](08-busca-e-ux.md) | Busca FTS5, home por perfil, polimento de UX | 02 |
| 09 | [09-testes-e-operacao.md](09-testes-e-operacao.md) | Suíte de testes dos invariantes, backup/restore, seed, runbook | 12, 09 |
| 10 | [10-ia-plugavel.md](10-ia-plugavel.md) | (v2, opcional) Módulo de IA: contrato, adapters, features de sugestão | 08 |

> As referências "04, 10" etc. são os arquivos `docs/wiki/NN-*.md` correspondentes.

## Prompt de contexto (cole no início de TODA sessão)

```text
Você é um desenvolvedor Python sênior implementando o CreditOps, um sistema de
governança de políticas de crédito. A especificação completa está nos arquivos
docs/wiki/ anexados — siga-os à risca; não invente requisitos nem mude a stack.

Stack fixa: Python 3.11+, FastAPI, SQLAlchemy 2.x, Alembic, SQLite (WAL + FTS5),
Jinja2 + HTMX (server-side rendering, sem Node/build), pytest, ruff.

Regras inegociáveis:
- Versões de política fora de rascunho são IMUTÁVEIS (aplicação + triggers no banco).
- audit_log é append-only (sem UPDATE/DELETE, enforced por trigger).
- Toda regra de negócio vive em app/services/ (sem HTTP); rotas são camada fina.
- app/services/ não importa app/web/, app/api/ nem app/plugins/.
- Autorização é validada no service layer, não apenas na UI.
- Autor não pode aprovar a própria versão.
- Transições de estado só pela whitelist do workflow (docs/wiki/06).
- Nada de dependências além das listadas; nada de serviços externos no core.

Escreva código completo e funcional (sem placeholders "TODO"), com type hints,
e testes pytest para cada regra de negócio implementada.
```

## Dicas para reduzir custo

- Anexe **somente** os arquivos de wiki listados para a etapa (não a wiki inteira).
- Reaproveite a sessão para correções da mesma etapa; abra sessão nova a cada etapa.
- Peça "apenas os arquivos novos/alterados, completos" — evita o modelo reimprimir o repo.
- Use o modelo barato para implementar e, se disponível, um modelo melhor apenas para revisar as etapas críticas (02, 06 e 07 — esquema, workflow e auditoria).

## Prompts de runtime (não confundir)

A subpasta [`runtime/`](runtime/) contém os prompts que **o próprio sistema** usa no módulo de IA opcional (resumir diff, sugerir tags etc.). Eles são artefatos da aplicação, não instruções de desenvolvimento.
