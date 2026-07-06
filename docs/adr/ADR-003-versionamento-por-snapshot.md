# ADR-003: Versionamento por snapshot no banco (vs. Git como storage)

**Status**: Aceito · **Data**: 2026-07-06

## Contexto

Cada versão de política precisa ser imutável, legível em O(1) e comparável com
qualquer outra. Git como storage (alternativa avaliada na wiki 14) traria
conceitos alheios ao público (branch, merge, rebase) e acoplamento operacional.

## Decisão

Cada `policy_version` guarda o conteúdo completo (snapshot) em `body_md`.
Diffs são calculados on-the-fly com `difflib` — nunca armazenados. História
linear: um único rascunho aberto por política; rollback é roll-forward de
conteúdo antigo.

## Consequências

- Leitura de qualquer versão sem reconstrução por deltas; sem classe de bugs
  de corrupção de histórico.
- Espaço irrelevante (políticas são KBs).
- Imutabilidade reforçada por triggers no banco + `content_hash` congelado na
  entrada em aprovação.
