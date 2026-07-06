# 11. Roadmap

## Visão geral

```
Fase 0        MVP            v1                v2                Enterprise
fundação  →  fonte de   →   governança    →   plataforma    →   produto
(2-3 sem)    verdade        para valer        da empresa        SaaS/on-prem
             (6-8 sem)      (6-8 sem)         (8-12 sem)        (contínuo)
```

Durações assumem 1–2 desenvolvedores (ou execução assistida por IA com os [prompts](../../prompts/README.md)).

---

## Fase 0 — Fundação (pré-requisito de tudo)

**Objetivo**: repositório pronto para desenvolvimento incremental, decisões travadas.

| Entrega | Dependência |
|---|---|
| Estrutura de diretórios ([página 10](10-estrutura-do-repositorio.md)) | — |
| Esta wiki commitada + ADRs 001–005 | — |
| Esqueleto FastAPI + SQLite + Alembic rodando (health check) | estrutura |
| Migração inicial do esquema core | modelo de dados |
| CI simples (lint ruff + pytest) — GitHub Actions ou script local | esqueleto |
| Templates de política em `docs/templates/` | — |
| `seed_demo.py` com dados fictícios | migração |

---

## MVP — "Fonte de verdade" (destrava piloto com 1 time)

| Prioridade | Feature | Depende de |
|---|---|---|
| P0 | Autenticação local + RBAC (5 papéis) | Fase 0 |
| P0 | CRUD de políticas + metadados (área/produto/segmento/tags) | auth |
| P0 | Versões imutáveis + editor Markdown com preview | CRUD |
| P0 | Máquina de estados completa do workflow | versões |
| P0 | Aprovação com segregação autor≠aprovador + justificativa | workflow |
| P0 | Publicação com data de vigência + substituição automática | workflow |
| P0 | Trilha de auditoria append-only | tudo grava nela |
| P1 | Diff entre versões (texto) | versões |
| P1 | Busca FTS5 | CRUD |
| P1 | Comentários por versão | versões |
| P1 | Anexos com hash | versões |
| P1 | Filas por perfil na home (rascunhos / pendências) | workflow |
| P1 | Linha do tempo + time travel ("ver em uma data") | publicação |
| P2 | Exportação Markdown/JSON + dossiê de auditoria | versões, auditoria |
| P2 | Rollback (fluxo expresso) | workflow |
| P2 | Backup script + runbook | — |

**Gate de saída**: piloto com um time real — 10 políticas migradas, 1 ciclo completo de alteração aprovada, 1 consulta de auditoria respondida.

---

## v1 — "Governança para valer" (adoção pela diretoria)

| Prioridade | Feature | Depende de |
|---|---|---|
| P0 | Notificações por e-mail (SMTP) via plugin | eventos de domínio |
| P0 | Permissões por área | RBAC |
| P0 | Hash chain na auditoria + `verify_audit.py` | auditoria |
| P1 | Aprovação multinível por tipo de política | workflow |
| P1 | Delegação de aprovação | aprovação |
| P1 | Releases (pacotes de publicação) | publicação |
| P1 | Campos estruturados por tipo + diff de campos | versões |
| P1 | Demanda de mudança (`change_request`) + lead time demanda→vigência | workflow |
| P1 | Catálogo de indicadores + hipótese estruturada por mudança (`impact_metric`) | versões |
| P1 | Impacto observado (`impact_record` + observado por indicador em 30/60/90d) + cobrança pendente | publicação, indicadores |
| P2 | Referência de implementação (`implementation_ref`, registro manual) | publicação |
| P2 | Dashboard de governança (status, tempos de ciclo, políticas paradas, esperado × observado) | dados do MVP |
| P2 | Importador de legado em lote | anexos |
| P2 | Exportação PDF (plugin) | export |

**Gate de saída**: 3+ áreas usando; 100% das publicações com trilha; auditoria interna valida o dossiê.

---

## v2 — "Plataforma da empresa"

| Prioridade | Feature | Depende de |
|---|---|---|
| P0 | SSO (LDAP/AD; OIDC se houver IdP) via plugin | plugin auth |
| P0 | API REST de consumo (somente leitura, tokens de serviço) | `app/api/` |
| P1 | Módulo de IA plugável + provider adapters + features: resumo de diff, tags, rascunho de legado | eventos, prompts/runtime |
| P1 | Recertificação periódica (`review_due_at` + relatório) | modelo de dados |
| P1 | Webhooks de publicação | eventos |
| P2 | RAG local (FTS5/embeddings + provider) para perguntas | IA |
| P2 | Trilha de leitura obrigatória ("ciência da operação") | auditoria |
| P2 | Comparação entre políticas | diff |
| P2 | Grafo de referências entre políticas + análise de impacto | modelo de dados |
| P2 | Publicação-experimento (piloto com escopo, prazo e promoção) | publicação |

**Gate de saída**: sistemas consumindo a API; IA em uso com pelo menos 1 provedor (ou decisão consciente de não usar).

---

## Enterprise — produto

- Postgres como padrão (migração Alembic testada), HA, observabilidade.
- Multi-tenant **ou** single-tenant gerenciado (recomendado para bancos).
- Workflow configurável por tenant; alçadas parametrizáveis.
- Assinatura digital de aprovações (não-repúdio forte).
- Relatórios regulatórios prontos; SLA; MFA; marketplace de provedores de IA.
- Conferência automática de implantação (integração com motores de decisão).
- **Exploratório**: biblioteca de regras reutilizáveis — só com valor comprovado ([Domínio](16-dominio-do-produto.md#regra-reutilizável-biblioteca-de-regras--exploratório--enterprise)).

---

## Regras de sequenciamento

1. **Nada entra na fase N+1 se o gate da fase N não passou** — o produto cresce por adoção comprovada, não por feature.
2. Plugins (e-mail, LDAP, IA) só depois que o sistema de **eventos de domínio** existir (MVP a constrói; v1 a usa).
3. IA por último entre as integrações: exige core estável e é o item mais sujeito a restrições corporativas.
