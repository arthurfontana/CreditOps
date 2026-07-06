# Prompt 03 — Autenticação, sessões e RBAC

> **Anexar ao contexto**: `docs/wiki/09-seguranca-e-governanca.md` (seções Autenticação e Autorização), `docs/wiki/05-modelo-de-dados.md` (entidade `user`) e o "Prompt de contexto". Pré-requisitos: prompts 01–02.

---

Implemente autenticação local e autorização por papéis.

1. **`app/auth/passwords.py`**: hash e verificação com `argon2-cffi`.

2. **`app/auth/sessions.py`**: sessão via cookie assinado (`itsdangerous`, chave = `CREDITOPS_SECRET_KEY`): payload `{user_id, issued_at}`; expiração por inatividade de 8h; cookie `HttpOnly`, `SameSite=Lax`, `Secure` configurável (`settings.cookie_secure`, default true).

3. **`app/auth/deps.py`** (dependencies FastAPI):
   - `current_user` → 401/redirect para `/login` se ausente/expirado;
   - `require_role(*roles)` → 403 se papel insuficiente.

4. **Proteção contra força bruta**: contador de falhas por usuário (tabela `setting` ou coluna em `user`); 5 falhas → bloqueio 15 min; tudo auditado.

5. **Rotas web** (`app/web/routes/auth.py` + templates): `GET/POST /login`, `POST /logout`. CSRF token (assinado com a mesma secret) em todos os formulários POST — crie helper reutilizável `app/web/csrf.py` e use daqui em diante em todo formulário do sistema.

6. **Administração de usuários** (`app/web/routes/admin.py`, papel `admin`): listar/criar/editar usuários (nome, e-mail, papel, área, ativo); **desativação lógica apenas** (nunca DELETE); reset de senha gera senha temporária com troca obrigatória no próximo login.

7. **Serviço de auditoria mínimo** (`app/services/audit_service.py`): `record(db, actor_id, action, entity_type, entity_id, payload: dict)` — INSERT simples em `audit_log` (hash chain fica para a v1; deixe colunas `prev_hash`/`row_hash` nulas). Audite: `user.login`, `user.login_failed`, `user.logout`, `user.created`, `user.updated` (payload com before/after dos campos alterados, sem senhas).

8. **Enforcement no service layer**: crie `app/services/authz.py` com `ensure(actor, permission, resource=None)` e exceção `PermissionDenied` (rotas a convertem em 403). Os services dos próximos prompts DEVEM usá-la — documente isso em docstring.

9. **CLI** (`app/cli.py`): comando `create-admin --email --name` que pede senha no terminal.

10. **Testes**: login ok/senha errada/bloqueio após 5 falhas; expiração de sessão; `require_role` nega papel insuficiente; desativação impede login; auditoria gravada em cada caso.

**Critérios de aceite**: fluxo completo login→página protegida→logout funciona no navegador; testes passam; nenhuma senha em log ou auditoria.
