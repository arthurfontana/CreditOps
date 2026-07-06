# frontend/ — reservado

O MVP usa server-side rendering (Jinja2 + HTMX) em `app/web/` — decisão
registrada em [ADR-002](../docs/adr/ADR-002-server-side-rendering-htmx.md).

Este diretório fica reservado para uma SPA futura, se algum dia for
necessária. Nesse cenário, a camada `app/api/` (v2) fornecerá o JSON e o
frontend atual continua funcionando durante a transição.
