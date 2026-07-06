# CreditOps

**Plataforma de governança de políticas de crédito** — documentação, versionamento imutável, workflow de aprovação e trilha de auditoria. Uma mistura de wiki especializada, controle de versão estilo Git e catálogo de políticas, projetada para rodar em ambiente corporativo restrito (um servidor Python, SQLite, sem SaaS e sem IA obrigatória).

## Estado do projeto

📐 **Fase de especificação.** A especificação completa do produto está pronta e é a fonte de verdade para a implementação.

## Comece por aqui

| O que você quer | Onde ir |
|---|---|
| Entender o produto | [Wiki de desenvolvimento — índice](docs/wiki/00-indice.md) |
| Visão, problema e objetivos | [Visão Geral](docs/wiki/01-visao-geral.md) |
| Arquitetura técnica | [Arquitetura](docs/wiki/04-arquitetura.md) |
| Modelo de dados | [Modelo de Dados](docs/wiki/05-modelo-de-dados.md) |
| Fluxo de aprovação | [Workflow de Aprovação](docs/wiki/06-workflow-de-aprovacao.md) |
| **Implementar a aplicação** | [Prompts de execução (ordem 01→10)](prompts/README.md) |

## Resumo em 30 segundos

- **Problema**: políticas de crédito vivem em planilhas, e-mails e na memória das pessoas; ninguém sabe qual é a versão vigente nem quem aprovou.
- **Solução**: catálogo único com versões imutáveis, diff entre versões, aprovação formal do gerente de crédito, data de vigência explícita e auditoria append-only.
- **Stack**: Python 3.11+, FastAPI, SQLite (WAL+FTS5), Jinja2+HTMX. Um processo, um arquivo de banco, backup = copiar uma pasta.
- **IA**: módulo 100% opcional e plugável (OpenAI, Anthropic, Gemini ou modelo interno) — o core funciona sem nenhum modelo.