# 9. Segurança e Governança

## Modelo de ameaças (proporcional ao contexto)

Sistema interno, rede corporativa, dados sensíveis de estratégia de crédito (não dados de clientes). Principais riscos:

1. Acesso não autorizado a políticas (confidencialidade estratégica).
2. Alteração indevida de histórico (integridade/auditabilidade) — **o risco nº 1 do produto**.
3. Aprovação forjada ou repúdio ("eu não aprovei isso").
4. Perda de dados (disponibilidade do histórico).
5. Vazamento via módulo de IA externa.

## Autenticação

| Fase | Mecanismo |
|---|---|
| MVP | Usuário/senha local; hash argon2id; bloqueio após N tentativas; política de senha configurável; sessões com cookie `HttpOnly`+`Secure`+`SameSite=Lax`, expiração por inatividade |
| v2 | LDAP/Active Directory (bind) e/ou OIDC/SAML via IdP corporativo; usuários locais permanecem como fallback de emergência (quebra-vidro auditada) |
| Enterprise | MFA, políticas por tenant |

TLS: terminação no proxy corporativo (nginx/IIS) ou direto no uvicorn com certificado interno. **Nunca HTTP puro fora de localhost.**

## Autorização (RBAC)

- Papéis: `admin`, `author`, `reviewer`, `approver`, `reader` (MVP: globais; v1: escopados por área).
- Autorização **no service layer** (não só na UI): toda operação valida papel + escopo + estado da entidade.
- Segregação de funções enforced por código:
  - autor não aprova a própria versão;
  - admin administra cadastros mas **não participa do workflow** (sem aprovar/publicar);
  - leitor não vê rascunhos (configurável: rascunhos visíveis só a autor/revisores da área).
- Matriz completa de permissões: ver [Workflow](06-workflow-de-aprovacao.md#papéis-e-responsabilidades).

## Trilha de auditoria

### O que é registrado (INSERT-only)

- Workflow: criação, submissão, comentários, decisões, publicação, vigência, rollback, arquivamento.
- Acesso: login/logout, falhas de login, exportações geradas, leitura de política (v2, para "ciência da operação").
- Administração: criação/alteração de usuários, papéis, áreas, configurações (com before/after no payload).
- IA: sugestões geradas e aceitas/recusadas.

### Garantias de integridade

1. Tabela `audit_log` sem UPDATE/DELETE (triggers).
2. **Hash encadeado** (v1): `row_hash = sha256(prev_hash || payload)`; `scripts/verify_audit.py` valida a cadeia inteira — adulteração no arquivo do banco é detectável.
3. `content_hash` por versão congelada.
4. Export assinável do log (enterprise: assinatura digital).
5. Backups diários retidos conforme política de retenção (recomendação: **7 anos**, alinhado a prazos regulatórios de crédito; retenção configurável).

### Acesso do auditor

- Papel `reader` + acesso à área de auditoria (consulta e exportação da trilha, time-travel, dossiês) — autosserviço, sem depender de TI.

## Governança do produto

### Publicação (política de publicação)

- Só entra em vigor o que passou por aprovação registrada — sem exceções, por construção.
- Vigência sempre explícita e nunca retroativa.
- Mudanças editoriais usam fluxo expresso, mas ficam **marcadas como editoriais** — relatórios distinguem mudança material de cosmética.
- Releases (v1) permitem comunicar pacotes de mudanças à operação de forma coordenada.

### Ciclo de revisão (v2)

- Toda política pode ter `review_due_at` (recertificação periódica, ex.: anual).
- Relatório de recertificação lista vencidas/vincendas; recertificar sem mudança também é evento auditado.

### Dados e privacidade

- O sistema guarda **regras**, não dados de clientes — manter assim (orientação de produto: anexos não devem conter dados pessoais; aviso na UI).
- Com IA externa habilitada, banner explícito de para onde o conteúdo é enviado; feature desligada por padrão.

## Segurança de aplicação (checklist de implementação)

- Validação de entrada via Pydantic em todas as rotas.
- Escape de template por padrão (Jinja2 autoescape); Markdown renderizado com sanitização de HTML (sem HTML bruto do usuário).
- CSRF token em todos os formulários de mutação.
- Uploads: extensões permitidas por lista, tamanho máximo, armazenamento fora da raiz web, servidos com `Content-Disposition: attachment`, hash SHA-256 verificado.
- Cabeçalhos: `X-Content-Type-Options`, `X-Frame-Options`, CSP restritiva (sem scripts externos — tudo é servido localmente).
- Dependências mínimas e pinadas (`requirements.txt` com hashes); atualização periódica auditável.
- Segredos apenas em variáveis de ambiente/arquivos protegidos; nunca em banco, código ou logs.
- Logs sem conteúdo sensível (IDs, não corpos de política).

## Continuidade

- **Backup**: `scripts/backup.py` (SQLite backup API + cópia de anexos + manifesto com hashes). Agendado via cron/Task Scheduler.
- **Restore testado**: `scripts/restore.py` + teste periódico documentado em runbook.
- **RPO** alvo: 24h (backup diário) no MVP; **RTO**: < 1h (restaurar pasta + subir processo).
