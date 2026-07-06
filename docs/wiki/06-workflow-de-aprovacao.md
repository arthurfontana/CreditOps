# 6. Workflow de Aprovação

## Máquina de estados

```
                         (autor)          (autor)            (revisor)
  ┌────────┐  submeter  ┌───────────┐  enviar p/ ┌──────────────┐
  │RASCUNHO│───────────►│ EM REVISÃO│──aprovação─►│ EM APROVAÇÃO │
  └───▲────┘            └─────┬─────┘            └──────┬───────┘
      │   solicitar ajustes   │                         │
      ├───────────────────────┘                         │ (aprovador)
      │            rejeitar (aprovador)                 ▼
      ├────────────────────────────────────┐      ┌──────────┐
      │                                    │      │ APROVADO │
  [REJEITADO]* ─── reabrir como rascunho ──┘      └────┬─────┘
                                                       │ publicar (publicador)
                                                       ▼
                                                 ┌───────────┐
                                                 │ PUBLICADO │ (aguarda vigência)
                                                 └────┬──────┘
                                          data de vigência atingida (sistema)
                                                       ▼
                                                 ┌───────────┐
                        nova versão entra em ───►│ EM VIGOR  │
                        vigor: anterior vira     └────┬──────┘
                        SUBSTITUÍDA                   │
                                                      ▼
                                          ┌─────────────┐   ┌───────────┐
                                          │ SUBSTITUÍDA │   │ ARQUIVADA │
                                          └─────────────┘   └───────────┘
                                          (histórico,        (política inteira
                                           somente leitura)   descontinuada)
```

\* `REJEITADO` é registrado como decisão + transição de volta para `RASCUNHO`, preservando comentários e a justificativa da rejeição.

### Transições permitidas (whitelist)

| De | Para | Quem pode | Condições |
|---|---|---|---|
| — | draft | Autor | cria política ou "Nova revisão" a partir da vigente |
| draft | in_review | Autor | `change_summary` e `expected_impact` preenchidos |
| in_review | draft | Revisor ou Autor | "solicitar ajustes" (comentários abertos) |
| in_review | in_approval | Revisor | revisão marcada como concluída |
| in_approval | approved | Aprovador | não pode ser o próprio autor (segregação de funções) |
| in_approval | draft | Aprovador | rejeição — justificativa obrigatória |
| approved | published | Aprovador ou Publicador | define `effective_from` (hoje ou futura) |
| published | effective | **Sistema** | ao atingir `effective_from` (job diário/na leitura) |
| effective | superseded | **Sistema** | quando outra versão da mesma política entra em vigor |
| effective/superseded | archived | Aprovador | arquivamento da política inteira, com justificativa |
| draft | archived | Autor | descarte de rascunho (permanece no histórico) |

Qualquer transição fora desta tabela é **rejeitada pelo core** — não existe "força bruta" nem edição direta de status.

## Papéis e responsabilidades

| Papel | Cria | Revisa | Aprova | Publica | Lê |
|---|---|---|---|---|---|
| Autor (analista) | ✅ | — | — | — | ✅ |
| Revisor (par / 2ª linha) | — | ✅ | — | — | ✅ |
| Aprovador (gerente de crédito) | — | ✅ | ✅ | ✅ | ✅ |
| Publicador (opcional, governança) | — | — | — | ✅ | ✅ |
| Leitor (operação) | — | — | — | — | ✅ |
| Admin | gestão de usuários/cadastros; **não participa do fluxo** | | | | ✅ |

Regras de segregação:
- **Autor ≠ Aprovador** na mesma versão (bloqueado pelo sistema).
- Aprovação registra usuário, data/hora e nível — evidência não repudiável.
- No MVP o Aprovador também publica; o papel separado de Publicador é opcional (v1) para empresas que segregam "decidir" de "colocar em produção".

## Regras de negócio detalhadas

### Criação
- Nova política → nasce com versão 1 em `draft`.
- Alteração → botão **"Nova revisão"** na versão vigente cria `draft` com `version_number = max + 1` e `based_on_version_id` apontando para a vigente. Só pode existir **um rascunho aberto por política** (evita forks paralelos e conflitos de merge — simplificação deliberada; ver [Riscos](13-riscos-e-trade-offs.md)).

### Revisão
- Revisor comenta (comentários ancoráveis a seções) e pode devolver ao autor quantas vezes necessário.
- O ciclo revisão↔ajuste acontece **dentro da mesma versão** enquanto ela está em `draft`/`in_review` — o conteúdo só congela (hash calculado) quando entra em `in_approval`.

### Aprovação
- Tela do aprovador mostra: diff contra a versão vigente, justificativa, impacto esperado, comentários da revisão.
- **Rejeição**: justificativa obrigatória; versão volta a `draft`; autor é notificado (v1); tentativa fica registrada em `approval` e `status_transition`.
- **Multinível (v1)**: tipos de política podem exigir níveis 1..N em sequência; qualquer rejeição em qualquer nível devolve ao autor.
- **Delegação (v1)**: aprovador ausente delega a um par; a aprovação registra `delegated_from`.

### Publicação e vigência
- Publicar = escolher `effective_from` (hoje → vigência imediata; futura → fica `published` aguardando).
- Na data de vigência, o sistema (job agendado + verificação lazy em cada leitura, para não depender de cron):
  1. marca a nova versão como `effective`;
  2. marca a anterior como `superseded` e preenche seu `effective_until`;
  3. atualiza `policy.current_version_id`;
  4. grava tudo na auditoria — em uma única transação.
- **Vigência retroativa não existe**: `effective_from ≥ data de publicação`. Se a operação já aplicava a regra antes, isso é registrado em comentário/impacto, não falsificando a linha do tempo.

### Mudanças futuras (registro contínuo)
- Toda necessidade de mudança nasce como **nova revisão** — mesmo trivial. Não há "editar só uma vírgula" fora do fluxo.
- Para mudanças editoriais (typo, formatação), o aprovador pode usar **fluxo expresso**: revisão dispensada, aprovação direta. O sistema marca `change_summary` com categoria `editorial` — auditoria distingue mudança material de cosmética.

### Rejeição posterior / revisão de política publicada
- Não existe "despublicar". Se uma versão vigente está errada, o caminho é **rollback** (abaixo) ou nova revisão corrigida.
- Revisão periódica (v2): política com `review_due_at` vencida entra em relatório de recertificação; recertificar = registrar evento de auditoria "revisado sem mudança" ou abrir nova revisão.

### Rollback
1. Aprovador aciona rollback e escolhe a versão-alvo (ex.: v5, quando a vigente é v7).
2. Sistema cria v8 em `draft` com conteúdo copiado de v5, `is_rollback = true`, `based_on_version_id = v5`, justificativa obrigatória.
3. Fluxo expresso: vai direto para `in_approval` (o conteúdo já foi aprovado no passado); aprovação do gerente publica com vigência imediata.
4. v7 vira `superseded`. A linha do tempo mostra: v5 → v6 → v7 → **v8 (rollback para v5)**. Nada é apagado.

### Histórico imutável — como é garantido

1. **Aplicação**: services recusam UPDATE em versões fora de `draft`.
2. **Banco**: triggers SQLite impedem UPDATE/DELETE em `policy_version` congelada, `approval`, `publication`, `status_transition` e `audit_log`.
3. **Hash de conteúdo**: `content_hash` congelado na submissão; qualquer adulteração direta no arquivo do banco é detectável por re-hash.
4. **Hash encadeado na auditoria (v1)**: cada linha referencia o hash da anterior; verificador em `scripts/verify_audit.py`.
5. **Backups**: snapshots diários retidos por política de retenção (ex.: 7 anos — alinhado a requisitos regulatórios de crédito).
