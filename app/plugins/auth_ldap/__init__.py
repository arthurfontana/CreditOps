"""Plugin de SSO corporativo via LDAP/Active Directory (v2).

Implementa a interface AuthPlugin (plugins/base.py). Dois modos:

1. **Bind direto** (`ldap_user_dn_template`): monta o DN do usuário a
   partir do template e tenta o bind com a senha informada.
2. **Busca + bind** (`ldap_base_dn` + filtro): autentica a conta de
   serviço (opcional), localiza o DN do usuário e faz o bind.

Falha do diretório NUNCA derruba o core: usuários com senha local
continuam autenticando (fallback), e o erro é apenas logado.
"""

from __future__ import annotations

import logging

from app.config import Settings

logger = logging.getLogger("creditops.plugins.ldap")

# caracteres com significado em filtros LDAP (RFC 4515) — sempre escapados
_FILTER_ESCAPES = {"\\": r"\5c", "*": r"\2a", "(": r"\28", ")": r"\29", "\0": r"\00"}


def escape_filter_value(value: str) -> str:
    return "".join(_FILTER_ESCAPES.get(ch, ch) for ch in value)


class LdapAuthenticator:
    """AuthPlugin sobre ldap3 (pure-Python, aprovável em TI restrita)."""

    def __init__(self, settings: Settings) -> None:
        import ldap3  # import no load: sem a lib, o plugin falha soft no registry

        self._ldap3 = ldap3
        if not settings.ldap_server:
            raise ValueError("auth_sso=ldap exige ldap_server configurado")
        if not settings.ldap_user_dn_template and not settings.ldap_base_dn:
            raise ValueError("configure ldap_user_dn_template OU ldap_base_dn")
        self.settings = settings
        self.server = ldap3.Server(
            settings.ldap_server,
            use_ssl=settings.ldap_use_ssl,
            connect_timeout=settings.ldap_timeout_seconds,
        )

    def _bind(self, dn: str, password: str) -> bool:
        conn = self._ldap3.Connection(
            self.server, user=dn, password=password,
            receive_timeout=self.settings.ldap_timeout_seconds,
        )
        try:
            return bool(conn.bind())
        finally:
            conn.unbind()

    def _find_user_dn(self, username: str) -> str | None:
        s = self.settings
        conn = self._ldap3.Connection(
            self.server,
            user=s.ldap_bind_dn or None,
            password=s.ldap_bind_password or None,
            receive_timeout=s.ldap_timeout_seconds,
        )
        try:
            if not conn.bind():
                logger.warning("bind da conta de serviço LDAP falhou")
                return None
            conn.search(
                search_base=s.ldap_base_dn,
                search_filter=s.ldap_user_filter.format(
                    username=escape_filter_value(username)
                ),
                search_scope=self._ldap3.SUBTREE,
                attributes=[],
                size_limit=1,
            )
            if not conn.entries:
                return None
            return conn.entries[0].entry_dn
        finally:
            conn.unbind()

    def authenticate(self, username: str, password: str) -> bool:
        """True somente se o diretório confirmar a credencial. Erros = False."""
        if not password:  # bind anônimo nunca conta como autenticação
            return False
        try:
            if self.settings.ldap_user_dn_template:
                dn = self.settings.ldap_user_dn_template.format(username=username)
                return self._bind(dn, password)
            dn = self._find_user_dn(username)
            if dn is None:
                return False
            return self._bind(dn, password)
        except Exception:  # noqa: BLE001 - diretório fora do ar não derruba o core
            logger.exception("falha ao consultar o diretório LDAP")
            return False
