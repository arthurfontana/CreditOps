# ADR-001: SQLite como banco padrão do MVP

**Status**: Aceito · **Data**: 2026-07-06

## Contexto

O ambiente-alvo é um único servidor corporativo Python, sem Docker, sem cloud e
com TI de baixa disponibilidade (wiki 04). O produto exige transações, busca
full-text e integridade forte (triggers), com dezenas de usuários simultâneos e
workload dominado por leitura.

## Decisão

SQLite em modo WAL, com FTS5 para busca e triggers para imutabilidade, acessado
via SQLAlchemy 2.x + Alembic.

## Consequências

- Instalação e backup triviais (um arquivo); zero administração de banco.
- Escritas serializadas — irrelevante para o volume de um time de políticas.
- SQLAlchemy/Alembic mantêm o caminho de migração para Postgres aberto
  (gatilho: >~200 usuários ativos, HA ou exigência da TI) sem reescrita.
- Testes usam banco de arquivo temporário (triggers idênticos aos de produção).
