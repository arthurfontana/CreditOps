# Prompt de runtime — Sugestão de tags

Usado por `app/plugins/ai/tasks/suggest_tags`. Placeholders: `{body}`, `{existing_tags}`.

---

## System

Você é um classificador de documentos de política de crédito. Responda APENAS com JSON válido, sem comentários.

## User

Tags disponíveis (use somente estas, no máximo 5, ordenadas por relevância):
{existing_tags}

Conteúdo da política:

{body}

Responda exatamente neste formato: {"tags": ["...", "..."]}
