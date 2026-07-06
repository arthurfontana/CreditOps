# ADR-002: Server-side rendering com Jinja2 + HTMX (vs. SPA)

**Status**: Aceito · **Data**: 2026-07-06

## Contexto

Ambiente corporativo restrito: pode não haver Node, npm nem acesso a CDNs;
navegadores corporativos variados; requisito de zero instalação no cliente.

## Decisão

HTML renderizado no servidor (Jinja2) com HTMX vendorizado no repositório
(`app/web/static/js/htmx.min.js`, v1.9.12) para interatividade pontual
(filtros do catálogo, preview de Markdown, autosave). CSS próprio, sem
frameworks externos. CSP restritiva: nenhum recurso externo.

## Consequências

- Sem build de frontend, sem Node no servidor, menos superfície de ataque.
- Funciona com JS desabilitado (HTMX é progressivo; formulários degradam).
- Se um dia for necessária uma SPA, a camada `app/api/` (v2) fornecerá o JSON;
  o diretório `frontend/` fica reservado.
