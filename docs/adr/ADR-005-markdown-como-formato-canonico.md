# ADR-005: Markdown como formato canônico do corpo da política

**Status**: Aceito · **Data**: 2026-07-06

## Contexto

O conteúdo precisa ser: diffável linha a linha, legível sem o sistema,
exportável, editável por analistas e livre de aprisionamento a fornecedor.

## Decisão

`body_md` em Markdown (CommonMark) é o conteúdo canônico. Renderização com
markdown-it-py em modo `html=False`: HTML bruto do usuário é escapado, nunca
interpretado (sem XSS). Templates por tipo de política em `docs/templates/`.
Campos estruturados por tipo (v1) complementam — não substituem — o corpo.

## Consequências

- Diff textual legível para o aprovador; export .md com front matter YAML.
- Editor simples (textarea + preview) sem WYSIWYG pesado.
- Anexos (Word/PDF legados) convivem como arquivos com hash, mas o documento
  primário é sempre o Markdown estruturado.
