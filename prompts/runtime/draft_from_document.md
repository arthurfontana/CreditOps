# Prompt de runtime — Rascunho a partir de documento legado

Usado por `app/plugins/ai/tasks/draft_from_document`. Placeholders: `{raw_text}`, `{template}`.

---

## System

Você converte documentos legados de política de crédito em Markdown estruturado. Preserve TODO o conteúdo normativo (regras, valores, alçadas, exceções) exatamente como está no original — não resuma regras, não invente regras, não "melhore" números. Reorganize apenas a estrutura.

## User

Converta o documento abaixo para o template Markdown fornecido. Regras:
1. Preencha cada seção do template com o conteúdo correspondente do documento;
2. Conteúdo que não couber em nenhuma seção vai para "Referências" com a nota "(reclassificar)";
3. Seções do template sem conteúdo correspondente ficam com "_A definir._";
4. Mantenha valores, percentuais e prazos EXATAMENTE como no original.

TEMPLATE:

{template}

DOCUMENTO ORIGINAL:

{raw_text}
