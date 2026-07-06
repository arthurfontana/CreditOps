# ADR-004: Plugins por eventos de domínio + configuração (vs. import direto)

**Status**: Aceito · **Data**: 2026-07-06

## Contexto

E-mail (v1), LDAP e IA (v2) são opcionais: o core precisa operar 100% sem eles
e a indisponibilidade de um plugin nunca pode derrubar o sistema.

## Decisão

O core emite eventos de domínio (`version.submitted`, `version.published`,
`version.effective`, …) via pub/sub em memória (`app/services/events.py`),
entregues **após o commit** da transação. Plugins implementam interfaces de
`app/plugins/base.py`, são descobertos por configuração
(`config/settings.toml`) e assinam eventos. Nenhum módulo do core importa um
plugin; `app/services/` não importa `app/web/`, `app/api/` nem `app/plugins/`.

## Consequências

- Erros de handler são logados e nunca propagam (fail-soft).
- Eventos emitidos em transação revertida são descartados.
- Adicionar um canal novo (webhook, chat) = um subscriber, zero mudança no core.
