# Prompt 12 — v2 "Plataforma da empresa"

> **Status: implementado.** Este prompt fica como registro do escopo executado
> e como guia para reimplementação/revisão. Wiki a anexar: 03, 04, 05, 08, 11.

## Contexto

A v1 ("Governança para valer") está completa e testada. Esta etapa implementa a
v2 do roadmap (`docs/wiki/11-roadmap.md`): a plataforma que outras diretorias e
sistemas consomem — SSO, API de leitura, webhooks, IA plugável, recertificação,
grafo de referências, trilha de leitura e publicação-experimento.

## Entregas (na ordem)

### P0

1. **API REST de consumo** (`app/api/v1.py`): somente leitura, autenticada por
   tokens de serviço (`service_token`, SHA-256 no banco, token em claro exibido
   uma vez). Endpoints: catálogo, versão vigente por código, histórico público,
   versão específica e time travel (`?at=AAAA-MM-DD`). Rascunhos e versões em
   fluxo nunca aparecem; verificação lazy de vigência em toda leitura.
   CLI: `create-token`, `list-tokens`, `revoke-token`; ciclo de vida auditado
   (`api.token_created` / `api.token_revoked`).
2. **SSO LDAP/AD via plugin** (`app/plugins/auth_ldap/`): implementa `AuthPlugin`;
   dois modos (bind direto por template de DN ou busca+bind com conta de
   serviço); escape de filtro RFC 4515; `auth_sso = "ldap"` ativa. Usuário SSO
   tem `password_hash` nulo (admin cria com checkbox "Usuário SSO"); usuários
   com senha local continuam autenticando (fallback se o diretório cair);
   diretório fora do ar nunca derruba o core.

### P1

3. **Módulo de IA plugável** (`app/plugins/ai/`): fachada `AIService` sobre o
   contrato `AIProvider` (uma primitiva `complete`); adapters HTTP puros (httpx)
   para openai, anthropic, gemini e internal (OpenAI-compatible: Ollama/vLLM);
   provider padrão `none` = nenhum conteúdo sai do ambiente, por construção.
   Casos de uso em `app/plugins/ai/tasks.py` com prompts versionados em
   `prompts/runtime/`: resumo de diff, sugestão de tags (filtradas ao catálogo),
   rascunho a partir de legado. Features individuais (`ai_summarize_diff` etc.),
   fail-soft (erro vira "sugestão indisponível"), toda sugestão auditada
   (`ai.suggestion_generated` com provedor, modelo, tokens, hash e excerto).
   Credencial só via env (`CREDITOPS_AI_API_KEY`) ou arquivo protegido.
4. **Recertificação periódica** (`recertification_service`): `policy.review_due_at`;
   definir prazo (autor/aprovador/admin), recertificar (aprovador/admin, com
   ciclo em meses e observação, auditado como `policy.recertified`); relatório
   `/recertification` (vencidas, ≤60 dias, agendadas, sem prazo).
5. **Webhooks de publicação** (`app/plugins/webhook.py` + `webhook_service`):
   fila persistente `webhook_delivery` (padrão da `notification` da v1);
   eventos `version.published` e `version.effective`; um registro por endpoint
   configurado (`webhook_urls`); assinatura HMAC-SHA256 no header
   `X-CreditOps-Signature` (segredo em env); envio pós-commit + retry
   periódico até `webhook_max_attempts`; payload com política, versão,
   `content_hash` e vigência.

### P2

6. **RAG local para perguntas** (`/ask` + task `qa_answer`): FTS5 recupera as
   versões vigentes mais relevantes; com `ai_qa_search` ligado o provider
   responde citando `(POL-XXX-NNN vN)`; sem provider a página vira busca
   melhorada (retrieval sozinho) — nunca erro.
7. **Trilha de leitura obrigatória** (`read_receipt_service`): "li e estou
   ciente" por (versão vigente, usuário), idempotente, auditado
   (`version.acknowledged`); nova vigência reabre a pendência; relatório por
   política (`/policies/{id}/readers`) e fila pessoal (`/reading`).
8. **Comparação entre políticas** (`/compare-policies`): diff lado a lado entre
   os conteúdos vigentes de duas políticas diferentes (reuso do `diff_service`).
9. **Grafo de referências + análise de impacto** (`reference_service`):
   `policy_reference` com arestas `usa`/`depende_de`/`substitui` para política
   ou artefato (ex.: "Score Serasa"); CRUD no detalhe da política (auditado);
   `/impact` responde "se eu mudar X, quais políticas são afetadas?" com BFS
   inverso transitivo, tolerante a ciclos.
10. **Publicação-experimento (piloto)**: `publication.rollout_scope`
    (`full`/`pilot`) + `pilot_description`/`pilot_ends_at`; piloto exige escopo
    declarado e prazo posterior à vigência; badge e banner no detalhe; painel
    "Pilotos em vigor" no dashboard com alerta de prazo vencido; promoção,
    ajuste ou encerramento seguem o fluxo normal de aprovação.

## Regras transversais

- Migração `0003_v2_platform` idempotente (tabelas novas + colunas garantidas).
- Plugins descobertos por configuração (`registry.load_plugins`), falham soft;
  o core nunca importa plugin diretamente (import lazy nos pontos de borda,
  mesma convenção do `notification_service` da v1).
- Autorização sempre no service layer; leitura da API restrita a conteúdo
  público; imutabilidade e whitelist do workflow intactas.
- Testes: `tests/unit/test_v2_platform.py` + `tests/integration/test_v2_routes.py`
  cobrem tokens/API, SSO (plugin fake), grafo/impacto (inclusive ciclos),
  recertificação, leitura, piloto, webhooks (fila/retry/assinatura) e IA
  (provider fake, flags, prompts de runtime, RAG com e sem provider).

## Gate de saída (organizacional — validar antes do enterprise)

Sistemas consumindo a API; IA em uso com pelo menos 1 provedor **ou** decisão
consciente de não usar (provider = none).
