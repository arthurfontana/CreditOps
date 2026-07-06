# CreditOps — Wiki de Desenvolvimento

> Plataforma de documentação, versionamento, aprovação e auditoria de políticas de crédito.

Esta wiki é a fonte única de verdade da especificação do produto. As páginas seguem a ordem lógica de leitura e também a ordem de implementação.

## Índice

| # | Página | Conteúdo |
|---|--------|----------|
| 1 | [Visão Geral](01-visao-geral.md) | Título, resumo executivo, problema, visão do produto, objetivos |
| 2 | [Personas e Fluxo do Usuário](02-personas-e-fluxo-do-usuario.md) | Quem usa, jornadas principais, usabilidade corporativa |
| 3 | [MVP e Evolução](03-mvp-e-evolucao.md) | MVP → intermediária → completa → enterprise, com dores resolvidas por fase |
| 4 | [Arquitetura](04-arquitetura.md) | Arquitetura técnica para ambiente corporativo restrito, core vs. opcional |
| 5 | [Modelo de Dados](05-modelo-de-dados.md) | Entidades, relacionamentos, esquema SQL de referência |
| 6 | [Workflow de Aprovação](06-workflow-de-aprovacao.md) | Máquina de estados, papéis, rejeição, rollback, vigência |
| 7 | [Versionamento e Histórico](07-versionamento-e-historico.md) | Modelo de versões imutáveis, diffs, justificativas, impacto |
| 8 | [IA Modular](08-ia-modular.md) | IA como plugin opcional: interface, provedores, isolamento de credenciais |
| 9 | [Segurança e Governança](09-seguranca-e-governanca.md) | RBAC, trilha de auditoria, publicação, retenção, compliance |
| 10 | [Estrutura do Repositório](10-estrutura-do-repositorio.md) | Árvore de diretórios pronta para desenvolvimento incremental |
| 11 | [Roadmap](11-roadmap.md) | Fase 0, MVP, v1, v2, enterprise, com dependências |
| 12 | [Backlog Inicial](12-backlog.md) | Épicos e histórias priorizadas do MVP |
| 13 | [Riscos e Trade-offs](13-riscos-e-trade-offs.md) | Riscos técnicos, de adoção e de governança, com mitigação |
| 14 | [Alternativas e Trade-offs de Solução](14-alternativas.md) | Soluções mais simples/melhores e quando escolhê-las |
| 15 | [Conclusão](15-conclusao.md) | Síntese e próximos passos |
| — | [Prompts de Execução](../../prompts/README.md) | **Prompts ordenados para implementar a aplicação com modelos mais baratos** |

## Como usar esta wiki

- **Para entender o produto**: leia 1 → 2 → 3.
- **Para implementar**: leia 4 → 5 → 6 → 7, depois execute os [prompts](../../prompts/README.md) na ordem.
- **Para governança e compliance**: leia 6, 7 e 9.
- **Para decidir se vale a pena**: leia 13 e 14 antes de tudo.

## Convenções

- Toda decisão de arquitetura relevante deve virar um ADR em `docs/adr/`.
- Páginas desta wiki são versionadas junto com o código — mudança de especificação passa por PR.
- Termos de negócio estão definidos no [Modelo de Dados](05-modelo-de-dados.md#glossario).
