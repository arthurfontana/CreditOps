# Runbook de Operação — CreditOps

Guia do administrador: instalar, operar, fazer backup e recuperar o sistema.

## 1. Instalação

Requisitos: Python 3.11+, ~200 MB de disco, nenhum serviço externo.

```bash
git clone <repo> creditops && cd creditops
python -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                  # edite: gere CREDITOPS_SECRET_KEY
alembic upgrade head                                  # cria/migra o banco
python -m app.cli create-admin --email admin@empresa.com --name "Admin"
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Gere a secret key com: `python -c "import secrets; print(secrets.token_hex(32))"`.

### Instalação offline (servidor sem internet)

Em uma máquina com internet:

```bash
pip download -r requirements.txt -d wheelhouse/
```

Copie `wheelhouse/` junto com o código e instale com:

```bash
pip install --no-index --find-links wheelhouse/ -r requirements.txt
```

### Dados de demonstração (treinamento)

```bash
python scripts/seed_demo.py    # exige banco recém-migrado e vazio
```

Usuários criados (senha `demo1234`): `admin`, `ana` (autora), `rafael`
(revisor), `carlos` (aprovador), `lia` (leitora), `aud` (auditor).

## 2. TLS / proxy

**Nunca exponha HTTP puro fora de localhost.** Opções:

- **nginx** (Linux): proxy reverso com certificado interno terminando TLS e
  repassando para `127.0.0.1:8000`;
- **IIS** (Windows): ARR/URL Rewrite com o mesmo arranjo;
- alternativa: `uvicorn --ssl-keyfile ... --ssl-certfile ...` com certificado
  interno.

Mantenha `CREDITOPS_COOKIE_SECURE=true` em produção (cookies só via HTTPS).

## 3. Backup

`python scripts/backup.py --dest /backup/creditops --keep 30`

- Usa a API de backup do SQLite: **pode rodar com a aplicação no ar**.
- Gera `creditops.db` + `attachments.tar.gz` + `manifest.json` (SHA-256).
- RPO alvo: 24h (agende diariamente); retenção recomendada: 7 anos para
  atender requisitos regulatórios (ajuste `--keep` e arquive mensais).

Agendamento — cron (Linux):

```cron
15 2 * * * cd /opt/creditops && .venv/bin/python scripts/backup.py --dest /backup/creditops >> logs/backup.log 2>&1
```

Agendamento — Task Scheduler (Windows): tarefa diária executando
`C:\creditops\.venv\Scripts\python.exe scripts\backup.py --dest D:\backup\creditops`.

## 4. Restore (RTO alvo: < 1h)

1. Pare a aplicação (`systemctl stop creditops` / parar o serviço).
2. `python scripts/restore.py /backup/creditops/creditops-AAAAMMDD-HHMMSS`
   — o script **valida os hashes do manifesto antes** de substituir qualquer
   arquivo e preserva cópias `.pre-restore`.
3. Suba a aplicação e valide login + abertura de uma política.
4. Descarte os `.pre-restore` após validação.

Teste o restore periodicamente (recomendado: trimestral) em máquina separada.

## 5. Upgrade de versão

```bash
systemctl stop creditops
git pull                      # ou substitua o código pela nova versão
pip install -r requirements.txt
alembic upgrade head          # migrações de esquema
systemctl start creditops
```

Sempre faça backup antes do upgrade. Rollback = restaurar código anterior +
restore do backup (migrações não são revertidas em produção).

## 6. Verificação de integridade

- `python scripts/verify_data.py` — re-calcula o hash de todas as versões
  congeladas e anexos; qualquer divergência indica adulteração direta no
  arquivo do banco/filesystem. Rode após restores e periodicamente.
- `python scripts/verify_audit.py` (v1) — verifica a **cadeia de hashes da
  trilha de auditoria** (`row_hash = sha256(prev_hash + dados)`): linha
  adulterada, removida ou inserida fora de ordem quebra a cadeia e é
  reportada. Linhas anteriores à v1 (sem hash) são toleradas apenas antes do
  início da cadeia. Código de saída 1 = violação.

Agendamento recomendado (junto do backup diário):

```cron
30 2 * * * cd /opt/creditops && .venv/bin/python scripts/verify_audit.py >> logs/verify.log 2>&1
```

## 7. Notificações por e-mail (v1)

Desligadas por padrão. Para ativar, em `config/settings.toml`:

```toml
[plugins]
notify_email = true
smtp_host = "smtp.empresa.com"
smtp_port = 587
smtp_from = "creditops@empresa.com"
smtp_starttls = true
smtp_username = "creditops"        # se o servidor exige autenticação
app_base_url = "https://creditops.empresa.com"   # links nos e-mails
```

A senha SMTP vai **apenas** em variável de ambiente: `CREDITOPS_SMTP_PASSWORD`.

Comportamento: eventos de workflow (submissão, aprovação pendente,
aprovação, rejeição, publicação, vigência) enfileiram notificações na tabela
`notification`; o envio acontece logo após o commit e, em caso de falha de
SMTP, a fila é reprocessada a cada 5 min (retry sem perda de eventos).
Indisponibilidade de SMTP **nunca** afeta o workflow.

## 8. API de consumo (v2)

Somente leitura, autenticada por tokens de serviço (`Authorization: Bearer`).
Ativa por padrão (`api_enabled = true` na seção `[api]`).

```bash
python -m app.cli create-token --name "motor-powercurve"   # exibe o token UMA vez
python -m app.cli list-tokens
python -m app.cli revoke-token <id>
```

O banco guarda apenas o SHA-256 do token; criação/revogação vão para a
auditoria. Endpoints principais:

```
GET /api/v1/policies                          # catálogo (vigentes)
GET /api/v1/policies/{code}                   # versão EM VIGOR (corpo + campos + hash)
GET /api/v1/policies/{code}/versions          # histórico público
GET /api/v1/policies/{code}/effective?at=AAAA-MM-DD   # time travel
```

Rascunhos e versões em fluxo **nunca** são servidos pela API.

## 9. SSO LDAP/Active Directory (v2)

Desligado por padrão. Ative com `auth_sso = "ldap"` na seção `[sso]` do
`settings.toml` (servidor, e um dos modos: template de DN **ou** base de
busca com conta de serviço — senha da conta **apenas** em
`CREDITOPS_LDAP_BIND_PASSWORD`).

- Usuário SSO é criado pelo admin com o checkbox "Usuário SSO" (sem senha
  local; `password_hash` nulo) e autentica no diretório.
- Usuários com senha local continuam funcionando — fallback que mantém o
  acesso se o diretório cair. Diretório indisponível nunca derruba a
  aplicação (falha é logada; bloqueio por tentativas continua valendo).

## 10. Webhooks de publicação (v2)

Desligados por padrão. Configure endpoints na seção `[webhooks]`
(`webhook_urls`, separados por vírgula) e o segredo em
`CREDITOPS_WEBHOOK_SECRET`. Eventos `version.published` e `version.effective`
são entregues como POST JSON com headers `X-CreditOps-Event` e
`X-CreditOps-Signature` (`sha256=<HMAC do corpo>`). Entrega falha fica na
fila `webhook_delivery` com retry a cada 5 min até `webhook_max_attempts`;
consumidor fora do ar nunca afeta o workflow.

## 11. Módulo de IA (v2)

Desligado por padrão (`ai_provider = "none"` — garantia por construção de que
nenhum conteúdo de política sai do ambiente). Para ativar: seção `[ai]` do
`settings.toml` (provider, modelo, base_url para gateways corporativos) +
credencial **apenas** em `CREDITOPS_AI_API_KEY` (ou `CREDITOPS_AI_KEY_FILE`).
Cada feature liga individualmente (`ai_summarize_diff`, `ai_suggest_tags`,
`ai_draft_from_document`, `ai_qa_search`). Toda sugestão gerada é auditada
(`ai.suggestion_generated`); falha de provedor vira "sugestão indisponível"
na UI, nunca erro. Prompts usados ficam versionados em `prompts/runtime/`.

## 12. Rotinas automáticas

- **Vigências agendadas**: ativadas pela própria aplicação (tarefa interna a
  cada 10 min + verificação ao abrir a política). Sem cron necessário; o
  comando manual `python -m app.cli apply-effectiveness` existe para
  contingência.
- **Reindexação da busca**: automática na publicação; reconstrução completa
  com `python -m app.cli reindex-all`.
- **Retry de notificações** (v1): interno, a cada 5 min, apenas com
  `notify_email = true`.
- **Retry de webhooks** (v2): interno, a cada 5 min, apenas com
  `webhook_urls` configurado.

## 13. Troubleshooting

| Sintoma | Causa provável | Ação |
|---|---|---|
| `database is locked` persistente | processo morto segurando WAL | pare a app, remova `creditops.db-wal`/`-shm` **somente com a app parada**, suba de novo |
| Migração falhou no upgrade | esquema divergente | restaure o backup pré-upgrade e reaplique; nunca edite o esquema à mão |
| Todos os usuários deslogados | `CREDITOPS_SECRET_KEY` mudou | esperado: sessões são assinadas pela chave; usuários fazem login de novo |
| Login bloqueado (`conta bloqueada`) | 5 falhas seguidas | aguardar 15 min ou admin faz reset de senha |
| Busca sem resultados | índice defasado | `python -m app.cli reindex-all` |
| `immutable version` em log | tentativa de UPDATE em versão congelada | comportamento correto (proteção); investigue quem tentou na trilha |
| E-mails não chegam | SMTP indisponível ou credencial errada | veja `logs` (falha de envio é logada); fila reprocessa a cada 5 min; confira `CREDITOPS_SMTP_PASSWORD` |
| `verify_audit.py` reporta violação | adulteração direta na trilha | trate como incidente: preserve o banco, restaure backup íntegro e investigue |
| API devolve 401 | token ausente, inválido ou revogado | `python -m app.cli list-tokens`; gere token novo se necessário (o antigo não é recuperável) |
| Usuário SSO não loga | plugin LDAP inativo ou diretório fora | confira `auth_sso = "ldap"` e o log do plugin; usuários com senha local seguem funcionando |
| Webhooks não chegam ao consumidor | endpoint fora do ar ou assinatura rejeitada | fila `webhook_delivery` guarda `last_error`; retry a cada 5 min até o limite de tentativas |
| Botões de IA dizem "indisponível" | provider `none`, feature desligada ou credencial ausente | ligue a feature na seção `[ai]` e defina `CREDITOPS_AI_API_KEY`; comportamento é fail-soft por design |

## 14. Logs

- Aplicação: stdout do uvicorn (redirecione para `logs/` no serviço).
- Logs não contêm corpos de política nem senhas — apenas IDs e ações.
- Trilha de negócio: tabela `audit_log` (consulta em `/audit`, export CSV).
