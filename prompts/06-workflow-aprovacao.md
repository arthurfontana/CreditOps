# Prompt 06 — Workflow de aprovação (etapa mais crítica)

> **Anexar ao contexto**: `docs/wiki/06-workflow-de-aprovacao.md` (INTEIRO — é a especificação exata) e o "Prompt de contexto". Pré-requisitos: prompts 01–05.
> Se disponível, revise o resultado desta etapa com um modelo mais capaz.

---

Implemente a máquina de estados do workflow exatamente como especificada.

1. **`app/services/workflow_service.py`** com a whitelist de transições da wiki como estrutura de dados explícita:

   ```python
   TRANSITIONS: dict[tuple[VersionStatus, VersionStatus], TransitionRule]
   # TransitionRule: papéis permitidos, condições (callables), reason_required: bool
   ```

   Funções públicas (todas: validam transição + papel via `authz`, gravam `status_transition`, auditam, em transação única):
   - `submit_for_review(db, actor, version_id)` — exige `change_summary` e `expected_impact` não vazios.
   - `request_changes(db, actor, version_id, reason)` — volta a draft.
   - `send_to_approval(db, actor, version_id)` — chama `version_service.freeze` (congela `content_hash`).
   - `approve(db, actor, version_id, justification="")` — **rejeita se `actor.id == version.created_by`** (segregação); grava `approval(decision='approved')`.
   - `reject(db, actor, version_id, justification)` — justificativa obrigatória; grava `approval(decision='rejected')`; status volta a `draft`.
   - `publish(db, actor, version_id, effective_from: date)` — exige `effective_from >= hoje`; cria `publication`; se `effective_from == hoje`, aplica vigência imediatamente (item 2).
   - `make_effective(db, version_id)` — **ação de sistema**: numa única transação, nova versão → `effective`; anterior `effective` da mesma política → `superseded` + `effective_until = effective_from`; atualiza `policy.current_version_id`; audita com `actor_id=None`.
   - `rollback(db, actor, policy_id, target_version_id, reason)` — cria nova versão com conteúdo copiado do alvo, `is_rollback=True`, `based_on_version_id=target`, `change_summary=f"Rollback para v{target.version_number}: {reason}"`, e status direto `in_approval` (fluxo expresso).
   - `archive(db, actor, version_id, reason)`.

2. **Ativação de vigência agendada** (sem cron externo):
   - `apply_due_publications(db)`: encontra `publication` com `effective_from <= hoje` e versão ainda `published`, chama `make_effective`;
   - executada por: (a) tarefa em background do FastAPI a cada 10 min (`asyncio` loop no lifespan), e (b) verificação lazy ao carregar a página de uma política.

3. **UI**:
   - página da versão mostra botões condicionais ao papel+estado (submeter, revisar, aprovar, rejeitar, publicar, rollback), com modal exigindo justificativa quando obrigatória;
   - **tela do aprovador**: diff contra a vigente + `change_summary` + `expected_impact` + comentários, tudo em uma página, com Aprovar/Rejeitar;
   - **filas na home** (`GET /`): autor → rascunhos e rejeitadas; revisor → em revisão; aprovador → em aprovação e aprovadas aguardando publicação; leitor → catálogo.

4. **Testes (a parte mais importante do sistema — seja exaustivo)**:
   - toda transição da whitelist funciona com o papel certo;
   - TODAS as transições fora da whitelist falham (teste parametrizado percorrendo o produto cartesiano estados×estados);
   - papel errado falha para cada transição;
   - autor aprovando a própria versão falha;
   - rejeição sem justificativa falha; rejeição devolve a draft e preserva comentários;
   - publicar com data passada falha;
   - vigência futura: não fica effective antes da data; `apply_due_publications` ativa; anterior vira superseded com `effective_until` correto; `current_version_id` atualizado;
   - rollback cria versão nova com conteúdo do alvo e histórico linear;
   - cada transição gera `status_transition` + `audit_log`.

**Critérios de aceite**: ciclo completo criar→submeter→revisar→aprovar→publicar→vigorar→nova revisão→substituir funciona na UI com 3 usuários de papéis distintos; todos os testes passam.
